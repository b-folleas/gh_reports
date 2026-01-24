"""Helper utilities for GitHub reports.

Uses PyGithub to access GitHub REST API.
Provides helpers to create the client, parse dates and get username.

Notes
- `parse_date_range` now accepts optional start/end and will default to
  (today - 1 year) .. today when values are omitted. Returned datetimes
  are timezone-aware (UTC).
"""
from typing import Optional, Tuple
from datetime import datetime, timezone
from dateutil import parser as dateparser
from dateutil.relativedelta import relativedelta
import os

from github import Github


def get_github_client(token: Optional[str] = None) -> Github:
    """Return a PyGithub Github client.

    If `token` is not provided, read the `GITHUB_TOKEN` environment variable.
    Raises EnvironmentError when no token is available.
    """
    token = token or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise EnvironmentError("GITHUB_TOKEN not found in environment variables")
    return Github(token)


def parse_date_range(start: Optional[str], end: Optional[str]) -> Tuple[datetime, datetime]:
    """Parse ISO-ish date strings to timezone-aware datetimes (UTC).

    Behavior:
    - If both `start` and `end` are provided, parse and return them.
    - If `start` is omitted/None, default to (today UTC - 1 year).
    - If `end` is omitted/None, default to now (UTC).

    Returns (start_dt, end_dt).
    """
    now_utc = datetime.now(timezone.utc)

    if start:
        start_dt = dateparser.parse(start)
    else:
        # default to 1 year ago
        start_dt = now_utc - relativedelta(years=1)

    end_dt = dateparser.parse(end) if end else now_utc

    # If parsed datetimes are naive, make them UTC-aware
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=timezone.utc)

    return start_dt, end_dt


def get_authenticated_username(g: Github) -> str:
    """Return the login/username for the authenticated client `g`."""
    user = g.get_user()
    return user.login
