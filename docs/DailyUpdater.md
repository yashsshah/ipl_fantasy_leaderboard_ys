# Daily Updater

Use `scripts/run_daily_update.sh` to run the full unattended league refresh.

What it does:

- runs `scripts/update_league_data.py`
- refreshes `data/TableRankings.csv` from ESPN Cricinfo unless you pass `-- --no-refresh-standings`
- regenerates prize CSVs, including `data/PlayerBasedPrize.csv`
- rewrites `data.json`
- stages generated changes in `data/` and `data.json`
- creates a git commit when generated data changed
- fast-forward merges the current branch into `main`
- can send optional success email and SMS notifications from a gitignored local env file

It uses the repo `.venv`, so Playwright-based standings refresh works.

## Manual run

```bash
scripts/run_daily_update.sh
```

If you want the scheduled job to also push `main` after the merge, use:

```bash
scripts/run_daily_update.sh --push-target
```

## launchd schedule for 4:00 PM ET

Create `~/Library/LaunchAgents/com.yash.ipl-updater.plist` with:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>com.yash.ipl-updater</string>

    <key>ProgramArguments</key>
    <array>
      <string>/bin/zsh</string>
      <string>/Users/yshah/Code_Yash/ipl_fantasy_leaderboard_ys/scripts/run_daily_update.sh</string>
      <string>--push-target</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/Users/yshah/Code_Yash/ipl_fantasy_leaderboard_ys</string>

    <key>StartCalendarInterval</key>
    <dict>
      <key>Hour</key>
      <integer>16</integer>
      <key>Minute</key>
      <integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>/Users/yshah/Code_Yash/ipl_fantasy_leaderboard_ys/logs/launchd.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/yshah/Code_Yash/ipl_fantasy_leaderboard_ys/logs/launchd.stderr.log</string>
  </dict>
</plist>
```

Load it with:

```bash
launchctl unload ~/Library/LaunchAgents/com.yash.ipl-updater.plist 2>/dev/null
launchctl load ~/Library/LaunchAgents/com.yash.ipl-updater.plist
launchctl list | grep com.yash.ipl-updater
```

`launchd` uses the Mac's local timezone. If the Mac stays on Eastern Time, the job runs at 4:00 PM ET.

## Cookie requirement

The updater still needs a valid IPL fantasy cookie in `.local/ipl_fantasy_cookie.txt`. Refresh that cookie manually whenever it expires.

## Optional notifications

If you want a success email and text after the updater finishes, create `.local/daily_updater.env` with the credentials you want to use. The `.local/` directory is gitignored.

Email uses SMTP and sends only when all of these are present:

```bash
UPDATER_EMAIL_SMTP_HOST=smtp.gmail.com
UPDATER_EMAIL_SMTP_PORT=587
UPDATER_EMAIL_SMTP_USERNAME=your_email@gmail.com
UPDATER_EMAIL_SMTP_PASSWORD=your_app_password
UPDATER_EMAIL_FROM=your_email@gmail.com
UPDATER_EMAIL_TO=ysshah04@gmail.com
```

SMS uses Twilio and sends only when all of these are present:

```bash
UPDATER_TWILIO_ACCOUNT_SID=AC...
UPDATER_TWILIO_AUTH_TOKEN=...
UPDATER_TWILIO_FROM=+1YOURTWILIONUMBER
UPDATER_SMS_TO=+17326665493
```

The updater reads `.local/daily_updater.env` automatically at runtime. If email or SMS credentials are incomplete, that channel is skipped. If a notification call fails, the updater logs the notification failure but does not fail the league-data update itself.