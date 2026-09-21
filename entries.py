"""
Timesheet entries: the weekly grid data and the per-cell upsert/delete,
including the daily/weekly hour-cap validation. All scoped to the
logged-in user.
"""
from datetime import datetime

from flask import Blueprint, jsonify, request

from auth import active_password_required, get_current_user
from config import DAYS, MAX_DAY_HOURS, MAX_WEEK_HOURS
from dateutils import monday_of, parse_date, week_dates
from db import get_db

entries_bp = Blueprint("entries", __name__, url_prefix="/api")


@entries_bp.route("/week")
@active_password_required
def get_week():
    """
    GET /api/week?date=YYYY-MM-DD
    Returns the Monday-Sunday week containing `date` (defaults to today),
    with all of the current user's entries plus daily/weekly totals.
    """
    user = get_current_user()
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
        WHERE e.week_start = ? AND p.user_id = ?
        ORDER BY p.name, e.entry_date
        """,
        (ws.isoformat(), user["id"]),
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


def _validate_and_get_totals(db, user_id, week_start, entry_date, project_id, hours, exclude_entry_id=None):
    """
    Compute what the daily and weekly totals WOULD be if this entry were
    saved, scoped to `user_id` (two different users can each have entries on
    the same calendar date -- their caps must never interfere with each
    other). Returns an error string if any rule is violated, else None.
    """
    if hours < 0 or hours > MAX_DAY_HOURS:
        return f"Hours for a single project/day must be between 0 and {MAX_DAY_HOURS}."

    # Sum of this user's other entries for this day (excluding the entry
    # being updated, and this project).
    q = """
        SELECT COALESCE(SUM(e.hours), 0) AS total
        FROM timesheet_entries e
        JOIN projects p ON p.id = e.project_id
        WHERE e.entry_date = ? AND p.user_id = ? AND e.project_id != ?
    """
    params = [entry_date, user_id, project_id]
    if exclude_entry_id is not None:
        q += " AND e.id != ?"
        params.append(exclude_entry_id)
    other_day_total = db.execute(q, params).fetchone()["total"]

    new_day_total = round(other_day_total + hours, 2)
    if new_day_total > MAX_DAY_HOURS + 1e-9:
        return (
            f"Total hours for {entry_date} would be {new_day_total}, "
            f"which exceeds the {MAX_DAY_HOURS}-hour daily limit."
        )

    q = """
        SELECT COALESCE(SUM(e.hours), 0) AS total
        FROM timesheet_entries e
        JOIN projects p ON p.id = e.project_id
        WHERE e.week_start = ? AND p.user_id = ? AND NOT (e.entry_date = ? AND e.project_id = ?)
    """
    params = [week_start, user_id, entry_date, project_id]
    if exclude_entry_id is not None:
        q += " AND e.id != ?"
        params.append(exclude_entry_id)
    other_week_total = db.execute(q, params).fetchone()["total"]

    new_week_total = round(other_week_total + hours, 2)
    if new_week_total > MAX_WEEK_HOURS + 1e-9:
        return (
            f"Total hours for the week would be {new_week_total}, "
            f"which exceeds the {MAX_WEEK_HOURS}-hour weekly limit."
        )

    return None


@entries_bp.route("/entries", methods=["POST"])
@active_password_required
def upsert_entry():
    """
    Create or update (upsert) a single cell: one project, one day, some hours.
    Body: { project_id, entry_date (YYYY-MM-DD), hours, notes? }
    If hours == 0, the entry (if any) is deleted.
    """
    user = get_current_user()
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

    # Verify the project exists AND belongs to the current user.
    proj = db.execute(
        "SELECT id FROM projects WHERE id = ? AND user_id = ?", (project_id, user["id"])
    ).fetchone()
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
        db, user["id"], week_start, entry_date_s, project_id, hours, exclude_entry_id=exclude_id
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


@entries_bp.route("/entries/<int:entry_id>", methods=["DELETE"])
@active_password_required
def delete_entry(entry_id):
    user = get_current_user()
    db = get_db()
    db.execute(
        """
        DELETE FROM timesheet_entries
        WHERE id = ? AND project_id IN (SELECT id FROM projects WHERE user_id = ?)
        """,
        (entry_id, user["id"]),
    )
    db.commit()
    return jsonify({"ok": True})
