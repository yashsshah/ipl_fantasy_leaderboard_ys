from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import time


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"


CSV_FILES = [
    "Participants.csv",
    "PrizesList.csv",
    "MatchSchedule.csv",
    "TablePredictions.csv",
    "TableRankings.csv",
    "Leaderboard.csv",
    "PlayerBasedPrize.csv",
    "MatchDayScores.csv",
    "MatchDayWinners.csv",
    "BonusPrizes.csv",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync the league CSV files into data.json."
    )
    parser.add_argument(
        "--root",
        default=str(DATA_DIR),
        help="Directory containing the CSV files.",
    )
    parser.add_argument(
        "--output",
        default=str(PROJECT_ROOT / "data.json"),
        help="Path to output data.json.",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch the CSV inputs and rewrite data.json whenever they change.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Polling interval in seconds when using --watch.",
    )
    return parser.parse_args()


def clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value if value else None


def parse_number(value: str | None) -> int | float | None:
    normalized = clean(value)
    if normalized is None:
        return None
    number = float(normalized)
    return int(number) if number.is_integer() else number


def parse_number_or_text(value: str | None) -> int | float | str | None:
    normalized = clean(value)
    if normalized is None:
        return None
    if "/" in normalized:
        return normalized
    try:
        return parse_number(normalized)
    except ValueError:
        return normalized


