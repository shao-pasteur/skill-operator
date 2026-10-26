#!/bin/bash
# install_launchd_jobs.sh — create and load launchd jobs for tw-stock-daily-tracker (lean schedule, 3 runs a day)
#
# Usage:
#   bash scripts/install_launchd_jobs.sh
#
# What it does:
#   1. Creates 3 plists in ~/Library/LaunchAgents/ (1 pre-market, 1 intraday, 1 closing summary)
#   2. Each plist runs claude with --dangerously-skip-permissions so background runs can browse,
#      curl TWSE and write to the Obsidian vault without approval (nobody is there to approve headless runs)
#   3. Loads each one with launchctl load
#
# To uninstall:
#   bash scripts/install_launchd_jobs.sh --uninstall
#
# ⚠️ Each plist only prompts Claude Code to run one phase of the tw-stock-daily-tracker skill;
#    the skill itself decides whether to do anything (for example whether today is a trading day).

set -euo pipefail

LABEL_PREFIX="com.pasteur.tw-stock-tracker"
PLIST_DIR="$HOME/Library/LaunchAgents"
CLAUDE_BIN="$(command -v claude || echo "$HOME/.local/bin/claude")"
LOG_DIR="$HOME/Library/Logs/tw-stock-tracker"

mkdir -p "$PLIST_DIR" "$LOG_DIR"

# Lean schedule (3 runs a day) to keep usage low: pre-market picks → one intraday check → closing summary.
# Format: "HHMM:phase"
SLOTS=(
  "0850:premarket"
  "1200:update"
  "1335:close_summary"
)

uninstall() {
  echo "Uninstalling the tw-stock-tracker jobs..."
  # Glob every ${LABEL_PREFIX}.* plist (including slots left by older versions) so no orphan jobs remain
  shopt -s nullglob
  for plist in "$PLIST_DIR/${LABEL_PREFIX}."*.plist; do
    launchctl unload "$plist" 2>/dev/null || true
    rm -f "$plist"
    echo "  removed $(basename "$plist" .plist)"
  done
  shopt -u nullglob
  echo "Done."
  exit 0
}

if [ "${1:-}" == "--uninstall" ]; then
  uninstall
fi

# launchd does not read ~/.zshrc, so the vault path goes straight into each plist
: "${TW_STOCK_INVESTING_DIR:?set TW_STOCK_INVESTING_DIR (the path of the Investing folder in your Obsidian vault) first}"
# A quoted path keeps "~" unexpanded, so replace it with $HOME here
TW_STOCK_INVESTING_DIR="${TW_STOCK_INVESTING_DIR/#\~/$HOME}"

for slot in "${SLOTS[@]}"; do
  hhmm="${slot%%:*}"
  phase="${slot##*:}"
  hour="${hhmm:0:2}"
  minute="${hhmm:2:2}"
  # Strip the leading zero so values like 08 are not parsed as octal
  hour_dec=$((10#$hour))
  minute_dec=$((10#$minute))

  label="${LABEL_PREFIX}.${hhmm}"
  plist="$PLIST_DIR/${label}.plist"
  prompt="Run the tw-stock-daily-tracker skill, phase=${phase}, time_label=${hhmm}. If today is not a Taiwan stock trading day, skip as the skill describes."

  cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${CLAUDE_BIN}</string>
        <string>-p</string>
        <string>--dangerously-skip-permissions</string>
        <string>${prompt}</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>TW_STOCK_INVESTING_DIR</key>
        <string>${TW_STOCK_INVESTING_DIR}</string>
    </dict>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>${hour_dec}</integer>
        <key>Minute</key>
        <integer>${minute_dec}</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/${hhmm}_${phase}.out.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/${hhmm}_${phase}.err.log</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
EOF

  launchctl unload "$plist" 2>/dev/null || true
  launchctl load "$plist"
  echo "Installed and loaded: ${label} (daily at ${hour}:${minute}, phase=${phase})"
done

echo ""
echo "All ${#SLOTS[@]} jobs installed. Check them with:"
echo "  launchctl list | grep tw-stock-tracker"
echo ""
echo "Log files: ${LOG_DIR}/"
