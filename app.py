"""
Timesheet web application
--------------------------
Multi-user web app (Python 3 + Flask + SQLite) for entering weekly time data
against one or more projects, with email/password authentication so several
people can use the same server with their own private projects and hours.

This file just wires the pieces together; the actual logic lives in:
  config.py      - constants & paths
  db.py          - SQLite connection handling, schema creation & migrations
  dateutils.py   - week/date helpers
  emailer.py     - sending (or logging, if SMTP isn't configured) email
  auth.py        - login/register/logout/change-password + auth decorators
  user_profile.py- first/last name, mobile phone, entity name
  projects.py    - per-user project CRUD
  entries.py     - the weekly grid data + hour-cap validation
  pages.py       - server-rendered page routes (/, /login, /profile, ...)

Business rules enforced server-side (never trust the client) -- see
entries.py for the implementation:
  * Week always starts on Monday.
  * Sum of hours for any single day (across all of a user's projects) must be <= 8.
  * Sum of hours for a user's whole week must be <= 40.
  * Hours per cell must be >= 0 and <= 8.
  * Every project and every hour entry belongs to exactly one user; users
    never see or affect each other's data, and the daily/weekly caps are
    computed per-user.

Run:
    python3 app.py
Then open http://127.0.0.1:5000/ in a browser.

Email delivery (optional -- see README.md for details):
    Set SMTP_HOST (and friends) as environment variables to send real email.
    Without it, registration emails are logged to the console and to
    outbox/outbox.log, and the temporary password is also returned directly
    in the API response so the app stays usable with no mail server.
"""
import os
import secrets
from datetime import timedelta

from flask import Flask

from auth import auth_bp
from config import SECRET_KEY_PATH
from db import close_db, init_db
from entries import entries_bp
from pages import pages_bp
from projects import projects_bp
from user_profile import profile_bp


def _load_or_create_secret_key():
    env_key = os.environ.get("FLASK_SECRET_KEY")
    if env_key:
        return env_key
    if os.path.exists(SECRET_KEY_PATH):
        with open(SECRET_KEY_PATH, "r", encoding="utf-8") as f:
            key = f.read().strip()
            if key:
                return key
    key = secrets.token_hex(32)
    with open(SECRET_KEY_PATH, "w", encoding="utf-8") as f:
        f.write(key)
    return key


def create_app():
    app = Flask(__name__)
    app.secret_key = _load_or_create_secret_key()
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=14)

    app.teardown_appcontext(close_db)

    app.register_blueprint(pages_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(entries_bp)

    return app


app = create_app()


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
else:
    # Also initialize (and migrate/repair) the DB when imported, e.g. by a WSGI server.
    init_db()
