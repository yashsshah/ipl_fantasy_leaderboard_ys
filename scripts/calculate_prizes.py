from __future__ import annotations

import argparse
import csv
from pathlib import Path
import time

from auth_cookie import DEFAULT_COOKIE_PATH, load_saved_cookie
from check_match_player_prizes import (
    CATEGORY_NAMES,
    build_category_winners,
    fetch_league_teams,
    fetch_match_players,
    load_participant_lookup,
)
from scrape_participant_gameday_points import (
    DEFAULT_LEAGUE_ID,
    DEFAULT_LEADERBOARD_GAMEDAY_PROBE,
    DEFAULT_TIMEOUT,
    build_session,
    fetch_leaderboard,
)


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

PLAYER_PRIZE_HEADERS = [
    "PrizeName",
    "PlayerName",
    "LeagueMemberName",
    "LeagueTeamName",
    "PointsScored",
    "MatchNum",
    "MatchDetails",
    "CaptainOrViceCaptain",
    "Booster",
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
        "--player-prizes-output",
        default=str(DATA_DIR / "PlayerBasedPrize.csv"),
        help="Path to write PlayerBasedPrize.csv",
    )
    parser.add_argument(
        "--league-id",
        default=DEFAULT_LEAGUE_ID,
        help="League ID used by the IPL fantasy leaderboard API.",
    )
    parser.add_argument(
        "--phase-id",
        type=int,
        default=1,
        help="Tournament phase ID for the API requests.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="HTTP timeout in seconds for authenticated player-prize lookups.",
    )
    parser.add_argument(
        "--cookie",
        help="Optional Cookie header value for authenticated player-prize lookups.",
    )
    parser.add_argument(
        "--saved-cookie-path",
        default=str(DEFAULT_COOKIE_PATH),
        help="Path to the locally saved IPL fantasy cookie used for player-prize lookups.",
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


def load_player_prize_amounts(prizes_path: Path) -> dict[str, str]:
    prize_amounts: dict[str, str] = {}

    with prizes_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            prize_name = row.get("PrizeName", "").strip()
            prize_amount = row.get("PrizeAmount", "").strip()
            if prize_name.casefold() == "highest batter":
                prize_amounts["Highest Batter"] = prize_amount
            elif prize_name.casefold() == "highest bowler":
                prize_amounts["Highest Bowler"] = prize_amount
            elif prize_name.casefold() == "highest wk":
                prize_amounts["Highest WK"] = prize_amount
            elif prize_name.casefold() == "highest allrounder":
                prize_amounts["Highest Allrounder"] = prize_amount

    missing = set(CATEGORY_NAMES.values()) - set(prize_amounts)
    if missing:
        missing_names = ", ".join(sorted(missing))
        raise ValueError(f"Missing player-based prize amounts in {prizes_path}: {missing_names}")

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


def validate_cookie(cookie: str, league_id: str, phase_id: int, timeout: float) -> bool:
    try:
        session = build_session(cookie)
        teams = fetch_leaderboard(
            session,
            league_id,
            DEFAULT_LEADERBOARD_GAMEDAY_PROBE,
            phase_id,
            timeout,
        )
        return bool(teams)
    except Exception:
        return False


def resolve_player_prize_cookie(
    explicit_cookie: str | None,
    saved_cookie_path: Path,
    league_id: str,
    phase_id: int,
    timeout: float,
) -> str | None:
    if explicit_cookie and validate_cookie(explicit_cookie, league_id, phase_id, timeout):
        return explicit_cookie

    saved_cookie = load_saved_cookie(saved_cookie_path)
    if saved_cookie and validate_cookie(saved_cookie, league_id, phase_id, timeout):
        return saved_cookie

    return None


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


def load_completed_match_nums(winner_rows: list[dict[str, str]]) -> list[int]:
    return [parse_match_num(row["MatchNum"]) for row in load_completed_winners(winner_rows)]


def build_player_prize_rows(
    winner_rows: list[dict[str, str]],
    schedule_lookup: dict[str, dict[str, str]],
    participants_path: Path,
    prizes_path: Path,
    league_id: str,
    phase_id: int,
    timeout: float,
    cookie: str | None,
) -> list[dict[str, str]]:
    resolved_cookie = resolve_player_prize_cookie(
        cookie,
        Path(DEFAULT_COOKIE_PATH),
        league_id,
        phase_id,
        timeout,
    )
    if resolved_cookie is None:
        return []

    session = build_session(resolved_cookie)
    teams = fetch_league_teams(session, league_id, phase_id, timeout)
    participant_lookup = load_participant_lookup(participants_path)
    prize_amounts = load_player_prize_amounts(prizes_path)
    completed_match_nums = load_completed_match_nums(winner_rows)

    best_rows_by_category: dict[str, list[dict[str, object]]] = {
        label: [] for label in CATEGORY_NAMES.values()
    }
    best_scores_by_category: dict[str, float] = {
        label: float("-inf") for label in CATEGORY_NAMES.values()
    }

    for match_num in completed_match_nums:
        players_by_id = fetch_match_players(session, match_num, timeout)
        match_winners = build_category_winners(
            teams,
            players_by_id,
            participant_lookup,
            phase_id,
            match_num,
            session,
            timeout,
        )
        for category_label, rows in match_winners.items():
            if not rows:
                continue
            current_score = float(rows[0]["effectivePoints"])
            annotated_rows = [
                {
                    **row,
                    "matchNum": match_num,
                    "matchDetails": schedule_lookup[str(match_num)]["MatchDetails"],
                }
                for row in rows
            ]
            if current_score > best_scores_by_category[category_label]:
                best_scores_by_category[category_label] = current_score
                best_rows_by_category[category_label] = annotated_rows
            elif current_score == best_scores_by_category[category_label]:
                best_rows_by_category[category_label].extend(annotated_rows)

    player_prize_rows: list[dict[str, str]] = []
    for category_label in CATEGORY_NAMES.values():
        category_rows = best_rows_by_category[category_label]
        if not category_rows:
            continue
        split_prize = float(prize_amounts[category_label]) / len(category_rows)
        sorted_rows = sorted(
            category_rows,
            key=lambda row: (
                int(row["matchNum"]),
                str(row.get("leagueMemberName") or ""),
                str(row.get("leagueTeamName") or ""),
            ),
        )
        for row in sorted_rows:
            effective_points = float(row["effectivePoints"])
            player_prize_rows.append(
                {
                    "PrizeName": category_label,
                    "PlayerName": str(row.get("playerName") or ""),
                    "LeagueMemberName": str(row.get("leagueMemberName") or ""),
                    "LeagueTeamName": str(row.get("leagueTeamName") or ""),
                    "PointsScored": format_score(effective_points),
                    "MatchNum": str(row["matchNum"]),
                    "MatchDetails": str(row["matchDetails"]),
                    "CaptainOrViceCaptain": str(row.get("captainOrViceCaptain") or ""),
                    "Booster": str(row.get("booster") or ""),
                    "PrizeAmount": format_amount(split_prize),
                }
            )

    return player_prize_rows


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
    player_prizes_output_path: Path,
    league_id: str = DEFAULT_LEAGUE_ID,
    phase_id: int = 1,
    timeout: float = DEFAULT_TIMEOUT,
    cookie: str | None = None,
) -> tuple[int, int, int]:
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
    player_prize_rows = build_player_prize_rows(
        winner_rows,
        schedule_lookup,
        participants_path,
        prizes_path,
        league_id,
        phase_id,
        timeout,
        cookie,
    )

    write_rows(winners_output_path, WINNER_HEADERS, winner_rows)
    write_rows(bonus_output_path, BONUS_HEADERS, bonus_rows)
    write_rows(player_prizes_output_path, PLAYER_PRIZE_HEADERS, player_prize_rows)

    return len(winner_rows), len(bonus_rows), len(player_prize_rows)


