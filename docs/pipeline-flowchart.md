# Match Update Pipeline

This document shows the end-to-end pipeline for turning an authenticated IPL fantasy refresh into synced site data.

```mermaid
flowchart TD
    A[Run scripts/update_league_data.py] --> B[Prompt for IPL fantasy cookie]
    A --> A1{Valid saved cookie?}
    A1 -->|Yes| C[Scrape participant gameday history from API]
    A1 -->|No| B[Open browser login and capture cookie]
    B --> B1[Save .local/ipl_fantasy_cookie.txt]
    B1 --> C
    C --> C1[data/ParticipantGamedayPoints.csv]
    C --> C2[data/ParticipantGamedayPointsWide.csv]

    C2 --> D[Regenerate data/MatchDayScores.csv]
    C2 --> E[Regenerate data/Leaderboard.csv]

    D --> F[Run prize calculation]
    F --> F1[data/MatchDayWinners.csv]
    F --> F2[data/BonusPrizes.csv]

    D --> G[Run sync step]
    E --> G
    F1 --> G
    F2 --> G
    G --> H[data.json]

    H --> I[Frontend reads data.json]
    I --> I1[Overall Leaderboard]
    I --> I2[Completed Match Winners]
    I --> I3[Bonus Prizes]
    I --> I4[League Member Prize Breakdown]

    H --> J[Validate generated outputs]
    J --> K[git add -u]
    K --> L[git commit]
    L --> M[git push origin main]
```

## Notes

- `scripts/update_league_data.py` is the intended operator entry point.
- The updater can reuse `.local/ipl_fantasy_cookie.txt` or refresh it via a browser-assisted login flow.
- `scripts/scrape_participant_gameday_points.py` refreshes the long and wide participant gameday CSVs from the IPL fantasy API.
- `scripts/sync_csvs_to_data_json.py` rebuilds `data/MatchDayScores.csv` and `data/Leaderboard.csv`, then regenerates `data.json`.
- `scripts/calculate_prizes.py` derives `data/MatchDayWinners.csv` and `data/BonusPrizes.csv`.
- `data.json` should not be hand-edited; it should always be regenerated from the CSV sources.