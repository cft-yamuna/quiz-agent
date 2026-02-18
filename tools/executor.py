import os
import json
import subprocess
import threading
import time

from tools.safety import validate_path, validate_command
from figma.client import FigmaClient
from figma.parser import extract_design_specs, extract_frames_summary

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# These are set by AgentCore after initialization
_memory = None
_planner = None
_current_project = None  # Active project name — used to enforce output/<project>/ paths

# Lock for shared dependencies
_deps_lock = threading.Lock()

# Track the running dev server so we can kill it before starting a new one
_dev_server_proc = None
_dev_server_project = None
_dev_server_lock = threading.Lock()


def set_dependencies(memory, planner, ask_user_fn=None, project_name=None):
    """Called by AgentCore to inject shared instances.
    ask_user_fn is accepted for backwards compatibility but ignored (autonomous mode).
    project_name sets the active project so file paths are enforced under output/<project>/."""
    global _memory, _planner, _current_project
    with _deps_lock:
        _memory = memory
        _planner = planner
        if project_name is not None:
            _current_project = project_name


def execute_tool(name: str, inputs) -> str:
    """
    Dispatch tool call to the appropriate handler.
    Returns a string result (success message or error).
    """
    # Validate inputs is a dict
    if not isinstance(inputs, dict):
        return json.dumps({"error": True, "message": f"Invalid inputs: expected dict, got {type(inputs).__name__}", "tool": name})

    handlers = {
        "create_file": _handle_create_file,
        "create_files": _handle_create_files,
        "read_file": _handle_read_file,
        "list_files": _handle_list_files,
        "run_command": _handle_run_command,
        "search_memory": _handle_search_memory,
        "save_memory": _handle_save_memory,
        "plan_tasks": _handle_plan_tasks,
        "preview_app": _handle_preview_app,
        "ask_user": _handle_ask_user,
        "fetch_figma_design": _handle_fetch_figma_design,
        "validate_screenshots": _handle_validate_screenshots,
        "analyze_flow": _handle_analyze_flow,
        "fetch_figma_mcp": _handle_fetch_figma_mcp,
    }

    handler = handlers.get(name)
    if not handler:
        return json.dumps({"error": True, "message": f"Unknown tool '{name}'", "tool": name})

    # Check required keys per tool
    required_keys = {
        "create_file": ["path", "content"],
        "read_file": ["path"],
        "list_files": ["directory"],
        "run_command": ["command"],
        "search_memory": ["query"],
        "save_memory": ["category", "key", "data"],
        "plan_tasks": ["tasks"],
        "preview_app": ["path"],
        "validate_screenshots": ["project_name"],
    }
    if name in required_keys:
        missing = [k for k in required_keys[name] if k not in inputs]
        if missing:
            return json.dumps({"error": True, "message": f"Missing required keys: {missing}", "tool": name})

    return handler(inputs)


def _enforce_output_dir(path: str) -> str:
    """Ensure file path is inside output/<project>/. Auto-correct bad paths."""
    normalized = path.replace("\\", "/").lstrip("./")

    # Already correct: output/<something>/...
    if normalized.startswith("output/"):
        parts = normalized.split("/")
        # Must have at least output/<project>/<file> — not just output/<file>
        if len(parts) >= 3:
            return normalized
        # Edge case: output/package.json — missing project name
        if _current_project and len(parts) == 2:
            print(f"  [Path Fix] Added project name: {path} -> output/{_current_project}/{parts[1]}")
            return f"output/{_current_project}/{parts[1]}"
        return normalized

    # Path does NOT start with output/ — agent mistake.
    # Check if it starts with the project name already (e.g. "my_quiz/src/App.jsx")
    if _current_project and normalized.startswith(f"{_current_project}/"):
        print(f"  [Path Fix] Added output/ prefix: {path} -> output/{normalized}")
        return f"output/{normalized}"

    # Bare path like "src/App.jsx" or "package.json" — prepend output/<project>/
    if _current_project:
        fixed = f"output/{_current_project}/{normalized}"
        print(f"  [Path Fix] Redirected to project: {path} -> {fixed}")
        return fixed

    # No project context — last resort, just put under output/
    print(f"  [Path Fix] No project context, using output/: {path}")
    return f"output/{normalized}"


def _handle_create_file(inputs: dict) -> str:
    raw_path = _enforce_output_dir(inputs["path"])
    path = validate_path(raw_path, BASE_DIR)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(inputs["content"])
    size = len(inputs["content"])
    return f"Created {raw_path} ({size} bytes)"


