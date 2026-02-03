"""
weekly_report.py
Aggregate weekly activity and generate a short AI-written summary.
By default it operates on the last 7 days. You can pass --start/--end to override.

Sends results to Notion (if NOTION_TOKEN and NOTION_PAGE_ID set) and to Slack (if SLACK_WEBHOOK set).
"""
import argparse
from datetime import datetime, timedelta
import os
from typing import Optional

import openai
from scripts.gh_utils import get_github_client, parse_date_range, get_authenticated_username


def collect_counts(g, username: str, start_dt: datetime, end_dt: datetime):
    # commits: use search commits
    commits_q = f"author:{username} committer-date:{start_dt.date().isoformat()}..{end_dt.date().isoformat()}"
    commits = g.search_commits(commits_q)

    prs_q = f"type:pr author:{username} created:{start_dt.date().isoformat()}..{end_dt.date().isoformat()}"
    prs = list(g.search_issues(prs_q))

    reviews_q = f"type:pr reviewed-by:{username} updated:{start_dt.date().isoformat()}..{end_dt.date().isoformat()}"
    reviews = list(g.search_issues(reviews_q))

    return len(list(commits)), len(prs), len(reviews)


def make_ai_summary(openai_key: Optional[str], report_text: str) -> str:
    if not openai_key:
        return "(No AI key provided) Brief summary:\n" + report_text[:500]
    openai.api_key = openai_key
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": f"Summarize this weekly developer report and add 3 bullet points for next week's learning:\n\n{report_text}"}],
            max_tokens=400,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"(AI call failed) {e}\n\n{report_text[:500]}"


def post_to_slack(webhook: str, text: str):
    import requests
    payload = {"text": text}
    r = requests.post(webhook, json=payload)
    r.raise_for_status()


def post_to_notion(token: str, parent_page_id: str, title: str, content: str):
    import requests
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    data = {
        "parent": {"page_id": parent_page_id},
        "properties": {
            "title": {
                "title": [{"text": {"content": title}}]
            }
        },
        "children": [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"text": [{"type": "text", "text": {"content": content}}]}
            }
        ]
    }
    r = requests.post(url, json=data, headers=headers)
    r.raise_for_status()


def main(start: Optional[str], end: Optional[str]):
    g = get_github_client()
    username = get_authenticated_username(g)

    if start and end:
        start_dt, end_dt = parse_date_range(start, end)
    else:
        # default to last 7 days ending now
        end_dt = datetime.utcnow()
        start_dt = end_dt - timedelta(days=7)

    commits_count, prs_count, reviews_count = collect_counts(g, username, start_dt, end_dt)

    report_text = (
        f"Weekly report for {username}\n"
        f"Period: {start_dt.date().isoformat()} - {end_dt.date().isoformat()}\n"
        f"Commits: {commits_count}\n"
        f"PRs created: {prs_count}\n"
        f"Reviews done: {reviews_count}\n"
    )

    # AI summary
    ai_summary = make_ai_summary(os.environ.get('OPENAI_API_KEY'), report_text)

    full_report = report_text + "\nAI Summary:\n" + ai_summary

    print(full_report)

    # optionally send to Slack/Notion
    if os.environ.get('SLACK_WEBHOOK'):
        try:
            post_to_slack(os.environ['SLACK_WEBHOOK'], full_report)
            print("Posted to Slack")
        except Exception as e:
            print("Slack post failed:", e)

    if os.environ.get('NOTION_TOKEN') and os.environ.get('NOTION_PAGE_ID'):
        try:
            post_to_notion(os.environ['NOTION_TOKEN'], os.environ['NOTION_PAGE_ID'],
                           f"Weekly report {start_dt.date().isoformat()} - {end_dt.date().isoformat()}",
                           full_report)
            print("Posted to Notion")
        except Exception as e:
            print("Notion post failed:", e)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--start', required=False, help='Start date (ISO)')
    p.add_argument('--end', required=False, help='End date (ISO)')
    args = p.parse_args()
    main(args.start, args.end)
