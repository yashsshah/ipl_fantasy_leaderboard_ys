from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from auth_cookie import DEFAULT_COOKIE_PATH, capture_cookie_via_browser, load_saved_cookie
from scrape_participant_gameday_points import (
    DEFAULT_LEAGUE_ID,
    DEFAULT_LEADERBOARD_GAMEDAY_PROBE,
    DEFAULT_TIMEOUT,
    build_leaderboard_url,
    build_session,
    fetch_json,
    fetch_leaderboard,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLAYER_POOL_URL = (
    "https://fantasy.iplt20.com/classic/api/feed/gamedayplayers"
    "?lang=en&tourgamedayId={gameday_id}&teamgamedayId={gameday_id}"
    "&announcedVersion=04282026175302"
)
CATEGORY_NAMES = {
    "BATSMAN": "Highest Batter",
    "BOWLER": "Highest Bowler",
    "WICKET KEEPER": "Highest WK",
    "ALL ROUNDER": "Highest Allrounder",
}
BOOSTER_NAMES = {
    0: None,
    1: "Wild Card",
    3: "Double Power",
    9: "Foreign Stars",
    10: "Indian Warriors",
    11: "Free Hit",
    12: "Triple Captain",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check the highest effective scorer for each player category in a single IPL "
            "fantasy match, with C/VC and boosters applied."
        )
    )
    parser.add_argument("--match-num", type=int, help="Match number / gameday id to inspect.")
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
        "--participants",
        default=str(PROJECT_ROOT / "data" / "Participants.csv"),
        help="Path to Participants.csv used to map team names to league member names.",
    )
    parser.add_argument(
        "--winners",
        default=str(PROJECT_ROOT / "data" / "MatchDayWinners.csv"),
        help="Path to MatchDayWinners.csv used to determine completed matches for the all-matches summary.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--cookie",
        help="Optional Cookie header value. If omitted, the script reuses the saved cookie flow.",
    )
    parser.add_argument(
        "--saved-cookie-path",
        default=str(DEFAULT_COOKIE_PATH),
        help="Path to the locally saved IPL fantasy cookie used for reuse across runs.",
    )
    parser.add_argument(
        "--browser-login",
        action="store_true",
        help="Launch a browser login flow before the lookup and refresh the saved cookie.",
    )
    parser.add_argument(
        "--no-browser-login",
        action="store_true",
        help="Disable automatic browser fallback when no valid cookie is available.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format. Use json for programmatic consumption.",
    )
    parser.add_argument(
        "--all-matches-summary",
        action="store_true",
        help="Also summarize the highest effective scorer in each category across all completed matches.",
    )
    args = parser.parse_args()
    if args.match_num is None and not args.all_matches_summary:
        parser.error("Provide --match-num, --all-matches-summary, or both.")
    return args


def load_participant_lookup(participants_path: Path) -> dict[str, str]:
    lookup: dict[str, str] = {}
    if not participants_path.exists():
        return lookup

    with participants_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            team_name = (row.get("LeagueTeamName") or "").strip()
            member_name = (row.get("LeagueMemberName") or "").strip()
            if team_name and member_name:
                lookup[team_name.casefold()] = member_name

    return lookup


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


def resolve_cookie(args: argparse.Namespace) -> str:
    explicit_cookie = args.cookie.strip() if args.cookie else None
    saved_cookie = load_saved_cookie(Path(args.saved_cookie_path))

    if explicit_cookie:
        return explicit_cookie

    if args.browser_login:
        cookie = capture_cookie_via_browser(Path(args.saved_cookie_path))
        if validate_cookie(cookie, args.league_id, args.phase_id, args.timeout):
            return cookie

    if saved_cookie and validate_cookie(saved_cookie, args.league_id, args.phase_id, args.timeout):
        return saved_cookie

    if not args.no_browser_login:
        cookie = capture_cookie_via_browser(Path(args.saved_cookie_path))
        if validate_cookie(cookie, args.league_id, args.phase_id, args.timeout):
            return cookie

    raise RuntimeError("No valid IPL fantasy cookie available for the lookup.")


