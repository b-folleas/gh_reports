"""List open PRs authored by you that are approved and ready to merge.

Usage:
    python to_merge.py

Columns:
    Repo, Title, Age, Approvals, Conflicts, CI, URL

Environment variables:
    GITHUB_TOKEN  (required)
"""

import os
import unicodedata
from datetime import datetime, timezone
from typing import List

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
    w = 0
    for ch in s:
        eaw = unicodedata.east_asian_width(ch)
        w += 2 if eaw in ("W", "F") else 1
    return w


def _fit(s: str, width: int, align: str = "<") -> str:
    dw = _display_width(s)
    if dw > width:
        truncated = []
        used = 0
        for ch in s:
            cw = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
            if used + cw > width - 1:
                break
            truncated.append(ch)
            used += cw
        s = "".join(truncated) + "…"
        dw = used + 1
    pad = width - dw
    if align == ">":
        return " " * pad + s
    return s + " " * pad


def _fmt_age(seconds: float) -> str:
    if seconds < 3600:
        return f"{int(seconds / 60)}m"
    if seconds < 86400:
        return f"{int(seconds / 3600)}h"
    return f"{int(seconds / 86400)}d"


def _get_ci_status(pr) -> str:
    """Return 'pass', 'fail', 'pending', or 'none' based on check runs and commit status."""
    sha = pr.head.sha
    try:
        check_runs = list(pr.head.repo.get_commit(sha).get_check_runs())
    except Exception:
        check_runs = []

    if check_runs:
        statuses = [r.conclusion for r in check_runs]
        # in_progress / queued checks have conclusion=None
        if any(s is None for s in statuses):
            return "pending"
        if all(s in ("success", "skipped", "neutral") for s in statuses):
            return "pass"
        return "fail"

    # Fall back to legacy commit status
    try:
        combined = pr.head.repo.get_commit(sha).get_combined_status()
        state = combined.state  # "success", "failure", "error", "pending"
        if state == "success":
            return "pass"
        if state == "pending":
            return "pending"
        if state in ("failure", "error"):
            return "fail"
    except Exception:
        pass

    return "none"


def fetch_approved_prs(g, username: str):
    query = f"type:pr author:{username} is:open review:approved"
    print(_c(_DIM, f"Fetching PRs with query: {query}"))
    return g.search_issues(query)


def collect_pr_data(issues, g) -> List[dict]:
    now = datetime.now(timezone.utc)
    entries = []

    for issue in issues:
        repo_name = issue.repository.full_name
        repo = g.get_repo(repo_name)
        pr = repo.get_pull(issue.number)

        age_seconds = (now - pr.created_at).total_seconds()
        age_days = (now - pr.created_at).days

        # Count distinct approvals (non-bot, latest review per user)
        reviews = list(pr.get_reviews())
        latest_by_user: dict = {}
        for r in reviews:
            if r.user and r.user.type != "Bot":
                latest_by_user[r.user.login] = r.state
        approvals = sum(1 for s in latest_by_user.values() if s == "APPROVED")

        # Conflict detection
        mergeable_state = pr.mergeable_state  # "clean","dirty","blocked","unstable","unknown"
        has_conflict = mergeable_state == "dirty"

        ci_status = _get_ci_status(pr)

        entries.append({
            "repo": repo_name,
            "number": pr.number,
            "title": pr.title,
            "url": pr.html_url,
            "age_seconds": age_seconds,
            "age_days": age_days,
            "approvals": approvals,
            "mergeable_state": mergeable_state,
            "has_conflict": has_conflict,
            "ci_status": ci_status,
        })

    # Sort: conflicts and CI failures first, then by age descending
    def sort_key(e):
        return (not e["has_conflict"], e["ci_status"] not in ("fail",), -e["age_days"])

    entries.sort(key=sort_key)
    return entries


def format_report(entries: List[dict]) -> str:
    if not entries:
        return _c(_YELLOW, "No approved open PRs found.")

    C_PROJ  = 22
    C_TITLE = 36
    C_AGE   = 6
    C_APPR  = 5
    C_CONF  = 9
    C_CI    = 9
    SEP = C_PROJ + C_TITLE + C_AGE + C_APPR + C_CONF + C_CI + 6

    total = len(entries)
    out = []
    out.append("")
    out.append(_c(_BOLD, f"  PRs to merge  —  {total} approved open PR(s)"))
    out.append("─" * SEP)

    header = (
        f"{'Project':<{C_PROJ}} "
        f"{'Title':<{C_TITLE}} "
        f"{'Age':>{C_AGE}} "
        f"{'Approvals':>{C_APPR}} "
        f"{'Conflicts':>{C_CONF}} "
        f"{'CI':>{C_CI}}"
    )
    out.append(_c(_BOLD, header))
    out.append("─" * SEP)

    for e in entries:
        proj_raw = _fit(e["repo"].split("/")[-1], C_PROJ)
        proj = _c(_MAGENTA, proj_raw)

        title = _fit(e["title"], C_TITLE)

        age_str = _fmt_age(e["age_seconds"])
        age = f"{age_str:>{C_AGE}}"
        if e["age_days"] >= 7:
            age = _c(_RED, age)
        elif e["age_days"] >= 3:
            age = _c(_YELLOW, age)
        else:
            age = _c(_GREEN, age)

        appr = f"{e['approvals']:>{C_APPR}}"
        appr = _c(_GREEN, appr)

        # Conflicts column
        if e["has_conflict"]:
            conf = _c(_RED, _fit("YES", C_CONF, ">"))
        elif e["mergeable_state"] == "Unknown":
            conf = _c(_YELLOW, _fit("?", C_CONF, ">"))
        else:
            conf = _c(_GREEN, _fit("No", C_CONF, ">"))

        # CI column
        ci = e["ci_status"]
        if ci == "pass":
            ci_cell = _c(_GREEN, _fit("Pass", C_CI, ">"))
        elif ci == "fail":
            ci_cell = _c(_RED, _fit("FAIL", C_CI, ">"))
        elif ci == "pending":
            ci_cell = _c(_YELLOW, _fit("Pending", C_CI, ">"))
        else:
            ci_cell = _c(_DIM, _fit("None", C_CI, ">"))

        out.append(f"{proj} {title} {age} {appr} {conf} {ci_cell}")
        out.append(_c(_DIM + _CYAN, f"{'':>{2}}   ↳ {e['url']}"))

    out.append("─" * SEP)
    return "\n".join(out)


def main():
    g = get_github_client()
    username = get_authenticated_username(g)
    print(_c(_DIM, f"Fetching approved PRs for: {username}"))

    issues = fetch_approved_prs(g, username)
    entries = collect_pr_data(issues, g)
    print(format_report(entries))


if __name__ == "__main__":
    main()
