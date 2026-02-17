import os

# Patterns that are blocked in shell commands
BLOCKED_PATTERNS = [
    "rm ", "del ", "rmdir", "rd ",
    "format", "mkfs",
    "sudo", "su ",
    "chmod", "chown",
    "curl", "wget",
    "pip install", "npm install",
    "> /dev", "| rm",
    "&&", "||", ";",
    "`", "$(",
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
    """
    cmd_lower = command.lower().strip()

    for pattern in BLOCKED_PATTERNS:
        if pattern in cmd_lower:
            raise ValueError(
                f"Command blocked for safety: contains '{pattern}'. "
                f"Only safe read-only commands are allowed."
            )

    return command
