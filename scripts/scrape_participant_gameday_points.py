from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
import time

import pandas as pd
import requests


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_LEAGUE_ID = "59290110"
DEFAULT_TIMEOUT = 30
DEFAULT_DELAY = 0.5
DEFAULT_LEADERBOARD_GAMEDAY_PROBE = 100
AUTO_GAMEDAY_EMPTY_STREAK = 3
USER_AGENT = "ipl-fantasy-scraper/1.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Scrape per-gameday IPL fantasy scores for all teams in the league and "
            "optionally map them to participant names from Participants.csv."
        )
    )
    parser.add_argument(
        "--league-id",
        default=DEFAULT_LEAGUE_ID,
        help="League ID used by the IPL fantasy leaderboard API.",
    )
    parser.add_argument(
        "--gameday-id",
        type=int,
        help=(
            "Optional latest gameday to fetch. If omitted, the scraper auto-detects "
            "the highest real gameday from the team detail API."
        ),
    )
    parser.add_argument(
        "--phase-id",
        type=int,
        default=1,
        help="Tournament phase ID for the API requests.",
    )
    parser.add_argument(
        "--participants",
        default=str(DATA_DIR / "Participants.csv"),
        help="Path to Participants.csv used to map team names to league member names.",
    )
    parser.add_argument(
        "--scores-output",
        default=str(DATA_DIR / "ParticipantGamedayPoints.csv"),
        help="Path for the long-format output CSV.",
    )
    parser.add_argument(
        "--wide-output",
        default=str(DATA_DIR / "ParticipantGamedayPointsWide.csv"),
        help="Path for the wide-format output CSV.",
    )
    parser.add_argument(
        "--full-refresh",
        action="store_true",
        help="Ignore any existing scraped CSV and rebuild all gamedays from scratch.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help="Delay in seconds between team detail requests.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--cookie",
        default=os.environ.get("IPL_FANTASY_COOKIE"),
        help=(
            "Optional Cookie header value for authenticated API access. "
            "Can also be provided via IPL_FANTASY_COOKIE environment variable."
        ),
    )
    return parser.parse_args()


def build_leaderboard_url(league_id: str, gameday_id: int, phase_id: int) -> str:
    return (
        f"https://fantasy.iplt20.com/classic/api/user/leagues/{league_id}/leaderboard"
        f"?optType=1&gamedayId={gameday_id}&phaseId={phase_id}&pageNo=1&topNo=100"
        f"&pageChunk=100&pageOneChunk=100&minCount=15&leagueId={league_id}"
    )


def build_team_detail_url(team_id: int | str, social_id: int | str, phase_id: int) -> str:
    return (
        "https://fantasy.iplt20.com/classic/api/user/guid/lb-team/overall-get"
        f"?optType=1&teamgamedayId=1&arrtourGamedayId=1&phaseId={phase_id}"
        f"&teamId={team_id}&SocialId={social_id}"
    )


def build_session(cookie: str | None) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
    )
    if cookie:
        session.headers["Cookie"] = cookie
    return session


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
                lookup[team_name] = member_name

    return lookup


def load_existing_scores(scores_output_path: Path) -> list[dict[str, object]]:
    if not scores_output_path.exists():
        return []

    with scores_output_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows: list[dict[str, object]] = []
        for row in reader:
            team_name = (row.get("team_name") or "").strip()
            team_id = (row.get("team_id") or "").strip()
            gameday = (row.get("gameday") or "").strip()
            points = (row.get("points") or "").strip()
            if not team_name or not team_id or not gameday or not points:
                continue
            rows.append(
                {
                    "team_name": team_name,
                    "team_id": int(team_id),
                    "gameday": int(gameday),
                    "points": float(points),
                }
            )

    return rows


