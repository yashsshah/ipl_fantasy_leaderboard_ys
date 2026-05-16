from __future__ import annotations

import argparse
import base64
import csv
from datetime import datetime
import os
from pathlib import Path
import smtplib
import subprocess
import sys
from email.message import EmailMessage
from urllib import parse, request


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGET_BRANCH = "main"
DEFAULT_GENERATED_PATHS = ("data", "data.json")
DEFAULT_UPDATE_TIMEOUT_SECONDS = 1800
DEFAULT_NOTIFICATION_ENV_PATH = PROJECT_ROOT / ".local" / "daily_updater.env"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the IPL updater, stage generated data changes, commit them, and fast-forward merge into main."
        )
    )
    parser.add_argument(
        "--repo-root",
        default=str(PROJECT_ROOT),
        help="Path to the git repository root.",
    )
    parser.add_argument(
        "--target-branch",
        default=DEFAULT_TARGET_BRANCH,
        help="Branch that should receive the generated update commit.",
    )
    parser.add_argument(
        "--skip-merge",
        action="store_true",
        help="Commit generated data changes on the current branch but skip the merge into the target branch.",
    )
    parser.add_argument(
        "--push-target",
        action="store_true",
        help="Push the target branch to origin after a successful commit and merge.",
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Allow the run to continue even if the repository has tracked changes before the update starts.",
    )
    parser.add_argument(
        "--update-timeout-seconds",
        type=int,
        default=DEFAULT_UPDATE_TIMEOUT_SECONDS,
        help="Maximum wall-clock time allowed for scripts/update_league_data.py. Use 0 to disable.",
    )
    parser.add_argument(
        "update_args",
        nargs=argparse.REMAINDER,
        help="Arguments forwarded to scripts/update_league_data.py. Prefix forwarded flags with '--'.",
    )
    return parser.parse_args()


def run_command(
    command: list[str],
    cwd: Path,
    capture_output: bool = False,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        check=True,
        capture_output=capture_output,
        timeout=timeout,
    )


def git_output(repo_root: Path, *args: str) -> str:
    result = run_command(["git", *args], cwd=repo_root, capture_output=True)
    return result.stdout.strip()


def has_tracked_changes(repo_root: Path) -> bool:
    status = git_output(repo_root, "status", "--porcelain", "--untracked-files=no")
    return bool(status)


def get_current_branch(repo_root: Path) -> str:
    return git_output(repo_root, "rev-parse", "--abbrev-ref", "HEAD")


def stage_generated_paths(repo_root: Path) -> None:
    run_command(["git", "add", "--", *DEFAULT_GENERATED_PATHS], cwd=repo_root)


def has_staged_changes(repo_root: Path) -> bool:
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet", "--", *DEFAULT_GENERATED_PATHS],
        cwd=repo_root,
        text=True,
    )
    return result.returncode == 1


def get_latest_gameday(repo_root: Path) -> int | None:
    scores_path = repo_root / "data" / "ParticipantGamedayPoints.csv"
    if not scores_path.exists():
        return None

    latest_gameday: int | None = None
    with scores_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            gameday = (row.get("gameday") or "").strip()
            if not gameday:
                continue
            try:
                gameday_number = int(gameday)
            except ValueError:
                continue
            if latest_gameday is None or gameday_number > latest_gameday:
                latest_gameday = gameday_number
    return latest_gameday


def build_commit_message(repo_root: Path) -> str:
    timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %I:%M %p %Z")
    latest_gameday = get_latest_gameday(repo_root)
    if latest_gameday is None:
        return f"Automated league data update {timestamp}"
    return f"Automated league data update through GD{latest_gameday} {timestamp}"


def normalize_update_args(raw_args: list[str]) -> list[str]:
    if raw_args and raw_args[0] == "--":
        return raw_args[1:]
    return raw_args


def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def send_email_notification(subject: str, body: str) -> None:
    smtp_host = os.environ.get("UPDATER_EMAIL_SMTP_HOST")
    smtp_port = os.environ.get("UPDATER_EMAIL_SMTP_PORT")
    smtp_username = os.environ.get("UPDATER_EMAIL_SMTP_USERNAME")
    smtp_password = os.environ.get("UPDATER_EMAIL_SMTP_PASSWORD")
    sender = os.environ.get("UPDATER_EMAIL_FROM")
    recipient = os.environ.get("UPDATER_EMAIL_TO")

    required_values = [smtp_host, smtp_port, smtp_username, smtp_password, sender, recipient]
    if not all(required_values):
        return

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message.set_content(body)

    with smtplib.SMTP(smtp_host, int(smtp_port), timeout=30) as server:
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.send_message(message)


