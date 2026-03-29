from __future__ import annotations

import argparse
import csv
from pathlib import Path
import time


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"


BONUS_HEADERS = [
    "PrizeName",
    "MatchNum",
    "MatchDetails",
    "LeagueMemberName",
    "LeagueTeamName",
    "Score",
    "PrizeAmount",
]

WINNER_HEADERS = [
    "MatchNum",
    "MatchDetails",
    "LeagueMemberName",
    "LeagueTeamName",
    "Score",
    "PrizeAmount",
]

TEAM_ABBREVIATIONS = {
    "Royal Challengers Bengaluru": "RCB",
    "Sunrisers Hyderabad": "SRH",
    "Chennai Super Kings": "CSK",
    "Mumbai Indians": "MI",
    "Kolkata Knight Riders": "KKR",
    "Rajasthan Royals": "RR",
    "Punjab Kings": "PBKS",
    "Lucknow Super Giants": "LSG",
    "Delhi Capitals": "DC",
    "Gujarat Titans": "GT",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Populate MatchDayWinners.csv from MatchDayScores.csv and regenerate "
            "BonusPrizes.csv from the winner rows."
        )
    )
    parser.add_argument(
        "--scores",
        default=str(DATA_DIR / "MatchDayScores.csv"),
        help="Path to MatchDayScores.csv",
    )
    parser.add_argument(
        "--schedule",
        default=str(DATA_DIR / "MatchSchedule.csv"),
        help="Path to MatchSchedule.csv",
    )
    parser.add_argument(
        "--participants",
        default=str(DATA_DIR / "Participants.csv"),
        help="Path to Participants.csv",
    )
    parser.add_argument(
        "--prizes",
        default=str(DATA_DIR / "PrizesList.csv"),
        help="Path to PrizesList.csv",
    )
    parser.add_argument(
        "--winners-output",
        default=str(DATA_DIR / "MatchDayWinners.csv"),
        help="Path to write MatchDayWinners.csv",
    )
    parser.add_argument(
        "--bonus-output",
        default=str(DATA_DIR / "BonusPrizes.csv"),
        help="Path to write BonusPrizes.csv",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Keep watching the inputs and rewrite outputs whenever they change.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Polling interval in seconds when using --watch.",
    )
    return parser.parse_args()


def parse_score(raw_score: str) -> float | None:
    if raw_score is None:
        return None

    value = raw_score.strip()
    if not value:
        return None

    return float(value)


def format_score(score: float) -> str:
    return str(int(score)) if score.is_integer() else str(score)


def format_amount(amount: float) -> str:
    return str(int(amount)) if amount.is_integer() else f"{amount:.2f}".rstrip("0").rstrip(".")


def parse_match_num(raw_match_num: str) -> int:
    return int(raw_match_num.strip())


def load_prize_amounts(prizes_path: Path) -> dict[str, str]:
    prize_amounts: dict[str, str] = {}

    with prizes_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            prize_name = row.get("PrizeName", "")
            prize_amount = row.get("PrizeAmount", "")
            if prize_name == "Highest team score for each match":
                prize_amounts["Match Winner"] = prize_amount
            elif "[Lucky Prize]" in prize_name:
                prize_amounts["Lucky Prize"] = prize_amount
            elif "[Dominator Prize]" in prize_name:
                prize_amounts["Dominator Prize"] = prize_amount

    missing = {"Match Winner", "Lucky Prize", "Dominator Prize"} - set(prize_amounts)
    if missing:
        missing_names = ", ".join(sorted(missing))
        raise ValueError(f"Missing prize amounts in {prizes_path}: {missing_names}")

    return prize_amounts


def load_team_lookup(participants_path: Path) -> dict[str, str]:
    team_lookup: dict[str, str] = {}

    with participants_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            member_name = row.get("LeagueMemberName", "").strip()
            if not member_name:
                continue
            team_lookup[member_name] = row.get("LeagueTeamName", "").strip()

    return team_lookup


