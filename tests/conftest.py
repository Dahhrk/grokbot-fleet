import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from grokbot_fleet.store import Store
from grokbot_fleet.jobs import JobManager
from grokbot_fleet.server import create_app


TEST_TOKEN = "test-mcp-token-xyz"
TEST_WEBHOOK_KEY = "test-webhook-key-abc"
TEST_WEBHOOK_URL = "https://webhook.test/fleet"
FLEET_BOT_ID = "fleet-bot"


@pytest.fixture()
def store_root(tmp_path: Path) -> Path:
    """Create a fixture store with sample data."""
    agents = tmp_path / "agents"

    bot1_dir = agents / "bot-1"
    bot1_dir.mkdir(parents=True)
    (bot1_dir / "profile.json").write_text(json.dumps({
        "id": "bot-1",
        "name": "Helper",
        "description": "A helpful bot",
    }))

    fleet_dir = agents / FLEET_BOT_ID
    fleet_dir.mkdir(parents=True)
    (fleet_dir / "profile.json").write_text(json.dumps({
        "id": FLEET_BOT_ID,
        "name": "Fleet",
        "description": "Fleet management bot",
    }))

    auto_dir = tmp_path / "automations"
    auto_dir.mkdir()
    (auto_dir / "routine-1.json").write_text(json.dumps({
        "id": "routine-1",
        "bot_id": FLEET_BOT_ID,
        "name": "Daily cleanup",
        "prompt": "Clean up old jobs",
        "status": "active",
    }))

    wf_dir = tmp_path / "workflows"
    wf_dir.mkdir()
    (wf_dir / "skill-1.json").write_text(json.dumps({
        "id": "skill-1",
        "name": "Web search",
        "body": "Search the web for information",
        "type": "user",
    }))
    (wf_dir / "skill-system.json").write_text(json.dumps({
        "id": "skill-system",
        "name": "Core runtime",
        "body": "internal",
        "type": "system",
    }))

    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()

    return tmp_path


@pytest.fixture()
def store(store_root: Path) -> Store:
    return Store(store_root)


@pytest.fixture()
def job_manager(store_root: Path) -> JobManager:
    return JobManager(store_root, TEST_WEBHOOK_URL, TEST_WEBHOOK_KEY)


@pytest.fixture()
def app(store_root: Path):
    """ASGI app wired to the temp fixture store."""
    return create_app(
        mcp_token=TEST_TOKEN,
        webhook_url=TEST_WEBHOOK_URL,
        webhook_key=TEST_WEBHOOK_KEY,
        store_root=str(store_root),
        fleet_bot_id=FLEET_BOT_ID,
    )
