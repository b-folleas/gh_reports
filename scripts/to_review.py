"""List open PRs where your review is requested, as a single priority-sorted table.

Usage:
    python to_review.py [--priority-repos org/repo1,org/repo2]

Priority score:
    staling_days * 3
    + 10 if the repo is in the priority list
    + log2(files_changed + 1)
    + log2(lines_changed + 1)
    + 20 if only 1 reviewer requested

Environment variables:
    GITHUB_TOKEN   (required)
    PRIORITY_REPOS (optional) comma-separated list of full repo names
"""

import argparse
import math
import os
import unicodedata
from datetime import datetime, timezone
from typing import List, Optional

from dotenv import load_dotenv

from gh_utils import get_github_client, get_authenticated_username

load_dotenv()

# ANSI colors
_RESET   = "\033[0m"
_BOLD    = "\033[1m"
_DIM     = "\033[2m"
_RED     = "\033[1;31m"
_YELLOW  = "\033[33m"
_GREEN   = "\033[32m"
_CYAN    = "\033[36m"
_MAGENTA = "\033[1;35m"


def _c(code: str, text: str) -> str:
    return f"{code}{text}{_RESET}"


def _display_width(s: str) -> int:
    """Return the number of terminal columns occupied by string s."""
    w = 0
    for ch in s:
        eaw = unicodedata.east_asian_width(ch)
        w += 2 if eaw in ("W", "F") else 1
    return w


def _fit(s: str, width: int, align: str = "<") -> str:
    """Truncate s to fit in `width` display columns, then pad to exactly `width`."""
    dw = _display_width(s)
    if dw > width:
        # Trim character by character until we have room for the ellipsis
        truncated = []
        used = 0
        for ch in s:
            cw = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
            if used + cw > width - 1:
                break
            truncated.append(ch)
            used += cw
        s = "".join(truncated) + "…"
        dw = used + 1  # "…" is always 1 column wide
    pad = width - dw
    if align == ">":
        return " " * pad + s
    return s + " " * pad


def fetch_prs_to_review(g, username: str):
    """Return open PRs where `username` has been requested to review."""
    query = f"type:pr user-review-requested:{username} is:open"
    print(_c(_DIM, f"Fetching PRs with query: {query}"))
    return g.search_issues(query)


def compute_priority_score(
    staling_days: int,
    is_priority: bool,
    files_changed: int,
    lines_changed: int,
    pending_count: int = 0,
    total_reviewers: int = 0,
) -> float:
    """Return a numeric priority score (higher = more urgent to review).

    Components:
        staling_days * 3
        + 10 if repo is in the priority list
        + log2(files_changed + 1)
        + log2(lines_changed + 1)
        + reviewer ratio bonus (when pending == 1):
          - 10 if 1/1 (only reviewer)
          - 5 if 1/2
          - 2.5 if 1/3
          - 1.25 if 1/4+
    """
    score = staling_days * 3
    if is_priority:
        score += 10
    score += math.log2(files_changed + 1)
    score += math.log2(lines_changed + 1)

    # Reviewer ratio bonus: urgent if only one reviewer pending
    if pending_count == 1 and total_reviewers > 0:
        reviewer_bonus = 10 / (2 ** min(3, total_reviewers - 1))
        score += reviewer_bonus

    return round(score, 1)


def collect_pr_data(issues, g, priority_repos: List[str]) -> List[dict]:
    """Build a flat list of PR metadata sorted by priority score descending."""
    now = datetime.now(timezone.utc)
    entries = []

    for issue in issues:
        repo_name = issue.repository.full_name
        repo = g.get_repo(repo_name)
        pr = repo.get_pull(issue.number)

        delta = now - pr.updated_at
        staling_days = delta.days
        staling_seconds = delta.total_seconds()
        is_priority = repo_name in priority_repos
        lines_changed = pr.additions + pr.deletions

        # Count reviewers: pending (requested) and already reviewed
        # Exclude bot/AI reviewers from count (they don't affect merge requirements)
        pending_reviewers = set(
            r.login for r in pr.requested_reviewers if r.type != "Bot"
        )
        reviewed_by = set(
            r.user.login for r in pr.get_reviews() if r.user and r.user.type != "Bot"
        )
        total_reviewers = len(pending_reviewers | reviewed_by)
        pending_count = len(pending_reviewers)

        score = compute_priority_score(
            staling_days, is_priority, pr.changed_files, lines_changed,
            pending_count, total_reviewers
        )

        entries.append({
            "repo": repo_name,
            "title": pr.title,
            "url": pr.html_url,
            "author": pr.user.login if pr.user else "unknown",
            "files_changed": pr.changed_files,
            "additions": pr.additions,
            "deletions": pr.deletions,
            "staling_seconds": staling_seconds,
            "staling_days": staling_days,
            "is_priority": is_priority,
            "priority_score": score,
            "pending_reviewers": pending_count,
            "total_reviewers": total_reviewers,
        })

    entries.sort(key=lambda e: e["priority_score"], reverse=True)
    for i, e in enumerate(entries, 1):
        e["rank"] = i

    return entries


