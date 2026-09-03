# grokbot-fleet

Open-source MCP server to list and update Grok Bots from Cursor (and Grok Bot plugins): names, prompts (descriptions), routines, user skills.

There is no official Grok Bot management API. This MCP is a bridge that runs on the Grok Bot's computer and mediates reads from the local file store and writes through a Fleet bot job inbox.

## Two secrets

grokbot-fleet uses exactly two secrets. They serve different purposes and must never be mixed.

| Secret | Purpose | Who holds it |
|---|---|---|
| `MCP_TOKEN` | Authenticates every MCP request (`Authorization: Bearer <MCP_TOKEN>`) | MCP clients (Cursor, plugins) |
| `WEBHOOK_KEY` | Authenticates the job-wake POST from fleet-mcp to the Fleet bot webhook | fleet-mcp server only |

Both are set as environment variables. Neither appears in git, logs, tool results, or bot descriptions. See [SECURITY.md](SECURITY.md) for threat model details.

## Running the server (Streamable HTTP)

### Prerequisites

- Python >= 3.11
- A Grok Bot computer with agent data under `STORE_ROOT` (default `/home/box/agent-data`)
- A Fleet bot with a webhook routine (see [docs/FLEET-BOT.md](docs/FLEET-BOT.md) and [docs/WEBHOOK.md](docs/WEBHOOK.md))

### Install

```bash
pip install -e .
```

### Configure

Copy `.env.example` and fill in the values:

```bash
cp .env.example .env
```

Required environment variables:

| Variable | Description | Default |
|---|---|---|
| `MCP_TOKEN` | Bearer token for MCP client auth | *(required)* |
| `WEBHOOK_URL` | Fleet bot webhook endpoint URL | *(required)* |
| `WEBHOOK_KEY` | Shared secret for webhook auth | *(required)* |
| `STORE_ROOT` | Path to agent data directory | `/home/box/agent-data` |
| `FLEET_BOT_ID` | ID of the Fleet bot in the store | `fleet` |
| `PORT` | Server listen port | `8080` |

### Start

```bash
python -m grokbot_fleet
```

The server binds `0.0.0.0` on the configured port. The MCP endpoint is at `/mcp`.

## Pointing a Grok Bot plugin (or Cursor)

Configure your MCP client with:

- **URL**: `http://<host>:<port>/mcp`
- **Authorization header**: `Bearer <MCP_TOKEN>`

The transport is Streamable HTTP. The server responds to standard MCP `initialize`, `tools/list`, and `tools/call` requests.

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

Routine tools require `bot_id` to match the Fleet bot ID (422 otherwise).

## Job inbox

Every mutating tool follows this write path:

1. Validate arguments; reject unknown fields
2. Write `jobs/<job_id>.json` with `status: "queued"` and the payload
3. POST webhook `{"v": 1, "job_id": "<uuid>"}` with `WEBHOOK_KEY` (both `Authorization: Bearer` and `X-Automation-Key` headers)
4. Poll job file until `done`/`error` or 30 s timeout
5. Return result or `{"status": "running", "job_id": "..."}` so the client can `get_job` later

**One write at a time.** A second mutating call while a job is `queued` or `running` returns 409.

The webhook body is intentionally tiny and carries no payload — the Fleet bot reads the full job from the file. `job_id` of `"probe"` is ignored by the Fleet bot (health check).

### Job file schema

```json
{
  "v": 1,
  "job_id": "<uuid>",
  "status": "queued | running | done | error",
  "action": "create_bot | update_bot | create_routine | pause_routine | resume_routine | write_skill",
  "created_at": "<ISO-8601>",
  "payload": {},
  "result": null,
  "error": null
}
```

## Fleet-bot-local routines

`create_routine`, `pause_routine`, and `resume_routine` only operate on the Fleet bot. Passing any other `bot_id` returns 422. This is by design — routines belong to the bot that executes them.

## Error codes

| Code | Meaning |
|---|---|
| 401 | Missing or invalid `MCP_TOKEN` |
| 404 | Bot, job, skill, or routine not found |
| 409 | Another write is in progress |
| 422 | Validation error (wrong bot_id, bot cap reached, etc.) |
| 503 | Webhook unreachable or host refused |

## Development

```bash
pip install -e ".[dev]"
python3 -m pytest tests/ -v
```

Tests use a temporary fixture store and mock webhook calls — no live Grok Bot or webhook required.

## License

[MIT](LICENSE)
