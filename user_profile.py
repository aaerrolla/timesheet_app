"""
Profile: view/edit first/last name, mobile phone, entity name.
(Login email is not editable here; password changes go through
auth.change_password.)
"""
from flask import Blueprint, jsonify, request

from auth import get_current_user, login_required, user_public
from db import get_db

profile_bp = Blueprint("profile", __name__, url_prefix="/api/profile")


@profile_bp.route("", methods=["GET"])
@login_required
def get_profile():
    return jsonify(user_public(get_current_user()))


@profile_bp.route("", methods=["PUT"])
@login_required
def update_profile():
    data = request.get_json(force=True) or {}
    first_name = (data.get("first_name") or "").strip()
    last_name = (data.get("last_name") or "").strip()
    mobile_phone = (data.get("mobile_phone") or "").strip()
    entity_name = (data.get("entity_name") or "").strip()

    user = get_current_user()
    db = get_db()
    db.execute(
        "UPDATE users SET first_name = ?, last_name = ?, mobile_phone = ?, entity_name = ? WHERE id = ?",
        (first_name, last_name, mobile_phone, entity_name, user["id"]),
    )
    db.commit()
    updated = db.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
    return jsonify(user_public(updated))
