"""
reviews_report.py
Collect statistics about reviews you made in a date range.
Usage:
    python reviews_report.py --start 2026-01-01 --end 2026-01-15

Environment variables required:
    GITHUB_TOKEN - personal access token with repo/read access
"""
import argparse
from datetime import datetime
from typing import List, Tuple
import os

from gh_reports.gh_utils import get_github_client, parse_date_range, get_authenticated_username


def main(start: str, end: str):
    g = get_github_client()
    username = get_authenticated_username(g)
    start_dt, end_dt = parse_date_range(start, end)

    # Search PRs reviewed by the user in the date range
    # Using GitHub search issues: type:pr reviewed-by:USERNAME updated:START..END
    start_s = start_dt.date().isoformat()
    end_s = end_dt.date().isoformat()
    query = f"type:pr reviewed-by:{username} updated:{start_s}..{end_s}"
    issues = g.search_issues(query)

    total_reviews = 0
    approvals = 0
    change_requests = 0
    comment_count = 0
    pr_review_deltas = []  # time delta (in hours) from PR created -> review

    for issue in issues:
        # issue is a PR issue; get repo and pull
        repo = g.get_repo(issue.repository.full_name)
        pr = repo.get_pull(issue.number)

        # get review events and comments
        reviews = pr.get_reviews()
        # review comments (inline)
        review_comments = pr.get_review_comments()
        # issue comments
        issue_comments = pr.get_issue_comments()

        # comments made by our user
        for c in review_comments:
            if c.user and c.user.login == username and start_dt <= c.created_at <= end_dt:
                comment_count += 1

        for c in issue_comments:
            if c.user and c.user.login == username and start_dt <= c.created_at <= end_dt:
                comment_count += 1

        # reviews (APPROVED / CHANGES_REQUESTED / COMMENTED)
        for r in reviews:
            if r.user and r.user.login == username and start_dt <= r.submitted_at <= end_dt:
                total_reviews += 1
                state = r.state.upper()
                if state == 'APPROVED':
                    approvals += 1
                if state == 'CHANGES_REQUESTED':
                    change_requests += 1

                # compute delta from PR creation to review
                delta = (r.submitted_at - pr.created_at).total_seconds() / 3600.0
                pr_review_deltas.append(delta)

    avg_review_hours = sum(pr_review_deltas) / len(pr_review_deltas) if pr_review_deltas else None

    print("Reviews report")
    print(f"Date range: {start_s} .. {end_s}")
    print(f"Total review events: {total_reviews}")
    print(f"Approvals: {approvals}")
    print(f"Change requests: {change_requests}")
    print(f"Comments made on PRs: {comment_count}")
    if avg_review_hours is not None:
        print(f"Average hours between PR creation and your review: {avg_review_hours:.2f} hours")
    else:
        print("No reviews found in the date range.")


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--start', required=True, help='Start date (ISO format)')
    p.add_argument('--end', required=False, help='End date (ISO format). Defaults to now')
    args = p.parse_args()
    main(args.start, args.end)
