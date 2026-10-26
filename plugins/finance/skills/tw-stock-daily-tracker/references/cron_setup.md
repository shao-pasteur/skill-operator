# 排程設定

這個 skill 本身不會「一直跑」，需要靠 macOS 的排程機制在固定時間點呼叫 `claude -p "..."` 來觸發每一次執行。

## 建議排程時間表

| 時間 | phase | 說明 |
|---|---|---|
| 08:50 | `premarket` | 開盤前簡報：選股、算基準布林通道 |
| 09:00 ~ 12:00（每 30 分） | `update` | 盤中動態更新，共 7 次 |
| 12:30, 13:00, 13:25 | `close_watch` | 收盤前賣點追蹤，共 3 次 |
| 13:35 | `close_summary` | 收盤總結 |

台股交易時間是 09:00–13:30，所以 13:25 是最後一次盤中快照，13:35 抓收盤後的資料做總結。

## 方式 A：launchd（推薦，macOS 原生排程）

直接執行安裝腳本，會自動產生 12 個 plist 並載入：

```bash
cd ~/path/to/tw-stock-daily-tracker   # 換成 skill 實際安裝的路徑
bash scripts/install_launchd_jobs.sh
```

確認排程是否載入成功：

```bash
launchctl list | grep tw-stock-tracker
```

log 檔案會寫在 `~/Library/Logs/tw-stock-tracker/`，每個時段各自獨立的 `.out.log` / `.err.log`，方便排查某個時段執行失敗的原因。

卸載全部排程：

```bash
bash scripts/install_launchd_jobs.sh --uninstall
```

**注意事項：**
- launchd 是每天都會觸發（含週末），是否為交易日的判斷交給 skill 內部邏輯處理（非交易日會自己跳過、只寫一行 log）。這樣設計比在 plist 裡塞星期幾邏輯簡單很多。
- 電腦在排程時間必須是開機且沒有睡眠。如果會讓 Mac 睡眠，建議搭配「電源與電池」設定裡的排定啟動，或用 `pmset` 設定喚醒時間。
- 從舊版（路徑寫死在腳本裡的版本）升級時，請先設定 `TW_STOCK_INVESTING_DIR`，再重新執行一次安裝腳本，讓每個 plist 都帶上這個環境變數。
- 如果之後想調整時間或新增/減少排程次數，直接改 `scripts/install_launchd_jobs.sh` 裡的 `SLOTS` 陣列，重新執行一次腳本即可（會先 unload 舊的再重新 load）。

## 方式 B：crontab（比較陽春但簡單）

如果不想用 launchd，也可以直接編輯 crontab（`crontab -e`），加入類似下面的內容（記得把路徑換成實際安裝路徑，`claude` 換成 `which claude` 查到的完整路徑）：

cron 不會讀 `~/.zshrc`，所以要在 crontab 最上面另外設定 `TW_STOCK_INVESTING_DIR`（cron 允許這種變數設定行；路徑有空白也不需要加引號，但不能用 `~`，要寫完整路徑）：

```cron
TW_STOCK_INVESTING_DIR=/Users/<你>/Library/Mobile Documents/iCloud~md~obsidian/Documents/<vault 名稱>/Investing
50 8 * * 1-5   /usr/local/bin/claude -p "請執行 tw-stock-daily-tracker skill，phase=premarket，time_label=0850"
0,30 9-11 * * 1-5   /usr/local/bin/claude -p "請執行 tw-stock-daily-tracker skill，phase=update，time_label=從現在時間帶入（例如0900、0930）"
0 12 * * 1-5   /usr/local/bin/claude -p "請執行 tw-stock-daily-tracker skill，phase=update，time_label=1200"
30 12 * * 1-5  /usr/local/bin/claude -p "請執行 tw-stock-daily-tracker skill，phase=close_watch，time_label=1230"
0 13 * * 1-5   /usr/local/bin/claude -p "請執行 tw-stock-daily-tracker skill，phase=close_watch，time_label=1300"
25 13 * * 1-5  /usr/local/bin/claude -p "請執行 tw-stock-daily-tracker skill，phase=close_watch，time_label=1325"
35 13 * * 1-5  /usr/local/bin/claude -p "請執行 tw-stock-daily-tracker skill，phase=close_summary，time_label=1335"
```

`cron` 的一行沒辦法很乾淨地把 `time_label` 動態帶成當下時間，所以每個時間點還是建議各寫一行明確指定，跟上面表格一一對應（範例只列了部分，9:00~11:30 中間的整點/半點依同樣規則補齊）。

cron 的缺點是 Mac 睡眠時錯過的排程不會補跑，長時間沒開機的話當天可能會漏掉幾個時段的更新，這點跟 launchd 差不多，只是 launchd 生態上更貼近 macOS、管理上（分開的 log、labels）比較清楚，所以還是建議優先用方式 A。

## 測試單次執行（不用等排程時間到）

安裝完 skill 之後，想先手動測試某個階段能不能正常跑，直接在終端機打：

```bash
claude -p "請執行 tw-stock-daily-tracker skill，phase=premarket，time_label=0850"
```

看它能不能正確跑完整個開盤前簡報流程、把報告跟圖表以 Obsidian 格式寫到 vault 的 `$TW_STOCK_INVESTING_DIR/Daily/{今天日期}/` 底下。確認沒問題後再裝排程。