def _handle_create_files(inputs: dict) -> str:
    """Create multiple files in one call for faster project scaffolding."""
    files = inputs.get("files", [])
    if not files:
        return "ERROR: No files provided"

    results = []
    errors = []
    for f in files:
        try:
            raw_path = _enforce_output_dir(f["path"])
            path = validate_path(raw_path, BASE_DIR)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(f["content"])
            results.append(f"  {raw_path} ({len(f['content'])} bytes)")
        except Exception as e:
            errors.append(f"  FAILED {f.get('path', '???')}: {e}")

    summary = f"Created {len(results)} files"
    if errors:
        summary += f", {len(errors)} failed"
    parts = [summary + ":"]
    parts.extend(results)
    if errors:
        parts.append("Errors:")
        parts.extend(errors)
    return "\n".join(parts)


def _handle_read_file(inputs: dict) -> str:
    raw_path = _enforce_output_dir(inputs["path"])
    path = validate_path(raw_path, BASE_DIR)
    if not os.path.exists(path):
        return f"ERROR: File not found: {inputs['path']}"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    total = len(content)
    if total > 10000:
        content = content[:10000] + f"\n\n--- FILE TRUNCATED (showing first 10000 of {total} chars) ---"
    return content


def _handle_list_files(inputs: dict) -> str:
    raw_dir = _enforce_output_dir(inputs["directory"])
    directory = validate_path(raw_dir, BASE_DIR)
    if not os.path.isdir(directory):
        return f"ERROR: Not a directory: {inputs['directory']}"
    entries = []
    for item in sorted(os.listdir(directory)):
        full_path = os.path.join(directory, item)
        prefix = "[DIR] " if os.path.isdir(full_path) else "      "
        entries.append(f"{prefix}{item}")
    return "\n".join(entries) if entries else "(empty directory)"


def _resolve_project_cwd(command: str) -> str:
    """Extract project directory from 'cd output/xxx && ...' commands.
    Returns the absolute project path if found, otherwise BASE_DIR.
    """
    import re
    match = re.search(r'cd\s+(output[/\\]\S+)', command)
    if match:
        rel_path = match.group(1).replace("\\", "/")
        abs_path = os.path.join(BASE_DIR, rel_path)
        if os.path.isdir(abs_path):
            return abs_path
    return BASE_DIR


def _kill_port(port=5173):
    """Kill any process listening on the given port (Windows + Unix)."""
    import platform
    try:
        if platform.system() == "Windows":
            result = subprocess.run(
                f'netstat -ano | findstr :{port} | findstr LISTENING',
                shell=True, capture_output=True, text=True
            )
            killed_pids = set()
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    parts = line.split()
                    pid = parts[-1]
                    if pid.isdigit() and pid not in killed_pids:
                        subprocess.run(f'taskkill /F /PID {pid}', shell=True,
                                       capture_output=True)
                        killed_pids.add(pid)
                        print(f"  [Dev Server] Killed process {pid} on port {port}")
        else:
            result = subprocess.run(
                f'lsof -ti :{port}', shell=True, capture_output=True, text=True
            )
            for pid in result.stdout.strip().split('\n'):
                if pid.strip().isdigit():
                    subprocess.run(f'kill -9 {pid}', shell=True, capture_output=True)
                    print(f"  [Dev Server] Killed process {pid} on port {port}")
    except Exception:
        pass


def kill_dev_server():
    """Kill the currently running dev server (public, used by web/server.py too)."""
    global _dev_server_proc, _dev_server_project
    with _dev_server_lock:
        if _dev_server_proc and _dev_server_proc.poll() is None:
            try:
                _dev_server_proc.terminate()
                _dev_server_proc.wait(timeout=5)
            except Exception:
                try:
                    _dev_server_proc.kill()
                except Exception:
                    pass
            old_project = _dev_server_project
            _dev_server_proc = None
            _dev_server_project = None
            print(f"  [Dev Server] Killed tracked server ({old_project})")
        # Also kill anything else on port 5173 (e.g. server started by another module)
        _kill_port(5173)


def _kill_dev_server():
    """Internal alias — calls the public kill_dev_server."""
    kill_dev_server()


