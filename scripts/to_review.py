"""List open PRs where your review is requested, grouped by repo, with a priority score.

Usage:
    python to_review.py [--priority-repos org/repo1,org/repo2]

Priority score:
    staling_days * 2
    + 10 if the repo is in the priority list
    + log2(files_changed + 1) * 2
    + log2(lines_changed + 1)

Environment variables:
    GITHUB_TOKEN   (required)
    PRIORITY_REPOS (optional) comma-separated list of full repo names
"""

import argparse
import math
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

from dotenv import load_dotenv

from gh_utils import get_github_client, get_authenticated_username

load_dotenv()


def fetch_prs_to_review(g, username: str):
    """Return open PRs where `username` has been requested to review."""
    query = f"type:pr user-review-requested:{username} is:open"
    print(f"Fetching PRs with query: {query}")
    return g.search_issues(query)


def compute_priority_score(
    staling_days: int,
    is_priority: bool,
    files_changed: int,
    lines_changed: int,
) -> float:
    """Return a numeric priority score (higher = more urgent to review).

    Components:
        staling_days * 2
        + 10 if repo is in the priority list
        + log2(files_changed + 1) * 2
        + log2(lines_changed + 1)
    """
    score = staling_days * 2
    if is_priority:
        score += 10
    score += math.log2(files_changed + 1) * 2
    score += math.log2(lines_changed + 1)
    return round(score, 1)


def collect_pr_data(
    issues, g, priority_repos: List[str]
) -> Dict[str, List[dict]]:
    """Build a per-repo dict of PR metadata, sorted by priority score."""
    now = datetime.now(timezone.utc)
    by_repo: Dict[str, List[dict]] = {}

    for issue in issues:
        repo_name = issue.repository.full_name
        repo = g.get_repo(repo_name)
        pr = repo.get_pull(issue.number)

        staling_days = (now - pr.updated_at).days
        is_priority = repo_name in priority_repos
        lines_changed = pr.additions + pr.deletions

        score = compute_priority_score(
            staling_days, is_priority, pr.changed_files, lines_changed
        )

        by_repo.setdefault(repo_name, []).append(
            {
                "title": pr.title,
                "url": pr.html_url,
                "author": pr.user.login if pr.user else "unknown",
                "files_changed": pr.changed_files,
                "additions": pr.additions,
                "deletions": pr.deletions,
                "staling_days": staling_days,
                "is_priority": is_priority,
                "priority_score": score,
            }
        )

    for entries in by_repo.values():
        entries.sort(key=lambda e: e["priority_score"], reverse=True)

    return by_repo


def format_report(by_repo: Dict[str, List[dict]]) -> str:
    """Return a plain-text report grouped by repo, sorted by priority."""
    if not by_repo:
        return "No PRs awaiting your review."

    COL_TITLE = 40
    COL_AUTHOR = 18
    COL_FILES = 7
    COL_LINES = 12
    COL_STALING = 8
    COL_SCORE = 7
    SEP_WIDTH = COL_TITLE + COL_AUTHOR + COL_FILES + COL_LINES + COL_STALING + COL_SCORE + 6

    total = sum(len(v) for v in by_repo.values())
    lines = [
        "PRs to review",
        "=" * SEP_WIDTH,
        f"Total: {total} open PR(s) awaiting your review",
        "",
    ]

    def repo_sort_key(item):
        _, entries = item
        return (
            not any(e["is_priority"] for e in entries),
            -max(e["priority_score"] for e in entries),
        )

    header = (
        f"{'Title':<{COL_TITLE}} "
        f"{'Author':<{COL_AUTHOR}} "
        f"{'Files':>{COL_FILES}} "
        f"{'±Lines':>{COL_LINES}} "
        f"{'Staling':>{COL_STALING}} "
        f"{'Score':>{COL_SCORE}}"
    )

    for repo_name, entries in sorted(by_repo.items(), key=repo_sort_key):
        priority_tag = " [PRIORITY]" if any(e["is_priority"] for e in entries) else ""
        lines.append(f"## {repo_name}{priority_tag}  ({len(entries)} PR(s))")
        lines.append("-" * SEP_WIDTH)
        lines.append(header)
        lines.append("-" * SEP_WIDTH)

        for e in entries:
            title = e["title"]
            if len(title) > COL_TITLE - 1:
                title = title[: COL_TITLE - 2] + "…"
            lines_delta = f"+{e['additions']}/-{e['deletions']}"
            row = (
                f"{title:<{COL_TITLE}} "
                f"{e['author']:<{COL_AUTHOR}} "
                f"{e['files_changed']:>{COL_FILES}} "
                f"{lines_delta:>{COL_LINES}} "
                f"{e['staling_days']:>{COL_STALING}}d "
                f"{e['priority_score']:>{COL_SCORE}}"
            )
            lines.append(row)
            lines.append(f"  {e['url']}")

        lines.append("")

    return "\n".join(lines)


def main(priority_repos_arg: Optional[str]):
    priority_repos_env = os.environ.get("PRIORITY_REPOS", "")
    raw = priority_repos_arg or priority_repos_env
    priority_repos = [r.strip() for r in raw.split(",") if r.strip()]

    g = get_github_client()
    username = get_authenticated_username(g)
    print(f"Fetching PRs to review for: {username}\n")

    issues = fetch_prs_to_review(g, username)
    by_repo = collect_pr_data(issues, g, priority_repos)
    print(format_report(by_repo))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="List open PRs assigned to you for review, with a priority score."
    )
    p.add_argument(
        "--priority-repos",
        required=False,
        help=(
            "Comma-separated full repo names that get a +10 priority boost "
            "(e.g. org/backend,org/api). Also reads PRIORITY_REPOS env var."
        ),
    )
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(args.priority_repos)
