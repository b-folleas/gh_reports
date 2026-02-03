# GitHub activity reports

This small collection of scripts helps you collect GitHub activity statistics for personal reporting and weekly summaries.

## Files

- In the `scripts/` folder
  - `gh_utils.py` - helper functions for GitHub authentication and date parsing
  - `reviews_report.py` - collect stats about reviews you made in a date range
  - `prs_report.py` - collect stats about PRs you created in a date range
  - `weekly_report.py` - aggregate weekly numbers and generate an AI summary; can post to Notion and Slack

- `requirements.txt` - Python dependencies

## Environment variables

- `GITHUB_TOKEN` (required) - GitHub Personal Access Token with repo access
- `OPENAI_API_KEY` (optional) - for AI summary in `weekly_report.py`
- `NOTION_TOKEN` and `NOTION_PAGE_ID` (optional) - to post the weekly report to Notion.

NOTE: Notion posting is currently unavailable and the README instructions are commented for now.
When you want to enable Notion posting later, set these vars and adjust the payload in `weekly_report.py` to match your Notion database schema.

- `SLACK_WEBHOOK` (optional) - Slack incoming webhook to post the report

## Run locally

- For local testing you can create a `.env` file in the project root and load it with `python-dotenv` (a sample `.env.sample` is included).

### Quick run examples

- Generate review stats:

```bash
python ./reviews_report.py --start 2026-01-01 --end 2026-01-15
```

- Generate PR stats:

```bash
python ./prs_report.py --start 2026-01-01 --end 2026-01-15
```

- Generate weekly report (defaults to last 7 days):

```bash
python ./weekly_report.py
```

### Local development (using `venv`)

1. Remove any old virtualenv (optional)

If you already have a `.venv` folder and want a fresh start, remove it first.

```bash
rm -rf .venv
deactivate # to deactivate the in memory venv
```

1. Create and activate a virtual environment

- Create the venv:

```bash
  python -m venv .venv
```

- Activate:

```bash
  source .venv/Scripts/activate
```

After activation your prompt should show `(.venv)`.

1. Install dependencies into the venv

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

4. Configure environment variables

Copy `.env.sample` to `.env` and edit it (do not commit `.env`). This file is loaded by the scripts using `python-dotenv`.

5. Run the script

```bash
# Default (past year -> today):
python ./reviews_report.py

# With AI summary:
python ./reviews_report.py --ai

# Post to Notion and Slack (requires NOTION_TOKEN/NOTION_PAGE_ID and SLACK_WEBHOOK):
python ./reviews_report.py --ai --notion --slack
```

## Run a GitHub Actions

- For scheduled runs on GitHub Actions you need to set repository secrets
  Guide: Go to `Repository Settings` → `Secrets and variables` → `Actions` → `New repository secret`.
  Use the same variable names (e.g. `GITHUB_TOKEN`, `OPENAI_API_KEY`, `NOTION_TOKEN`, `NOTION_PAGE_ID`, `SLACK_WEBHOOK`).

## Notes

- These scripts use the GitHub search API and may hit rate limits for large queries. Use a token with appropriate scopes.
- Notion API calls create a simple page under the provided `NOTION_PAGE_ID`. You may want to adapt the payload depending on your Notion database schema.