def build_team_detail_url(team_id: int | str, social_id: int | str, phase_id: int, gameday_id: int) -> str:
    return (
        "https://fantasy.iplt20.com/classic/api/user/guid/lb-team/overall-get"
        f"?optType=1&teamgamedayId={gameday_id}&arrtourGamedayId={gameday_id}&phaseId={phase_id}"
        f"&teamId={team_id}&SocialId={social_id}"
    )


def fetch_match_players(session, gameday_id: int, timeout: float) -> dict[int, dict[str, object]]:
    payload = fetch_json(session, PLAYER_POOL_URL.format(gameday_id=gameday_id), timeout)
    players = ((payload.get("Data") or {}).get("Value") or {}).get("Players") or []
    return {int(player["Id"]): player for player in players}


def normalize_booster_name(booster_id: int) -> str | None:
    return BOOSTER_NAMES.get(booster_id, f"Unknown ({booster_id})")


def is_foreign_player(player: dict[str, object]) -> bool:
    return str(player.get("IS_FP") or "0") == "1"


def compute_player_multiplier(
    player_id: int,
    player: dict[str, object],
    team_entry: dict[str, object],
) -> tuple[float, str | None, str | None]:
    booster_id = int(team_entry.get("boosterid") or 0)
    booster_name = normalize_booster_name(booster_id)
    captain_id = int(team_entry.get("mcapt") or 0)
    vice_captain_id = int(team_entry.get("vcapt") or 0)

    role: str | None = None
    multiplier = 1.0
    is_captain = captain_id == player_id
    is_vice_captain = vice_captain_id == player_id

    if is_captain:
        role = "C"
        multiplier = 2.0
    elif is_vice_captain:
        role = "VC"
        multiplier = 1.5

    if booster_id == 3:
        multiplier *= 2.0
    elif booster_id == 9 and is_foreign_player(player):
        multiplier *= 2.0
    elif booster_id == 10 and not is_foreign_player(player):
        multiplier *= 2.0
    elif booster_id == 12 and is_captain:
        multiplier = 3.0

    return multiplier, role, booster_name


def build_category_winners(
    teams: list[dict[str, object]],
    players_by_id: dict[int, dict[str, object]],
    participant_lookup: dict[str, str],
    phase_id: int,
    gameday_id: int,
    session,
    timeout: float,
) -> dict[str, list[dict[str, object]]]:
    winners: dict[str, list[dict[str, object]]] = {label: [] for label in CATEGORY_NAMES.values()}
    best_scores: dict[str, float] = {label: float("-inf") for label in CATEGORY_NAMES.values()}

    for team in teams:
        payload = fetch_json(
            session,
            build_team_detail_url(team["team_id"], team["social_id"], phase_id, gameday_id),
            timeout,
        )
        team_entries = ((payload.get("Data") or {}).get("Value") or {}).get("teams") or []
        if not team_entries:
            continue

        team_entry = team_entries[0]
        for raw_player_id in team_entry.get("plyid") or []:
            player_id = int(raw_player_id)
            player = players_by_id.get(player_id)
            if player is None:
                continue

            category_label = CATEGORY_NAMES.get(str(player.get("SkillName") or "").upper())
            if category_label is None:
                continue

            multiplier, role, booster_name = compute_player_multiplier(player_id, player, team_entry)
            base_points = float(player.get("GamedayPoints") or 0.0)
            effective_points = base_points * multiplier

            row = {
                "playerName": player.get("Name"),
                "leagueTeamName": team["team_name"],
                "leagueMemberName": participant_lookup.get(str(team["team_name"]).casefold()),
                "basePoints": base_points,
                "effectivePoints": effective_points,
                "captainOrViceCaptain": role,
                "booster": booster_name,
            }

            current_best = best_scores[category_label]
            if effective_points > current_best:
                best_scores[category_label] = effective_points
                winners[category_label] = [row]
            elif effective_points == current_best:
                winners[category_label].append(row)

    return winners


def load_completed_match_nums(winners_path: Path) -> list[int]:
    completed: list[int] = []
    with winners_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            league_member_name = (row.get("LeagueMemberName") or "").strip()
            match_num = (row.get("MatchNum") or "").strip()
            if league_member_name and match_num:
                completed.append(int(match_num))
    return completed


