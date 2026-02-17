import os
import subprocess
import webbrowser

from tools.safety import validate_path, validate_command

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# These are set by AgentCore after initialization
_memory = None
_planner = None


def set_dependencies(memory, planner):
    """Called by AgentCore to inject shared instances."""
    global _memory, _planner
    _memory = memory
    _planner = planner


def execute_tool(name: str, inputs: dict) -> str:
    """
    Dispatch tool call to the appropriate handler.
    Returns a string result (success message or error).
    """
    handlers = {
        "create_file": _handle_create_file,
        "read_file": _handle_read_file,
        "list_files": _handle_list_files,
        "run_command": _handle_run_command,
        "search_memory": _handle_search_memory,
        "save_memory": _handle_save_memory,
        "plan_tasks": _handle_plan_tasks,
        "preview_app": _handle_preview_app,
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


def _handle_run_command(inputs: dict) -> str:
    command = validate_command(inputs["command"])
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=BASE_DIR,
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
        return "ERROR: Command timed out after 30 seconds"


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
    webbrowser.open(f"file:///{abs_path}")
    return f"Opened {abs_path} in browser"
