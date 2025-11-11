"""Async MCP client for invoking tools exposed by the Odoo MCP server."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Dict, Optional

import httpx

LOGGER = logging.getLogger(__name__)


class MCPClientError(RuntimeError):
    """Raised when the MCP server returns an error response."""


class MCPClient:
    """Small JSON-RPC client for the LangChain PoC."""

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._session_id: Optional[str] = None
        self._lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            async with self._lock:
                if self._client is None:
                    self._client = httpx.AsyncClient(
                        base_url=self._base_url,
                        timeout=self._timeout,
                        headers={"Accept": "application/json"},
                    )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._session_id = None

    async def _ensure_session(self) -> None:
        if self._session_id:
            return
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "langchain-agent", "version": "0.1.0"},
            },
        }
        client = await self._get_client()
        try:
            response = await client.post("/mcp", json=payload)
        except httpx.HTTPError as exc:
            LOGGER.error("Failed to reach MCP server at %s: %s", self._base_url, exc)
            raise MCPClientError(str(exc)) from exc
        response.raise_for_status()
        self._session_id = response.headers.get("Mcp-Session-Id")

    async def call_tool(self, tool_name: str, params: Dict[str, Any]) -> Any:
        """Invoke an MCP tool via JSON-RPC."""

        await self._ensure_session()
        client = await self._get_client()
        request_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": params or {},
            },
        }

        headers = {}
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id

        LOGGER.debug("Calling MCP tool %s with payload %s", tool_name, payload)
        try:
            response = await client.post("/mcp", json=payload, headers=headers)
        except httpx.HTTPError as exc:
            LOGGER.error("Failed to reach MCP server at %s: %s", self._base_url, exc)
            raise MCPClientError(str(exc)) from exc
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            error = data["error"]
            LOGGER.error("MCP error (tool=%s): %s", tool_name, error)
            raise MCPClientError(str(error))
        result = data.get("result", {})
        content = result.get("content", [])
        if not content:
            return result
        # Prefer first text content entry
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                return item.get("text")
        return content

    async def ping(self) -> bool:
        try:
            result = await self.call_tool("server_status", {})
        except MCPClientError:
            return False
        return bool(result)
