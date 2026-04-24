from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path

from auth_cookie import DEFAULT_COOKIE_PATH, capture_cookie_via_browser, load_saved_cookie
from scrape_participant_gameday_points import (
    DATA_DIR as SCRAPE_DATA_DIR,
    DEFAULT_DELAY,
    DEFAULT_LEAGUE_ID,
    DEFAULT_LEADERBOARD_GAMEDAY_PROBE,
    DEFAULT_TIMEOUT,
    build_session,
    fetch_json,
    fetch_leaderboard,
    build_team_detail_url,
    run_scrape_pipeline,
)
from sync_csvs_to_data_json import DEFAULT_STANDINGS_URL, PROJECT_ROOT, run_sync_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Reuse or capture an IPL fantasy cookie, scrape fresh participant score "
            "data, and regenerate all derived CSV and JSON outputs."
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
        help="Optional latest gameday to fetch. If omitted, the scraper auto-detects it.",
    )
    parser.add_argument(
        "--phase-id",
        type=int,
        default=1,
        help="Tournament phase ID for the API requests.",
    )
    parser.add_argument(
        "--participants",
        default=str(SCRAPE_DATA_DIR / "Participants.csv"),
        help="Path to Participants.csv used to map team names to league member names.",
    )
    parser.add_argument(
        "--scores-output",
        default=str(SCRAPE_DATA_DIR / "ParticipantGamedayPoints.csv"),
        help="Path for the long-format scraped scores CSV.",
    )
    parser.add_argument(
        "--wide-output",
        default=str(SCRAPE_DATA_DIR / "ParticipantGamedayPointsWide.csv"),
        help="Path for the wide-format scraped scores CSV.",
    )
    parser.add_argument(
        "--data-root",
        default=str(SCRAPE_DATA_DIR),
        help="Directory containing the league CSV files used by the sync step.",
    )
    parser.add_argument(
        "--data-json",
        default=str(PROJECT_ROOT / "data.json"),
        help="Path to the output data.json file.",
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
        "--full-refresh",
        action="store_true",
        help="Ignore any existing scraped scores and rebuild all gamedays from scratch.",
    )
    parser.add_argument(
        "--cookie",
        help="Optional Cookie header value. If omitted, the script prompts for it.",
    )
    parser.add_argument(
        "--saved-cookie-path",
        default=str(DEFAULT_COOKIE_PATH),
        help="Path to the locally saved IPL fantasy cookie used for reuse across runs.",
    )
    parser.add_argument(
        "--browser-login",
        action="store_true",
        help="Launch a browser login flow before scraping and refresh the saved cookie.",
    )
    parser.add_argument(
        "--no-browser-login",
        action="store_true",
        help="Disable automatic browser fallback when no valid cookie is available.",
    )
    parser.add_argument(
        "--no-refresh-standings",
        action="store_true",
        help="Skip the ESPNcricinfo standings refresh and only rebuild derived files from local CSV inputs.",
    )
    parser.add_argument(
        "--standings-url",
        default=DEFAULT_STANDINGS_URL,
        help="Standings page URL used when refreshing TableRankings.csv during the sync step.",
    )
    return parser.parse_args()


def prompt_for_cookie(default_cookie: str | None) -> str:
    prompt = "Paste the IPL fantasy Cookie header value (input hidden): "
    if default_cookie:
        prompt = (
            "Paste the IPL fantasy Cookie header value (input hidden, press Enter to use "
            "IPL_FANTASY_COOKIE): "
        )

    while True:
        cookie = getpass.getpass(prompt).strip()
        if cookie:
            return cookie
        if default_cookie:
            return default_cookie
        print("A cookie value is required to call the authenticated IPL fantasy API.")


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
        if not teams:
            return False

        first_team = teams[0]
        fetch_json(
            session,
            build_team_detail_url(first_team["team_id"], first_team["social_id"], phase_id),
            timeout,
        )
        return True
    except Exception:
        return False


def resolve_cookie(args: argparse.Namespace) -> str:
    explicit_cookie = args.cookie.strip() if args.cookie else None
    env_cookie = os.environ.get("IPL_FANTASY_COOKIE")
    saved_cookie = load_saved_cookie(Path(args.saved_cookie_path))

    if explicit_cookie:
        return explicit_cookie

    if args.browser_login:
        print("Launching browser login to refresh the IPL fantasy cookie...")
        cookie = capture_cookie_via_browser(Path(args.saved_cookie_path))
        if validate_cookie(cookie, args.league_id, args.phase_id, args.timeout):
            print(f"Saved fresh IPL fantasy cookie to {args.saved_cookie_path}.")
            return cookie
        print("Browser login completed, but the captured cookie did not validate.")

    candidates: list[tuple[str, str | None]] = [
        ("IPL_FANTASY_COOKIE", env_cookie),
        (str(Path(args.saved_cookie_path)), saved_cookie),
    ]
    for label, candidate in candidates:
        if not candidate:
            continue
        if validate_cookie(candidate, args.league_id, args.phase_id, args.timeout):
            print(f"Using saved IPL fantasy cookie from {label}.")
            return candidate
        print(f"Saved IPL fantasy cookie from {label} is no longer valid.")

    if not args.no_browser_login:
        try:
            print("Launching browser login to capture a fresh IPL fantasy cookie...")
            cookie = capture_cookie_via_browser(Path(args.saved_cookie_path))
            if validate_cookie(cookie, args.league_id, args.phase_id, args.timeout):
                print(f"Saved fresh IPL fantasy cookie to {args.saved_cookie_path}.")
                return cookie
            print("Browser login completed, but the captured cookie did not validate.")
        except RuntimeError as exc:
            print(exc)

    return prompt_for_cookie(None)


def main() -> None:
    args = parse_args()
    cookie = resolve_cookie(args)

    participants_path = Path(args.participants)
    scores_output_path = Path(args.scores_output)
    wide_output_path = Path(args.wide_output)
    data_root = Path(args.data_root)
    data_json_path = Path(args.data_json)

    print("Starting IPL fantasy update...")
    run_scrape_pipeline(
        league_id=args.league_id,
        gameday_id=args.gameday_id,
        phase_id=args.phase_id,
        delay=args.delay,
        timeout=args.timeout,
        cookie=cookie,
        participants_path=participants_path,
        scores_output_path=scores_output_path,
        wide_output_path=wide_output_path,
        full_refresh=args.full_refresh,
    )

    print("\nRegenerating derived CSVs and data.json...")
    run_sync_pipeline(
        data_root,
        data_json_path,
        refresh_standings=not args.no_refresh_standings,
        standings_url=args.standings_url,
    )
    print("\nUpdate complete.")


if __name__ == "__main__":
    main()