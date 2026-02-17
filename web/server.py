import os
import json
import subprocess
import signal
import threading
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
                has_html = os.path.exists(os.path.join(project_path, "index.html"))

                if has_pkg and has_src:
                    tech = "React"
                elif has_pkg:
                    tech = "Node.js"
                elif has_html:
                    tech = "HTML/CSS/JS"
                else:
                    tech = "Unknown"

                projects.append({"name": item, "tech": tech})
    return jsonify(projects)


@app.route("/api/build", methods=["POST"])
def build():
    """Start building a quiz app from a prompt."""
    data = request.json
    prompt = data.get("prompt", "").strip()
    if not prompt:
        return jsonify({"error": "Prompt is required"}), 400

    # Auto-detect Figma URL in prompt and update .env
    from figma.client import extract_and_update_figma_url
    extract_and_update_figma_url(prompt)

    # Add Figma hint if configured
    figma_url = os.environ.get("FIGMA_URL", "")
    if figma_url or os.environ.get("FIGMA_FILE_KEY"):
        if "figma" not in prompt.lower() and "design" not in prompt.lower():
            hint = (
                "\n\n[System: A Figma design file is connected. "
                "Use fetch_figma_design to get the design specs and match them exactly."
            )
            if "node-id=" in figma_url:
                hint += (
                    " The Figma URL points to a SPECIFIC page/section — "
                    "focus only on the frames returned, do not look for other pages."
                )
            hint += "]"
            prompt += hint

    # Create a unique session ID for log streaming
    import uuid
    session_id = str(uuid.uuid4())[:8]
    log_q = queue.Queue()
    answer_q = queue.Queue()
    log_queues[session_id] = log_q
    answer_queues[session_id] = answer_q

    def web_ask_user(question):
        """Send question to frontend via SSE, wait for answer via POST."""
        log_q.put({"type": "ask_user", "message": question})
        try:
            answer = answer_q.get(timeout=300)  # 5 min timeout
            return answer if answer else "User did not respond."
        except queue.Empty:
            return "User did not respond (timed out)."

    def run_agent():
        import sys
        from tools.executor import set_dependencies

        agent, mem = _get_agent()

        # Inject ask_user callback for this session
        set_dependencies(memory=agent.memory, planner=agent.planner, ask_user_fn=web_ask_user)

        # Capture stdout to stream logs
        old_stdout = sys.stdout
        sys.stdout = LogCapture(log_q)

        try:
            result = agent.run(prompt)
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
            answer_queues.pop(session_id, None)

    thread = threading.Thread(target=run_agent, daemon=True)
    thread.start()

    return jsonify({"session_id": session_id})


@app.route("/api/stream/<session_id>")
def stream(session_id):
    """Stream agent logs via Server-Sent Events."""
    log_q = log_queues.get(session_id)
    if not log_q:
        return jsonify({"error": "Session not found"}), 404

    def generate():
        while True:
            try:
                msg = log_q.get(timeout=120)
                if msg["type"] == "done":
                    yield f"data: {json.dumps(msg)}\n\n"
                    break
                yield f"data: {json.dumps(msg)}\n\n"
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'log', 'message': 'Still working...'})}\n\n"

        # Cleanup
        log_queues.pop(session_id, None)

    return Response(generate(), mimetype="text/event-stream")


@app.route("/api/answer/<session_id>", methods=["POST"])
def answer(session_id):
    """Receive user's answer to an ask_user question."""
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

    has_pkg = os.path.exists(os.path.join(project_dir, "package.json"))
    if not has_pkg:
        # Static HTML project — no dev server needed
        return jsonify({
            "status": "static",
            "url": None,
            "message": f"Static project. Open output/{project_name}/index.html directly.",
        })

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


@app.route("/api/memory", methods=["GET"])
def get_memory():
    """Get recent memory entries."""
    _, mem = _get_agent()
    context = mem.get_relevant_context("recent projects")
    return jsonify({"context": context})


def start_server(port=5000):
    """Start the web interface server."""
    print(f"\n{'=' * 60}")
    print(f"  Quiz Agent Platform")
    print(f"  Open http://localhost:{port} in your browser")
    print(f"{'=' * 60}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
