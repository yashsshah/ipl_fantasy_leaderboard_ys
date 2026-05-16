from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGET_BRANCH = "main"
DEFAULT_GENERATED_PATHS = ("data", "data.json")


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
        "update_args",
        nargs=argparse.REMAINDER,
        help="Arguments forwarded to scripts/update_league_data.py. Prefix forwarded flags with '--'.",
    )
    return parser.parse_args()


def run_command(command: list[str], cwd: Path, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        check=True,
        capture_output=capture_output,
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


def fast_forward_merge(repo_root: Path, source_branch: str, target_branch: str) -> None:
    if source_branch == target_branch:
        return
    run_command(["git", "checkout", target_branch], cwd=repo_root)
    run_command(["git", "merge", "--ff-only", source_branch], cwd=repo_root)


def main() -> None:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    update_args = normalize_update_args(args.update_args)

    if not args.allow_dirty and has_tracked_changes(repo_root):
        raise SystemExit(
            "Repository has tracked changes before the daily update run. Commit or stash them first, or rerun with --allow-dirty."
        )

    source_branch = get_current_branch(repo_root)

    update_command = [sys.executable, str(repo_root / "scripts" / "update_league_data.py"), *update_args]
    run_command(update_command, cwd=repo_root)

    stage_generated_paths(repo_root)
    if not has_staged_changes(repo_root):
        print("No generated data changes detected; nothing to commit.")
        return

    commit_message = build_commit_message(repo_root)
    run_command(["git", "commit", "-m", commit_message], cwd=repo_root)

    if not args.skip_merge:
        fast_forward_merge(repo_root, source_branch, args.target_branch)

    if args.push_target:
        target_branch = args.target_branch if not args.skip_merge else source_branch
        run_command(["git", "push", "origin", target_branch], cwd=repo_root)


if __name__ == "__main__":
    main()