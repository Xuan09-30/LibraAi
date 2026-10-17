import os
import json
import sqlite3
import asyncio
from typing import Dict, Any, Optional, List

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    MCP_SDK_AVAILABLE = True
except ImportError:
    ClientSession = None
    StdioServerParameters = None
    stdio_client = None
    MCP_SDK_AVAILABLE = False

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_MCP_CONFIG = os.path.join(PROJECT_ROOT, "assets", "mcp_servers.json")


class LibraMCPClient:
    """
    Universal Model Context Protocol (MCP) Client Bridge for Project Libra v8.0.
    Configured via `assets/mcp_servers.json`. Supports official `mcp.ClientSession`
    stdio transport execution as well as deterministic built-in tool handlers for
    offline/headless reliability.
    """

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path if config_path else DEFAULT_MCP_CONFIG
        self.servers: Dict[str, Dict[str, Any]] = {}
        self.tool_registry: Dict[str, Dict[str, Any]] = {}
        self.load_config()

    def load_config(self) -> Dict[str, Any]:
        """Loads server definitions and exposed tool schemas from assets/mcp_servers.json."""
        self.servers.clear()
        self.tool_registry.clear()

        if not os.path.isfile(self.config_path):
            return {}

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw_servers = data.get("mcpServers", {})
            for srv_name, srv_cfg in raw_servers.items():
                self.servers[srv_name] = srv_cfg
                for tool in srv_cfg.get("tools", []):
                    t_name = tool.get("name")
                    if t_name:
                        self.tool_registry[f"{srv_name}.{t_name}"] = {
                            "server": srv_name,
                            "name": t_name,
                            "enabled": bool(srv_cfg.get("enabled", False)),
                            "description": tool.get("description", ""),
                            "inputSchema": tool.get("inputSchema", {})
                        }
            return self.servers
        except Exception as e:
            print(f"[LibraMCPClient Config Warning]: {e}")
            return {}

    def list_servers(self) -> Dict[str, Dict[str, Any]]:
        """Returns all configured MCP servers from assets/mcp_servers.json."""
        return dict(self.servers)

    def list_tools(self) -> List[Dict[str, Any]]:
        """Returns all registered MCP tool schemas across configured servers."""
        return list(self.tool_registry.values())

    async def _call_stdio_mcp_async(
        self,
        command: str,
        args: List[str],
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Executes a tool over an official MCP stdio_client and ClientSession."""
        if not MCP_SDK_AVAILABLE or StdioServerParameters is None:
            raise RuntimeError("MCP Python SDK not installed.")

        server_params = StdioServerParameters(command=command, args=args)
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments=arguments)
                return {
                    "status": "success",
                    "content": [getattr(c, "text", str(c)) for c in getattr(result, "content", [])]
                }

    def call_mcp_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Executes a tool on the specified MCP server with structured error handling
        and built-in local fallbacks for deterministic execution.
        """
        args = arguments or {}
        if dry_run:
            return {
                "status": "success",
                "server": server_name,
                "tool": tool_name,
                "arguments": args,
                "dry_run": True,
                "result": f"Simulated MCP call to {server_name}.{tool_name}"
            }

        # Built-in fast handlers for workspace_filesystem / local_filesystem and sqlite_memory / sqlite_inspector
        if server_name in ("workspace_filesystem", "local_filesystem"):
            if tool_name == "read_project_file":
                rel_path = args.get("path", "README.md")
                target = os.path.abspath(os.path.join(PROJECT_ROOT, rel_path))
                if not target.startswith(PROJECT_ROOT) or not os.path.isfile(target):
                    return {"status": "error", "error": f"File not found or outside workspace: {rel_path}"}
                with open(target, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read(4096)
                return {"status": "success", "server": server_name, "tool": tool_name, "result": content}

            if tool_name == "list_directory":
                rel_path = args.get("path", ".")
                target = os.path.abspath(os.path.join(PROJECT_ROOT, rel_path))
                if not target.startswith(PROJECT_ROOT) or not os.path.isdir(target):
                    return {"status": "error", "error": f"Directory not found: {rel_path}"}
                items = os.listdir(target)
                return {"status": "success", "server": server_name, "tool": tool_name, "result": items}

        if server_name in ("sqlite_memory", "sqlite_inspector") and tool_name == "list_tables":
            db_rel = args.get("db_path", "assets/libra_memory.db")
            db_full = db_rel if os.path.isfile(db_rel) else os.path.join(PROJECT_ROOT, db_rel)
            if not os.path.isfile(db_full):
                return {"status": "error", "error": f"Database not found: {db_rel}"}
            conn = sqlite3.connect(db_full)
            try:
                tables = [
                    r[0] for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                ]
                return {"status": "success", "server": server_name, "tool": tool_name, "result": tables}
            finally:
                conn.close()

        # External stdio MCP server execution if configured and enabled
        srv_cfg = self.servers.get(server_name)
        if not srv_cfg:
            return {"status": "error", "error": f"Unknown MCP server: {server_name}"}

        if not srv_cfg.get("enabled", False):
            return {
                "status": "disabled",
                "server": server_name,
                "tool": tool_name,
                "result": f"MCP server '{server_name}' is currently disabled in assets/mcp_servers.json."
            }

        try:
            cmd = srv_cfg.get("command", "python")
            cmd_args = srv_cfg.get("args", [])
            res = asyncio.run(self._call_stdio_mcp_async(cmd, cmd_args, tool_name, args))
            res["server"] = server_name
            res["tool"] = tool_name
            return res
        except Exception as e:
            return {
                "status": "error",
                "server": server_name,
                "tool": tool_name,
                "error": str(e)
            }
