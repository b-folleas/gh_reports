# Repository TODO

Top priority

- Add tests for `reviews_report.py` (happy path + one edge case).
- Add CI job to run flake8 and unit tests.
- Improve error handling when GitHub API rate limits are hit.

Medium priority

- Make Notion posting use a configurable page or database schema
  (currently a simple page is created).
- Add a dedicated `weekly_report.py` that aggregates multiple reports
  (PRs, reviews) and formats one combined summary.
- Add end-to-end tests that run a tiny local harness against mocks.

Nice to have

- Add type annotations across the codebase and mypy CI.
- Add `requirements-dev.txt` and pin dev dependencies.
- Add GitHub Action to post a weekly report and notify Slack/Notion.