def read_csv(root: Path, name: str) -> list[dict[str, str]]:
    with (root / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def score_table_prediction(actual_order: list[str], predicted_order: list[str | None]) -> int:
    actual_top_four = set(actual_order[:4])
    exact_points = sum(
        1
        for actual_team, predicted_team in zip(actual_order, predicted_order)
        if predicted_team and actual_team == predicted_team
    )
    playoff_points = sum(1 for team in predicted_order[:4] if team in actual_top_four)
    return exact_points + playoff_points


def build_table_prediction_scores(
    table_predictions_rows: list[dict[str, str]],
    member_columns: list[str],
    table_rankings_rows: list[dict[str, str]],
) -> dict[str, int]:
    prediction_rows = [row for row in table_predictions_rows if clean(row.get("Rank")) != "Total Points"]
    actual_order = [clean(row.get("IPLTeamName")) for row in table_rankings_rows if clean(row.get("IPLTeamName"))]

    return {
        member: score_table_prediction(actual_order, [clean(row.get(member)) for row in prediction_rows])
        for member in member_columns
    }


def load_existing_colors(data_path: Path) -> dict[str, str | None]:
    if not data_path.exists():
        return {}

    with data_path.open(encoding="utf-8") as handle:
        existing = json.load(handle)

    return {
        member["name"]: member.get("color")
        for member in existing.get("leagueMembers", [])
        if member.get("name")
    }


def build_synced_data(root: Path, output_path: Path) -> dict[str, object]:
    color_lookup = load_existing_colors(output_path)

    participants_rows = [
        row for row in read_csv(root, "Participants.csv")
        if clean(row.get("LeagueMemberName"))
    ]
    leaderboard_rows = [
        row for row in read_csv(root, "Leaderboard.csv")
        if clean(row.get("LeagueMemberName"))
    ]
    player_prize_rows = [
        row for row in read_csv(root, "PlayerBasedPrize.csv")
        if clean(row.get("PrizeName"))
    ]
    match_day_winner_rows = read_csv(root, "MatchDayWinners.csv")
    match_day_score_rows = read_csv(root, "MatchDayScores.csv")
    table_predictions_rows = read_csv(root, "TablePredictions.csv")
    table_rankings_rows = read_csv(root, "TableRankings.csv")

    score_member_columns = [
        key for key in (match_day_score_rows[0].keys() if match_day_score_rows else [])
        if key not in {"MatchNum", "MatchDetails"}
    ]
    prediction_member_columns = [
        key for key in (table_predictions_rows[0].keys() if table_predictions_rows else [])
        if key != "Rank"
    ]
    prediction_input_rows = [row for row in table_predictions_rows if clean(row.get("Rank")) != "Total Points"]

    return {
        "meta": {
            "lastSyncedAt": datetime.now(timezone.utc).isoformat(),
            "source": "csv-sync",
        },
        "leagueMembers": [
            {
                "name": row["LeagueMemberName"].strip(),
                "teamName": clean(row.get("LeagueTeamName")),
                "color": color_lookup.get(row["LeagueMemberName"].strip()),
            }
            for row in participants_rows
        ],
        "players": [
            {
                "name": row["LeagueMemberName"].strip(),
                "totalPoints": parse_number(row.get("TotalPoints")),
            }
            for row in leaderboard_rows
        ],
        "matches": [
            {
                "match": parse_number(row.get("MatchNum")),
                "matchDetails": clean(row.get("MatchDetails")),
                "winner": clean(row.get("LeagueMemberName")) or "",
                "winnerTeamName": clean(row.get("LeagueTeamName")),
                "points": parse_number(row.get("Score")),
                "amount": parse_number(row.get("PrizeAmount")),
            }
            for row in match_day_winner_rows
        ],
        "playerPrizes": [
            {
                "prize": row["PrizeName"].strip(),
                "player": clean(row.get("PlayerName")),
                "points": parse_number(row.get("PointsScored")),
                "match": parse_number(row.get("MatchNum")),
                "matchDetails": clean(row.get("MatchDetails")),
                "captainOrViceCaptain": clean(row.get("CaptainOrViceCaptain")),
                "booster": clean(row.get("Booster")),
                "amount": parse_number(row.get("PrizeAmount")),
            }
            for row in player_prize_rows
        ],
        "participants": [
            {
                "leagueMemberNum": parse_number(row.get("#")),
                "leagueMemberName": row["LeagueMemberName"].strip(),
                "leagueTeamName": clean(row.get("LeagueTeamName")),
                "joinedStatus": clean(row.get("JoinedStatus")),
                "paymentStatus": clean(row.get("PaymentStatus")),
                "buyInAmount": parse_number(row.get("BuyInAmount")),
                "email": clean(row.get("Email")),
            }
            for row in participants_rows
        ],
        "prizesList": [
            {
                "prizeName": clean(row.get("PrizeName")),
                "prizeAmount": parse_number(row.get("PrizeAmount")),
                "prizeCount": parse_number(row.get("PrizeCount")),
                "prizeTotalAmount": parse_number(row.get("PrizeTotalAmount")),
                "totalPotAmount": parse_number(row.get("TotalPotAmount")),
                "differenceAmount": parse_number(row.get("DifferenceAmount")),
            }
            for row in read_csv(root, "PrizesList.csv")
        ],
        "matchSchedule": [
            {
                "matchNum": parse_number(row.get("MatchNum")),
                "matchDate": clean(row.get("MatchDate")),
                "matchTimeIST": clean(row.get("MatchTimeIST")),
                "homeTeamName": clean(row.get("HomeTeamName")),
                "awayTeamName": clean(row.get("AwayTeamName")),
                "venue": clean(row.get("Venue")),
            }
            for row in read_csv(root, "MatchSchedule.csv")
        ],
        "tablePredictions": [
            {
                "rank": parse_number(row.get("Rank")),
                "predictions": {
                    member: clean(row.get(member)) for member in prediction_member_columns
                },
            }
            for row in prediction_input_rows
        ],
        "tablePredictionScores": build_table_prediction_scores(
            prediction_input_rows,
            prediction_member_columns,
            table_rankings_rows,
        ),
        "tableRankings": [
            {
                "rank": parse_number(row.get("Rank")),
                "iplTeamName": clean(row.get("IPLTeamName")),
            }
            for row in table_rankings_rows
        ],
        "leaderboard": [
            {
                "rank": parse_number(row.get("Rank")),
                "leagueMemberName": row["LeagueMemberName"].strip(),
                "leagueTeamName": clean(row.get("LeagueTeamName")),
                "totalPoints": parse_number(row.get("TotalPoints")),
            }
            for row in leaderboard_rows
        ],
        "playerBasedPrizes": [
            {
                "prizeName": row["PrizeName"].strip(),
                "playerName": clean(row.get("PlayerName")),
                "pointsScored": parse_number(row.get("PointsScored")),
                "matchNum": parse_number(row.get("MatchNum")),
                "matchDetails": clean(row.get("MatchDetails")),
                "captainOrViceCaptain": clean(row.get("CaptainOrViceCaptain")),
                "booster": clean(row.get("Booster")),
                "prizeAmount": parse_number(row.get("PrizeAmount")),
            }
            for row in player_prize_rows
        ],
        "matchDayScores": [
            {
                "matchNum": parse_number(row.get("MatchNum")),
                "matchDetails": clean(row.get("MatchDetails")),
                "scores": {
                    member: parse_number(row.get(member)) for member in score_member_columns
                },
            }
            for row in match_day_score_rows
        ],
        "matchDayWinners": [
            {
                "matchNum": parse_number(row.get("MatchNum")),
                "matchDetails": clean(row.get("MatchDetails")),
                "leagueMemberName": clean(row.get("LeagueMemberName")),
                "leagueTeamName": clean(row.get("LeagueTeamName")),
                "score": parse_number(row.get("Score")),
                "prizeAmount": parse_number(row.get("PrizeAmount")),
            }
            for row in match_day_winner_rows
        ],
        "bonusPrizes": [
            {
                "prizeName": clean(row.get("PrizeName")),
                "matchNum": parse_number_or_text(row.get("MatchNum")),
                "matchDetails": clean(row.get("MatchDetails")),
                "leagueMemberName": clean(row.get("LeagueMemberName")),
                "leagueTeamName": clean(row.get("LeagueTeamName")),
                "score": parse_number(row.get("Score")),
                "prizeAmount": parse_number(row.get("PrizeAmount")),
            }
            for row in read_csv(root, "BonusPrizes.csv")
        ],
    }


def write_data(output_path: Path, data: dict[str, object]) -> None:
    output_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def sync_once(root: Path, output_path: Path) -> None:
    data = build_synced_data(root, output_path)
    write_data(output_path, data)


def get_mtimes(root: Path) -> tuple[int, ...]:
    return tuple((root / name).stat().st_mtime_ns for name in CSV_FILES)


def watch(root: Path, output_path: Path, interval: float) -> None:
    last_state: tuple[int, ...] | None = None
    while True:
        current_state = get_mtimes(root)
        if current_state != last_state:
            sync_once(root, output_path)
            print(f"Synced CSV data into {output_path.name}")
            last_state = current_state
        time.sleep(interval)


def main() -> None:
    args = parse_args()
    root = Path(args.root).resolve()
    output_path = Path(args.output).resolve()

    if args.watch:
        watch(root, output_path, args.interval)
        return

    sync_once(root, output_path)
    print(f"Synced CSV data into {output_path.name}")


if __name__ == "__main__":
    main()