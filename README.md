# grokbot-fleet

Open-source MCP server to list and update Grok Bots from Cursor (and Grok Bot plugins): names, prompts (descriptions), routines, user skills.

There is no official Grok Bot management API. This MCP is a bridge that runs on the Grok Bot's computer and mediates reads from the local file store and writes through a Fleet bot job inbox.

## Quick start

### One-shot setup (on the Grok Bot's computer)

```bash
git clone https://github.com/dahhrk/grokbot-fleet ~/grokbot-fleet
cd ~/grokbot-fleet
bash scripts/setup.sh
```

The script installs deps, generates secrets, and tells you what to do next.

### Add the plugin in Grok Bot

Settings > Plugins:
- **URL**: `http://localhost:8080/mcp`
- **Auth**: `Bearer <MCP_TOKEN from .env>`

### Sync all bot profiles

Once the MCP is running and the plugin is connected, tell any bot:

```
Use grokbot-fleet sync_profiles with repo_root=~/grokbot-fleet
```

All 7 profiles from `profiles/` get pushed in one call. No manual pasting.

### Sync routines

```
Use grokbot-fleet sync_routines with repo_root=~/grokbot-fleet
```

## How it works

```
profiles/              ← YAML files, one per bot (edit here)
routines/              ← YAML files, one per routine (edit here)
src/grokbot_fleet/
  server.py            ← MCP server with sync_profiles + sync_routines
  guardrails.py        ← pre-flight checks on every write
  store.py             ← reads from local agent data
  jobs.py              ← job inbox + webhook
scripts/
  setup.sh             ← one-shot install on Grok Bot computer
```

**Workflow:** edit a YAML file → `git push` → tell a bot to `sync_profiles` → done.

## Two secrets

| Secret | Purpose | Who holds it |
|---|---|---|
| `MCP_TOKEN` | Authenticates every MCP request (`Authorization: Bearer <MCP_TOKEN>`) | MCP clients (Cursor, plugins) |
| `WEBHOOK_KEY` | Authenticates the job-wake POST from fleet-mcp to the Fleet bot webhook | fleet-mcp server only |

Both are set as environment variables. Neither appears in git, logs, tool results, or bot descriptions. See [SECURITY.md](SECURITY.md) for threat model details.

## Tools

### Reads (local store, no webhook)

| Tool | Description |
|---|---|
| `list_bots` | List all Grok Bots visible on this computer |
| `get_bot(bot_id)` | Get details of a specific Grok Bot |
| `list_routines` | List routines (automations) |
| `list_skills` | List user skills (workflows) |
| `get_job(job_id)` | Get the status/result of a job |

### Writes (job inbox + webhook)

| Tool | Description |
|---|---|
| `create_bot(name, description)` | Create a new Grok Bot |
| `update_bot(bot_id, name?, description?)` | Update a bot's name and/or prompt |
| `create_routine(bot_id, name, prompt)` | Create a routine (Fleet-bot-local) |
| `pause_routine(routine_id, bot_id)` | Pause a routine (Fleet-bot-local) |
| `resume_routine(routine_id, bot_id)` | Resume a routine (Fleet-bot-local) |
| `write_skill(name, body)` | Write a user skill |

### Batch operations

| Tool | Description |
|---|---|
| `sync_profiles(repo_root)` | Push all `profiles/*.yaml` — creates or updates bots by name |
| `sync_routines(repo_root)` | Push all `routines/*.yaml` — creates routines on the Fleet bot |

### Guardrails

Every write passes through `guardrails.py` before hitting the job inbox:

| Guard | Blocks |
|---|---|
| `no-push-main` | Descriptions mentioning push to main/master or force push |
| `no-destructive-prod` | Descriptions mentioning destructive production actions |
| `fork-before-upstream` | Descriptions mentioning upstream without fork |
| `no-secrets-in-prompt` | Descriptions containing secret/token patterns (ghp_, sk-, etc.) |

Guardrails return 422 with a clear rejection message.

## Profile YAML format

```yaml
name: Harvey Specter
role: Chief of Staff
from: Suits
description: |
  You are Harvey Specter...
```

`name` is used to match against existing bots (case-insensitive). `role` and `from` are metadata. `description` becomes the bot's prompt.

## Routine YAML format

```yaml
name: Daily Standup
bot: harvey-specter
trigger: "Every day at 9:00 AM"
prompt: |
  You are running the daily standup...
```

`bot` is metadata (for your reference). Routines are created on the Fleet bot. `trigger` is metadata — set the actual trigger in Grok Bot after creation.

## Job inbox

Every mutating tool follows this write path:

1. Validate arguments; run guardrails
2. Write `jobs/<job_id>.json` with `status: "queued"` and the payload
3. POST webhook `{"v": 1, "job_id": "<uuid>"}` with `WEBHOOK_KEY`
4. Poll job file until `done`/`error` or 30 s timeout
5. Return result or `{"status": "running", "job_id": "..."}` so the client can `get_job` later

**One write at a time.** A second mutating call while a job is `queued` or `running` returns 409 (sync_profiles/sync_routines run sequentially internally).

## Development

```bash
pip install -e ".[dev]"
python3 -m pytest tests/ -v
```

Tests use a temporary fixture store and mock webhook calls — no live Grok Bot or webhook required.

## License

[MIT](LICENSE)
