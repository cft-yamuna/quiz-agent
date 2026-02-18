import os
import json
import subprocess
import signal
import threading
import time
from flask import Flask, render_template, request, jsonify, Response
import queue

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Track the running dev server process
_dev_server_proc = None
_dev_server_project = None


def _kill_all_dev_servers():
    """Kill dev servers tracked by BOTH this module and the executor module."""
    global _dev_server_proc, _dev_server_project

    # 1. Kill our own tracked process
    if _dev_server_proc and _dev_server_proc.poll() is None:
        try:
            _dev_server_proc.terminate()
            _dev_server_proc.wait(timeout=5)
        except Exception:
            try:
                _dev_server_proc.kill()
            except Exception:
                pass
    _dev_server_proc = None
    _dev_server_project = None

    # 2. Kill the executor's tracked process + anything on port 5173
    try:
        from tools.executor import kill_dev_server
        kill_dev_server()
    except ImportError:
        pass

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), "templates"),
    static_folder=os.path.join(os.path.dirname(__file__), "static"),
)

# Lazy-initialized agent (created on first request, after .env is loaded)
_memory = None
_agent = None

# Queue for streaming agent logs to the frontend
log_queues = {}
# Queue for receiving user answers (ask_user tool in web mode)
answer_queues = {}
# Timestamps for queue creation (for TTL cleanup)
_queue_timestamps = {}
# Lock to protect queue dicts from concurrent access
_queues_lock = threading.Lock()


def _get_agent():
    """Lazy-initialize agent and memory on first use."""
    global _memory, _agent
    if _agent is None:
        from agent.core import AgentCore
        from memory.manager import MemoryManager
        _memory = MemoryManager()
        _agent = AgentCore(memory=_memory)
    return _agent, _memory


class LogCapture:
    """Captures print output and sends it to a queue for streaming."""

    def __init__(self, q):
        self.queue = q
        self._original_print = None

    def write(self, text):
        if text.strip():
            self.queue.put({"type": "log", "message": text.strip()})

    def flush(self):
        pass


# ---- TTL Cleanup Thread ----
def _cleanup_stale_queues():
    """Background thread that removes orphaned queues older than 10 minutes."""
    while True:
        time.sleep(60)
        cutoff = time.time() - 600  # 10 minutes
        with _queues_lock:
            stale = [sid for sid, ts in _queue_timestamps.items() if ts < cutoff]
            for sid in stale:
                log_queues.pop(sid, None)
                answer_queues.pop(sid, None)
                _queue_timestamps.pop(sid, None)
                if stale:
                    print(f"  [Cleanup] Removed {len(stale)} stale queue(s)")

_cleanup_thread = threading.Thread(target=_cleanup_stale_queues, daemon=True)
_cleanup_thread.start()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/projects", methods=["GET"])
def list_projects():
    """List existing projects in output/."""
    output_dir = os.path.join(BASE_DIR, "output")
    projects = []
    if os.path.exists(output_dir):
        for item in sorted(os.listdir(output_dir)):
            project_path = os.path.join(output_dir, item)
            if os.path.isdir(project_path):
                has_pkg = os.path.exists(os.path.join(project_path, "package.json"))
                has_src = os.path.isdir(os.path.join(project_path, "src"))

                if has_pkg and has_src:
                    tech = "React"
                elif has_pkg:
                    tech = "Node.js"
                else:
                    tech = "Unknown"

                projects.append({"name": item, "tech": tech})
    return jsonify(projects)


