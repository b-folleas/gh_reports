# GitHub activity reports

This small collection of scripts helps you collect GitHub activity statistics for personal reporting and weekly summaries.

Files

- `gh_utils.py` - helper functions for GitHub authentication and date parsing
- `reviews_report.py` - collect stats about reviews you made in a date range
- `prs_report.py` - collect stats about PRs you created in a date range
- `weekly_report.py` - aggregate weekly numbers and generate an AI summary; can post to Notion and Slack
- `requirements.txt` - Python dependencies

Environment variables

- `GITHUB_TOKEN` (required) - GitHub Personal Access Token with repo access
- `OPENAI_API_KEY` (optional) - for AI summary in `weekly_report.py`
- `NOTION_TOKEN` and `NOTION_PAGE_ID` (optional) - used to post the weekly report to Notion.
	NOTE: Notion posting is currently considered optional and the README instructions are commented for now.
	If you want to enable Notion posting later, set these vars and adjust the payload in `weekly_report.py` to match your Notion database schema.
- `SLACK_WEBHOOK` (optional) - Slack incoming webhook to post the report

Local development vs CI / GitHub Actions

- For local testing you can create a `.env` file in the project root and load it with `python-dotenv` (a sample `.env.sample` is included).
- For scheduled runs on GitHub Actions you should set repository secrets (recommended): go to your repository Settings → Secrets and variables → Actions → New repository secret. Use the same variable names (e.g. `GITHUB_TOKEN`, `OPENAI_API_KEY`, `NOTION_TOKEN`, `NOTION_PAGE_ID`, `SLACK_WEBHOOK`).

Which to use?
- Use a local `.env` only for development on your machine. Do NOT commit real secrets.
- Use GitHub repository secrets for automated runs in Actions (this is the recommended production approach).

Quick run examples

Generate review stats:

```bash
python gh_reports/reviews_report.py --start 2026-01-01 --end 2026-01-15
```

Generate PR stats:

```bash
python gh_reports/prs_report.py --start 2026-01-01 --end 2026-01-15
```

Generate weekly report (defaults to last 7 days):

```bash
python gh_reports/weekly_report.py
```

Scheduling

- Recommended: use GitHub Actions (see `.github/workflows/weekly-report.yml`) to run every Friday at 18:00 UTC and post to Notion/Slack.
- Or set a cron job or Windows Task Scheduler to run the weekly script.

Notes

- These scripts use the GitHub search API and may hit rate limits for large queries. Use a token with appropriate scopes.
- Notion API calls create a simple page under the provided `NOTION_PAGE_ID`. You may want to adapt the payload depending on your Notion database schema.