def _handle_run_command(inputs: dict) -> str:
    global _dev_server_proc, _dev_server_project

    command = validate_command(inputs["command"])
    cmd_lower = command.lower().strip()

    # Resolve the project directory from the command (e.g., "cd output/my_quiz && ...")
    project_cwd = _resolve_project_cwd(command)

    # Strip the "cd output/xxx && " prefix since we set cwd directly
    import re
    clean_command = re.sub(r'^cd\s+\S+\s*&&\s*', '', command).strip()

    # Detect long-running dev server commands — run in background
    bg_patterns = ["npm run dev", "npm start", "npx vite", "npm run preview"]
    is_bg = any(p in cmd_lower for p in bg_patterns)

    if is_bg:
        # Kill any previous dev server first
        _kill_dev_server()

        # Extract project name for tracking
        project_name = os.path.basename(project_cwd) if project_cwd != BASE_DIR else "unknown"

        try:
            with _dev_server_lock:
                _dev_server_proc = subprocess.Popen(
                    clean_command,
                    shell=True,
                    cwd=project_cwd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                _dev_server_project = project_name

            # Verify the process is still alive after a brief wait
            time.sleep(2)
            with _dev_server_lock:
                if _dev_server_proc and _dev_server_proc.poll() is not None:
                    exit_code = _dev_server_proc.returncode
                    _dev_server_proc = None
                    _dev_server_project = None
                    return f"ERROR: Dev server exited immediately with code {exit_code}. Check that npm install was run and package.json is valid."

            print(f"  [Dev Server] Started for '{project_name}' (cwd: {project_cwd})")
            return (
                f"Started dev server for '{project_name}' in background (cwd: {project_cwd}). "
                f"Dev server running at http://localhost:5173"
            )
        except Exception as e:
            return f"ERROR: Could not start background process: {e}"

    # npm install can be slow — give it 120s
    timeout = 120 if "npm install" in cmd_lower else 30

    try:
        result = subprocess.run(
            clean_command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=project_cwd,
        )
        output = ""
        if result.stdout:
            output += f"STDOUT:\n{result.stdout}"
        if result.stderr:
            output += f"STDERR:\n{result.stderr}"
        if result.returncode != 0:
            output += f"\nExit code: {result.returncode}"
        return output or "(no output)"
    except subprocess.TimeoutExpired:
        return f"ERROR: Command timed out after {timeout} seconds"


def _handle_search_memory(inputs: dict) -> str:
    if _memory is None:
        return "ERROR: Memory not initialized"
    category = inputs.get("category", "all")
    results = _memory.search(inputs["query"], category)
    if not results:
        return "No matching memories found."

    lines = []
    for r in results:
        lines.append(
            f"[{r['category']}] {r['key']}: "
            f"{json.dumps(r['data'], indent=None)[:300]}"
        )
    return "\n---\n".join(lines)


def _handle_save_memory(inputs: dict) -> str:
    if _memory is None:
        return "ERROR: Memory not initialized"
    _memory.save(inputs["category"], inputs["key"], inputs["data"])

    # If saving to "projects" category, also write .project_memory.json
    # in the project directory so it's available on next modify
    if inputs["category"] == "projects":
        project_dir = os.path.join(BASE_DIR, "output", inputs["key"])
        if os.path.isdir(project_dir):
            mem_path = os.path.join(project_dir, ".project_memory.json")
            try:
                # Load existing memory to merge (preserve change history)
                existing = {}
                if os.path.exists(mem_path):
                    with open(mem_path, "r", encoding="utf-8") as f:
                        existing = json.load(f)

                new_data = inputs["data"]
                # Merge changes list (append new changes to history)
                if "changes" in existing and "changes" in new_data:
                    all_changes = existing["changes"] + new_data["changes"]
                    new_data["changes"] = all_changes[-10:]  # Keep last 10
                elif "changes" in existing and "changes" not in new_data:
                    new_data["changes"] = existing["changes"]

                existing.update(new_data)
                with open(mem_path, "w", encoding="utf-8") as f:
                    json.dump(existing, f, indent=2)
            except Exception as e:
                print(f"  Warning: Could not save project memory: {e}")

    return f"Saved to {inputs['category']}/{inputs['key']}"


def _handle_plan_tasks(inputs: dict) -> str:
    if _planner is None:
        return "ERROR: Planner not initialized"
    _planner.update_tasks(inputs["tasks"])
    return _planner.get_status_report()


def _handle_preview_app(inputs: dict) -> str:
    path = validate_path(inputs["path"], BASE_DIR)
    if not os.path.exists(path):
        return f"ERROR: File not found: {inputs['path']}"
    abs_path = os.path.abspath(path)

    project_dir = os.path.dirname(abs_path)
    package_json = os.path.join(project_dir, "package.json")
    if not os.path.exists(package_json):
        return f"ERROR: No package.json found in {project_dir}. Only React/Node projects are supported."

    try:
        subprocess.Popen(
            "npm run dev",
            shell=True,
            cwd=project_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return (
            f"Started React dev server in {project_dir}. "
            f"Open http://localhost:5173 in your browser. "
            f"(Run 'npm run dev' in {project_dir} if it didn't start)"
        )
    except Exception as e:
        return f"Could not start dev server: {e}. Run 'npm run dev' manually in {project_dir}"


def _handle_ask_user(inputs: dict) -> str:
    """Autonomous mode: agent should not ask the user. Returns a directive to proceed."""
    question = inputs.get("question", "")
    print(f"  [Autonomous] Agent attempted to ask: {question}")
    return (
        "AUTONOMOUS MODE: Do not wait for user input. "
        "Make your best professional judgment and proceed. "
        "You are the expert — decide and continue building."
    )



def _handle_validate_screenshots(inputs: dict) -> str:
    """Take app screenshots with Playwright and pair with Figma screenshots for comparison."""
    from tools.screenshot_validator import validate

    project_name = inputs.get("project_name", "")
    if not project_name:
        return "ERROR: project_name is required"

    project_dir = os.path.join(BASE_DIR, "output", project_name)
    if not os.path.isdir(project_dir):
        return f"ERROR: Project '{project_name}' not found in output/"

    routes = inputs.get("routes", None)

    result = validate(project_name, routes)
    report = result["report"]
    image_paths = result["image_paths"]

    # Append image marker so agent core can send images to Gemini vision
    if image_paths:
        report += "\n\n__VALIDATION_IMAGES__:" + ",".join(image_paths)

    return report


def _handle_fetch_figma_design(inputs: dict) -> str:
    token = os.environ.get("FIGMA_ACCESS_TOKEN")
    figma_url = os.environ.get("FIGMA_URL") or os.environ.get("FIGMA_FILE_KEY")
    if not token or not figma_url:
        return "ERROR: FIGMA_ACCESS_TOKEN and FIGMA_URL must be set in .env"

    client = FigmaClient()

    # Log what we parsed from the URL
    print(f"  Figma file: {client.file_key}")
    if client.node_id:
        print(f"  Figma target node: {client.node_id} (from URL)")

    figma_data = client.get_file()
    specs = extract_design_specs(figma_data)

    # Add header showing scope
    if client.node_id:
        header = (
            f"## Figma Design (targeting node {client.node_id} from URL)\n"
            f"Only showing the specific page/section linked in the Figma URL.\n\n"
        )
        specs = header + specs

    # Export frame screenshots for visual reference
    frames = client.get_frame_ids()
    image_paths = {}
    if frames:
        frame_ids = [f["id"] for f in frames[:10]]  # Up to 10 frames for targeted pages
        try:
            image_paths = client.export_images(frame_ids, scale=1)
        except Exception as e:
            specs += f"\n\n(Could not export frame images: {e})"

    # If a specific page was requested via tool param, filter further
    page_name = inputs.get("page_name", "")
    if page_name:
        lines = specs.split("\n")
        filtered = []
        in_target = False
        for line in lines:
            if line.startswith("### Page:"):
                in_target = page_name.lower() in line.lower()
            if not line.startswith("### Page:") or in_target:
                if in_target or not line.startswith("  "):
                    filtered.append(line)
        if filtered:
            specs = "\n".join(filtered)

    # Append image paths so the agent core can send them to Gemini vision
    if image_paths:
        specs += "\n\n## Frame Screenshots (sent as images for visual reference)\n"
        frame_manifest = []
        for frame in frames[:10]:
            if frame["id"] in image_paths:
                path = image_paths[frame["id"]]
                specs += f"  - {frame['name']} ({frame['page']}): {path}\n"
                frame_manifest.append({
                    "id": frame["id"],
                    "name": frame.get("name", ""),
                    "page": frame.get("page", ""),
                    "image_path": path,
                })
        # Mark with special tag for agent core to detect
        specs += "\n__FIGMA_IMAGES__:" + ",".join(image_paths.values())

        # Save frame manifest so the validator knows which frames are current
        manifest_path = os.path.join(BASE_DIR, "figma", "cache", "_current_frames.json")
        try:
            with open(manifest_path, "w") as f:
                json.dump(frame_manifest, f, indent=2)
        except Exception:
            pass

    # Truncate if too large
    if len(specs) > 15000:
        specs = specs[:15000] + "\n... (truncated)"

    return specs


def _handle_analyze_flow(inputs: dict) -> str:
    """Analyze Figma frames to determine app screen flow and navigation."""
    from figma.flow_analyzer import analyze_flow, save_confirmed_flow

    # Load cached Figma data
    token = os.environ.get("FIGMA_ACCESS_TOKEN")
    figma_url = os.environ.get("FIGMA_URL") or os.environ.get("FIGMA_FILE_KEY")
    if not token or not figma_url:
        return "ERROR: Figma is not configured. Call fetch_figma_design first."

    client = FigmaClient()
    try:
        figma_data = client.get_file()
    except Exception as e:
        return f"ERROR: Could not load Figma data: {e}"

    # Extract structured frame + interactive element data
    frames, interactive_elements = extract_frames_summary(figma_data)

    if not frames:
        return "ERROR: No frames found in the Figma design. Make sure the Figma URL points to a page with frames."

    # Analyze the flow
    flow = analyze_flow(frames, interactive_elements)

    # Auto-confirm flow — no user interaction needed
    save_confirmed_flow(flow)

    result = (
        "Flow analysis auto-confirmed.\n\n"
        f"{flow['flow_text']}\n\n"
        f"Screens: {len(flow['screens'])}\n"
        f"Transitions: {len(flow['transitions'])}\n"
        "\nUse this confirmed flow to:\n"
        "  1. Create React Router routes matching each screen\n"
        "  2. Build components for each screen\n"
        "  3. Wire up navigation based on the transitions above"
    )

    return result


def _handle_fetch_figma_mcp(inputs: dict) -> str:
    """Fetch Figma design data via MCP server for LLM-optimized output."""
    from mcp.config import is_mcp_configured, get_figma_mcp_config

    if not is_mcp_configured():
        # Fall back to standard fetch_figma_design
        print("  [MCP] Not configured, falling back to fetch_figma_design")
        return _handle_fetch_figma_design(inputs)

    config = get_figma_mcp_config()

    # Determine the Figma URL to fetch
    figma_url = inputs.get("figma_url", "") or os.environ.get("FIGMA_URL", "")
    if not figma_url:
        return "ERROR: No Figma URL provided and FIGMA_URL not set in .env"

    node_id = inputs.get("node_id", "")

    # Start MCP server and fetch design data
    from mcp.client import MCPClient, MCPError

    mcp_result = ""
    try:
        client = MCPClient(config["command"], config["args"])
        client.start()

        # List available tools to find the right one
        tools = client.list_tools()
        tool_names = [t.get("name", "") for t in tools]
        print(f"  [MCP] Available tools: {tool_names}")

        # Try common Figma MCP tool names
        mcp_args = {"url": figma_url}
        if node_id:
            mcp_args["node_id"] = node_id

        if "get_figma_data" in tool_names:
            mcp_result = client.call_tool("get_figma_data", mcp_args)
        elif "get_file" in tool_names:
            mcp_result = client.call_tool("get_file", {"fileKey": figma_url})
        elif tools:
            # Try the first tool as a fallback
            mcp_result = client.call_tool(tool_names[0], mcp_args)

        client.stop()
        print(f"  [MCP] Design data fetched ({len(mcp_result)} chars)")

    except MCPError as e:
        print(f"  [MCP] Error: {e}. Falling back to standard fetch.")
        return _handle_fetch_figma_design(inputs)
    except Exception as e:
        print(f"  [MCP] Unexpected error: {e}. Falling back to standard fetch.")
        return _handle_fetch_figma_design(inputs)

    # Also export frame screenshots (MCP doesn't provide these)
    try:
        figma_client = FigmaClient()
        frames = figma_client.get_frame_ids()
        image_paths = {}
        if frames:
            frame_ids = [f["id"] for f in frames[:10]]
            image_paths = figma_client.export_images(frame_ids, scale=1)

        if image_paths:
            mcp_result += "\n\n## Frame Screenshots (sent as images for visual reference)\n"
            frame_manifest = []
            for frame in frames[:10]:
                if frame["id"] in image_paths:
                    path = image_paths[frame["id"]]
                    mcp_result += f"  - {frame['name']} ({frame['page']}): {path}\n"
                    frame_manifest.append({
                        "id": frame["id"],
                        "name": frame.get("name", ""),
                        "page": frame.get("page", ""),
                        "image_path": path,
                    })

            mcp_result += "\n__FIGMA_IMAGES__:" + ",".join(image_paths.values())

            # Save frame manifest
            manifest_path = os.path.join(BASE_DIR, "figma", "cache", "_current_frames.json")
            try:
                with open(manifest_path, "w") as f:
                    json.dump(frame_manifest, f, indent=2)
            except Exception:
                pass

    except Exception as e:
        mcp_result += f"\n\n(Could not export frame screenshots: {e})"

    # Truncate if too large
    if len(mcp_result) > 15000:
        mcp_result = mcp_result[:15000] + "\n... (truncated)"

    return mcp_result
