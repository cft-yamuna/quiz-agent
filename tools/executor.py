import os
import subprocess
import webbrowser

from tools.safety import validate_path, validate_command
from figma.client import FigmaClient
from figma.parser import extract_design_specs

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# These are set by AgentCore after initialization
_memory = None
_planner = None
_ask_user_fn = None  # Callback for getting user input

# Track the running dev server so we can kill it before starting a new one
_dev_server_proc = None
_dev_server_project = None


def set_dependencies(memory, planner, ask_user_fn=None):
    """Called by AgentCore to inject shared instances."""
    global _memory, _planner, _ask_user_fn
    _memory = memory
    _planner = planner
    if ask_user_fn is not None:
        _ask_user_fn = ask_user_fn


def execute_tool(name: str, inputs: dict) -> str:
    """
    Dispatch tool call to the appropriate handler.
    Returns a string result (success message or error).
    """
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
        "check_existing_projects": _handle_check_existing_projects,
        "fetch_figma_design": _handle_fetch_figma_design,
        "validate_screenshots": _handle_validate_screenshots,
    }

    handler = handlers.get(name)
    if not handler:
        return f"ERROR: Unknown tool '{name}'"

    return handler(inputs)


def _handle_create_file(inputs: dict) -> str:
    path = validate_path(inputs["path"], BASE_DIR)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(inputs["content"])
    size = len(inputs["content"])
    return f"Created {inputs['path']} ({size} bytes)"


def _handle_create_files(inputs: dict) -> str:
    """Create multiple files in one call for faster project scaffolding."""
    files = inputs.get("files", [])
    if not files:
        return "ERROR: No files provided"

    results = []
    for f in files:
        path = validate_path(f["path"], BASE_DIR)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f["content"])
        results.append(f"  {f['path']} ({len(f['content'])} bytes)")

    return f"Created {len(results)} files:\n" + "\n".join(results)


def _handle_read_file(inputs: dict) -> str:
    path = validate_path(inputs["path"], BASE_DIR)
    if not os.path.exists(path):
        return f"ERROR: File not found: {inputs['path']}"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if len(content) > 10000:
        content = content[:10000] + f"\n... (truncated, {len(content)} total chars)"
    return content


def _handle_list_files(inputs: dict) -> str:
    directory = validate_path(inputs["directory"], BASE_DIR)
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
            _dev_server_proc = subprocess.Popen(
                clean_command,
                shell=True,
                cwd=project_cwd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _dev_server_project = project_name
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
    import json

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

    # Check if this is a React project (has package.json)
    project_dir = os.path.dirname(abs_path)
    package_json = os.path.join(project_dir, "package.json")
    if os.path.exists(package_json):
        # For React projects, start the dev server
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

    # Fallback: open static HTML directly
    webbrowser.open(f"file:///{abs_path}")
    return f"Opened {abs_path} in browser"


def _handle_ask_user(inputs: dict) -> str:
    """Ask the user a question and return their response."""
    question = inputs.get("question", "")
    if not question:
        return "ERROR: No question provided"

    if _ask_user_fn is None:
        # Fallback: direct stdin (works in CLI)
        print(f"\n  Agent asks: {question}")
        try:
            answer = input("  You: ").strip()
        except (EOFError, KeyboardInterrupt):
            return "User did not respond."
        return answer if answer else "User did not respond."

    # Use injected callback (for web UI, etc.)
    return _ask_user_fn(question)


def _handle_check_existing_projects(inputs: dict) -> str:
    output_dir = os.path.join(BASE_DIR, "output")
    if not os.path.exists(output_dir):
        return "No existing projects found. The output/ directory does not exist yet."

    projects = []
    for item in sorted(os.listdir(output_dir)):
        project_path = os.path.join(output_dir, item)
        if not os.path.isdir(project_path):
            continue

        # Detect project type
        has_package_json = os.path.exists(os.path.join(project_path, "package.json"))
        has_index_html = os.path.exists(os.path.join(project_path, "index.html"))
        has_src = os.path.isdir(os.path.join(project_path, "src"))

        if has_package_json and has_src:
            tech = "React (Vite)"
        elif has_package_json:
            tech = "Node.js project"
        elif has_index_html:
            tech = "Static HTML/CSS/JS"
        else:
            tech = "Unknown"

        # List key files
        files = []
        for root, dirs, filenames in os.walk(project_path):
            # Skip node_modules
            dirs[:] = [d for d in dirs if d != "node_modules"]
            for fname in filenames:
                rel = os.path.relpath(os.path.join(root, fname), project_path)
                files.append(rel)

        projects.append({
            "name": item,
            "tech": tech,
            "files": files[:20],  # Limit to 20 files
            "file_count": len(files),
        })

    if not projects:
        return "No existing projects found in the output/ directory."

    import json
    lines = [f"Found {len(projects)} existing project(s):\n"]
    for p in projects:
        lines.append(f"### {p['name']} ({p['tech']})")
        lines.append(f"  Files ({p['file_count']} total): {', '.join(p['files'][:10])}")
        if p['file_count'] > 10:
            lines.append(f"  ... and {p['file_count'] - 10} more files")
        lines.append("")

    lines.append(
        "NEXT STEP: Use the ask_user tool to ask the user whether they want to "
        "MODIFY one of these existing projects or CREATE a completely new one."
    )
    return "\n".join(lines)


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
        import json
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
