"""
MCP server configuration.
Reads MCP settings from environment variables (.env file).
"""

import os


def get_figma_mcp_config() -> dict | None:
    """
    Returns MCP server config if configured, None otherwise.

    Environment variables:
        MCP_FIGMA_COMMAND  - Server command (e.g., 'npx framelink-figma-mcp')
        MCP_FIGMA_ARGS     - Additional args (e.g., '--figma-api-key=<key>')

    If MCP_FIGMA_ARGS contains '<figma-api-key>' placeholder, it will be
    replaced with the FIGMA_ACCESS_TOKEN from environment.
    """
    command = os.environ.get("MCP_FIGMA_COMMAND", "").strip()
    if not command:
        return None

    args_str = os.environ.get("MCP_FIGMA_ARGS", "").strip()

    # Replace placeholder with actual token
    figma_token = os.environ.get("FIGMA_ACCESS_TOKEN", "")
    if "<figma-api-key>" in args_str and figma_token:
        args_str = args_str.replace("<figma-api-key>", figma_token)

    args = args_str.split() if args_str else []

    return {
        "command": command,
        "args": args,
    }


def is_mcp_configured() -> bool:
    """Check if an MCP Figma server is configured."""
    return bool(os.environ.get("MCP_FIGMA_COMMAND", "").strip())
