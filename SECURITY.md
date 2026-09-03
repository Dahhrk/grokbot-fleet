# Security

grokbot-fleet uses two secrets. They serve different roles, and mixing them defeats the security model.

## MCP_TOKEN

**What it protects:** every MCP request. Any client that presents a valid `MCP_TOKEN` can list bots, read prompts, create bots, rewrite any bot's prompt, create routines, and write skills.

**If stolen:** the attacker has root over every bot managed by this Fleet instance. They can rewrite every bot prompt, create routines, and inject user skills. Rotate immediately: generate a new token, update all authorized clients, and restart the server.

**Where it lives:** environment variable on the server. Never in git, never in logs, never in tool results, never in bot descriptions.

## WEBHOOK_KEY

**What it protects:** the webhook POST from fleet-mcp to the Fleet bot. The key is sent in two headers: `Authorization: Bearer <WEBHOOK_KEY>` and `X-Automation-Key: <WEBHOOK_KEY>`.

**If stolen (without filesystem access):** the attacker can only wake the Fleet bot with arbitrary `job_id` values. If there is no matching `jobs/<job_id>.json` file on disk, the Fleet bot reads nothing and stops. The attacker cannot inject payload because the webhook body is `{"v": 1, "job_id": "<uuid>"}` only — the payload lives in the job file.

**If stolen (with filesystem access):** the attacker can write a crafted job file and then wake the Fleet bot to execute it. This is equivalent to having shell access on the Grok Bot computer, which is already a full compromise.

**Where it lives:** environment variable on the server. Never in git, never in logs, never in tool results, never in bot descriptions.

## Never mix the two secrets

- `MCP_TOKEN` faces MCP clients (Cursor, plugins). It gates who can issue commands.
- `WEBHOOK_KEY` faces the Fleet bot webhook. It gates who can wake the Fleet bot.

Using the same value for both means a compromised MCP client can also wake the Fleet bot directly, bypassing the job inbox.

## Nothing secret in git, logs, or tool results

- `.env.example` contains empty placeholders only.
- The server never logs either secret.
- Tool results never contain either secret.
- Bot descriptions written by Fleet never contain either secret.
- Job files contain the payload (names, prompts) but never the secrets.
