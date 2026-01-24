"""
prs_report.py
Collect statistics about PRs you created in a date range.
Usage:
    python prs_report.py --start 2026-01-01 --end 2026-01-15

Environment variables required:
    GITHUB_TOKEN
"""
import argparse
from datetime import datetime
import os
from statistics import mean

from gh_reports.gh_utils import get_github_client, parse_date_range, get_authenticated_username


def main(start: str, end: str):
    g = get_github_client()
    username = get_authenticated_username(g)
    start_dt, end_dt = parse_date_range(start, end)

    start_s = start_dt.date().isoformat()
    end_s = end_dt.date().isoformat()
    query = f"type:pr author:{username} created:{start_s}..{end_s}"
    issues = g.search_issues(query)

    prs = []
    change_requests_received = 0
    time_to_approved_hours = []
    time_to_merged_hours = []
    comments_received = 0

    for issue in issues:
        repo = g.get_repo(issue.repository.full_name)
        pr = repo.get_pull(issue.number)
        prs.append(pr)

        # received reviews from others
        for r in pr.get_reviews():
            if r.state and r.state.upper() == 'CHANGES_REQUESTED' and r.user and r.user.login != username:
                change_requests_received += 1
            if r.state and r.state.upper() == 'APPROVED' and r.user and r.user.login != username:
                # first approval time
                delta = (r.submitted_at - pr.created_at).total_seconds() / 3600.0
                time_to_approved_hours.append(delta)

        # merged time
        if pr.merged_at:
            delta = (pr.merged_at - pr.created_at).total_seconds() / 3600.0
            time_to_merged_hours.append(delta)

        # comments received (exclude your own)
        for c in pr.get_review_comments():
            if c.user and c.user.login != username:
                comments_received += 1
        for c in pr.get_issue_comments():
            if c.user and c.user.login != username:
                comments_received += 1

    print("PRs report")
    print(f"Date range: {start_s} .. {end_s}")
    print(f"Number of PRs created: {len(prs)}")
    print(f"Change requests received (count of change-request reviews): {change_requests_received}")
    if time_to_approved_hours:
        print(f"Average hours until approval: {mean(time_to_approved_hours):.2f} hours")
    else:
        print("No approvals found in range.")
    if time_to_merged_hours:
        print(f"Average hours until merge: {mean(time_to_merged_hours):.2f} hours")
    else:
        print("No merges found in range.")
    print(f"Comments received on your PRs: {comments_received}")


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--start', required=True, help='Start date (ISO format)')
    p.add_argument('--end', required=False, help='End date (ISO format). Defaults to now')
    args = p.parse_args()
    main(args.start, args.end)
