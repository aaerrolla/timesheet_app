"""
Projects: list/create/rename/deactivate, all scoped to the logged-in user.
"""
import sqlite3

from flask import Blueprint, jsonify, request

from auth import active_password_required, get_current_user
from db import get_db

projects_bp = Blueprint("projects", __name__, url_prefix="/api/projects")


@projects_bp.route("", methods=["GET"])
@active_password_required
def list_projects():
    user = get_current_user()
    db = get_db()
    rows = db.execute(
        "SELECT id, name, active FROM projects WHERE active = 1 AND user_id = ? ORDER BY name",
        (user["id"],),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@projects_bp.route("", methods=["POST"])
@active_password_required
def create_project():
    user = get_current_user()
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Project name is required."}), 400
    db = get_db()

    dup = db.execute(
        "SELECT id FROM projects WHERE user_id = ? AND LOWER(name) = LOWER(?)",
        (user["id"], name),
    ).fetchone()
    if dup is not None:
        return jsonify({"error": f"Project '{name}' already exists."}), 409

    try:
        cur = db.execute(
            "INSERT INTO projects (user_id, name) VALUES (?, ?)", (user["id"], name)
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": f"Project '{name}' already exists."}), 409
    return jsonify({"id": cur.lastrowid, "name": name, "active": 1}), 201


@projects_bp.route("/<int:project_id>", methods=["PATCH", "PUT"])
@active_password_required
def rename_project(project_id):
    """
    Rename a project. Because timesheet_entries reference project_id (not the
    name), a rename automatically applies to every past and future entry for
    this project the moment it's saved -- no data migration needed.
    """
    user = get_current_user()
    data = request.get_json(force=True) or {}
    new_name = (data.get("name") or "").strip()
    if not new_name:
        return jsonify({"error": "Project name is required."}), 400

    db = get_db()

    existing = db.execute(
        "SELECT id, name FROM projects WHERE id = ? AND user_id = ?", (project_id, user["id"])
    ).fetchone()
    if existing is None:
        return jsonify({"error": "Unknown project."}), 404

    dup = db.execute(
        "SELECT id FROM projects WHERE id != ? AND user_id = ? AND LOWER(name) = LOWER(?)",
        (project_id, user["id"], new_name),
    ).fetchone()
    if dup is not None:
        return jsonify({"error": f"Project '{new_name}' already exists."}), 409

    if new_name == existing["name"]:
        return jsonify({"id": project_id, "name": new_name})

    db.execute("UPDATE projects SET name = ? WHERE id = ?", (new_name, project_id))
    db.commit()
    return jsonify({"id": project_id, "name": new_name})


@projects_bp.route("/<int:project_id>", methods=["DELETE"])
@active_password_required
def deactivate_project(project_id):
    """Soft-delete: mark inactive rather than removing history."""
    user = get_current_user()
    db = get_db()
    db.execute(
        "UPDATE projects SET active = 0 WHERE id = ? AND user_id = ?", (project_id, user["id"])
    )
    db.commit()
    return jsonify({"ok": True})