def merge_rows(
    existing_rows: list[dict[str, object]],
    new_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    merged: dict[tuple[int, int], dict[str, object]] = {
        (int(row["team_id"]), int(row["gameday"])): row for row in existing_rows
    }
    for row in new_rows:
        merged[(int(row["team_id"]), int(row["gameday"]))] = row
    return list(merged.values())


def fetch_json(session: requests.Session, url: str, timeout: float) -> dict:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    payload = response.json()

    meta = payload.get("Meta") or {}
    if payload.get("Data") is None and meta.get("Success") is False:
        message = meta.get("Message") or "Unknown API failure"
        raise RuntimeError(
            "IPL API request failed. "
            f"Message: {message}. "
            "This API may require an authenticated Cookie header. "
            "Pass --cookie '<cookie-value>' or set IPL_FANTASY_COOKIE."
        )

    return payload


def fetch_leaderboard(
    session: requests.Session,
    league_id: str,
    gameday_id: int,
    phase_id: int,
    timeout: float,
) -> list[dict[str, object]]:
    print("Fetching leaderboard...")
    data = fetch_json(session, build_leaderboard_url(league_id, gameday_id, phase_id), timeout)

    teams: list[dict[str, object]] = []
    for entry in data["Data"]["Value"]:
        teams.append(
            {
                "rank": entry["rno"],
                "team_id": entry["temid"],
                "team_name": entry["temname"],
                "social_id": entry["usrscoid"],
                "total_points": float(entry["points"]),
            }
        )

    print(f"  Found {len(teams)} teams in league.")
    return teams


def fetch_team_gameday_scores(
    session: requests.Session,
    team: dict[str, object],
    start_gameday_id: int,
    latest_gameday_id: int | None,
    phase_id: int,
    timeout: float,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    gameday_id = start_gameday_id
    empty_streak = 0
    max_gameday_id = latest_gameday_id or DEFAULT_LEADERBOARD_GAMEDAY_PROBE

    while gameday_id <= max_gameday_id:
        url = build_team_detail_url(team["team_id"], team["social_id"], phase_id)
        url = url.replace("teamgamedayId=1", f"teamgamedayId={gameday_id}")
        url = url.replace("arrtourGamedayId=1", f"arrtourGamedayId={gameday_id}")
        data = fetch_json(session, url, timeout)

        value = ((data.get("Data") or {}).get("Value") or {})
        gdpts = value.get("gdpts") or []
        if not gdpts:
            if latest_gameday_id is None and rows:
                empty_streak += 1
                if empty_streak >= AUTO_GAMEDAY_EMPTY_STREAK:
                    break
            gameday_id += 1
            continue

        gameday_row = gdpts[0]
        empty_streak = 0
        rows.append(
            {
                "team_name": team["team_name"],
                "team_id": team["team_id"],
                "gameday": int(gameday_row["gdid"]),
                "points": float(gameday_row["gdpts"]),
            }
        )
        gameday_id += 1

    if not rows:
        print(f"  WARNING: No gameday points returned for {team['team_name']}")

    return rows


def scrape_all(
    league_id: str,
    gameday_id: int | None,
    phase_id: int,
    delay: float,
    timeout: float,
    cookie: str | None,
    existing_rows: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    session = build_session(cookie)
    leaderboard_gameday_id = gameday_id or DEFAULT_LEADERBOARD_GAMEDAY_PROBE
    teams = fetch_leaderboard(session, league_id, leaderboard_gameday_id, phase_id, timeout)
    all_rows: list[dict[str, object]] = []
    discovered_gameday_ids: set[int] = set()
    existing_gamedays_by_team_id: dict[int, set[int]] = {}

    for row in existing_rows:
        team_id = int(row["team_id"])
        existing_gamedays_by_team_id.setdefault(team_id, set()).add(int(row["gameday"]))

    for team in teams:
        team_id = int(team["team_id"])
        existing_gamedays = existing_gamedays_by_team_id.get(team_id, set())
        start_gameday_id = max(existing_gamedays) if existing_gamedays else 1

        if existing_gamedays:
            print(
                f"  Fetching scores for: {team['team_name']} (id={team['team_id']}) "
                f"from GD{start_gameday_id}"
            )
        else:
            print(f"  Fetching scores for: {team['team_name']} (id={team['team_id']})")

        rows = fetch_team_gameday_scores(
            session,
            team,
            start_gameday_id,
            gameday_id,
            phase_id,
            timeout,
        )
        new_rows = [row for row in rows if int(row["gameday"]) not in existing_gamedays]
        print(f"    -> {len(new_rows)} new gamedays found")
        all_rows.extend(new_rows)
        discovered_gameday_ids.update(int(row["gameday"]) for row in new_rows)
        time.sleep(delay)

    if gameday_id is None and discovered_gameday_ids:
        print(
            "Auto-detected latest gameday: "
            f"GD{max(discovered_gameday_ids)}"
        )
    elif gameday_id is None and existing_rows:
        latest_existing_gameday = max(int(row["gameday"]) for row in existing_rows)
        print(f"No new gamedays found beyond GD{latest_existing_gameday}")

    return teams, all_rows


def save_outputs(
    teams: list[dict[str, object]],
    all_rows: list[dict[str, object]],
    participant_lookup: dict[str, str],
    scores_output_path: Path,
    wide_output_path: Path,
) -> None:
    if not all_rows:
        print("No data to save.")
        return

    df_long = pd.DataFrame(all_rows)
    df_long["league_member_name"] = df_long["team_name"].map(participant_lookup)
    df_long["display_name"] = df_long["league_member_name"].fillna(df_long["team_name"])
    df_long = df_long.sort_values(["gameday", "points"], ascending=[True, False])

    scores_output_path.parent.mkdir(parents=True, exist_ok=True)
    wide_output_path.parent.mkdir(parents=True, exist_ok=True)

    df_long.to_csv(scores_output_path, index=False)
    print(f"\nSaved {scores_output_path} ({len(df_long)} rows)")

    df_wide = df_long.pivot(index="display_name", columns="gameday", values="points")
    df_wide.columns = [f"GD{column}" for column in df_wide.columns]
    df_wide["TOTAL"] = df_wide.sum(axis=1)
    df_wide = df_wide.sort_values("TOTAL", ascending=False)
    df_wide.to_csv(wide_output_path)
    print(f"Saved {wide_output_path} ({len(df_wide)} teams x {len(df_wide.columns)} columns)")

    leaderboard = pd.DataFrame(teams)[["rank", "team_name", "total_points"]]
    print("\n-- Current Standings ------------------------------")
    print(leaderboard.to_string(index=False))


def run_scrape_pipeline(
    league_id: str = DEFAULT_LEAGUE_ID,
    gameday_id: int | None = None,
    phase_id: int = 1,
    delay: float = DEFAULT_DELAY,
    timeout: float = DEFAULT_TIMEOUT,
    cookie: str | None = None,
    participants_path: Path = DATA_DIR / "Participants.csv",
    scores_output_path: Path = DATA_DIR / "ParticipantGamedayPoints.csv",
    wide_output_path: Path = DATA_DIR / "ParticipantGamedayPointsWide.csv",
    full_refresh: bool = False,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    participant_lookup = load_participant_lookup(participants_path)
    existing_rows: list[dict[str, object]] = []
    if not full_refresh:
        existing_rows = load_existing_scores(scores_output_path)
        if existing_rows:
            max_existing_gameday = max(int(row["gameday"]) for row in existing_rows)
            print(
                f"Loaded {len(existing_rows)} existing rows from {scores_output_path} "
                f"through GD{max_existing_gameday}"
            )

    teams, new_rows = scrape_all(
        league_id=league_id,
        gameday_id=gameday_id,
        phase_id=phase_id,
        delay=delay,
        timeout=timeout,
        cookie=cookie,
        existing_rows=existing_rows,
    )
    merged_rows = merge_rows(existing_rows, new_rows)
    save_outputs(
        teams,
        merged_rows,
        participant_lookup,
        scores_output_path,
        wide_output_path,
    )
    return teams, merged_rows


def main() -> None:
    args = parse_args()
    run_scrape_pipeline(
        league_id=args.league_id,
        gameday_id=args.gameday_id,
        phase_id=args.phase_id,
        delay=args.delay,
        timeout=args.timeout,
        cookie=args.cookie,
        participants_path=Path(args.participants),
        scores_output_path=Path(args.scores_output),
        wide_output_path=Path(args.wide_output),
        full_refresh=args.full_refresh,
    )
    print("\nDone!")


if __name__ == "__main__":
    main()