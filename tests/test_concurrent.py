"""Concurrent write (409) tests: second mutate while queued/running → ConcurrentWriteError."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from grokbot_fleet.jobs import ConcurrentWriteError, JobManager
from tests.conftest import TEST_WEBHOOK_URL


def _make_ok_response() -> httpx.Response:
    return httpx.Response(200, request=httpx.Request("POST", TEST_WEBHOOK_URL))


async def test_409_second_mutate_while_queued(
    job_manager: JobManager,
    store_root: Path,
) -> None:
    """A second submit while the first job is still queued must raise ConcurrentWriteError."""

    with patch("grokbot_fleet.jobs.httpx.AsyncClient") as mock_cls:
        instance = AsyncMock()
        instance.post = AsyncMock(return_value=_make_ok_response())
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = instance

        # First submit: override poll so the job stays "queued" (poll returns running)
        job_manager._poll = AsyncMock(
            side_effect=lambda jid, **kw: {"status": "running", "job_id": jid}
        )

        first = await job_manager.submit(
            "create_bot",
            {"name": "Bot1", "description": "first"},
        )
        assert first["status"] == "running"

        # The job file is still queued on disk
        job_path = store_root / "jobs" / f"{first['job_id']}.json"
        job_data = json.loads(job_path.read_text())
        assert job_data["status"] == "queued"

        # Second submit must fail with ConcurrentWriteError
        with pytest.raises(ConcurrentWriteError):
            await job_manager.submit(
                "update_bot",
                {"bot_id": "bot-1", "name": "Renamed"},
            )


async def test_409_second_mutate_while_running(
    job_manager: JobManager,
    store_root: Path,
) -> None:
    """A second submit while the first job is running must raise ConcurrentWriteError."""

    with patch("grokbot_fleet.jobs.httpx.AsyncClient") as mock_cls:
        instance = AsyncMock()
        instance.post = AsyncMock(return_value=_make_ok_response())
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = instance

        job_manager._poll = AsyncMock(
            side_effect=lambda jid, **kw: {"status": "running", "job_id": jid}
        )

        first = await job_manager.submit(
            "write_skill",
            {"name": "Skill1", "body": "do stuff"},
        )

        # Manually set job to "running" (as if Fleet bot picked it up)
        job_path = store_root / "jobs" / f"{first['job_id']}.json"
        job_data = json.loads(job_path.read_text())
        job_data["status"] = "running"
        job_path.write_text(json.dumps(job_data))

        with pytest.raises(ConcurrentWriteError):
            await job_manager.submit(
                "create_bot",
                {"name": "Bot2", "description": "second"},
            )


async def test_allows_new_write_after_done(
    job_manager: JobManager,
    store_root: Path,
) -> None:
    """After a job completes (done), a new write must be allowed."""

    with patch("grokbot_fleet.jobs.httpx.AsyncClient") as mock_cls:
        instance = AsyncMock()
        instance.post = AsyncMock(return_value=_make_ok_response())
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = instance

        job_manager._poll = AsyncMock(
            side_effect=lambda jid, **kw: {"status": "running", "job_id": jid}
        )

        first = await job_manager.submit(
            "create_bot",
            {"name": "Bot1", "description": "first"},
        )

        # Mark first job as done
        job_path = store_root / "jobs" / f"{first['job_id']}.json"
        job_data = json.loads(job_path.read_text())
        job_data["status"] = "done"
        job_data["result"] = {"id": "new-bot-1"}
        job_path.write_text(json.dumps(job_data))

        # Second submit should succeed (no ConcurrentWriteError)
        second = await job_manager.submit(
            "create_bot",
            {"name": "Bot2", "description": "second"},
        )
        assert second["job_id"] != first["job_id"]
