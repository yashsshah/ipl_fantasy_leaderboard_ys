from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from calculate_prizes import calculate_outputs


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_STANDINGS_URL = "https://www.espncricinfo.com/series/ipl-2026-1510719/points-table-standings"


CSV_FILES = [
    "Participants.csv",
    "PrizesList.csv",
    "MatchSchedule.csv",
    "TablePredictions.csv",
    "TableRankings.csv",
    "Leaderboard.csv",
    "PlayerBasedPrize.csv",
    "ParticipantGamedayPointsWide.csv",
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

STANDINGS_DISPLAY_TO_ABBREVIATION = {
    team_name.upper(): abbreviation
    for team_name, abbreviation in TEAM_ABBREVIATIONS.items()
}


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
    parser.add_argument(
        "--refresh-standings",
        action="store_true",
        help="Fetch the latest IPL standings from ESPNcricinfo and rewrite TableRankings.csv before syncing.",
    )
    parser.add_argument(
        "--standings-url",
        default=DEFAULT_STANDINGS_URL,
        help="Standings page URL used when --refresh-standings is enabled.",
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


def fetch_current_standings_from_espncricinfo(standings_url: str) -> list[dict[str, str]]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is required to refresh standings. Install it with 'pip install playwright' "
            "and install Chromium with 'python -m playwright install chromium'."
        ) from exc

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=False)
            page = browser.new_page()
            page.goto(standings_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
            page_text = page.locator("body").inner_text()
            browser.close()
    except PlaywrightError as exc:
        raise RuntimeError(
            f"Could not load standings page: {standings_url}."
        ) from exc

    lines = [line.strip() for line in page_text.splitlines() if line.strip()]
    try:
        teams_index = lines.index("Teams")
    except ValueError as exc:
        raise RuntimeError(
            "Could not find the standings table on the ESPNcricinfo page."
        ) from exc

    standings_rows: list[dict[str, str]] = []
    for index in range(teams_index + 1, len(lines) - 1):
        rank_text = lines[index]
        team_display_name = lines[index + 1]
        if not rank_text.isdigit():
            continue

        team_abbreviation = STANDINGS_DISPLAY_TO_ABBREVIATION.get(team_display_name)
        if team_abbreviation is None:
            continue

        standings_rows.append(
            {
                "Rank": rank_text,
                "IPLTeamName": team_abbreviation,
            }
        )
        if len(standings_rows) == len(STANDINGS_DISPLAY_TO_ABBREVIATION):
            break

    if len(standings_rows) != len(STANDINGS_DISPLAY_TO_ABBREVIATION):
        raise RuntimeError(
            "Parsed an incomplete standings table from ESPNcricinfo. "
            f"Expected {len(STANDINGS_DISPLAY_TO_ABBREVIATION)} teams, found {len(standings_rows)}."
        )

    return standings_rows


def write_table_rankings_csv(root: Path, standings_rows: list[dict[str, str]]) -> None:
    output_path = root / "TableRankings.csv"
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Rank", "IPLTeamName"])
        writer.writeheader()
        writer.writerows(standings_rows)


def normalize_lookup_key(value: str | None) -> str | None:
    normalized = clean(value)
    return normalized.casefold() if normalized is not None else None


def format_csv_number(value: int | float | None) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def build_match_details(home_team: str | None, away_team: str | None) -> str | None:
    home_name = clean(home_team)
    away_name = clean(away_team)
    if home_name is None or away_name is None:
        return None
    try:
        return f"{TEAM_ABBREVIATIONS[home_name]} vs {TEAM_ABBREVIATIONS[away_name]}"
    except KeyError as exc:
        missing_team = exc.args[0]
        raise ValueError(f"Missing team abbreviation for: {missing_team}") from exc


def build_display_name_lookup(participants_rows: list[dict[str, str]]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for row in participants_rows:
        member_name = clean(row.get("LeagueMemberName"))
        if member_name is None:
            continue

        team_name = clean(row.get("LeagueTeamName"))
        member_key = normalize_lookup_key(member_name)
        team_key = normalize_lookup_key(team_name)

        if team_key is not None:
            lookup[team_key] = member_name
        if member_key is not None:
            lookup.setdefault(member_key, member_name)

    return lookup


def build_match_day_score_rows_from_wide(
    participants_rows: list[dict[str, str]],
    schedule_rows: list[dict[str, str]],
    wide_rows: list[dict[str, str]],
) -> tuple[list[str], list[dict[str, str]]]:
    member_columns = [
        row["LeagueMemberName"].strip()
        for row in participants_rows
        if clean(row.get("LeagueMemberName"))
    ]
    display_name_lookup = build_display_name_lookup(participants_rows)
    scores_by_member: dict[str, dict[int, str]] = {member_name: {} for member_name in member_columns}

    for wide_row in wide_rows:
        display_name = clean(wide_row.get("display_name"))
        if display_name is None:
            continue

        lookup_key = normalize_lookup_key(display_name)
        member_name = display_name_lookup.get(lookup_key or "")
        if member_name is None:
            raise ValueError(
                "Could not map ParticipantGamedayPointsWide display name "
                f"'{display_name}' to a LeagueMemberName via Participants.csv"
            )

        for column_name, raw_value in wide_row.items():
            if not column_name.startswith("GD"):
                continue
            gameday = int(column_name.removeprefix("GD"))
            scores_by_member[member_name][gameday] = format_csv_number(parse_number(raw_value))

    score_rows: list[dict[str, str]] = []
    for schedule_row in schedule_rows:
        raw_match_num = clean(schedule_row.get("MatchNum"))
        if raw_match_num is None:
            continue

        match_num = int(raw_match_num)
        row = {
            "MatchNum": str(match_num),
            "MatchDetails": build_match_details(
                schedule_row.get("HomeTeamName"),
                schedule_row.get("AwayTeamName"),
            ) or "",
        }
        for member_name in member_columns:
            row[member_name] = scores_by_member.get(member_name, {}).get(match_num, "")
        score_rows.append(row)

    return member_columns, score_rows


def write_match_day_scores_csv(root: Path) -> None:
    participants_rows = [
        row for row in read_csv(root, "Participants.csv")
        if clean(row.get("LeagueMemberName"))
    ]
    schedule_rows = read_csv(root, "MatchSchedule.csv")
    wide_rows = read_csv(root, "ParticipantGamedayPointsWide.csv")

    member_columns, score_rows = build_match_day_score_rows_from_wide(
        participants_rows,
        schedule_rows,
        wide_rows,
    )

    output_path = root / "MatchDayScores.csv"
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["MatchNum", "MatchDetails", *member_columns],
        )
        writer.writeheader()
        writer.writerows(score_rows)


def build_leaderboard_rows_from_wide(
    participants_rows: list[dict[str, str]],
    wide_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    display_name_lookup = build_display_name_lookup(participants_rows)
    team_name_by_member = {
        row["LeagueMemberName"].strip(): clean(row.get("LeagueTeamName")) or ""
        for row in participants_rows
        if clean(row.get("LeagueMemberName"))
    }

    totals_by_member: dict[str, int | float] = {
        member_name: 0 for member_name in team_name_by_member
    }

    for wide_row in wide_rows:
        display_name = clean(wide_row.get("display_name"))
        if display_name is None:
            continue

        lookup_key = normalize_lookup_key(display_name)
        member_name = display_name_lookup.get(lookup_key or "")
        if member_name is None:
            raise ValueError(
                "Could not map ParticipantGamedayPointsWide display name "
                f"'{display_name}' to a LeagueMemberName via Participants.csv"
            )

        total_points = parse_number(wide_row.get("TOTAL"))
        if total_points is None:
            total_points = sum(
                float(parse_number(raw_value) or 0)
                for column_name, raw_value in wide_row.items()
                if column_name.startswith("GD")
            )

        totals_by_member[member_name] = normalize_amount(float(total_points))

    ranked_rows = sorted(
        (
            {
                "LeagueMemberName": member_name,
                "LeagueTeamName": team_name_by_member.get(member_name, ""),
                "TotalPoints": totals_by_member.get(member_name, 0),
            }
            for member_name in team_name_by_member
        ),
        key=lambda row: (-float(row["TotalPoints"]), row["LeagueMemberName"]),
    )

    leaderboard_rows: list[dict[str, str]] = []
    index = 0
    position = 1
    while index < len(ranked_rows):
        current_points = ranked_rows[index]["TotalPoints"]
        tied_group = [ranked_rows[index]]
        index += 1
        while index < len(ranked_rows) and ranked_rows[index]["TotalPoints"] == current_points:
            tied_group.append(ranked_rows[index])
            index += 1

        for tied_row in tied_group:
            leaderboard_rows.append(
                {
                    "Rank": str(position),
                    "LeagueMemberName": tied_row["LeagueMemberName"],
                    "LeagueTeamName": tied_row["LeagueTeamName"],
                    "TotalPoints": format_csv_number(tied_row["TotalPoints"]),
                }
            )

        position += len(tied_group)

    return leaderboard_rows


def write_leaderboard_csv(root: Path) -> None:
    participants_rows = [
        row for row in read_csv(root, "Participants.csv")
        if clean(row.get("LeagueMemberName"))
    ]
    wide_rows = read_csv(root, "ParticipantGamedayPointsWide.csv")
    leaderboard_rows = build_leaderboard_rows_from_wide(participants_rows, wide_rows)

    output_path = root / "Leaderboard.csv"
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["Rank", "LeagueMemberName", "LeagueTeamName", "TotalPoints"],
        )
        writer.writeheader()
        writer.writerows(leaderboard_rows)


def write_prize_csvs(root: Path) -> None:
    calculate_outputs(
        root / "MatchDayScores.csv",
        root / "MatchSchedule.csv",
        root / "Participants.csv",
        root / "PrizesList.csv",
        root / "MatchDayWinners.csv",
        root / "BonusPrizes.csv",
    )


def split_combined_names(value: str | None) -> list[str]:
    normalized = clean(value)
    if normalized is None:
        return []
    return [item.strip() for item in normalized.split(" / ") if item.strip()]


def normalize_amount(value: float) -> int | float:
    rounded = round(value, 2)
    return int(rounded) if float(rounded).is_integer() else rounded


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


def format_position_label(position: int) -> str:
    if 10 <= position % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(position % 10, "th")
    return f"{position}{suffix}"


def build_participant_prize_summary(
    participants_rows: list[dict[str, str]],
    leaderboard_rows: list[dict[str, str]],
    match_day_winner_rows: list[dict[str, str]],
    bonus_rows: list[dict[str, str]],
    prizes_rows: list[dict[str, str]],
) -> list[dict[str, object]]:
    summary_lookup: dict[str, dict[str, object]] = {}

    def ensure_entry(name: str, team_name: str | None = None) -> dict[str, object]:
        entry = summary_lookup.get(name)
        if entry is None:
            entry = {
                "leagueMemberName": name,
                "leagueTeamName": team_name,
                "lockedPrizeAmount": 0,
                "potentialPrizeAmount": 0,
                "lockedDailyWinnerAmount": 0,
                "potentialOverallPrizeAmount": 0,
                "potentialBonusPrizeAmount": 0,
                "lockedBreakdown": [],
                "potentialBreakdown": [],
            }
            summary_lookup[name] = entry
        elif team_name and not entry.get("leagueTeamName"):
            entry["leagueTeamName"] = team_name
        return entry

    for participant in participants_rows:
        name = clean(participant.get("LeagueMemberName"))
        if name is None:
            continue
        ensure_entry(name, clean(participant.get("LeagueTeamName")))

    for winner_row in match_day_winner_rows:
        prize_amount = parse_number(winner_row.get("PrizeAmount"))
        if prize_amount is None:
            continue
        member_names = split_combined_names(winner_row.get("LeagueMemberName"))
        team_name = clean(winner_row.get("LeagueTeamName"))
        for member_name in member_names:
            entry = ensure_entry(member_name, team_name)
            entry["lockedPrizeAmount"] = normalize_amount(entry["lockedPrizeAmount"] + prize_amount)
            entry["lockedDailyWinnerAmount"] = normalize_amount(entry["lockedDailyWinnerAmount"] + prize_amount)
            entry["lockedBreakdown"].append(
                {
                    "prizeType": "daily-winner",
                    "label": f"Match {winner_row.get('MatchNum')} winner",
                    "matchNum": parse_number(winner_row.get("MatchNum")),
                    "matchDetails": clean(winner_row.get("MatchDetails")),
                    "amount": prize_amount,
                    "status": "locked",
                }
            )

    overall_prizes_by_position: dict[int, int | float] = {}
    for prize_row in prizes_rows:
        if clean(prize_row.get("PrizeCategory")) != "overall-leaderboard":
            continue
        if clean(prize_row.get("PrizeStatusRule")) != "potential":
            continue
        position = parse_number(prize_row.get("PrizePosition"))
        amount = parse_number(prize_row.get("PrizeAmount"))
        if position is None or amount is None:
            continue
        overall_prizes_by_position[int(position)] = amount

    ranked_rows = [
        {
            "leagueMemberName": clean(row.get("LeagueMemberName")),
            "leagueTeamName": clean(row.get("LeagueTeamName")),
            "totalPoints": parse_number(row.get("TotalPoints")),
        }
        for row in leaderboard_rows
        if clean(row.get("LeagueMemberName")) and parse_number(row.get("TotalPoints")) is not None
    ]
    ranked_rows.sort(key=lambda row: float(row["totalPoints"]), reverse=True)

    leaderboard_index = 0
    leaderboard_position = 1
    while leaderboard_index < len(ranked_rows):
        current_points = ranked_rows[leaderboard_index]["totalPoints"]
        tied_group = [ranked_rows[leaderboard_index]]
        leaderboard_index += 1
        while leaderboard_index < len(ranked_rows) and ranked_rows[leaderboard_index]["totalPoints"] == current_points:
            tied_group.append(ranked_rows[leaderboard_index])
            leaderboard_index += 1

        start_position = leaderboard_position
        end_position = leaderboard_position + len(tied_group) - 1
        prize_pool = sum(overall_prizes_by_position.get(position, 0) for position in range(start_position, end_position + 1))

        if prize_pool:
            split_amount = normalize_amount(prize_pool / len(tied_group))
            if start_position == end_position:
                label = f"Current {format_position_label(start_position)} place"
            else:
                label = f"Current tie for {format_position_label(start_position)} to {format_position_label(end_position)}"

            for ranked_row in tied_group:
                member_name = ranked_row["leagueMemberName"]
                if member_name is None:
                    continue
                entry = ensure_entry(member_name, ranked_row["leagueTeamName"])
                entry["potentialPrizeAmount"] = normalize_amount(entry["potentialPrizeAmount"] + split_amount)
                entry["potentialOverallPrizeAmount"] = normalize_amount(entry["potentialOverallPrizeAmount"] + split_amount)
                entry["potentialBreakdown"].append(
                    {
                        "prizeType": "overall-leaderboard",
                        "label": label,
                        "amount": split_amount,
                        "status": "potential",
                    }
                )

        leaderboard_position += len(tied_group)

    for bonus_row in bonus_rows:
        prize_amount = parse_number(bonus_row.get("PrizeAmount"))
        member_names = split_combined_names(bonus_row.get("LeagueMemberName"))
        if prize_amount is None or not member_names:
            continue

        split_amount = normalize_amount(prize_amount / len(member_names))
        for member_name in member_names:
            entry = ensure_entry(member_name, clean(bonus_row.get("LeagueTeamName")))
            entry["potentialPrizeAmount"] = normalize_amount(entry["potentialPrizeAmount"] + split_amount)
            entry["potentialBonusPrizeAmount"] = normalize_amount(entry["potentialBonusPrizeAmount"] + split_amount)
            entry["potentialBreakdown"].append(
                {
                    "prizeType": "bonus",
                    "label": clean(bonus_row.get("PrizeName")) or "Bonus Prize",
                    "matchNum": parse_number_or_text(bonus_row.get("MatchNum")),
                    "matchDetails": clean(bonus_row.get("MatchDetails")),
                    "amount": split_amount,
                    "status": "potential",
                }
            )

    ordered_names = [clean(row.get("LeagueMemberName")) for row in participants_rows if clean(row.get("LeagueMemberName"))]
    ordered_entries = [summary_lookup[name] for name in ordered_names if name in summary_lookup]

    extra_entries = [
        entry for name, entry in summary_lookup.items() if name not in ordered_names
    ]
    extra_entries.sort(key=lambda entry: entry["leagueMemberName"])

    return ordered_entries + extra_entries


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
    bonus_rows = read_csv(root, "BonusPrizes.csv")
    prizes_rows = read_csv(root, "PrizesList.csv")

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
        "participantPrizeSummary": build_participant_prize_summary(
            participants_rows,
            leaderboard_rows,
            match_day_winner_rows,
            bonus_rows,
            prizes_rows,
        ),
        "prizesList": [
            {
                "prizeName": clean(row.get("PrizeName")),
                "prizeAmount": parse_number(row.get("PrizeAmount")),
                "prizeCount": parse_number(row.get("PrizeCount")),
                "prizeTotalAmount": parse_number(row.get("PrizeTotalAmount")),
                "totalPotAmount": parse_number(row.get("TotalPotAmount")),
                "differenceAmount": parse_number(row.get("DifferenceAmount")),
                "prizeCategory": clean(row.get("PrizeCategory")),
                "prizeStatusRule": clean(row.get("PrizeStatusRule")),
                "prizePosition": parse_number(row.get("PrizePosition")),
            }
            for row in prizes_rows
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
            for row in bonus_rows
        ],
    }


