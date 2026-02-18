"""
Generic MCP (Model Context Protocol) client.
Communicates with MCP servers over stdio using JSON-RPC 2.0.
"""

import json
import subprocess
import threading
import os


class MCPError(Exception):
    """Error from MCP server communication."""
    pass


class MCPClient:
    """
    Client for communicating with MCP servers over stdio.

    Usage:
        client = MCPClient("npx", ["framelink-figma-mcp", "--figma-api-key=KEY"])
        client.start()
        tools = client.list_tools()
        result = client.call_tool("get_figma_data", {"url": "..."})
        client.stop()
    """

    def __init__(self, command: str, args: list = None, env: dict = None):
        self.command = command
        self.args = args or []
        self.env = env
        self._process = None
        self._request_id = 0
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start the MCP server subprocess and perform initialization handshake."""
        if self._process and self._process.poll() is None:
            return  # Already running

        # Build environment
        proc_env = os.environ.copy()
        if self.env:
            proc_env.update(self.env)

        full_command = [self.command] + self.args

        try:
            self._process = subprocess.Popen(
                full_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=proc_env,
                shell=True,  # Needed for npx on Windows
            )
        except Exception as e:
            raise MCPError(f"Failed to start MCP server: {e}")

        # Send initialize request
        init_result = self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "quiz-agent",
                "version": "1.0.0",
            },
        })

        if not init_result:
            self.stop()
            raise MCPError("MCP server did not respond to initialization")

        # Send initialized notification
        self._send_notification("notifications/initialized", {})

        print(f"  [MCP] Server started: {' '.join(full_command)}")

    def list_tools(self) -> list:
        """Get the list of available tools from the MCP server."""
        self._ensure_running()
        result = self._send_request("tools/list", {})
        return result.get("tools", []) if result else []

    def call_tool(self, tool_name: str, arguments: dict = None) -> str:
        """
        Call a tool on the MCP server and return the text result.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments dict

        Returns:
            Combined text content from the tool response
        """
        self._ensure_running()
        result = self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments or {},
        })

        if not result:
            raise MCPError(f"No response from tool '{tool_name}'")

        # Extract text content from response
        content = result.get("content", [])
        texts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(item.get("text", ""))
        return "\n".join(texts) if texts else json.dumps(result)

    def stop(self) -> None:
        """Gracefully shut down the MCP server subprocess."""
        if self._process:
            try:
                if self._process.poll() is None:
                    self._process.stdin.close()
                    self._process.terminate()
                    try:
                        self._process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        self._process.kill()
                        self._process.wait(timeout=5)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None
            print("  [MCP] Server stopped")

    def _ensure_running(self):
        """Check if the server process is still running."""
        if not self._process or self._process.poll() is not None:
            raise MCPError("MCP server is not running")

    def _send_request(self, method: str, params: dict, timeout: float = 30.0) -> dict | None:
        """Send a JSON-RPC request and wait for response."""
        with self._lock:
            self._request_id += 1
            request_id = self._request_id

        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        try:
            msg_bytes = (json.dumps(message) + "\n").encode("utf-8")
            self._process.stdin.write(msg_bytes)
            self._process.stdin.flush()
        except Exception as e:
            raise MCPError(f"Failed to send request: {e}")

        # Read response with timeout
        return self._read_response(request_id, timeout)

    def _send_notification(self, method: str, params: dict) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

        try:
            msg_bytes = (json.dumps(message) + "\n").encode("utf-8")
            self._process.stdin.write(msg_bytes)
            self._process.stdin.flush()
        except Exception:
            pass  # Notifications don't require acknowledgment

    def _read_response(self, request_id: int, timeout: float) -> dict | None:
        """Read and parse the JSON-RPC response for a specific request ID."""
        import time
        deadline = time.time() + timeout

        while time.time() < deadline:
            if self._process.poll() is not None:
                # Process has exited — try to read any remaining output
                stderr = ""
                try:
                    stderr = self._process.stderr.read().decode("utf-8", errors="replace")
                except Exception:
                    pass
                raise MCPError(f"MCP server exited unexpectedly. Stderr: {stderr[:500]}")

            try:
                # Use a thread to read with timeout
                line = self._readline_with_timeout(1.0)
                if not line:
                    continue

                line = line.strip()
                if not line:
                    continue

                try:
                    response = json.loads(line)
                except json.JSONDecodeError:
                    continue  # Skip non-JSON lines (server logs, etc.)

                # Check if this is our response
                if response.get("id") == request_id:
                    if "error" in response:
                        err = response["error"]
                        raise MCPError(
                            f"MCP error ({err.get('code', '?')}): {err.get('message', 'Unknown error')}"
                        )
                    return response.get("result", {})

                # Skip notifications and other messages
            except MCPError:
                raise
            except Exception:
                continue

        raise MCPError(f"Timeout waiting for response to request {request_id}")

    def _readline_with_timeout(self, timeout: float) -> str | None:
        """Read a line from stdout with timeout."""
        result = [None]

        def _read():
            try:
                result[0] = self._process.stdout.readline().decode("utf-8", errors="replace")
            except Exception:
                pass

        thread = threading.Thread(target=_read, daemon=True)
        thread.start()
        thread.join(timeout=timeout)

        return result[0]

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()

    def __del__(self):
        self.stop()
