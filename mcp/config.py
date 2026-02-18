"""
MCP server configuration.
Reads MCP settings from environment variables (.env file).
"""

import os


def get_figma_mcp_config() -> dict | None:
    """
    Returns MCP server config if configured, None otherwise.

    Environment variables:
        MCP_FIGMA_COMMAND  - Server command with args (e.g., 'npx -y figma-developer-mcp')
        MCP_FIGMA_ARGS     - Additional args (e.g., '--figma-api-key=<key>')

    If MCP_FIGMA_ARGS contains '<figma-api-key>' placeholder, it will be
    replaced with the FIGMA_ACCESS_TOKEN from environment.
    """
    command_str = os.environ.get("MCP_FIGMA_COMMAND", "").strip()
    if not command_str:
        return None

    # Split command into executable + its own args
    command_parts = command_str.split()
    command = command_parts[0]
    command_args = command_parts[1:] if len(command_parts) > 1 else []

    # Process additional args
    args_str = os.environ.get("MCP_FIGMA_ARGS", "").strip()

    # Replace placeholder with actual token
    figma_token = os.environ.get("FIGMA_ACCESS_TOKEN", "")
    if "<figma-api-key>" in args_str and figma_token:
        args_str = args_str.replace("<figma-api-key>", figma_token)

    extra_args = args_str.split() if args_str else []

    # Combine: command's own args + extra args
    all_args = command_args + extra_args

    return {
        "command": command,
        "args": all_args,
    }


def is_mcp_configured() -> bool:
    """Check if an MCP Figma server is configured."""
    return bool(os.environ.get("MCP_FIGMA_COMMAND", "").strip())
