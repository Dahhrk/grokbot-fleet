#!/usr/bin/env bash
set -euo pipefail

# grokbot-fleet setup — run this on the Grok Bot's computer.
# It clones the repo, installs deps, generates secrets, and starts the server.

REPO_URL="${GROKBOT_FLEET_REPO:-https://github.com/dahhrk/grokbot-fleet}"
INSTALL_DIR="${GROKBOT_FLEET_DIR:-$HOME/grokbot-fleet}"
STORE_ROOT="${STORE_ROOT:-/home/box/agent-data}"
PORT="${PORT:-8080}"

echo "=== grokbot-fleet setup ==="

# 1. Clone or pull
if [ -d "$INSTALL_DIR" ]; then
  echo "→ Updating existing install at $INSTALL_DIR"
  cd "$INSTALL_DIR"
  git pull --ff-only
else
  echo "→ Cloning $REPO_URL to $INSTALL_DIR"
  git clone "$REPO_URL" "$INSTALL_DIR"
  cd "$INSTALL_DIR"
fi

# 2. Install
echo "→ Installing dependencies"
pip install -e ".[dev]" --quiet

# 3. Generate secrets if .env doesn't exist
if [ ! -f .env ]; then
  echo "→ Generating .env with fresh secrets"
  MCP_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
  WEBHOOK_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

  cat > .env <<ENVEOF
MCP_TOKEN=$MCP_TOKEN
WEBHOOK_URL=
WEBHOOK_KEY=$WEBHOOK_KEY
STORE_ROOT=$STORE_ROOT
FLEET_BOT_ID=fleet
PORT=$PORT
ENVEOF

  echo ""
  echo "╔══════════════════════════════════════════════════════════════╗"
  echo "║  .env created. You still need to fill in WEBHOOK_URL.      ║"
  echo "║                                                            ║"
  echo "║  MCP_TOKEN (for plugin config): $MCP_TOKEN"
  echo "║                                                            ║"
  echo "║  Save this token — you'll need it when adding the plugin.  ║"
  echo "╚══════════════════════════════════════════════════════════════╝"
  echo ""
else
  echo "→ .env already exists, skipping secret generation"
fi

# 4. Verify store root exists
if [ -d "$STORE_ROOT" ]; then
  echo "→ Store root found at $STORE_ROOT"
else
  echo "⚠ Store root $STORE_ROOT does not exist yet (ok if Grok Bot creates it)"
fi

# 5. Run tests
echo "→ Running tests"
python3 -m pytest tests/ -v --tb=short || echo "⚠ Some tests failed (non-fatal for setup)"

echo ""
echo "=== Setup complete ==="
echo ""
echo "To start the server:"
echo "  cd $INSTALL_DIR && python -m grokbot_fleet"
echo ""
echo "To sync all bot profiles:"
echo "  Use the sync_profiles MCP tool with repo_root=$INSTALL_DIR"
echo ""
echo "Plugin config for Grok Bot Settings > Plugins:"
echo "  URL:  http://localhost:$PORT/mcp"
echo "  Auth: Bearer <MCP_TOKEN from .env>"
