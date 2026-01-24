"""Collect statistics about PRs you created in a date range.

Usage:
    python prs_report.py --start 2026-01-01 --end 2026-01-15

This script follows the same pattern as `reviews_report.py` and can
optionally generate an AI summary and post results to Notion/Slack.
"""

import argparse
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv

from gh_utils import (
    get_github_client,
    parse_date_range,
    get_authenticated_username,
)

try:
    import openai
except Exception:
    openai = None


load_dotenv()


def fetch_pr_issues(
    g,
    username: str,
    start_dt: datetime,
    end_dt: datetime,
):
    """Return issues for PRs authored by `username` in the date range."""
    start_s = start_dt.date().isoformat()
    end_s = end_dt.date().isoformat()
    query = f"type:pr author:{username} created:{start_s}..{end_s}"
    return g.search_issues(query)


def count_comments_received(pr, username: str) -> int:
    """Count comments on `pr` that were made by others (not `username`)."""
    cnt = 0
    for c in pr.get_review_comments():
        if c.user and c.user.login != username:
            cnt += 1
    for c in pr.get_issue_comments():
        if c.user and c.user.login != username:
            cnt += 1
    return cnt


def process_pr_timings(
    pr, username: str
) -> Tuple[List[float], Optional[float]]:
    """Return (approval_deltas, merged_delta) in hours for `pr`.

    approval_deltas is a list (may be empty). merged_delta is a float or None.
    """
    approval_deltas: List[float] = []
    merged_delta = None

    for r in pr.get_reviews():
        # only consider reviews by others
        if not (r.user and r.user.login != username):
            continue
        state = (r.state or "").upper()
        if state == "CHANGES_REQUESTED":
            # count as a change request (higher-level caller will tally)
            pass
        if state == "APPROVED" and getattr(r, "submitted_at", None):
            delta = (r.submitted_at - pr.created_at).total_seconds() / 3600.0
            approval_deltas.append(delta)

    if pr.merged_at:
        merged_delta = (pr.merged_at - pr.created_at).total_seconds() / 3600.0

    return approval_deltas, merged_delta


def aggregate_pr_stats(
    issues, g, username: str, start_dt: datetime, end_dt: datetime
) -> Dict:
    """Aggregate statistics across PRs authored by `username`."""
    prs_count = 0
    change_requests_received = 0
    approval_hours: List[float] = []
    merged_hours: List[float] = []
    comments_received = 0

    for issue in issues:
        repo = g.get_repo(issue.repository.full_name)
        pr = repo.get_pull(issue.number)
        prs_count += 1

        # reviews from others
        for r in pr.get_reviews():
            if r.state and r.user and r.user.login != username:
                if r.state.upper() == "CHANGES_REQUESTED":
                    change_requests_received += 1

        # timings
        approvals, merged = process_pr_timings(pr, username)
        approval_hours.extend(approvals)
        if merged is not None:
            merged_hours.append(merged)

        # comments
        comments_received += count_comments_received(pr, username)

    avg_approval = (
        sum(approval_hours) / len(approval_hours) if approval_hours else None
    )
    avg_merged = (
        sum(merged_hours) / len(merged_hours) if merged_hours else None
    )

    return {
        "start": start_dt,
        "end": end_dt,
        "prs_count": prs_count,
        "change_requests_received": change_requests_received,
        "avg_hours_to_approval": avg_approval,
        "avg_hours_to_merge": avg_merged,
        "comments_received": comments_received,
    }


def format_plain_report(stats: Dict) -> str:
    """Return a plain-text report from aggregated PR stats."""
    start_s = stats["start"].date().isoformat()
    end_s = stats["end"].date().isoformat()
    lines = [
        "PRs report",
        f"Date range: {start_s} .. {end_s}",
        f"Number of PRs created: {stats['prs_count']}",
        f"Change requests received: {stats['change_requests_received']}",
        f"Comments received on your PRs: {stats['comments_received']}",
    ]
    if stats["avg_hours_to_approval"] is not None:
        lines.append(
            "Average hours until approval: "
            f"{stats['avg_hours_to_approval']:.2f} hours"
        )
    else:
        lines.append("No approvals found in range.")

    if stats["avg_hours_to_merge"] is not None:
        lines.append(
            "Average hours until merge: "
            f"{stats['avg_hours_to_merge']:.2f} hours"
        )
    else:
        lines.append("No merges found in range.")

    return "\n".join(lines)


