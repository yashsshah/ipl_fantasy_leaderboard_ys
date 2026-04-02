---
name: match-score-update-from-screenshot
description: 'Use when updating the IPL fantasy repo from a standings screenshot and a MatchNum. Trigger words: screenshot, MatchNum, calculate scores, update MatchDayScores.csv, update Leaderboard.csv, regenerate winners, regenerate bonus prizes, sync data.json, git add, git commit, git push.'
argument-hint: 'Provide the screenshot and MatchNum. Example: screenshot: attached image, MatchNum: 4'
user-invocable: true
disable-model-invocation: false
---

# Match Score Update From Screenshot

Use this skill when the user provides a screenshot of cumulative standings after a completed match and wants the repo updated end to end.

This workflow is repo-specific and should be used for this project only.

## Inputs

- A screenshot showing cumulative standings after the latest completed match
- The `MatchNum` that just completed

## Goal

Take the screenshot and `MatchNum`, derive that match's per-team scores, update the source CSVs, regenerate all downstream prize and JSON outputs, then stage, commit, and push the changes.

## Source Of Truth

- Match-by-match scores: `data/MatchDayScores.csv`
- Cumulative standings: `data/Leaderboard.csv`
- Winner and bonus derivation: `scripts/calculate_prizes.py`
- Final site sync: `scripts/sync_csvs_to_data_json.py`

## Procedure

1. Read the screenshot and extract the latest cumulative standings for all teams.
2. Read the current `data/MatchDayScores.csv` and `data/Leaderboard.csv`.
3. For each team, calculate the new match score as:

   $$
   \text{MatchNumScore} = \text{NewCumulativeTotal} - \text{PreviousCumulativeTotal}
   $$

4. Update the row for the given `MatchNum` in `data/MatchDayScores.csv`.
5. Update `data/Leaderboard.csv` so it matches the screenshot's post-match cumulative standings and ranks.
6. Run:

   ```bash
   /Users/yshah/Code_Yash/ipl_fantasy_leaderboard_ys/.venv/bin/python scripts/calculate_prizes.py
   /Users/yshah/Code_Yash/ipl_fantasy_leaderboard_ys/.venv/bin/python scripts/sync_csvs_to_data_json.py
   ```

7. Verify the outputs:
   - `data/MatchDayWinners.csv`
   - `data/BonusPrizes.csv`
   - `data.json`
8. Stage tracked changes with `git add -u`.
9. Commit with this exact format:

   ```text
   Update scores and synced site data after MatchNum <MatchNum>
   ```

10. Push the current branch, or push `main` if the user asked to update `main` directly.

## Rules

- Do not hand-edit `data.json`; always regenerate it through the script.
- Prefer updating CSV source files over editing derived outputs.
- If the screenshot is incomplete or ambiguous for any team, stop and ask the user only for the missing values.
- Leave unrelated untracked files alone.

## Validation Checklist

- Match row exists and is filled in `data/MatchDayScores.csv`
- `data/Leaderboard.csv` matches the screenshot totals and ordering
- `data/MatchDayWinners.csv` shows the correct winner for that match
- `data/BonusPrizes.csv` reflects the recalculated lucky and dominator prizes
- `data.json` contains the updated leaderboard, match scores, winners, and prize summaries

## References

- [Pipeline reference](../../../docs/pipeline-reference.md)
- [Repository flowchart](../../../docs/pipeline-flowchart.md)