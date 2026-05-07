"""
Collect statistics about reviews you made in a date range.

Usage:
    python reviews_report.py --start 2026-01-01 --end 2026-01-15

This script can optionally generate an AI-written summary and
post the report to Notion and/or Slack when flags are provided.

Environment variables used:
    GITHUB_TOKEN (required) - personal access token with repo/read access
    OPENAI_API_KEY (optional) - ChatGPT API key to generate a short sum
    NOTION_TOKEN, NOTION_PAGE_ID (optional) - to post to Notion
    SLACK_WEBHOOK (optional) - Slack incoming webhook
"""

import argparse
import os
from datetime import datetime
from typing import Dict, List, Optional

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


def fetch_review_issues(
    g,
    username: str,
    start_dt: datetime,
    end_dt: datetime,
):
    """
    Return issues for PRs reviewed by `username` in the date range.
    """
    start_s = start_dt.date().isoformat()
    end_s = end_dt.date().isoformat()
    query = (
        f"type:pr reviewed-by:{username} "
        f"updated:{start_s}..{end_s}"
    )
    return g.search_issues(query)


def count_comments_for_pr(
    pr,
    username: str,
    start_dt: datetime,
    end_dt: datetime,
) -> int:
    """
    Count inline and issue comments by `username` on `pr`.
    """
    cnt = 0
    for c in pr.get_review_comments():
        if (
            c.user
            and c.user.login == username
            and start_dt <= c.created_at <= end_dt
        ):
            cnt += 1
    for c in pr.get_issue_comments():
        if (
            c.user
            and c.user.login == username
            and start_dt <= c.created_at <= end_dt
        ):
            cnt += 1
    return cnt


def process_review_events(
    pr, username: str, start_dt: datetime, end_dt: datetime
) -> (int, int, int, List[float]):
    """
    Process review events and return totals and deltas.

    Returns (total, approvals, changes, deltas).
    """
    total = 0
    approvals = 0
    changes = 0
    deltas: List[float] = []
    for r in pr.get_reviews():
        submitted = getattr(r, "submitted_at", None)
        if not (r.user and submitted):
            continue
        if not (r.user.login == username and start_dt <= submitted <= end_dt):
            continue
        total += 1
        state = (r.state or "").upper()
        if state == "APPROVED":
            approvals += 1
        if state == "CHANGES_REQUESTED":
            changes += 1
        delta = (submitted - pr.created_at).total_seconds() / 3600.0
        deltas.append(delta)
    return total, approvals, changes, deltas


def aggregate_review_stats(
    issues, g, username: str, start_dt: datetime, end_dt: datetime
) -> Dict:
    """
    Aggregate counts and timing metrics from the given issues.
    """
    total_reviews = 0
    approvals = 0
    change_requests = 0
    comment_count = 0
    pr_review_deltas: List[float] = []

    for issue in issues:
        repo = g.get_repo(issue.repository.full_name)
        pr = repo.get_pull(issue.number)

        comment_count += count_comments_for_pr(
            pr, username, start_dt, end_dt
        )
        t, a, cr, deltas = process_review_events(
            pr, username, start_dt, end_dt
        )
        total_reviews += t
        approvals += a
        change_requests += cr
        pr_review_deltas.extend(deltas)

    avg_review_hours = (
        sum(pr_review_deltas) / len(pr_review_deltas)
        if pr_review_deltas
        else None
    )

    return {
        "start": start_dt,
        "end": end_dt,
        "total_reviews": total_reviews,
        "approvals": approvals,
        "change_requests": change_requests,
        "comment_count": comment_count,
        "avg_review_hours": avg_review_hours,
    }


def format_plain_report(stats: Dict) -> str:
    """Return a plain-text report from aggregated stats."""
    start_s = stats["start"].date().isoformat()
    end_s = stats["end"].date().isoformat()
    lines = [
        "Reviews report",
        f"Date range: {start_s} .. {end_s}",
        f"Total review events: {stats['total_reviews']}",
        f"Approvals: {stats['approvals']}",
        f"Change requests: {stats['change_requests']}",
        f"Comments made on PRs: {stats['comment_count']}",
    ]
    if stats["avg_review_hours"] is not None:
        lines.append(
            "Average hours between PR creation and your review: "
            f"{stats['avg_review_hours']:.2f} hours"
        )
    else:
        lines.append("No reviews found in the date range.")

    return "\n".join(lines)


def generate_ai_summary(stats: Dict, max_tokens: int = 150) -> Optional[str]:
    """
    Generate a concise natural-language summary using OpenAI.

    Returns the summary string or None if OpenAI is not configured.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key or openai is None:
        return None

    openai.api_key = api_key
    prompt = (
        "You are a concise assistant. Summarize the following GitHub review "
        "stats in 2-3 short sentences:\n"
        f"Total reviews: {stats['total_reviews']}, "
        f"approvals: {stats['approvals']}, "
        f"change requests: {stats['change_requests']}, "
        f"comments: {stats['comment_count']}. "
        "Also mention the average hours between PR creation and review "
        "if available."
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
    """
    Create a simple Notion page under the provided page id.
    """
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
                "title": [{"text": {"content": "GitHub Reviews Report"}}]
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
    """
    Post the summary to a Slack incoming webhook.
    """
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

    issues = fetch_review_issues(g, username, start_dt, end_dt)
    stats = aggregate_review_stats(issues, g, username, start_dt, end_dt)

    plain = format_plain_report(stats)
    print(plain)

    # Handle AI summary and optional integrations (Notion, Slack)
    if enable_ai:
        ai_summary = generate_ai_summary(stats)
        if ai_summary:
            print("\nAI summary:\n" + ai_summary)

        if enable_notion:
            notion_token = os.environ.get("NOTION_TOKEN")
            notion_page_id = os.environ.get("NOTION_PAGE_ID")
            notion_post_success = post_to_notion(
                ai_summary or plain, notion_token, notion_page_id
            )
            print(f"Notion post: {'OK' if notion_post_success else 'Failed'}")

        if enable_slack:
            slack_webhook = os.environ.get("SLACK_WEBHOOK")
            slack_post_success = post_to_slack(
                ai_summary or plain, slack_webhook
            )
            print(f"Slack post: {'OK' if slack_post_success else 'Failed'}")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments and return the Namespace.

    Extracted into a helper so argument parsing is reusable and testable.
    """
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
    p.add_argument(
        "--ai",
        dest="ai",
        action="store_true",
        help=("Generate AI summary"),
    )
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(
        args.start,
        args.end,
        enable_ai=args.ai,
        enable_notion=args.notion,
        enable_slack=args.slack,
    )