def _fmt_staling(staling_seconds: float) -> str:
    if staling_seconds < 3600:
        return f"{int(staling_seconds / 60)}m"
    if staling_seconds < 86400:
        return f"{int(staling_seconds / 3600)}h"
    return f"{int(staling_seconds / 86400)}d"


def format_report(entries: List[dict]) -> str:
    """Return a colored plain-text report as a single priority-sorted table."""
    if not entries:
        return _c(_YELLOW, "No PRs awaiting your review.")

    C_RANK  = 3
    C_PROJ  = 22
    C_TITLE = 32
    C_AUTH  = 15
    C_FILES = 5
    C_LINES = 12
    C_REVS  = 5
    C_STAL  = 6
    C_SCORE = 6
    SEP = C_RANK + C_PROJ + C_TITLE + C_AUTH + C_FILES + C_LINES + C_REVS + C_STAL + C_SCORE + 8

    total = len(entries)
    out = []
    out.append("")
    out.append(_c(_BOLD, f"  PRs to review  —  {total} open PR(s) awaiting your review"))
    out.append("─" * SEP)

    header = (
        f"{'#':>{C_RANK}} "
        f"{'Project':<{C_PROJ}} "
        f"{'Title':<{C_TITLE}} "
        f"{'Author':<{C_AUTH}} "
        f"{'Files':>{C_FILES}} "
        f"{'±Lines':>{C_LINES}} "
        f"{'Revs':>{C_REVS}} "
        f"{'Stale':>{C_STAL}} "
        f"{'Score':>{C_SCORE}}"
    )
    out.append(_c(_BOLD, header))
    out.append("─" * SEP)

    for e in entries:
        rank = _fit(str(e["rank"]), C_RANK, ">")

        proj_raw = _fit(e["repo"].split("/")[-1], C_PROJ)
        proj = _c(_MAGENTA, proj_raw) if e["is_priority"] else proj_raw

        title = _fit(e["title"], C_TITLE)

        author = _fit(e["author"], C_AUTH)

        files = f"{e['files_changed']:>{C_FILES}}"

        lines_raw = f"+{e['additions']}/-{e['deletions']}"
        lines = f"{lines_raw:>{C_LINES}}"

        revs_str = f"{e['pending_reviewers']}/{e['total_reviewers']}"
        revs = f"{revs_str:>{C_REVS}}"
        if e["total_reviewers"] == 1:
            revs = _c(_RED, revs)

        staling_str = _fmt_staling(e["staling_seconds"])
        staling = f"{staling_str:>{C_STAL}}"
        if e["staling_days"] >= 7:
            staling = _c(_RED, staling)
        elif e["staling_days"] >= 3 or e["staling_seconds"] >= 86400:
            staling = _c(_YELLOW, staling)
        else:
            staling = _c(_GREEN, staling)

        score_val = e["priority_score"]
        score = f"{score_val:>{C_SCORE}}"
        if score_val >= 20:
            score = _c(_RED, score)
        elif score_val >= 10:
            score = _c(_YELLOW, score)
        else:
            score = _c(_GREEN, score)

        out.append(f"{rank} {proj} {title} {author} {files} {lines} {revs} {staling} {score}")
        out.append(_c(_DIM + _CYAN, f"{'':>{C_RANK}}   ↳ {e['url']}"))

    out.append("─" * SEP)
    return "\n".join(out)


def main(priority_repos_arg: Optional[str]):
    priority_repos_env = os.environ.get("PRIORITY_REPOS", "")
    raw = priority_repos_arg or priority_repos_env
    priority_repos = [r.strip() for r in raw.split(",") if r.strip()]

    g = get_github_client()
    username = get_authenticated_username(g)
    print(_c(_DIM, f"Fetching PRs to review for: {username}"))

    issues = fetch_prs_to_review(g, username)
    entries = collect_pr_data(issues, g, priority_repos)
    print(format_report(entries))


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
