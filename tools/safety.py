import os
import re

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
    "npx vite build",
]

# Shell metacharacters that should not appear in command parts (beyond && for chaining)
_DANGEROUS_SHELL_CHARS = re.compile(r'[|;`$\(\)<>]')


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


def _is_safe_npm_install(part: str) -> bool:
    """Check if an npm install command is safe (no arbitrary packages from agent)."""
    part = part.strip()
    # Allow bare `npm install` or `npm i` (installs from package.json)
    if part in ("npm install", "npm i"):
        return True
    # Block `npm install <package>` — the agent should edit package.json instead
    if part.startswith("npm install ") or part.startswith("npm i "):
        return False
    return True


def validate_command(command: str) -> str:
    """
    Check command against blocklist. Raise if dangerous.
    Allows npm/npx commands for React project setup.
    """
    cmd_lower = command.lower().strip()

    # Check if command matches an allowed pattern first
    for allowed in ALLOWED_COMMANDS:
        if cmd_lower.startswith(allowed):
            # Extra check: restrict npm install arguments
            if allowed == "npm install" and not _is_safe_npm_install(cmd_lower):
                raise ValueError(
                    "npm install with package arguments is blocked. "
                    "Add dependencies to package.json and run `npm install` instead."
                )
            return command

    # Block command chaining (but allow it in npm scripts context)
    if any(chain in cmd_lower for chain in ["&&", "||", ";"]):
        # Allow chained npm commands like "cd output/proj && npm install"
        parts = cmd_lower.replace("&&", "|SEP|").replace("||", "|SEP|").replace(";", "|SEP|").split("|SEP|")
        for part in parts:
            part = part.strip()
            if not part:
                continue
            # Check if this part is an allowed command
            is_allowed = any(part.startswith(a) for a in ALLOWED_COMMANDS + ["cd ", "ls", "dir"])
            if is_allowed:
                # Extra check for npm install args
                if part.startswith("npm install") and not _is_safe_npm_install(part):
                    raise ValueError(
                        "npm install with package arguments is blocked. "
                        "Add dependencies to package.json and run `npm install` instead."
                    )
                continue
            # Not an allowed command — check for blocked patterns
            for pattern in BLOCKED_PATTERNS:
                if pattern in part:
                    raise ValueError(
                        f"Command blocked for safety: contains '{pattern}'. "
                        f"Only safe commands are allowed."
                    )
            # Also check for dangerous shell metacharacters in non-allowed parts
            if _DANGEROUS_SHELL_CHARS.search(part):
                raise ValueError(
                    f"Command blocked for safety: contains shell metacharacters. "
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
