#!/bin/bash
# install_launchd_jobs.sh — 幫 tw-stock-daily-tracker 產生並載入 launchd 排程（精簡 3 次/天）
#
# 用法：
#   bash scripts/install_launchd_jobs.sh
#
# 會做的事：
#   1. 在 ~/Library/LaunchAgents/ 產生 3 個 plist（盤前1、盤中1、收盤總結1）
#   2. 每個 plist 以 --dangerously-skip-permissions 執行 claude，讓背景排程不需人工核准即可
#      上網、curl TWSE、寫入 Obsidian vault（headless 無人能按同意，故略過權限提示）
#   3. 用 launchctl load 載入每一個
#
# 卸載的話用：
#   bash scripts/install_launchd_jobs.sh --uninstall
#
# ⚠️ 每個 plist 觸發的 prompt 只是「請 Claude Code 執行 tw-stock-daily-tracker skill 的某個階段」，
#    實際會不會做事（例如今天是不是交易日）由 skill 內部邏輯判斷，plist 本身不做這層過濾。

set -euo pipefail

LABEL_PREFIX="com.pasteur.tw-stock-tracker"
PLIST_DIR="$HOME/Library/LaunchAgents"
CLAUDE_BIN="$(command -v claude || echo "$HOME/.local/bin/claude")"
LOG_DIR="$HOME/Library/Logs/tw-stock-tracker"

mkdir -p "$PLIST_DIR" "$LOG_DIR"

# 精簡版排程（3 次/天），最省用量：盤前選股→盤中一次追蹤→收盤總結。
# 格式："HHMM:phase"
SLOTS=(
  "0850:premarket"
  "1200:update"
  "1335:close_summary"
)

uninstall() {
  echo "卸載 tw-stock-tracker 排程..."
  # 用 glob 掃掉所有 ${LABEL_PREFIX}.* 的 plist（含舊版留下的時段），避免遺留孤兒排程
  shopt -s nullglob
  for plist in "$PLIST_DIR/${LABEL_PREFIX}."*.plist; do
    launchctl unload "$plist" 2>/dev/null || true
    rm -f "$plist"
    echo "  移除 $(basename "$plist" .plist)"
  done
  shopt -u nullglob
  echo "完成。"
  exit 0
}

if [ "${1:-}" == "--uninstall" ]; then
  uninstall
fi

# launchd 不會讀 ~/.zshrc，所以要把 vault 路徑直接寫進 plist
: "${TW_STOCK_INVESTING_DIR:?請先設定 TW_STOCK_INVESTING_DIR（Obsidian vault 中 Investing 資料夾的路徑）}"
# 路徑加了引號時 "~" 不會被展開，這裡手動換成 $HOME
TW_STOCK_INVESTING_DIR="${TW_STOCK_INVESTING_DIR/#\~/$HOME}"

for slot in "${SLOTS[@]}"; do
  hhmm="${slot%%:*}"
  phase="${slot##*:}"
  hour="${hhmm:0:2}"
  minute="${hhmm:2:2}"
  # 去掉開頭 0，避免被當成八進位數字解析錯誤（例如 08 -> 使用時記得去 leading zero）
  hour_dec=$((10#$hour))
  minute_dec=$((10#$minute))

  label="${LABEL_PREFIX}.${hhmm}"
  plist="$PLIST_DIR/${label}.plist"
  prompt="請執行 tw-stock-daily-tracker skill，phase=${phase}，time_label=${hhmm}。若今天不是台股交易日請依 skill 說明直接跳過。"

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
  echo "已安裝並載入：${label}（每天 ${hour}:${minute}，phase=${phase}）"
done

echo ""
echo "全部 ${#SLOTS[@]} 個排程安裝完成。用以下指令確認："
echo "  launchctl list | grep tw-stock-tracker"
echo ""
echo "log 檔案位置：${LOG_DIR}/"
