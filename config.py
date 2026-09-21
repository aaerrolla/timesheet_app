"""
Configuration and constants shared across the app.
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "timesheet.db")
OUTBOX_DIR = os.path.join(BASE_DIR, "outbox")
SECRET_KEY_PATH = os.path.join(BASE_DIR, ".flask_secret")

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MAX_DAY_HOURS = 8
MAX_WEEK_HOURS = 40