def build_season_category_winners(
    teams: list[dict[str, object]],
    participant_lookup: dict[str, str],
    phase_id: int,
    match_nums: list[int],
    session,
    timeout: float,
) -> dict[str, list[dict[str, object]]]:
    winners: dict[str, list[dict[str, object]]] = {label: [] for label in CATEGORY_NAMES.values()}
    best_scores: dict[str, float] = {label: float("-inf") for label in CATEGORY_NAMES.values()}

    for match_num in match_nums:
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
                }
                for row in rows
            ]
            if current_score > best_scores[category_label]:
                best_scores[category_label] = current_score
                winners[category_label] = annotated_rows
            elif current_score == best_scores[category_label]:
                winners[category_label].extend(annotated_rows)

    return winners


def fetch_league_teams(session, league_id: str, phase_id: int, timeout: float) -> list[dict[str, object]]:
    payload = fetch_json(
        session,
        build_leaderboard_url(league_id, DEFAULT_LEADERBOARD_GAMEDAY_PROBE, phase_id),
        timeout,
    )
    rows = ((payload.get("Data") or {}).get("Value")) or []
    return [
        {
            "team_id": row["temid"],
            "team_name": row["temname"],
            "social_id": row["usrscoid"],
        }
        for row in rows
    ]


def format_text_output(match_num: int, winners: dict[str, list[dict[str, object]]]) -> str:
    lines = [f"Match {match_num} player prize leaders"]
    for category, rows in winners.items():
        lines.append(f"\n{category}")
        if not rows:
            lines.append("  No matching players found")
            continue
        for row in rows:
            details = [
                f"{row['playerName']} - {int(row['effectivePoints']) if float(row['effectivePoints']).is_integer() else row['effectivePoints']} pts",
                row["leagueMemberName"] or row["leagueTeamName"],
            ]
            if row["captainOrViceCaptain"]:
                details.append(str(row["captainOrViceCaptain"]))
            if row["booster"]:
                details.append(str(row["booster"]))
            lines.append("  " + " | ".join(details))
    return "\n".join(lines)


def format_season_text_output(winners: dict[str, list[dict[str, object]]]) -> str:
    lines = ["All completed matches player prize leaders"]
    for category, rows in winners.items():
        lines.append(f"\n{category}")
        if not rows:
            lines.append("  No matching players found")
            continue
        for row in rows:
            details = [
                f"Match {row['matchNum']}",
                f"{row['playerName']} - {int(row['effectivePoints']) if float(row['effectivePoints']).is_integer() else row['effectivePoints']} pts",
                row["leagueTeamName"],
            ]
            if row["leagueMemberName"]:
                details.append(str(row["leagueMemberName"]))
            if row["captainOrViceCaptain"]:
                details.append(str(row["captainOrViceCaptain"]))
            if row["booster"]:
                details.append(str(row["booster"]))
            lines.append("  " + " | ".join(details))
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    session = build_session(resolve_cookie(args))
    participant_lookup = load_participant_lookup(Path(args.participants))
    teams = fetch_league_teams(session, args.league_id, args.phase_id, args.timeout)
    match_winners: dict[str, list[dict[str, object]]] | None = None
    season_winners: dict[str, list[dict[str, object]]] | None = None

    if args.match_num is not None:
        players_by_id = fetch_match_players(session, args.match_num, args.timeout)
        match_winners = build_category_winners(
            teams,
            players_by_id,
            participant_lookup,
            args.phase_id,
            args.match_num,
            session,
            args.timeout,
        )

    if args.all_matches_summary:
        completed_match_nums = load_completed_match_nums(Path(args.winners))
        season_winners = build_season_category_winners(
            teams,
            participant_lookup,
            args.phase_id,
            completed_match_nums,
            session,
            args.timeout,
        )

    if args.format == "json":
        print(
            json.dumps(
                {
                    "matchNum": args.match_num,
                    "matchCategories": match_winners,
                    "seasonCategories": season_winners,
                },
                indent=2,
            )
        )
        return

    output_parts: list[str] = []
    if match_winners is not None and args.match_num is not None:
        output_parts.append(format_text_output(args.match_num, match_winners))
    if season_winners is not None:
        output_parts.append(format_season_text_output(season_winners))
    print("\n\n".join(output_parts))


if __name__ == "__main__":
    main()