"""
Shared context builder for both CLI and web interfaces.

Detects create vs modify mode, assembles full prompt with context blocks
including project info, memory, chat history, and key file contents.
"""

import os
import json
import re


def build_prompt_context(project_name: str, user_prompt: str, base_dir: str) -> str:
    """Build a fully-contextualized prompt for the agent.

    Detects whether the project exists (has package.json) and assembles
    the appropriate context blocks.

    Args:
        project_name: Sanitized project name (e.g., 'quiz_2').
        user_prompt: The user's raw prompt text.
        base_dir: Absolute path to the repo root (where output/ lives).

    Returns:
        Full prompt string with [Mode], [Project info], etc. prepended.
    """
    project_dir = os.path.join(base_dir, "output", project_name)
    is_existing = (
        os.path.isdir(project_dir)
        and os.path.exists(os.path.join(project_dir, "package.json"))
    )

    if is_existing:
        info = _scan_project_info(project_dir, project_name)
        project_mem = _load_project_memory(project_dir)
        recent_chat = _load_recent_chat(project_dir)
        key_files = _read_key_files(project_dir, project_name, user_prompt)

        parts = [f"[Project name: {project_name}] [Mode: modify]"]
        parts.append(f"[Project info]\n{info}\n[/Project info]")
        if project_mem:
            parts.append(f"[Project memory]\n{project_mem}\n[/Project memory]")
        if recent_chat:
            parts.append(f"[Recent conversation]\n{recent_chat}\n[/Recent conversation]")
        if key_files:
            parts.append(f"[Key file contents]\n{key_files}\n[/Key file contents]")
        parts.append(user_prompt)
        return "\n".join(parts)
    else:
        return f"[Project name: {project_name}] [Mode: create]\n{user_prompt}"


def _scan_project_info(project_dir: str, project_name: str) -> str:
    """Scan an existing project and return basic info for the agent."""
    lines = []

    # 1. File structure
    src_dir = os.path.join(project_dir, "src")
    if os.path.isdir(src_dir):
        files = []
        for root, dirs, filenames in os.walk(src_dir):
            dirs[:] = [d for d in dirs if d != "node_modules"]
            for fname in filenames:
                rel = os.path.relpath(os.path.join(root, fname), project_dir).replace("\\", "/")
                files.append(rel)
        lines.append(f"Files: {', '.join(sorted(files))}")
    else:
        lines.append("Files: src/ directory MISSING")

    # 2. node_modules
    has_modules = os.path.isdir(os.path.join(project_dir, "node_modules"))
    lines.append(f"node_modules: {'installed' if has_modules else 'MISSING (needs npm install)'}")

    # 3. Read package.json deps
    pkg_path = os.path.join(project_dir, "package.json")
    try:
        with open(pkg_path, "r", encoding="utf-8") as f:
            pkg = json.load(f)
        deps = list(pkg.get("dependencies", {}).keys())
        lines.append(f"Dependencies: {', '.join(deps)}")
    except Exception:
        lines.append("Dependencies: could not read package.json")

    return "\n".join(lines)


def _load_project_memory(project_dir: str) -> str:
    """Load project memory from .project_memory.json if it exists."""
    mem_path = os.path.join(project_dir, ".project_memory.json")
    if not os.path.exists(mem_path):
        return ""
    try:
        with open(mem_path, "r", encoding="utf-8") as f:
            mem = json.load(f)
        lines = []
        if mem.get("description"):
            lines.append(f"Project: {mem['description']}")
        if mem.get("quiz_type"):
            lines.append(f"Quiz type: {mem['quiz_type']}")
        if mem.get("components"):
            lines.append(f"Components: {', '.join(mem['components'])}")
        if mem.get("features"):
            lines.append(f"Features: {', '.join(mem['features'])}")
        if mem.get("changes"):
            lines.append("Recent changes:")
            for change in mem["changes"][-5:]:
                lines.append(f"  - {change}")
        return "\n".join(lines)
    except Exception:
        return ""


def _load_recent_chat(project_dir: str, limit: int = 6) -> str:
    """Load last few chat messages to give the agent conversation context."""
    history_path = os.path.join(project_dir, ".chat_history.json")
    if not os.path.exists(history_path):
        return ""
    try:
        with open(history_path, "r", encoding="utf-8") as f:
            history = json.load(f)
        if not history:
            return ""
        recent = history[-limit:]
        lines = []
        for msg in recent:
            role = msg.get("role", "user")
            text = msg.get("content", "")[:200]
            lines.append(f"  {role}: {text}")
        return "\n".join(lines)
    except Exception:
        return ""


def _read_key_files(project_dir: str, project_name: str, user_prompt: str) -> str:
    """Auto-read key project files and inject their contents into the prompt.

    Always reads App.jsx and App.css (the most commonly modified files).
    Also reads any component file mentioned in the user's prompt.
    Capped at 8000 chars total to avoid bloating the context.
    """
    MAX_CHARS = 8000
    files_to_read = []

    # Always include App.jsx and App.css
    default_files = ["src/App.jsx", "src/App.css"]
    for rel_path in default_files:
        full_path = os.path.join(project_dir, rel_path)
        if os.path.isfile(full_path):
            files_to_read.append(rel_path)

    # Scan for component names mentioned in the user's prompt
    # Match patterns like "QuizStart", "Question.jsx", "components/Results"
    prompt_lower = user_prompt.lower()
    src_dir = os.path.join(project_dir, "src")
    if os.path.isdir(src_dir):
        for root, dirs, filenames in os.walk(src_dir):
            dirs[:] = [d for d in dirs if d != "node_modules"]
            for fname in filenames:
                if not fname.endswith((".jsx", ".js", ".tsx", ".ts", ".css")):
                    continue
                # Check if the filename (without extension) is mentioned in the prompt
                name_no_ext = os.path.splitext(fname)[0].lower()
                if name_no_ext in prompt_lower and name_no_ext not in ("app", "main", "index"):
                    rel = os.path.relpath(os.path.join(root, fname), project_dir).replace("\\", "/")
                    if rel not in files_to_read:
                        files_to_read.append(rel)

    # Read files up to the char cap
    output_parts = []
    total_chars = 0
    for rel_path in files_to_read:
        full_path = os.path.join(project_dir, rel_path)
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            continue

        entry = f"--- {rel_path} ---\n{content}\n"
        if total_chars + len(entry) > MAX_CHARS:
            remaining = MAX_CHARS - total_chars
            if remaining > 200:  # Only include if we have meaningful space
                entry = f"--- {rel_path} (truncated) ---\n{content[:remaining - 50]}\n... (truncated)\n"
                output_parts.append(entry)
            break
        output_parts.append(entry)
        total_chars += len(entry)

    return "".join(output_parts)
