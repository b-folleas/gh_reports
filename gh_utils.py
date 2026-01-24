"""
Helper utilities for GitHub reports.
- Uses PyGithub to access GitHub REST API.
- Exposes helpers to create the client, parse dates and get username.
"""
from typing import Optional, Tuple
from datetime import datetime
import os
from dateutil import parser as dateparser

from github import Github


def get_github_client(token: Optional[str] = None) -> Github:
    """Return a PyGithub Github client. Use GITHUB_TOKEN env var if token not provided."""
    token = token or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise EnvironmentError("GITHUB_TOKEN not found in environment variables")
    return Github(token)


def parse_date_range(start: Optional[str], end: Optional[str]) -> Tuple[datetime, datetime]:
    """Parse ISO-ish date strings to datetime objects. If end is None, use now. If start None, raise."""
    if not start:
        raise ValueError("start date is required (e.g. --start 2026-01-01)")
    start_dt = dateparser.parse(start)
    end_dt = dateparser.parse(end) if end else datetime.utcnow()
    return start_dt, end_dt


def get_authenticated_username(g: Github) -> str:
    user = g.get_user()
    return user.login