@app.route("/api/build", methods=["POST"])
def build():
    """Start building a quiz app from a prompt. Accepts JSON or multipart/form-data (with images)."""
    image_paths = []

    if request.content_type and "multipart/form-data" in request.content_type:
        prompt = request.form.get("prompt", "").strip()
        project_name = request.form.get("project_name", "").strip()
        # Images are saved after project_name is sanitized (below)
        uploaded_files = request.files.getlist("images")
    else:
        data = request.json
        prompt = data.get("prompt", "").strip()
        project_name = data.get("project_name", "").strip()
        uploaded_files = []

    if not prompt:
        return jsonify({"error": "Prompt is required"}), 400
    if not project_name:
        return jsonify({"error": "Project name is required"}), 400

    # Sanitize project name
    project_name = project_name.lower().replace(" ", "_").replace("-", "_")

    # Save uploaded images INTO the project directory (not root uploads/)
    if uploaded_files:
        upload_dir = os.path.join(BASE_DIR, "output", project_name, "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        for uf in uploaded_files:
            if uf.filename:
                import uuid as _uuid
                safe_name = f"{_uuid.uuid4().hex[:8]}_{uf.filename}"
                save_path = os.path.join(upload_dir, safe_name)
                uf.save(save_path)
                image_paths.append(save_path)

    # Auto-detect Figma URL in prompt and update .env
    from figma.client import extract_and_update_figma_url
    extract_and_update_figma_url(prompt)

    # Add Figma/design hint based on config and intent
    from agent.intent import add_figma_hint
    prompt = add_figma_hint(prompt)

    # Build full context (detects create vs modify, injects file contents)
    from agent.context import build_prompt_context
    prompt = build_prompt_context(project_name, prompt, BASE_DIR)

    # Create a unique session ID for log streaming
    import uuid
    session_id = str(uuid.uuid4())[:8]

    # Auto-snapshot before modify builds so user can revert
    if "[Mode: modify]" in prompt:
        from tools.snapshots import take_snapshot
        take_snapshot(project_name, session_id, prompt[:100])

    log_q = queue.Queue()
    answer_q = queue.Queue()
    with _queues_lock:
        log_queues[session_id] = log_q
        answer_queues[session_id] = answer_q
        _queue_timestamps[session_id] = time.time()

    def web_ask_user(question):
        """Send question to frontend via SSE, wait for answer via POST."""
        log_q.put({"type": "ask_user", "message": question})
        try:
            answer = answer_q.get(timeout=300)  # 5 min timeout
            return answer if answer else "User did not respond."
        except queue.Empty:
            return "User did not respond (timed out)."

    # Capture image_paths in closure
    _image_paths = list(image_paths)

    def run_agent():
        import sys
        from tools.executor import set_dependencies

        agent, mem = _get_agent()

        # Autonomous mode — set project context so file paths are enforced
        set_dependencies(memory=agent.memory, planner=agent.planner, project_name=project_name)

        # Capture stdout to stream logs
        old_stdout = sys.stdout
        sys.stdout = LogCapture(log_q)

        try:
            result = agent.run(prompt, image_paths=_image_paths if _image_paths else None)
            log_q.put({"type": "result", "message": result})
        except Exception as e:
            from agent.core import AgentStopped
            if isinstance(e, AgentStopped):
                log_q.put({"type": "stopped", "message": "Build stopped. Files created so far are saved."})
            else:
                log_q.put({"type": "error", "message": str(e)})
        finally:
            sys.stdout = old_stdout
            log_q.put({"type": "done"})
            agent.reset()
            # Cleanup answer queue
            with _queues_lock:
                answer_queues.pop(session_id, None)

    thread = threading.Thread(target=run_agent, daemon=True)
    thread.start()

    return jsonify({"session_id": session_id})


@app.route("/api/stream/<session_id>")
def stream(session_id):
    """Stream agent logs via Server-Sent Events."""
    with _queues_lock:
        log_q = log_queues.get(session_id)
    if not log_q:
        return jsonify({"error": "Session not found"}), 404

    def generate():
        try:
            while True:
                try:
                    msg = log_q.get(timeout=30)
                    if msg["type"] == "done":
                        yield f"data: {json.dumps(msg)}\n\n"
                        break
                    yield f"data: {json.dumps(msg)}\n\n"
                except queue.Empty:
                    # Send heartbeat to keep connection alive
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
        finally:
            # Ensure queue cleanup even on client disconnect
            with _queues_lock:
                log_queues.pop(session_id, None)
                _queue_timestamps.pop(session_id, None)

    return Response(generate(), mimetype="text/event-stream")


@app.route("/api/answer/<session_id>", methods=["POST"])
def answer(session_id):
    """Receive user's answer to an ask_user question."""
    with _queues_lock:
        answer_q = answer_queues.get(session_id)
    if not answer_q:
        return jsonify({"error": "Session not found or not waiting for input"}), 404

    data = request.json
    user_answer = data.get("answer", "").strip()
    answer_q.put(user_answer)
    return jsonify({"status": "ok"})


@app.route("/api/stop", methods=["POST"])
def stop_build():
    """Stop the current build."""
    agent, _ = _get_agent()
    agent.stop()
    return jsonify({"status": "stop requested"})


@app.route("/api/stop-server", methods=["POST"])
def stop_server():
    """Stop the currently running dev server."""
    _kill_all_dev_servers()
    return jsonify({"status": "stopped"})


@app.route("/api/run/<project_name>", methods=["POST"])
def run_project(project_name):
    """Start the dev server for a project. Kills any previous dev server."""
    global _dev_server_proc, _dev_server_project

    project_dir = os.path.join(BASE_DIR, "output", project_name)
    if not os.path.isdir(project_dir):
        return jsonify({"error": f"Project '{project_name}' not found"}), 404

    if not os.path.exists(os.path.join(project_dir, "package.json")):
        return jsonify({"error": "No package.json found. Only React/Node projects are supported."}), 400

    # Kill ALL previous dev servers (ours + executor's + anything on port 5173)
    _kill_all_dev_servers()

    # Check if node_modules exists, install if not
    if not os.path.isdir(os.path.join(project_dir, "node_modules")):
        install = subprocess.run(
            "npm install",
            shell=True,
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if install.returncode != 0:
            return jsonify({"error": f"npm install failed: {install.stderr[:500]}"}), 500

    # Start dev server on port 5173
    _dev_server_proc = subprocess.Popen(
        "npm run dev -- --port 5173 --host",
        shell=True,
        cwd=project_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _dev_server_project = project_name

    return jsonify({
        "status": "running",
        "url": "http://localhost:5173",
        "project": project_name,
    })


@app.route("/api/running", methods=["GET"])
def get_running():
    """Check if a dev server is currently running (ours or executor's)."""
    # Check our own tracked process
    if _dev_server_proc and _dev_server_proc.poll() is None:
        return jsonify({"running": True, "project": _dev_server_project, "url": "http://localhost:5173"})
    # Also check the executor's tracked process (agent may have started one during build)
    try:
        from tools.executor import _dev_server_proc as exec_proc, _dev_server_project as exec_project
        if exec_proc and exec_proc.poll() is None:
            return jsonify({"running": True, "project": exec_project, "url": "http://localhost:5173"})
    except ImportError:
        pass
    return jsonify({"running": False})


@app.route("/api/chat-history/<project_name>", methods=["GET"])
def get_chat_history(project_name):
    """Load chat history for a project."""
    history_path = os.path.join(BASE_DIR, "output", project_name, ".chat_history.json")
    if not os.path.exists(history_path):
        return jsonify([])
    try:
        with open(history_path, "r", encoding="utf-8") as f:
            history = json.load(f)
        return jsonify(history)
    except Exception:
        return jsonify([])


@app.route("/api/chat-history/<project_name>", methods=["POST"])
def save_chat_message(project_name):
    """Append a message pair (user + agent) to the project's chat history."""
    project_dir = os.path.join(BASE_DIR, "output", project_name)
    if not os.path.isdir(project_dir):
        return jsonify({"error": "Project not found"}), 404

    history_path = os.path.join(project_dir, ".chat_history.json")

    # Load existing history
    history = []
    if os.path.exists(history_path):
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []

    # Append new message(s)
    data = request.json
    messages = data.get("messages", [])
    for msg in messages:
        history.append(msg)

    # Keep last 50 messages to avoid bloat
    history = history[-50:]

    try:
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "ok", "count": len(history)})


@app.route("/api/snapshots/<project_name>", methods=["GET"])
def get_snapshots(project_name):
    """List available snapshots for a project (newest-first)."""
    from tools.snapshots import list_snapshots
    return jsonify(list_snapshots(project_name))


@app.route("/api/revert/<project_name>", methods=["POST"])
def revert_project(project_name):
    """Revert a project to a previous snapshot."""
    from tools.snapshots import revert_to_snapshot
    data = request.json
    snapshot_id = data.get("snapshot_id", "").strip()
    if not snapshot_id:
        return jsonify({"status": "error", "message": "snapshot_id is required"}), 400
    result = revert_to_snapshot(project_name, snapshot_id)
    if result["status"] == "error":
        return jsonify(result), 404
    return jsonify(result)


@app.route("/api/memory", methods=["GET"])
def get_memory():
    """Get recent memory entries."""
    _, mem = _get_agent()
    context = mem.get_relevant_context("recent projects")
    return jsonify({"context": context})


@app.route("/api/status", methods=["GET"])
def get_status():
    """Return integration status (Figma, MCP, Memory)."""
    from agent.intent import is_figma_configured, is_mcp_configured
    figma = is_figma_configured()
    mcp = is_mcp_configured()
    memory = True  # Memory is always available
    return jsonify({"figma": figma, "mcp": mcp, "memory": memory})


def start_server(port=5000):
    """Start the web interface server."""
    print(f"\n{'=' * 60}")
    print(f"  Quiz Agent Platform")
    print(f"  Open http://localhost:{port} in your browser")
    print(f"{'=' * 60}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
