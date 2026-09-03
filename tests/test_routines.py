"""Routine validation tests: create_routine with bot_id != Fleet bot → 422."""

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from grokbot_fleet.store import Store
from grokbot_fleet.jobs import JobManager
from grokbot_fleet.server import register_tools
from tests.conftest import (
    FLEET_BOT_ID,
    TEST_WEBHOOK_KEY,
    TEST_WEBHOOK_URL,
)


def _make_ok_response() -> httpx.Response:
    return httpx.Response(200, request=httpx.Request("POST", TEST_WEBHOOK_URL))


@pytest.fixture()
def fleet_mcp(store, job_manager):
    """An MCPServer with tools registered against the fixture store."""
    mcp = MCPServer("test-fleet")
    register_tools(mcp, store, job_manager, FLEET_BOT_ID)
    return mcp


async def test_create_routine_wrong_bot_id_raises_422(fleet_mcp: MCPServer) -> None:
    """create_routine with a bot_id that is NOT the Fleet bot must raise ToolError (422)."""
    tools = await fleet_mcp.list_tools()
    tool_names = [t.name for t in tools]
    assert "create_routine" in tool_names

    with pytest.raises(ToolError, match="422"):
        await fleet_mcp.call_tool(
            "create_routine",
            {"bot_id": "wrong-bot", "name": "test", "prompt": "test prompt"},
        )


async def test_pause_routine_wrong_bot_id_raises_422(fleet_mcp: MCPServer) -> None:
    with pytest.raises(ToolError, match="422"):
        await fleet_mcp.call_tool(
            "pause_routine",
            {"routine_id": "routine-1", "bot_id": "wrong-bot"},
        )


async def test_resume_routine_wrong_bot_id_raises_422(fleet_mcp: MCPServer) -> None:
    with pytest.raises(ToolError, match="422"):
        await fleet_mcp.call_tool(
            "resume_routine",
            {"routine_id": "routine-1", "bot_id": "wrong-bot"},
        )


async def test_create_routine_correct_bot_id_accepted(
    fleet_mcp: MCPServer,
    job_manager: JobManager,
) -> None:
    """create_routine with the correct Fleet bot_id should not raise 422."""
    with patch("grokbot_fleet.jobs.httpx.AsyncClient") as mock_cls:
        instance = AsyncMock()
        instance.post = AsyncMock(return_value=_make_ok_response())
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = instance

        job_manager._poll = AsyncMock(
            side_effect=lambda jid, **kw: {"status": "running", "job_id": jid}
        )

        result = await fleet_mcp.call_tool(
            "create_routine",
            {"bot_id": FLEET_BOT_ID, "name": "test routine", "prompt": "do things"},
        )
        assert result is not None
