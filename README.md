# Timesheet

A multi-user timesheet web app built with **Python 3 (Flask)** and **SQLite**,
with email/password authentication so each person has their own private
projects and hours on the same server.

## Features
- **Accounts**: register with an email address, sign in, forced password
  change on first login, and a profile page (name, mobile, entity name).
- Weekly grid, Monday through Sunday, with one row per project.
- Enter hours per project per day; add, rename, or remove projects at any
  time (renaming a project applies to all of its saved hours automatically).
- Server-enforced rules, evaluated **per user** (checked on every save, not
  just in the UI):
  - A single day's total across all of your projects cannot exceed **8 hours**.
  - A week's total across all your days/projects cannot exceed **40 hours**.
  - Two different users can each log a full day/week on the same calendar
    dates — the caps never cross between accounts.
- Edit any cell at any time — saving updates the existing entry (upsert).
  Set a cell to 0 (or clear it) to remove that entry.
- Week navigation (Prev / Next / This week); daily and weekly totals with a
  progress bar that turns red if a limit is (attempted to be) exceeded.
- Removing a project only deactivates it — historical hours are preserved.
- Every project and hour entry belongs to exactly one user; nobody can see
  or modify another user's data.

## Requirements
- Python 3.8+
- Flask (`pip install flask`)

## Run it
```bash
cd timesheet_app
pip install flask          # if not already installed
python3 app.py
```
Then open **http://127.0.0.1:5000/** and register the first account.

The SQLite database file `timesheet.db` is created automatically on first
run. A brand-new database seeds three sample projects (Internal, Project
Alpha, Project Beta) which are automatically handed to whichever user
registers **first** — every user after that starts with an empty project
list of their own.

## Accounts and authentication

### Registration
Enter an email address on the "Create account" tab. If it isn't already
registered, a random temporary password is generated and:
- **emailed** to that address, if SMTP is configured (see below), or
- **logged to the server console and to `outbox/outbox.log`**, and returned
  directly in the API response, if it isn't.

This means the app is fully usable out of the box with zero configuration —
you just get your temporary password from the server's console/log instead
of your inbox until you wire up real SMTP.

### First login
Logging in with the temporary password forces a password-change screen
before anything else in the app is reachable. New password must be at least
8 characters and different from the current one.

### Profile
From the "Profile" link in the timesheet header you can edit your first/last
name, mobile phone, and entity name (the login email itself is not
editable there), and change your password again at any time.

### Configuring real email delivery (optional)
Set these environment variables before running `python3 app.py` to have
registration emails actually sent via SMTP instead of just logged:

| Variable         | Purpose                                   | Default            |
|-------------------|-------------------------------------------|---------------------|
| `SMTP_HOST`       | SMTP server hostname (required to enable) | *(none — disabled)* |
| `SMTP_PORT`       | SMTP port                                 | `587`               |
| `SMTP_USER`       | SMTP username                             | *(none)*             |
| `SMTP_PASSWORD`   | SMTP password                             | *(none)*             |
| `SMTP_FROM`       | "From" address                            | `SMTP_USER`          |
| `SMTP_USE_TLS`    | `"0"` to disable STARTTLS                 | `"1"`                |
| `FLASK_SECRET_KEY`| Session-signing key (auto-generated & persisted to `.flask_secret` if unset) | *(auto)* |

Example:
```bash
export SMTP_HOST=smtp.gmail.com
export SMTP_USER=you@gmail.com
export SMTP_PASSWORD=your_app_password
python3 app.py
```

## Project layout

The backend is split into one module per concern rather than one large
`app.py`:

