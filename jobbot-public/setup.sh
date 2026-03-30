#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# JobBot — One-time setup script for macOS
# Run this once after cloning: bash setup.sh
# ─────────────────────────────────────────────────────────────────────────────

set -e

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
RESET="\033[0m"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOT_DIR="$SCRIPT_DIR"

echo ""
echo -e "${BOLD}🤖 JobBot — Setup${RESET}"
echo "────────────────────────────────────────"
echo ""

# ── 1. Check Python ───────────────────────────────────────────────────────
echo -e "${BOLD}[1/5] Checking Python...${RESET}"
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}❌ Python 3 not found. Install from https://www.python.org${RESET}"
    exit 1
fi
PYTHON=$(command -v python3)
PY_VER=$($PYTHON --version 2>&1)
echo -e "${GREEN}✅ Found: $PY_VER ($PYTHON)${RESET}"
echo ""

# ── 2. Install dependencies ────────────────────────────────────────────────
echo -e "${BOLD}[2/5] Installing Python dependencies...${RESET}"
$PYTHON -m pip install --upgrade pip -q
$PYTHON -m pip install -r "$BOT_DIR/requirements.txt" -q
echo -e "${GREEN}✅ Dependencies installed${RESET}"
echo ""

# ── 3. Set up .env ─────────────────────────────────────────────────────────
echo -e "${BOLD}[3/5] Checking .env configuration...${RESET}"
if [ ! -f "$BOT_DIR/.env" ]; then
    cp "$BOT_DIR/.env.template" "$BOT_DIR/.env"
    echo -e "${YELLOW}⚠️  Created .env from template — fill in your credentials via the setup wizard.${RESET}"
else
    echo -e "${GREEN}✅ .env exists${RESET}"
fi
echo ""

# ── 4. Create data directories ─────────────────────────────────────────────
echo -e "${BOLD}[4/5] Creating data directories...${RESET}"
mkdir -p "$BOT_DIR/data/jobs" "$BOT_DIR/data/applications" "$BOT_DIR/data/sent" "$BOT_DIR/logs" "$BOT_DIR/config"
echo -e "${GREEN}✅ Directories ready${RESET}"
echo ""

# ── 5. Install launchd scheduler (macOS auto-start on login) ───────────────
echo -e "${BOLD}[5/5] Setting up login-trigger scheduler...${RESET}"

PLIST_LABEL="com.jobbot.daily"
PLIST_DST="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"

mkdir -p "$LAUNCH_AGENTS_DIR"

# Write plist dynamically (avoids path substitution issues)
cat > "$PLIST_DST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON}</string>
        <string>${BOT_DIR}/run_daily.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${BOT_DIR}</string>

    <!-- Run once per day on first login -->
    <key>StartInterval</key>
    <integer>86400</integer>
    <key>RunAtLoad</key>
    <true/>

    <key>StandardOutPath</key>
    <string>${BOT_DIR}/logs/launchd_out.log</string>
    <key>StandardErrorPath</key>
    <string>${BOT_DIR}/logs/launchd_err.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
</dict>
</plist>
PLIST

# Unload if already loaded, then load fresh
launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load "$PLIST_DST"
echo -e "${GREEN}✅ Scheduler installed — bot will run on first login each day${RESET}"
echo ""

# ── Done ───────────────────────────────────────────────────────────────────
echo "────────────────────────────────────────"
echo -e "${BOLD}${GREEN}🎉 Setup complete!${RESET}"
echo ""
echo "Next steps:"
echo ""
echo "  1. Complete setup wizard (run this to open it):"
echo "     python3 $BOT_DIR/dashboard/server.py"
echo "     Then open: http://localhost:5555/setup"
echo ""
echo "  2. Or run the bot right now:"
echo "     python3 $BOT_DIR/run_daily.py"
echo ""
echo "  Dashboard will open at: http://localhost:5555"
echo ""
echo "  To stop the bot:"
echo "     launchctl unload ~/Library/LaunchAgents/${PLIST_LABEL}.plist"
echo ""
echo "  To check logs:"
echo "     tail -f $BOT_DIR/logs/runner.log"
echo "────────────────────────────────────────"
