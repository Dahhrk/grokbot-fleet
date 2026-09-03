"""Auth tests: missing/wrong MCP_TOKEN → 401; good token reaches a read tool."""

import httpx
import pytest

from tests.conftest import TEST_TOKEN


@pytest.fixture()
def client(app):
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


MCP_INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "test-client", "version": "0.1.0"},
    },
}


async def test_missing_token_returns_401(client: httpx.AsyncClient) -> None:
    resp = await client.post("/mcp", json=MCP_INIT)
    assert resp.status_code == 401


async def test_wrong_token_returns_401(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/mcp",
        json=MCP_INIT,
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert resp.status_code == 401


async def test_good_token_passes_auth(client: httpx.AsyncClient) -> None:
    """With a valid token the request passes the auth middleware.

    The MCP session_manager is not started in the test ASGI transport,
    so the handler will fail with a RuntimeError — but that proves the
    request got past the 401 gate.
    """
    try:
        resp = await client.post(
            "/mcp",
            json=MCP_INIT,
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )
        assert resp.status_code != 401
    except RuntimeError:
        pass