def write_data(output_path: Path, data: dict[str, object]) -> None:
    output_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def sync_once(root: Path, output_path: Path, refresh_standings: bool = False, standings_url: str = DEFAULT_STANDINGS_URL) -> None:
    if refresh_standings:
        standings_rows = fetch_current_standings_from_espncricinfo(standings_url)
        write_table_rankings_csv(root, standings_rows)
    write_match_day_scores_csv(root)
    write_leaderboard_csv(root)
    write_prize_csvs(root)
    data = build_synced_data(root, output_path)
    write_data(output_path, data)

def run_sync_pipeline(
    root: Path = DATA_DIR,
    output_path: Path = PROJECT_ROOT / "data.json",
    refresh_standings: bool = False,
    standings_url: str = DEFAULT_STANDINGS_URL,
) -> None:
    sync_once(root, output_path, refresh_standings=refresh_standings, standings_url=standings_url)


def get_mtimes(root: Path) -> tuple[int, ...]:
    return tuple((root / name).stat().st_mtime_ns for name in CSV_FILES)


def watch(root: Path, output_path: Path, interval: float, refresh_standings: bool = False, standings_url: str = DEFAULT_STANDINGS_URL) -> None:
    last_state: tuple[int, ...] | None = None
    while True:
        current_state = get_mtimes(root)
        if current_state != last_state:
            sync_once(root, output_path, refresh_standings=refresh_standings, standings_url=standings_url)
            print(f"Synced CSV data into {output_path.name}")
            last_state = current_state
        time.sleep(interval)


def main() -> None:
    args = parse_args()
    root = Path(args.root).resolve()
    output_path = Path(args.output).resolve()

    if args.watch:
        watch(
            root,
            output_path,
            args.interval,
            refresh_standings=args.refresh_standings,
            standings_url=args.standings_url,
        )
        return

    run_sync_pipeline(
        root,
        output_path,
        refresh_standings=args.refresh_standings,
        standings_url=args.standings_url,
    )
    print(f"Synced CSV data into {output_path.name}")


if __name__ == "__main__":
    main()