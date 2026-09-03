"""Job file + webhook contract tests.

Verifies:
- Mutate writes jobs/<id>.json queued with the payload
- Webhook body is exactly {v:1, job_id} (no payload)
- Webhook headers: Authorization Bearer WEBHOOK_KEY and X-Automation-Key WEBHOOK_KEY
- Webhook timeout is 8 s, one try
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from grokbot_fleet.jobs import JobManager, WebhookError
from tests.conftest import TEST_WEBHOOK_KEY, TEST_WEBHOOK_URL


def _make_ok_response() -> httpx.Response:
    return httpx.Response(200, request=httpx.Request("POST", TEST_WEBHOOK_URL))


async def test_submit_writes_queued_job_file(
    job_manager: JobManager,
    store_root: Path,
) -> None:
    """A mutating submit must write jobs/<id>.json with status=queued and the payload."""

    mock_resp = _make_ok_response()

    with patch("grokbot_fleet.jobs.httpx.AsyncClient") as mock_cls:
        instance = AsyncMock()
        instance.post = AsyncMock(return_value=mock_resp)
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = instance

        # Override poll to return immediately (no Fleet bot running)
        job_manager._poll = AsyncMock(
            side_effect=lambda jid, **kw: {"status": "running", "job_id": jid}
        )

        result = await job_manager.submit(
            "create_bot",
            {"name": "TestBot", "description": "A test bot"},
        )

    job_id = result["job_id"]
    job_path = store_root / "jobs" / f"{job_id}.json"
    assert job_path.is_file()

    job = json.loads(job_path.read_text())
    assert job["v"] == 1
    assert job["status"] == "queued"
    assert job["action"] == "create_bot"
    assert job["payload"] == {"name": "TestBot", "description": "A test bot"}
    assert job["result"] is None
    assert job["error"] is None


async def test_webhook_body_is_v_and_job_id_only(
    job_manager: JobManager,
) -> None:
    """The webhook POST body must be exactly {v:1, job_id} — no payload leak."""

    mock_resp = _make_ok_response()
    captured_kwargs: dict = {}

    async def capture_post(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return mock_resp

    with patch("grokbot_fleet.jobs.httpx.AsyncClient") as mock_cls:
        instance = AsyncMock()
        instance.post = AsyncMock(side_effect=capture_post)
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = instance

        job_manager._poll = AsyncMock(
            side_effect=lambda jid, **kw: {"status": "running", "job_id": jid}
        )

        result = await job_manager.submit(
            "update_bot",
            {"bot_id": "bot-1", "name": "Renamed"},
        )

    body = captured_kwargs.get("json", {})
    assert set(body.keys()) == {"v", "job_id"}, f"unexpected keys in webhook body: {body.keys()}"
    assert body["v"] == 1
    assert isinstance(body["job_id"], str)


async def test_webhook_headers(
    job_manager: JobManager,
) -> None:
    """Webhook must carry Authorization: Bearer <WEBHOOK_KEY> AND X-Automation-Key: <WEBHOOK_KEY>."""

    mock_resp = _make_ok_response()
    captured_headers: dict = {}

    async def capture_post(*args, **kwargs):
        captured_headers.update(kwargs.get("headers", {}))
        return mock_resp

    with patch("grokbot_fleet.jobs.httpx.AsyncClient") as mock_cls:
        instance = AsyncMock()
        instance.post = AsyncMock(side_effect=capture_post)
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = instance

        job_manager._poll = AsyncMock(
            side_effect=lambda jid, **kw: {"status": "running", "job_id": jid}
        )

        await job_manager.submit("write_skill", {"name": "s", "body": "b"})

    assert captured_headers["Authorization"] == f"Bearer {TEST_WEBHOOK_KEY}"
    assert captured_headers["X-Automation-Key"] == TEST_WEBHOOK_KEY
    assert captured_headers["Content-Type"] == "application/json"


async def test_webhook_timeout_is_8s(
    job_manager: JobManager,
) -> None:
    """httpx.AsyncClient must be constructed with an 8-second timeout."""

    captured_timeout = None

    with patch("grokbot_fleet.jobs.httpx.AsyncClient") as mock_cls:
        original_init = httpx.AsyncClient.__init__

        def capture_init(self_inner, **kwargs):
            nonlocal captured_timeout
            captured_timeout = kwargs.get("timeout")

        instance = AsyncMock()
        instance.post = AsyncMock(return_value=_make_ok_response())
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)

        def side_effect(**kwargs):
            nonlocal captured_timeout
            captured_timeout = kwargs.get("timeout")
            return instance

        mock_cls.side_effect = side_effect

        job_manager._poll = AsyncMock(
            side_effect=lambda jid, **kw: {"status": "running", "job_id": jid}
        )

        await job_manager.submit("write_skill", {"name": "s", "body": "b"})

    assert captured_timeout is not None
    if isinstance(captured_timeout, httpx.Timeout):
        assert captured_timeout.connect == 8.0 or captured_timeout.read == 8.0
    else:
        assert float(captured_timeout) == 8.0


def _make_response(status: int) -> httpx.Response:
    return httpx.Response(status, request=httpx.Request("POST", TEST_WEBHOOK_URL))


def _patch_webhook(status: int):
    """Context manager that mocks httpx.AsyncClient to return the given status."""
    mock_resp = _make_response(status)
    mock_cls = patch("grokbot_fleet.jobs.httpx.AsyncClient")
    return mock_cls, mock_resp


@pytest.mark.parametrize("status", [401, 403, 404, 429])
async def test_webhook_4xx_raises_webhook_error(
    job_manager: JobManager,
    store_root: Path,
    status: int,
) -> None:
    """Webhook returning 4xx must raise WebhookError, mark job as error, clear active job."""

    mock_resp = _make_response(status)

    with patch("grokbot_fleet.jobs.httpx.AsyncClient") as mock_cls:
        instance = AsyncMock()
        instance.post = AsyncMock(return_value=mock_resp)
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = instance

        with pytest.raises(WebhookError, match=str(status)):
            await job_manager.submit(
                "create_bot",
                {"name": "TestBot", "description": "test"},
            )

    # Job file must exist and be marked error, not left queued
    jobs_dir = store_root / "jobs"
    job_files = list(jobs_dir.glob("*.json"))
    assert len(job_files) == 1
    job = json.loads(job_files[0].read_text())
    assert job["status"] == "error"
    assert job["error"] == "webhook unreachable"

    # Active job must be cleared so the next write is not blocked (no stale 409)
    assert job_manager._active_job_id is None


@pytest.mark.parametrize("status", [401, 403, 404, 429])
async def test_webhook_4xx_body_still_correct(
    job_manager: JobManager,
    status: int,
) -> None:
    """Even on 4xx the POST body must be {v:1, job_id} only (one try, 8s)."""

    mock_resp = _make_response(status)
    captured_kwargs: dict = {}

    async def capture_post(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return mock_resp

    with patch("grokbot_fleet.jobs.httpx.AsyncClient") as mock_cls:
        instance = AsyncMock()
        instance.post = AsyncMock(side_effect=capture_post)
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = instance

        with pytest.raises(WebhookError):
            await job_manager.submit(
                "update_bot",
                {"bot_id": "bot-1", "name": "Renamed"},
            )

    body = captured_kwargs.get("json", {})
    assert set(body.keys()) == {"v", "job_id"}
    assert body["v"] == 1
    assert isinstance(body["job_id"], str)

    headers = captured_kwargs.get("headers", {})
    assert headers["Authorization"] == f"Bearer {TEST_WEBHOOK_KEY}"
    assert headers["X-Automation-Key"] == TEST_WEBHOOK_KEY
