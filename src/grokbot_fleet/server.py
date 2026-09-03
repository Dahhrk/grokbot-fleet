"""grokbot-fleet MCP server: Streamable HTTP with Bearer auth."""

import json
import os
from typing import Any

from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings

from grokbot_fleet.store import Store
from grokbot_fleet.jobs import (
    ConcurrentWriteError,
    JobManager,
    ValidationError,
    WebhookError,
)

MAX_BOTS = 50


class AuthMiddleware:
    """ASGI middleware: reject requests without a valid Bearer token."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            raw_auth = headers.get(b"authorization", b"")
            auth = raw_auth.decode("latin-1") if isinstance(raw_auth, bytes) else raw_auth
            if auth != f"Bearer {self.token}":
                resp = Response("Unauthorized", status_code=401, media_type="text/plain")
                await resp(scope, receive, send)
                return
        await self.app(scope, receive, send)


def _error(code: int, message: str) -> str:
    return json.dumps({"code": code, "error": message})


def register_tools(
    mcp: MCPServer,
    store: Store,
    job_mgr: JobManager,
    fleet_bot_id: str,
) -> None:
    """Register all MCP tools on the server instance."""

    # ── reads (local store, no webhook) ──────────────────────────

    @mcp.tool(description="List all Grok Bots visible on this computer.")
    def list_bots() -> str:
        return json.dumps(store.list_bots())

    @mcp.tool(description="Get details of a specific Grok Bot by ID.")
    def get_bot(bot_id: str) -> str:
        bot = store.get_bot(bot_id)
        if bot is None:
            raise ToolError(_error(404, f"bot {bot_id} not found"))
        return json.dumps(bot)

    @mcp.tool(description="List routines (automations) on this computer.")
    def list_routines() -> str:
        return json.dumps(store.list_routines())

    @mcp.tool(description="List user skills (workflows) on this computer.")
    def list_skills() -> str:
        return json.dumps(store.list_skills())

    @mcp.tool(description="Get the status and result of a job by ID.")
    def get_job(job_id: str) -> str:
        job = store.get_job(job_id)
        if job is None:
            raise ToolError(_error(404, f"job {job_id} not found"))
        return json.dumps(job)

    # ── writes (job inbox + webhook) ─────────────────────────────

    @mcp.tool(description="Create a new Grok Bot.")
    async def create_bot(name: str, description: str) -> str:
        if store.bot_count() >= MAX_BOTS:
            raise ToolError(_error(422, "bot limit reached (max 50)"))
        try:
            result = await job_mgr.submit(
                "create_bot",
                {"name": name, "description": description},
            )
        except ConcurrentWriteError:
            raise ToolError(_error(409, "another write is in progress"))
        except WebhookError as exc:
            raise ToolError(_error(503, exc.detail))
        return json.dumps(result)

    @mcp.tool(description="Update name and/or description (prompt) of a Grok Bot.")
    async def update_bot(
        bot_id: str,
        name: str | None = None,
        description: str | None = None,
    ) -> str:
        if store.get_bot(bot_id) is None:
            raise ToolError(_error(404, f"bot {bot_id} not found"))
        payload: dict[str, Any] = {"bot_id": bot_id}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        try:
            result = await job_mgr.submit("update_bot", payload)
        except ConcurrentWriteError:
            raise ToolError(_error(409, "another write is in progress"))
        except WebhookError as exc:
            raise ToolError(_error(503, exc.detail))
        return json.dumps(result)

    @mcp.tool(description="Create a routine on the Fleet bot (bot_id must be the Fleet bot).")
    async def create_routine(bot_id: str, name: str, prompt: str) -> str:
        if bot_id != fleet_bot_id:
            raise ToolError(
                _error(422, f"bot_id must be the Fleet bot ({fleet_bot_id})")
            )
        try:
            result = await job_mgr.submit(
                "create_routine",
                {"bot_id": bot_id, "name": name, "prompt": prompt},
            )
        except ConcurrentWriteError:
            raise ToolError(_error(409, "another write is in progress"))
        except WebhookError as exc:
            raise ToolError(_error(503, exc.detail))
        return json.dumps(result)

    @mcp.tool(description="Pause a routine on the Fleet bot (bot_id must be the Fleet bot).")
    async def pause_routine(routine_id: str, bot_id: str) -> str:
        if bot_id != fleet_bot_id:
            raise ToolError(
                _error(422, f"bot_id must be the Fleet bot ({fleet_bot_id})")
            )
        try:
            result = await job_mgr.submit(
                "pause_routine",
                {"routine_id": routine_id, "bot_id": bot_id},
            )
        except ConcurrentWriteError:
            raise ToolError(_error(409, "another write is in progress"))
        except WebhookError as exc:
            raise ToolError(_error(503, exc.detail))
        return json.dumps(result)

    @mcp.tool(description="Resume a routine on the Fleet bot (bot_id must be the Fleet bot).")
    async def resume_routine(routine_id: str, bot_id: str) -> str:
        if bot_id != fleet_bot_id:
            raise ToolError(
                _error(422, f"bot_id must be the Fleet bot ({fleet_bot_id})")
            )
        try:
            result = await job_mgr.submit(
                "resume_routine",
                {"routine_id": routine_id, "bot_id": bot_id},
            )
        except ConcurrentWriteError:
            raise ToolError(_error(409, "another write is in progress"))
        except WebhookError as exc:
            raise ToolError(_error(503, exc.detail))
        return json.dumps(result)

    @mcp.tool(description="Write a user skill.")
    async def write_skill(name: str, body: str) -> str:
        try:
            result = await job_mgr.submit(
                "write_skill",
                {"name": name, "body": body},
            )
        except ConcurrentWriteError:
            raise ToolError(_error(409, "another write is in progress"))
        except WebhookError as exc:
            raise ToolError(_error(503, exc.detail))
        return json.dumps(result)


def create_app(
    mcp_token: str,
    webhook_url: str,
    webhook_key: str,
    store_root: str = "/home/box/agent-data",
    fleet_bot_id: str = "fleet",
    host: str = "0.0.0.0",
) -> ASGIApp:
    """Build the ASGI application (MCP over Streamable HTTP with Bearer auth)."""

    store = Store(store_root)
    job_mgr = JobManager(store_root, webhook_url, webhook_key)

    mcp = MCPServer("grokbot-fleet")
    register_tools(mcp, store, job_mgr, fleet_bot_id)

    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    )
    mcp_app = mcp.streamable_http_app(
        streamable_http_path="/mcp",
        transport_security=security,
        host=host,
    )

    return AuthMiddleware(mcp_app, mcp_token)


def main() -> None:
    import uvicorn

    mcp_token = os.environ.get("MCP_TOKEN", "")
    if not mcp_token:
        raise SystemExit("MCP_TOKEN environment variable is required")

    webhook_url = os.environ.get("WEBHOOK_URL", "")
    if not webhook_url:
        raise SystemExit("WEBHOOK_URL environment variable is required")

    webhook_key = os.environ.get("WEBHOOK_KEY", "")
    if not webhook_key:
        raise SystemExit("WEBHOOK_KEY environment variable is required")

    store_root = os.environ.get("STORE_ROOT", "/home/box/agent-data")
    fleet_bot_id = os.environ.get("FLEET_BOT_ID", "fleet")
    port = int(os.environ.get("PORT", "8080"))

    app = create_app(
        mcp_token=mcp_token,
        webhook_url=webhook_url,
        webhook_key=webhook_key,
        store_root=store_root,
        fleet_bot_id=fleet_bot_id,
    )

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
