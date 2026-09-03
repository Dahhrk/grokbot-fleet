import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx


class ConcurrentWriteError(Exception):
    """Raised when a second mutating operation is attempted while one is active."""


class WebhookError(Exception):
    """Raised when the webhook POST fails (unreachable, timeout, non-2xx)."""

    def __init__(self, detail: str = "webhook unreachable") -> None:
        self.detail = detail
        super().__init__(detail)


class ValidationError(Exception):
    """Raised on invalid tool arguments."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


VALID_ACTIONS = frozenset({
    "create_bot",
    "update_bot",
    "create_routine",
    "pause_routine",
    "resume_routine",
    "write_skill",
})


class JobManager:
    """Manages the job inbox: write → webhook → poll."""

    def __init__(
        self,
        store_root: str | Path,
        webhook_url: str,
        webhook_key: str,
    ) -> None:
        self.store_root = Path(store_root)
        self.jobs_dir = self.store_root / "jobs"
        self.webhook_url = webhook_url
        self.webhook_key = webhook_key
        self._active_job_id: str | None = None
        self._lock = asyncio.Lock()

    def _read_job(self, job_id: str) -> dict | None:
        path = self.jobs_dir / f"{job_id}.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text())

    def _write_job(self, job: dict) -> None:
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        path = self.jobs_dir / f"{job['job_id']}.json"
        path.write_text(json.dumps(job, indent=2))

    async def submit(self, action: str, payload: dict) -> dict:
        if action not in VALID_ACTIONS:
            raise ValidationError(f"unknown action: {action}")

        async with self._lock:
            if self._active_job_id is not None:
                active = self._read_job(self._active_job_id)
                if active and active["status"] in ("queued", "running"):
                    raise ConcurrentWriteError()
                self._active_job_id = None

            job_id = str(uuid.uuid4())
            job = {
                "v": 1,
                "job_id": job_id,
                "status": "queued",
                "action": action,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "payload": payload,
                "result": None,
                "error": None,
            }
            self._write_job(job)
            self._active_job_id = job_id

        try:
            await self._post_webhook(job_id)
        except WebhookError:
            job["status"] = "error"
            job["error"] = "webhook unreachable"
            self._write_job(job)
            async with self._lock:
                if self._active_job_id == job_id:
                    self._active_job_id = None
            raise

        return await self._poll(job_id)

    async def _post_webhook(self, job_id: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(8.0)) as client:
                resp = await client.post(
                    self.webhook_url,
                    json={"v": 1, "job_id": job_id},
                    headers={
                        "Authorization": f"Bearer {self.webhook_key}",
                        "X-Automation-Key": self.webhook_key,
                        "Content-Type": "application/json",
                    },
                )
                if not (200 <= resp.status_code < 300):
                    raise WebhookError(f"webhook returned {resp.status_code}")
        except httpx.HTTPError as exc:
            raise WebhookError(str(exc)) from exc

    async def _poll(self, job_id: str, timeout: float = 30.0) -> dict:
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            job = self._read_job(job_id)
            if job and job["status"] in ("done", "error"):
                async with self._lock:
                    if self._active_job_id == job_id:
                        self._active_job_id = None
                return job
            await asyncio.sleep(0.5)
        return {"status": "running", "job_id": job_id}