```
timesheet_app/
├── app.py                       # Entry point: creates the Flask app, registers
│                                 # blueprints, runs the dev server
├── config.py                    # Paths & constants (DB path, hour caps, etc.)
├── db.py                        # SQLite connection handling, schema creation,
│                                 # and migrations/self-repair (see below)
├── dateutils.py                 # Monday-of-week / date-range helpers
├── emailer.py                   # Sends email, or logs it if SMTP isn't configured
├── auth.py                      # get_current_user, login_required decorators,
│                                 # and /api/auth/* routes (register/login/...)
├── user_profile.py              # /api/profile routes
├── projects.py                  # /api/projects routes (per-user CRUD)
├── entries.py                   # /api/week, /api/entries + the hour-cap validation
├── pages.py                     # Server-rendered page routes (/, /login, ...)
├── templates/
│   ├── index.html               # Main timesheet grid (requires login)
│   ├── login.html               # Sign in / create account
│   ├── change_password.html     # Forced first-login password change
│   └── profile.html             # Name / phone / entity / password
├── static/
│   ├── style.css
│   ├── app.js                   # Grid rendering + API calls
│   ├── auth.js                  # Login / register forms
│   ├── change_password.js
│   └── profile.js
├── outbox/                      # "Sent" emails when SMTP isn't configured (gitignored)
├── .flask_secret                 # auto-generated session key (gitignored)
└── timesheet.db                  # created on first run (gitignored)
```

### About `db.py`'s migration/self-repair logic
An early version of this app hit a SQLite quirk: `ALTER TABLE ... RENAME`,
when foreign keys are enabled on the connection, silently rewrites *other*
tables' foreign-key clauses to point at the renamed table. That broke the
one-time migration that added multi-user support (added a `FOREIGN KEY
constraint failed` crash on startup, and — worse — left `timesheet_entries`
permanently referencing a table that no longer existed). `db.py` now (a)
never enables `foreign_keys` on its own migration connection and uses
`PRAGMA legacy_alter_table` around any rename, so this can't happen again,
and (b) detects and repairs a database that already hit the bug, so
upgrading from an affected copy fixes itself on the next `python3 app.py`
run without losing any data.

## API

### Auth
| Method | Path                        | Purpose                                                     |
|--------|-----------------------------|---------------------------------------------------------------|
| POST   | `/api/auth/register`        | `{email}` — create an account, emails/logs a temp password    |
| POST   | `/api/auth/login`           | `{email, password}` — sign in, sets the session cookie        |
| POST   | `/api/auth/logout`          | Clear the session                                             |
| GET    | `/api/auth/me`               | Current user's profile + `must_change_password` flag          |
| POST   | `/api/auth/change-password` | `{current_password, new_password}`                            |

### Profile
| Method | Path             | Purpose                                                              |
|--------|------------------|------------------------------------------------------------------------|
| GET    | `/api/profile`   | Current user's profile                                                |
| PUT    | `/api/profile`   | `{first_name, last_name, mobile_phone, entity_name}`                   |

### Timesheet (all require login; scoped to the logged-in user)
| Method | Path                         | Purpose                                            |
|--------|------------------------------|------------------------------------------------------|
| GET    | `/api/projects`              | List your active projects                            |
| POST   | `/api/projects`              | Add a project `{name}`                               |
| PATCH  | `/api/projects/<id>`         | Rename a project `{name}`                            |
| DELETE | `/api/projects/<id>`         | Deactivate a project (soft delete)                   |
| GET    | `/api/week?date=YYYY-MM-DD`  | Get the Mon-Sun week containing `date`               |
| POST   | `/api/entries`               | Upsert an hours cell `{project_id, entry_date, hours}` |
| DELETE | `/api/entries/<id>`          | Delete a specific entry                              |

All validation (daily ≤ 8h, weekly ≤ 40h, hours between 0 and 8, project name
uniqueness per user) is enforced in `app.py` regardless of what the browser
sends, so it can't be bypassed by calling the API directly. Any request to a
project/entry that isn't yours is rejected as "unknown" rather than "not
yours," so accounts can't be probed for the existence of other users' data.

## Security notes for this local/dev setup
- Passwords are hashed with Werkzeug's `generate_password_hash` (PBKDF2);
  plaintext passwords are never stored.
- Sessions are signed cookies keyed by a secret persisted to `.flask_secret`
  (or set `FLASK_SECRET_KEY` yourself).
- There's no CSRF token on the forms and no rate-limiting on login/register —
  fine for a single small team on a local network, but worth adding before
  exposing this on the open internet.
- Use `python3 app.py` (Flask's dev server) for local use only; put a real
  WSGI server (gunicorn, waitress) and HTTPS in front of it for anything
  production-facing.
