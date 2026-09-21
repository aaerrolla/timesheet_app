# Timesheet

A single-page timesheet web app built with **Python 3 (Flask)** and **SQLite**.

## Features
- Weekly grid, Monday through Sunday, with one row per project.
- Enter hours per project per day; add/remove projects at any time.
- Server-enforced rules (checked on every save, not just in the UI):
  - A single day's total across all projects cannot exceed **8 hours**.
  - A week's total across all days/projects cannot exceed **40 hours**.
- Edit any cell at any time — saving updates the existing entry (upsert).
- Set a cell to 0 (or clear it) to remove that entry.
- Week navigation (Prev / Next / This week); daily and weekly totals with a
  progress bar that turns red if a limit is (attempted to be) exceeded.
- Removing a project only deactivates it — historical hours are preserved.

## Requirements
- Python 3.8+
- Flask (`pip install flask`)

## Run it
```bash
cd timesheet_app
pip install flask          # if not already installed
python3 app.py
```
Then open **http://127.0.0.1:5000/** in your browser.

The SQLite database file `timesheet.db` is created automatically on first
run (with three sample projects seeded in). Delete it to start fresh.

## Project layout
```
timesheet_app/
├── app.py                # Flask app: routes, validation, SQLite access
├── templates/
│   └── index.html        # Single page shell
├── static/
│   ├── style.css
│   └── app.js             # Grid rendering + API calls
└── timesheet.db           # created on first run
```

## API
| Method | Path                     | Purpose                                  |
|--------|--------------------------|-------------------------------------------|
| GET    | `/api/projects`          | List active projects                     |
| POST   | `/api/projects`          | Add a project `{name}`                   |
| DELETE | `/api/projects/<id>`     | Deactivate a project (soft delete)       |
| GET    | `/api/week?date=YYYY-MM-DD` | Get the Mon-Sun week containing `date` |
| POST   | `/api/entries`           | Upsert an hours cell `{project_id, entry_date, hours}` |
| DELETE | `/api/entries/<id>`      | Delete a specific entry                  |

All validation (daily ≤ 8h, weekly ≤ 40h, hours between 0 and 8) is enforced
in `app.py` regardless of what the browser sends, so the limits can't be
bypassed by calling the API directly.
