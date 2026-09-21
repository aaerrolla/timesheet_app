"""
Small date helpers shared by the timesheet routes.
"""
from datetime import datetime, timedelta


def parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def monday_of(d):
    return d - timedelta(days=d.weekday())  # weekday(): Monday=0


def week_dates(week_start):
    """Return list of 7 ISO date strings, Monday..Sunday, for the given Monday."""
    return [(week_start + timedelta(days=i)).isoformat() for i in range(7)]
