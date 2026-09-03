import json
from pathlib import Path


class Store:
    """Read-only access to the Grok Bot local file store."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def list_bots(self) -> list[dict]:
        agents_dir = self.root / "agents"
        if not agents_dir.is_dir():
            return []
        bots: list[dict] = []
        for agent_dir in sorted(agents_dir.iterdir()):
            profile = agent_dir / "profile.json"
            if profile.is_file():
                bots.append(json.loads(profile.read_text()))
        return bots

    def get_bot(self, bot_id: str) -> dict | None:
        profile = self.root / "agents" / bot_id / "profile.json"
        if not profile.is_file():
            return None
        return json.loads(profile.read_text())

    def list_routines(self) -> list[dict]:
        auto_dir = self.root / "automations"
        if not auto_dir.is_dir():
            return []
        routines: list[dict] = []
        for f in sorted(auto_dir.iterdir()):
            if f.suffix == ".json" and f.is_file():
                routines.append(json.loads(f.read_text()))
        return routines

    def list_skills(self) -> list[dict]:
        wf_dir = self.root / "workflows"
        if not wf_dir.is_dir():
            return []
        skills: list[dict] = []
        for f in sorted(wf_dir.iterdir()):
            if f.suffix == ".json" and f.is_file():
                data = json.loads(f.read_text())
                if data.get("type") == "user":
                    skills.append(data)
        return skills

    def get_job(self, job_id: str) -> dict | None:
        if job_id == "probe":
            return None
        job_path = self.root / "jobs" / f"{job_id}.json"
        if not job_path.is_file():
            return None
        return json.loads(job_path.read_text())

    def bot_count(self) -> int:
        agents_dir = self.root / "agents"
        if not agents_dir.is_dir():
            return 0
        return sum(
            1
            for d in agents_dir.iterdir()
            if (d / "profile.json").is_file()
        )
