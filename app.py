"""
Timesheet web application
--------------------------
Single-page web app (Python 3 + Flask + SQLite) for entering weekly time data
against one or more projects.

Business rules enforced server-side (never trust the client):
  * Week always starts on Monday.
  * Sum of hours for any single day (across all projects) must be <= 8.
  * Sum of hours for the whole week (across all projects/days) must be <= 40.
  * Hours per cell must be >= 0 and <= 8 (a single project can't exceed a day alone either).
  * Entries can be created, edited (upserted) and deleted.

Run:
    python3 app.py
Then open http://127.0.0.1:5000/ in a browser.
"""
import os
import sqlite3
from datetime import datetime, timedelta

from flask import Flask, g, jsonify, render_template, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "timesheet.db")

app = Flask(__name__)

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MAX_DAY_HOURS = 8
MAX_WEEK_HOURS = 40


# ----------------------------------------------------------------------------
# Database helpers
# ----------------------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            name    TEXT NOT NULL UNIQUE,
            active  INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS timesheet_entries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id  INTEGER NOT NULL REFERENCES projects(id),
            entry_date  TEXT NOT NULL,          -- ISO date, always a Monday..Sunday date
            week_start  TEXT NOT NULL,          -- ISO date of the Monday that starts the week
            hours       REAL NOT NULL CHECK (hours >= 0 AND hours <= 8),
            notes       TEXT DEFAULT '',
            UNIQUE(project_id, entry_date)
        );

        CREATE INDEX IF NOT EXISTS idx_entries_week ON timesheet_entries(week_start);
        """
    )
    db.commit()

    # Seed a couple of sample projects if the table is empty, so the UI isn't blank.
    cur = db.execute("SELECT COUNT(*) AS c FROM projects")
    if cur.fetchone()["c"] == 0:
        db.executemany(
            "INSERT INTO projects (name) VALUES (?)",
            [("Internal",), ("Project Alpha",), ("Project Beta",)],
        )
        db.commit()
    db.close()


# ----------------------------------------------------------------------------
# Date helpers
# ----------------------------------------------------------------------------
def parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def monday_of(d):
    return d - timedelta(days=d.weekday())  # weekday(): Monday=0


def week_dates(week_start):
    """Return list of 7 ISO date strings, Monday..Sunday, for the given Monday."""
    return [(week_start + timedelta(days=i)).isoformat() for i in range(7)]


# ----------------------------------------------------------------------------
# Routes - pages
# ----------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


# ----------------------------------------------------------------------------
# Routes - projects API
# ----------------------------------------------------------------------------
@app.route("/api/projects", methods=["GET"])
def list_projects():
    db = get_db()
    rows = db.execute(
        "SELECT id, name, active FROM projects WHERE active = 1 ORDER BY name"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/projects", methods=["POST"])
def create_project():
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Project name is required."}), 400
    db = get_db()

    dup = db.execute("SELECT id FROM projects WHERE LOWER(name) = LOWER(?)", (name,)).fetchone()
    if dup is not None:
        return jsonify({"error": f"Project '{name}' already exists."}), 409

    try:
        cur = db.execute("INSERT INTO projects (name) VALUES (?)", (name,))
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": f"Project '{name}' already exists."}), 409
    return jsonify({"id": cur.lastrowid, "name": name, "active": 1}), 201


@app.route("/api/projects/<int:project_id>", methods=["PATCH", "PUT"])
def rename_project(project_id):
    """
    Rename a project. Because timesheet_entries reference project_id (not the
    name), a rename automatically applies to every past and future entry for
    this project the moment it's saved -- no data migration needed.
    """
    data = request.get_json(force=True) or {}
    new_name = (data.get("name") or "").strip()
    if not new_name:
        return jsonify({"error": "Project name is required."}), 400

    db = get_db()

    existing = db.execute("SELECT id, name FROM projects WHERE id = ?", (project_id,)).fetchone()
    if existing is None:
        return jsonify({"error": "Unknown project."}), 404

    # Case-insensitive uniqueness check against every other project
    # (active or not), so renaming can never collide with an existing name.
    dup = db.execute(
        "SELECT id FROM projects WHERE id != ? AND LOWER(name) = LOWER(?)",
        (project_id, new_name),
    ).fetchone()
    if dup is not None:
        return jsonify({"error": f"Project '{new_name}' already exists."}), 409

    if new_name == existing["name"]:
        return jsonify({"id": project_id, "name": new_name})

    db.execute("UPDATE projects SET name = ? WHERE id = ?", (new_name, project_id))
    db.commit()
    return jsonify({"id": project_id, "name": new_name})


@app.route("/api/projects/<int:project_id>", methods=["DELETE"])
def deactivate_project(project_id):
    """Soft-delete: mark inactive rather than removing history."""
    db = get_db()
    db.execute("UPDATE projects SET active = 0 WHERE id = ?", (project_id,))
    db.commit()
    return jsonify({"ok": True})


# ----------------------------------------------------------------------------
# Routes - timesheet week API
# ----------------------------------------------------------------------------
@app.route("/api/week")
def get_week():
    """
    GET /api/week?date=YYYY-MM-DD
    Returns the Monday-Sunday week containing `date` (defaults to today),
    with all entries plus daily/weekly totals.
    """
    date_param = request.args.get("date")
    ref_date = parse_date(date_param) if date_param else datetime.today().date()
    ws = monday_of(ref_date)
    dates = week_dates(ws)

    db = get_db()
    rows = db.execute(
        """
        SELECT e.id, e.project_id, p.name AS project_name, e.entry_date, e.hours, e.notes
        FROM timesheet_entries e
        JOIN projects p ON p.id = e.project_id
        WHERE e.week_start = ?
        ORDER BY p.name, e.entry_date
        """,
        (ws.isoformat(),),
    ).fetchall()

    entries = [dict(r) for r in rows]

    daily_totals = {d: 0.0 for d in dates}
    for e in entries:
        daily_totals[e["entry_date"]] = round(daily_totals[e["entry_date"]] + e["hours"], 2)
    week_total = round(sum(daily_totals.values()), 2)

    return jsonify(
        {
            "week_start": ws.isoformat(),
            "week_end": dates[-1],
            "days": dates,
            "day_labels": DAYS,
            "entries": entries,
            "daily_totals": daily_totals,
            "week_total": week_total,
            "max_day_hours": MAX_DAY_HOURS,
            "max_week_hours": MAX_WEEK_HOURS,
        }
    )


def _validate_and_get_totals(db, week_start, entry_date, project_id, hours, exclude_entry_id=None):
    """
    Compute what the daily and weekly totals WOULD be if this entry were saved,
    and return an error string if any rule is violated, else None.
    """
    if hours < 0 or hours > MAX_DAY_HOURS:
        return f"Hours for a single project/day must be between 0 and {MAX_DAY_HOURS}."

    # Sum of other entries for this day (excluding the entry being updated, and this project)
    q = """
        SELECT COALESCE(SUM(hours), 0) AS total
        FROM timesheet_entries
        WHERE entry_date = ? AND project_id != ?
    """
    params = [entry_date, project_id]
    if exclude_entry_id is not None:
        q += " AND id != ?"
        params.append(exclude_entry_id)
    other_day_total = db.execute(q, params).fetchone()["total"]

    new_day_total = round(other_day_total + hours, 2)
    if new_day_total > MAX_DAY_HOURS + 1e-9:
        return (
            f"Total hours for {entry_date} would be {new_day_total}, "
            f"which exceeds the {MAX_DAY_HOURS}-hour daily limit."
        )

    q = """
        SELECT COALESCE(SUM(hours), 0) AS total
        FROM timesheet_entries
        WHERE week_start = ? AND NOT (entry_date = ? AND project_id = ?)
    """
    params = [week_start, entry_date, project_id]
    if exclude_entry_id is not None:
        q += " AND id != ?"
        params.append(exclude_entry_id)
    other_week_total = db.execute(q, params).fetchone()["total"]

    new_week_total = round(other_week_total + hours, 2)
    if new_week_total > MAX_WEEK_HOURS + 1e-9:
        return (
            f"Total hours for the week would be {new_week_total}, "
            f"which exceeds the {MAX_WEEK_HOURS}-hour weekly limit."
        )

    return None


@app.route("/api/entries", methods=["POST"])
def upsert_entry():
    """
    Create or update (upsert) a single cell: one project, one day, some hours.
    Body: { project_id, entry_date (YYYY-MM-DD), hours, notes? }
    If hours == 0, the entry (if any) is deleted.
    """
    data = request.get_json(force=True) or {}
    try:
        project_id = int(data["project_id"])
        entry_date_s = data["entry_date"]
        hours = float(data["hours"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "project_id, entry_date and hours are required."}), 400

    notes = (data.get("notes") or "").strip()

    if hours < 0:
        return jsonify({"error": "Hours cannot be negative."}), 400

    try:
        entry_date = parse_date(entry_date_s)
    except ValueError:
        return jsonify({"error": "entry_date must be YYYY-MM-DD."}), 400

    week_start = monday_of(entry_date).isoformat()

    db = get_db()

    # Verify project exists
    proj = db.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
    if proj is None:
        return jsonify({"error": "Unknown project."}), 404

    existing = db.execute(
        "SELECT id FROM timesheet_entries WHERE project_id = ? AND entry_date = ?",
        (project_id, entry_date_s),
    ).fetchone()
    exclude_id = existing["id"] if existing else None

    if hours == 0:
        if existing:
            db.execute("DELETE FROM timesheet_entries WHERE id = ?", (existing["id"],))
            db.commit()
        return jsonify({"ok": True, "deleted": True})

    error = _validate_and_get_totals(
        db, week_start, entry_date_s, project_id, hours, exclude_entry_id=exclude_id
    )
    if error:
        return jsonify({"error": error}), 422

    if existing:
        db.execute(
            "UPDATE timesheet_entries SET hours = ?, notes = ? WHERE id = ?",
            (hours, notes, existing["id"]),
        )
        entry_id = existing["id"]
    else:
        cur = db.execute(
            "INSERT INTO timesheet_entries (project_id, entry_date, week_start, hours, notes) "
            "VALUES (?, ?, ?, ?, ?)",
            (project_id, entry_date_s, week_start, hours, notes),
        )
        entry_id = cur.lastrowid
    db.commit()

    return jsonify({"ok": True, "id": entry_id})


@app.route("/api/entries/<int:entry_id>", methods=["DELETE"])
def delete_entry(entry_id):
    db = get_db()
    db.execute("DELETE FROM timesheet_entries WHERE id = ?", (entry_id,))
    db.commit()
    return jsonify({"ok": True})


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
else:
    # Ensure DB exists even if imported (e.g. by a WSGI server) rather than run directly.
    if not os.path.exists(DB_PATH):
        init_db()