def get_mtime(path: Path) -> int:
    return path.stat().st_mtime_ns


def watch_inputs(
    scores_path: Path,
    schedule_path: Path,
    participants_path: Path,
    prizes_path: Path,
    winners_output_path: Path,
    bonus_output_path: Path,
    player_prizes_output_path: Path,
    interval: float,
    league_id: str,
    phase_id: int,
    timeout: float,
    cookie: str | None,
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
            winner_count, bonus_count, player_prize_count = calculate_outputs(
                scores_path,
                schedule_path,
                participants_path,
                prizes_path,
                winners_output_path,
                bonus_output_path,
                player_prizes_output_path,
                league_id=league_id,
                phase_id=phase_id,
                timeout=timeout,
                cookie=cookie,
            )
            print(
                f"Wrote {winner_count} winner rows to {winners_output_path}, {bonus_count} bonus prize rows to {bonus_output_path}, and {player_prize_count} player prize rows to {player_prizes_output_path}"
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
    player_prizes_output_path = Path(args.player_prizes_output)

    if args.watch:
        watch_inputs(
            scores_path,
            schedule_path,
            participants_path,
            prizes_path,
            winners_output_path,
            bonus_output_path,
            player_prizes_output_path,
            args.interval,
            args.league_id,
            args.phase_id,
            args.timeout,
            args.cookie,
        )
        return

    winner_count, bonus_count, player_prize_count = calculate_outputs(
        scores_path,
        schedule_path,
        participants_path,
        prizes_path,
        winners_output_path,
        bonus_output_path,
        player_prizes_output_path,
        league_id=args.league_id,
        phase_id=args.phase_id,
        timeout=args.timeout,
        cookie=args.cookie,
    )
    print(
        f"Wrote {winner_count} winner rows to {winners_output_path}, {bonus_count} bonus prize rows to {bonus_output_path}, and {player_prize_count} player prize rows to {player_prizes_output_path}"
    )


if __name__ == "__main__":
    main()