#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# JobBot — One-click launcher
# Double-click from Desktop, Dock, or Finder to start JobBot.
# ─────────────────────────────────────────────────────────────────────────────

# Resolve the jobbot-public directory relative to this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOT_DIR="$SCRIPT_DIR"

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
RESET="\033[0m"

echo ""
echo -e "${BOLD}🤖 JobBot — Starting...${RESET}"
echo "────────────────────────────────────────"

# ── Check Python ──────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}❌ Python 3 not found.${RESET}"
    echo "   Please install Python 3 from https://www.python.org and re-run this."
    read -p "Press Enter to close..."
    exit 1
fi
PYTHON=$(command -v python3)

# ── Check dependencies (fast — only installs if something is missing) ─────────
echo -e "${BOLD}Checking dependencies...${RESET}"
$PYTHON -m pip install -r "$BOT_DIR/requirements.txt" -q --disable-pip-version-check
echo -e "${GREEN}✅ Dependencies ready${RESET}"
echo ""

# ── Kill any existing server on port 5555 ─────────────────────────────────────
EXISTING=$(lsof -ti :5555 2>/dev/null)
if [ -n "$EXISTING" ]; then
    echo -e "${YELLOW}⚠️  Restarting existing JobBot server...${RESET}"
    kill "$EXISTING" 2>/dev/null
    sleep 1
fi

# ── Start the dashboard server in the background ─────────────────────────────
echo -e "${BOLD}Starting dashboard...${RESET}"
cd "$BOT_DIR"
$PYTHON dashboard/server.py &
SERVER_PID=$!

# ── Wait for server to be ready (up to 10 seconds) ───────────────────────────
echo -n "Waiting for server"
for i in {1..20}; do
    if curl -s http://localhost:5555 > /dev/null 2>&1; then
        echo ""
        echo -e "${GREEN}✅ Server is up${RESET}"
        break
    fi
    echo -n "."
    sleep 0.5
done
echo ""

# ── Check if setup has been completed ─────────────────────────────────────────
if [ ! -f "$BOT_DIR/data/profile.json" ]; then
    echo -e "${YELLOW}👋 First time? Opening setup wizard...${RESET}"
    open "http://localhost:5555/setup"
else
    echo -e "${GREEN}Opening dashboard...${RESET}"
    open "http://localhost:5555"
fi

echo ""
echo "────────────────────────────────────────"
echo -e "${BOLD}JobBot is running.${RESET}"
echo ""
echo "  Dashboard: http://localhost:5555"
echo "  To stop:   close this window or press Ctrl+C"
echo "────────────────────────────────────────"
echo ""

# Keep terminal open so the server stays alive (closing window = stops server)
wait $SERVER_PID
