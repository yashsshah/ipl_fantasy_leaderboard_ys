# Pipeline Reference

## Primary Command

```bash
/Users/yshah/Code_Yash/ipl_fantasy_leaderboard_ys/.venv/bin/python scripts/update_league_data.py
```

The script now tries cookies in this order:

1. `--cookie`
2. `IPL_FANTASY_COOKIE`
3. `.local/ipl_fantasy_cookie.txt`
4. browser-assisted login capture via Playwright
5. hidden terminal prompt as a final fallback

After it has a valid cookie, it scrapes the latest participant gameday data and then regenerates all derived CSV and JSON outputs.

## One-Time Browser Setup

Install Playwright in the repo environment and install Chromium once:

```bash
/Users/yshah/Code_Yash/ipl_fantasy_leaderboard_ys/.venv/bin/python -m playwright install chromium
```

On the first run without a valid saved cookie, the updater opens a browser window, waits for you to finish logging in, captures the resulting IPL cookies, and saves them to `.local/ipl_fantasy_cookie.txt` for reuse.

## Files Updated By The Full Pipeline

- `data/ParticipantGamedayPoints.csv`
- `data/ParticipantGamedayPointsWide.csv`
- `data/MatchDayScores.csv`
- `data/Leaderboard.csv`
- `data/MatchDayWinners.csv`
- `data/BonusPrizes.csv`
- `data.json`

## Underlying Flow

1. `scripts/update_league_data.py` reuses a valid saved cookie when possible and can launch a browser login to refresh it.
2. `scripts/scrape_participant_gameday_points.py` calls the IPL fantasy APIs and refreshes the long and wide participant gameday CSVs.
3. `scripts/sync_csvs_to_data_json.py` rebuilds `data/MatchDayScores.csv` from `ParticipantGamedayPointsWide.csv`.
4. The sync step also regenerates `data/Leaderboard.csv` from the latest cumulative totals in `ParticipantGamedayPointsWide.csv`.
5. `scripts/calculate_prizes.py` derives `data/MatchDayWinners.csv` and `data/BonusPrizes.csv` from `data/MatchDayScores.csv`.
6. The sync step rebuilds `data.json` for the frontend.

## Derived Prize Logic

- `scripts/calculate_prizes.py` chooses the highest score in a match as the daily winner.
- Tied winners split the daily winner prize amount equally.
- Lucky Prize is the lowest completed winning score across completed matches.
- Dominator Prize is the highest completed winning score across completed matches.

## Expected Git Behavior

- Stage tracked modifications with `git add -u`.
- Use the repo's requested commit message format when committing updates.
- Push only after the full regeneration has completed successfully.
- The saved cookie file lives under `.local/` and is intentionally ignored by git.