def send_sms_notification(body: str) -> None:
    account_sid = os.environ.get("UPDATER_TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("UPDATER_TWILIO_AUTH_TOKEN")
    from_number = os.environ.get("UPDATER_TWILIO_FROM")
    to_number = os.environ.get("UPDATER_SMS_TO")

    required_values = [account_sid, auth_token, from_number, to_number]
    if not all(required_values):
        return

    payload = parse.urlencode(
        {
            "From": from_number,
            "To": to_number,
            "Body": body,
        }
    ).encode()
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    twilio_request = request.Request(url, data=payload)
    credentials = f"{account_sid}:{auth_token}"
    auth_header = base64.b64encode(credentials.encode()).decode()
    twilio_request.add_header("Authorization", f"Basic {auth_header}")
    twilio_request.add_header("Content-Type", "application/x-www-form-urlencoded")
    with request.urlopen(twilio_request, timeout=30) as response:
        response.read()


def send_success_notifications(summary: str) -> None:
    subject = "IPL updater run succeeded"
    failures: list[str] = []

    try:
        send_email_notification(subject, summary)
    except Exception as exc:
        failures.append(f"email: {exc}")

    try:
        send_sms_notification(summary)
    except Exception as exc:
        failures.append(f"sms: {exc}")

    if failures:
        print(f"Notification failures: {'; '.join(failures)}", flush=True)


def build_success_summary(repo_root: Path, commit_message: str | None, target_branch: str) -> str:
    latest_gameday = get_latest_gameday(repo_root)
    gameday_label = f"GD{latest_gameday}" if latest_gameday is not None else "unknown GD"
    if commit_message is None:
        return f"IPL updater completed successfully with no generated data changes. Latest data seen: {gameday_label}."
    return (
        f"IPL updater completed successfully through {gameday_label}. "
        f"Committed to {target_branch}: {commit_message}"
    )


def fast_forward_merge(repo_root: Path, source_branch: str, target_branch: str) -> None:
    if source_branch == target_branch:
        return
    run_command(["git", "checkout", target_branch], cwd=repo_root)
    run_command(["git", "merge", "--ff-only", source_branch], cwd=repo_root)


def main() -> None:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    update_args = normalize_update_args(args.update_args)
    update_timeout = args.update_timeout_seconds if args.update_timeout_seconds > 0 else None
    load_env_file(DEFAULT_NOTIFICATION_ENV_PATH)

    if not args.allow_dirty and has_tracked_changes(repo_root):
        raise SystemExit(
            "Repository has tracked changes before the daily update run. Commit or stash them first, or rerun with --allow-dirty."
        )

    source_branch = get_current_branch(repo_root)

    update_command = [sys.executable, str(repo_root / "scripts" / "update_league_data.py"), *update_args]
    if update_timeout is None:
        print("Running updater without an outer wall-clock timeout.", flush=True)
    else:
        print(f"Running updater with a {update_timeout}s wall-clock timeout.", flush=True)

    try:
        run_command(update_command, cwd=repo_root, timeout=update_timeout)
    except subprocess.TimeoutExpired as exc:
        timeout_label = f"{update_timeout}s" if update_timeout is not None else "configured timeout"
        raise SystemExit(
            f"Updater exceeded the {timeout_label} wall-clock limit and was terminated."
        ) from exc

    stage_generated_paths(repo_root)
    if not has_staged_changes(repo_root):
        print("No generated data changes detected; nothing to commit.")
        send_success_notifications(build_success_summary(repo_root, None, args.target_branch))
        return

    commit_message = build_commit_message(repo_root)
    run_command(["git", "commit", "-m", commit_message], cwd=repo_root)

    if not args.skip_merge:
        fast_forward_merge(repo_root, source_branch, args.target_branch)

    if args.push_target:
        target_branch = args.target_branch if not args.skip_merge else source_branch
        run_command(["git", "push", "origin", target_branch], cwd=repo_root)

    final_branch = args.target_branch if not args.skip_merge else source_branch
    send_success_notifications(build_success_summary(repo_root, commit_message, final_branch))


if __name__ == "__main__":
    main()