def load_schedule(schedule_path: Path) -> dict[str, dict[str, str]]:
    schedule_lookup: dict[str, dict[str, str]] = {}

    with schedule_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            match_num = row["MatchNum"].strip()
            details = build_match_details(row["HomeTeamName"], row["AwayTeamName"])
            schedule_lookup[match_num] = {
                "MatchNum": match_num,
                "MatchDetails": details,
            }

    return schedule_lookup


def build_match_details(home_team: str, away_team: str) -> str:
    try:
        return f"{TEAM_ABBREVIATIONS[home_team]} vs {TEAM_ABBREVIATIONS[away_team]}"
    except KeyError as exc:
        missing_team = exc.args[0]
        raise ValueError(f"Missing team abbreviation for: {missing_team}") from exc


def load_score_rows(scores_path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with scores_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        member_columns = [
            field for field in (reader.fieldnames or []) if field not in {"MatchNum", "MatchDetails"}
        ]

    return member_columns, rows


def choose_winners(member_columns: list[str], score_row: dict[str, str]) -> tuple[list[str], float] | None:
    best_names: list[str] = []
    best_score: float | None = None

    for member_name in member_columns:
        score = parse_score(score_row.get(member_name, ""))
        if score is None:
            continue
        if best_score is None or score > best_score:
            best_names = [member_name]
            best_score = score
        elif score == best_score:
            best_names.append(member_name)

    if best_score is None:
        return None

    return best_names, best_score


def build_winner_rows(
    member_columns: list[str],
    score_rows: list[dict[str, str]],
    schedule_lookup: dict[str, dict[str, str]],
    team_lookup: dict[str, str],
    prize_amounts: dict[str, str],
) -> list[dict[str, str]]:
    winner_rows: list[dict[str, str]] = []

    for score_row in score_rows:
        match_num = score_row["MatchNum"].strip()
        schedule_row = schedule_lookup.get(match_num)
        if schedule_row is None:
            raise ValueError(f"Match {match_num} is present in MatchDayScores.csv but missing from MatchSchedule.csv")

        winners = choose_winners(member_columns, score_row)
        if winners is None:
            winner_rows.append(
                {
                    "MatchNum": match_num,
                    "MatchDetails": score_row.get("MatchDetails", "").strip() or schedule_row["MatchDetails"],
                    "LeagueMemberName": "",
                    "LeagueTeamName": "",
                    "Score": "",
                    "PrizeAmount": "",
                }
            )
            continue

        winner_names, score = winners
        split_prize = float(prize_amounts["Match Winner"]) / len(winner_names)
        winner_rows.append(
            {
                "MatchNum": match_num,
                "MatchDetails": score_row.get("MatchDetails", "").strip() or schedule_row["MatchDetails"],
                "LeagueMemberName": " / ".join(winner_names),
                "LeagueTeamName": " / ".join(team_lookup.get(member_name, "") for member_name in winner_names),
                "Score": format_score(score),
                "PrizeAmount": format_amount(split_prize),
            }
        )

    return winner_rows


def load_completed_winners(winner_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in winner_rows if row.get("LeagueMemberName", "").strip() and parse_score(row.get("Score", "")) is not None]


def build_bonus_rows(
    winner_rows: list[dict[str, str]], prize_amounts: dict[str, str]
) -> list[dict[str, str]]:
    completed_rows = load_completed_winners(winner_rows)
    if not completed_rows:
        return []

    def lucky_key(row: dict[str, str]) -> tuple[float, int]:
        return (parse_score(row["Score"]), parse_match_num(row["MatchNum"]))

    def dominator_key(row: dict[str, str]) -> tuple[float, int]:
        return (parse_score(row["Score"]), -parse_match_num(row["MatchNum"]))

    lucky_score = min(parse_score(row["Score"]) for row in completed_rows)
    dominator_score = max(parse_score(row["Score"]) for row in completed_rows)

    lucky_rows = [row for row in completed_rows if parse_score(row["Score"]) == lucky_score]
    dominator_rows = [row for row in completed_rows if parse_score(row["Score"]) == dominator_score]

    lucky_rows.sort(key=lambda row: parse_match_num(row["MatchNum"]))
    dominator_rows.sort(key=lambda row: parse_match_num(row["MatchNum"]))

    lucky_split = float(prize_amounts["Lucky Prize"]) / len(lucky_rows)
    dominator_split = float(prize_amounts["Dominator Prize"]) / len(dominator_rows)

    return [
        {
            "PrizeName": "Lucky Prize",
            "MatchNum": " / ".join(row["MatchNum"] for row in lucky_rows),
            "MatchDetails": " / ".join(row["MatchDetails"] for row in lucky_rows),
            "LeagueMemberName": " / ".join(row["LeagueMemberName"] for row in lucky_rows),
            "LeagueTeamName": " / ".join(row["LeagueTeamName"] for row in lucky_rows),
            "Score": lucky_rows[0]["Score"],
            "PrizeAmount": format_amount(lucky_split),
        },
        {
            "PrizeName": "Dominator Prize",
            "MatchNum": " / ".join(row["MatchNum"] for row in dominator_rows),
            "MatchDetails": " / ".join(row["MatchDetails"] for row in dominator_rows),
            "LeagueMemberName": " / ".join(row["LeagueMemberName"] for row in dominator_rows),
            "LeagueTeamName": " / ".join(row["LeagueTeamName"] for row in dominator_rows),
            "Score": dominator_rows[0]["Score"],
            "PrizeAmount": format_amount(dominator_split),
        },
    ]


def write_rows(output_path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def calculate_outputs(
    scores_path: Path,
    schedule_path: Path,
    participants_path: Path,
    prizes_path: Path,
    winners_output_path: Path,
    bonus_output_path: Path,
) -> tuple[int, int]:
    prize_amounts = load_prize_amounts(prizes_path)
    team_lookup = load_team_lookup(participants_path)
    schedule_lookup = load_schedule(schedule_path)
    member_columns, score_rows = load_score_rows(scores_path)
    winner_rows = build_winner_rows(
        member_columns,
        score_rows,
        schedule_lookup,
        team_lookup,
        prize_amounts,
    )
    bonus_rows = build_bonus_rows(winner_rows, prize_amounts)

    write_rows(winners_output_path, WINNER_HEADERS, winner_rows)
    write_rows(bonus_output_path, BONUS_HEADERS, bonus_rows)

    return len(winner_rows), len(bonus_rows)


def get_mtime(path: Path) -> int:
    return path.stat().st_mtime_ns


def watch_inputs(
    scores_path: Path,
    schedule_path: Path,
    participants_path: Path,
    prizes_path: Path,
    winners_output_path: Path,
    bonus_output_path: Path,
    interval: float,
) -> None:
    last_state: tuple[int, int, int, int] | None = None

    while True:
        current_state = (
            get_mtime(scores_path),
            get_mtime(schedule_path),
            get_mtime(participants_path),
            get_mtime(prizes_path),
        )
        if current_state != last_state:
            winner_count, bonus_count = calculate_outputs(
                scores_path,
                schedule_path,
                participants_path,
                prizes_path,
                winners_output_path,
                bonus_output_path,
            )
            print(
                f"Wrote {winner_count} winner rows to {winners_output_path} and {bonus_count} bonus prize rows to {bonus_output_path}"
            )
            last_state = current_state
        time.sleep(interval)


def main() -> None:
    args = parse_args()
    scores_path = Path(args.scores)
    schedule_path = Path(args.schedule)
    participants_path = Path(args.participants)
    prizes_path = Path(args.prizes)
    winners_output_path = Path(args.winners_output)
    bonus_output_path = Path(args.bonus_output)

    if args.watch:
        watch_inputs(
            scores_path,
            schedule_path,
            participants_path,
            prizes_path,
            winners_output_path,
            bonus_output_path,
            args.interval,
        )
        return

    winner_count, bonus_count = calculate_outputs(
        scores_path,
        schedule_path,
        participants_path,
        prizes_path,
        winners_output_path,
        bonus_output_path,
    )
    print(
        f"Wrote {winner_count} winner rows to {winners_output_path} and {bonus_count} bonus prize rows to {bonus_output_path}"
    )


if __name__ == "__main__":
    main()