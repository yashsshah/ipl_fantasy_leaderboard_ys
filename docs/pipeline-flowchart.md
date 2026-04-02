# Match Update Pipeline

This document shows the end-to-end pipeline for turning match results into synced site data.

```mermaid
flowchart TD
    A[Match result screenshot uploaded] --> B[Read existing data sources]
    B --> B1[data/MatchDayScores.csv]
    B --> B2[data/Leaderboard.csv]
    B --> B3[data/Participants.csv]
    B --> B4[data/MatchSchedule.csv]

    B1 --> C[Derive current match scores by subtracting prior cumulative totals]
    B2 --> C
    A --> C

    C --> D[Update data/MatchDayScores.csv for MatchNum N]
    C --> E[Update data/Leaderboard.csv with post-match cumulative standings]

    D --> F[Run scripts/calculate_prizes.py]
    E --> F
    F --> F1[data/MatchDayWinners.csv]
    F --> F2[data/BonusPrizes.csv]

    D --> G[Run scripts/sync_csvs_to_data_json.py]
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
    K --> L[git commit -m "Update scores and synced site data after MatchNum N"]
    L --> M[git push origin main]
```

## Notes

- `data/MatchDayScores.csv` is the match-by-match source of truth.
- `data/Leaderboard.csv` stores cumulative standings after the latest completed match.
- `scripts/calculate_prizes.py` derives `data/MatchDayWinners.csv` and `data/BonusPrizes.csv`.
- `scripts/sync_csvs_to_data_json.py` is the final sync step that rebuilds `data.json` for the UI.
- `data.json` should not be hand-edited; it should always be regenerated from the CSV sources.