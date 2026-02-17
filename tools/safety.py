import os

# Patterns that are blocked in shell commands
BLOCKED_PATTERNS = [
    "rm ", "del ", "rmdir", "rd ",
    "format", "mkfs",
    "sudo", "su ",
    "chmod", "chown",
    "curl", "wget",
    "pip install",
    "> /dev", "| rm",
    "`", "$(",
]

# Commands that are explicitly allowed even if they contain blocked substrings
ALLOWED_COMMANDS = [
    "npm install",
    "npm run dev",
    "npm run build",
    "npm run preview",
    "npm start",
    "npm init",
    "npx create-vite",
    "npm create vite",
]


def validate_path(path: str, base_dir: str) -> str:
    """
    Resolve path and ensure it stays within the project directory.
    Prevents path traversal attacks (../../etc/passwd).
    """
    if not os.path.isabs(path):
        resolved = os.path.abspath(os.path.join(base_dir, path))
    else:
        resolved = os.path.abspath(path)

    base_abs = os.path.abspath(base_dir)
    if not resolved.startswith(base_abs):
        raise ValueError(
            f"Path '{path}' resolves outside project directory. "
            f"Must be under {base_dir}"
        )

    return resolved


def validate_command(command: str) -> str:
    """
    Check command against blocklist. Raise if dangerous.
    Allows npm/npx commands for React project setup.
    """
    cmd_lower = command.lower().strip()

    # Check if command matches an allowed pattern first
    for allowed in ALLOWED_COMMANDS:
        if cmd_lower.startswith(allowed):
            return command

    # Block command chaining (but allow it in npm scripts context)
    if any(chain in cmd_lower for chain in ["&&", "||", ";"]):
        # Allow chained npm commands like "cd output/proj && npm install"
        parts = cmd_lower.replace("&&", "|").replace("||", "|").replace(";", "|").split("|")
        for part in parts:
            part = part.strip()
            if part and not any(part.startswith(a) for a in ALLOWED_COMMANDS + ["cd ", "ls", "dir"]):
                for pattern in BLOCKED_PATTERNS:
                    if pattern in part:
                        raise ValueError(
                            f"Command blocked for safety: contains '{pattern}'. "
                            f"Only safe commands are allowed."
                        )
        return command

    for pattern in BLOCKED_PATTERNS:
        if pattern in cmd_lower:
            raise ValueError(
                f"Command blocked for safety: contains '{pattern}'. "
                f"Only safe commands are allowed."
            )

    return command
