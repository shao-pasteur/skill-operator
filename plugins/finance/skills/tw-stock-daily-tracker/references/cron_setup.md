# Scheduling

The skill does not run continuously. A macOS scheduler calls `claude -p "..."` at fixed times to trigger each run.

## Suggested schedule

| Time | phase | What it does |
|---|---|---|
| 08:50 | `premarket` | Pre-market briefing: pick stocks and compute the Bollinger baseline |
| 09:00–12:00 (every 30 min) | `update` | Intraday updates, 7 runs |
| 12:30, 13:00, 13:25 | `close_watch` | Pre-close sell-zone tracking, 3 runs |
| 13:35 | `close_summary` | Closing summary |

The Taiwan market trades from 09:00 to 13:30, so 13:25 is the last intraday snapshot and 13:35 uses the post-close data for the summary.

## Option A: launchd (recommended, the native macOS scheduler)

Run the installer. It generates one plist per entry in its `SLOTS` array and loads them:

```bash
cd ~/path/to/tw-stock-daily-tracker   # replace with where the skill is installed
bash scripts/install_launchd_jobs.sh
```

Check that the jobs loaded:

```bash
launchctl list | grep tw-stock-tracker
```

Logs go to `~/Library/Logs/tw-stock-tracker/`, with separate `.out.log` / `.err.log` files per time slot, which makes it easy to see why a particular slot failed.

Remove every job:

```bash
bash scripts/install_launchd_jobs.sh --uninstall
```

**Notes:**
- launchd triggers every day, weekends included. The skill itself decides whether it is a trading day (on non-trading days it skips and writes one log line), which is much simpler than putting weekday logic in the plist.
- The computer must be on and awake at the scheduled times. If the Mac sleeps, schedule a wake-up under Battery settings or with `pmset`.
- When upgrading from the old version (with the path hardcoded in the scripts), set `TW_STOCK_INVESTING_DIR` first and run the installer again so every plist carries the variable.
- To change the times or the number of runs, edit the `SLOTS` array in `scripts/install_launchd_jobs.sh` and run the script again (it unloads the old jobs before loading the new ones).

## Option B: crontab (more basic but simple)

If you would rather not use launchd, edit the crontab (`crontab -e`) and add lines like the ones below (replace the paths with the real install path, and `claude` with the full path from `which claude`).

cron does not read `~/.zshrc`, so set `TW_STOCK_INVESTING_DIR` at the top of the crontab (cron allows variable lines like this; no quotes are needed even when the path has spaces, but `~` does not work, so write the full path):

```cron
TW_STOCK_INVESTING_DIR=/Users/<you>/Library/Mobile Documents/iCloud~md~obsidian/Documents/<vault name>/Investing
50 8 * * 1-5   /usr/local/bin/claude -p "Run the tw-stock-daily-tracker skill, phase=premarket, time_label=0850"
0,30 9-11 * * 1-5   /usr/local/bin/claude -p "Run the tw-stock-daily-tracker skill, phase=update, time_label=the current time (for example 0900 or 0930)"
0 12 * * 1-5   /usr/local/bin/claude -p "Run the tw-stock-daily-tracker skill, phase=update, time_label=1200"
30 12 * * 1-5  /usr/local/bin/claude -p "Run the tw-stock-daily-tracker skill, phase=close_watch, time_label=1230"
0 13 * * 1-5   /usr/local/bin/claude -p "Run the tw-stock-daily-tracker skill, phase=close_watch, time_label=1300"
25 13 * * 1-5  /usr/local/bin/claude -p "Run the tw-stock-daily-tracker skill, phase=close_watch, time_label=1325"
35 13 * * 1-5  /usr/local/bin/claude -p "Run the tw-stock-daily-tracker skill, phase=close_summary, time_label=1335"
```

A single cron line cannot cleanly fill `time_label` with the current time, so write one explicit line per time slot to match the table above (the example lists only some; fill in the other hours and half-hours between 9:00 and 11:30 the same way).

cron does not catch up on runs missed while the Mac sleeps, so a day without the computer on may miss several updates. launchd behaves similarly, but it fits macOS better and is easier to manage (separate logs and labels), so option A is still recommended.

## Test a single run (without waiting for the schedule)

After installing the skill, test a phase by hand in the terminal:

```bash
claude -p "Run the tw-stock-daily-tracker skill, phase=premarket, time_label=0850"
```

Check that it completes the whole pre-market flow and writes the report and charts in Obsidian format under `$TW_STOCK_INVESTING_DIR/Daily/{today}/`. Install the schedule once that works.