def generate_ai_summary(stats: Dict, max_tokens: int = 150) -> Optional[str]:
    """Generate a brief AI summary using OpenAI if configured."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key or openai is None:
        return None
    openai.api_key = api_key
    prompt = (
        "You are a concise assistant. Summarize the following GitHub PR "
        "stats in 2-3 short sentences:\n"
        f"PRs: {stats['prs_count']}, "
        f"change requests: {stats['change_requests_received']}, "
        f"comments: {stats['comments_received']}. "
        "Also mention average hours to approval/merge if available."
    )
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.2,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return None


def post_to_notion(
    summary: str, notion_token: str, notion_page_id: str
) -> bool:
    """Post a simple Notion page with the summary. Returns True on success."""
    if not notion_token or not notion_page_id:
        return False
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    payload = {
        "parent": {"page_id": notion_page_id},
        "properties": {
            "title": {
                "title": [{"text": {"content": "PRs Report"}}]
            }
        },
        "children": [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "text": [
                        {"type": "text", "text": {"content": summary}}
                    ]
                },
            }
        ],
    }
    r = requests.post(url, headers=headers, json=payload, timeout=10)
    return 200 <= r.status_code < 300


def post_to_slack(summary: str, slack_webhook: str) -> bool:
    """Post the summary to Slack via an incoming webhook."""
    if not slack_webhook:
        return False
    payload = {"text": summary}
    try:
        r = requests.post(slack_webhook, json=payload, timeout=5)
        return 200 <= r.status_code < 300
    except Exception:
        return False


def main(
    start: Optional[str],
    end: Optional[str],
    enable_ai: bool,
    enable_notion: bool,
    enable_slack: bool,
):
    g = get_github_client()
    username = get_authenticated_username(g)
    start_dt, end_dt = parse_date_range(start, end)

    issues = fetch_pr_issues(g, username, start_dt, end_dt)
    stats = aggregate_pr_stats(issues, g, username, start_dt, end_dt)

    plain = format_plain_report(stats)
    print(plain)

    if enable_ai:
        ai_summary = generate_ai_summary(stats)
        if ai_summary:
            print("\nAI summary:\n" + ai_summary)

        if enable_notion:
            notion_token = os.environ.get("NOTION_TOKEN")
            notion_page_id = os.environ.get("NOTION_PAGE_ID")
            ok = post_to_notion(
                ai_summary or plain,
                notion_token,
                notion_page_id,
            )
            print(f"Notion post: {'OK' if ok else 'Failed'}")

        if enable_slack:
            slack_webhook = os.environ.get("SLACK_WEBHOOK")
            ok = post_to_slack(ai_summary or plain, slack_webhook)
            print(f"Slack post: {'OK' if ok else 'Failed'}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--start",
        required=False,
        help=("Start date (ISO). Defaults to today - 1 year"),
    )
    p.add_argument(
        "--end",
        required=False,
        help=("End date (ISO). Defaults to today"),
    )
    p.add_argument(
        "--ai",
        dest="ai",
        action="store_true",
        help=("Generate AI summary"),
    )
    p.add_argument(
        "--notion",
        dest="notion",
        action="store_true",
        help=("Post summary to Notion"),
    )
    p.add_argument(
        "--slack",
        dest="slack",
        action="store_true",
        help=("Post summary to Slack"),
    )
    return p.parse_args()


if __name__ == '__main__':
    args = parse_args()
    main(
        args.start,
        args.end,
        enable_ai=args.ai,
        enable_notion=args.notion,
        enable_slack=args.slack,
    )
