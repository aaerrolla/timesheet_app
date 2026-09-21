"""
Authentication: current-user helpers, access-control decorators, and the
/api/auth/* routes (register, login, logout, me, change-password).
"""
import re
import sqlite3
from functools import wraps

from flask import Blueprint, g, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_db
from emailer import generate_temp_password, send_email

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


# ----------------------------------------------------------------------------
# Current-user helpers (used across auth/profile/projects/entries routes)
# ----------------------------------------------------------------------------
def get_current_user():
    if "user" in g:
        return g.user
    user_id = session.get("user_id")
    if not user_id:
        g.user = None
        return None
    g.user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return g.user


def user_public(user):
    return {
        "id": user["id"],
        "email": user["email"],
        "first_name": user["first_name"],
        "last_name": user["last_name"],
        "mobile_phone": user["mobile_phone"],
        "entity_name": user["entity_name"],
        "must_change_password": bool(user["must_change_password"]),
    }


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if get_current_user() is None:
            return jsonify({"error": "Please log in."}), 401
        return view(*args, **kwargs)

    return wrapped


def active_password_required(view):
    """Login required AND the forced first-login password change is done."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        user = get_current_user()
        if user is None:
            return jsonify({"error": "Please log in."}), 401
        if user["must_change_password"]:
            return (
                jsonify(
                    {
                        "error": "You must change your password before continuing.",
                        "code": "password_change_required",
                    }
                ),
                403,
            )
        return view(*args, **kwargs)

    return wrapped


def adopt_orphan_projects_if_first_user(user_id):
    """
    One-time upgrade path: if this is the very first user in the system,
    give them ownership of any pre-existing projects (and, transitively,
    their timesheet entries) that don't belong to anyone yet.
    """
    db = get_db()
    first_user_id = db.execute("SELECT MIN(id) AS id FROM users").fetchone()["id"]
    if first_user_id == user_id:
        db.execute("UPDATE projects SET user_id = ? WHERE user_id IS NULL", (user_id,))
        db.commit()


# ----------------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------------
@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(force=True) or {}
    email = (data.get("email") or "").strip().lower()
    if not email or not EMAIL_RE.match(email):
        return jsonify({"error": "Please enter a valid email address."}), 400

    db = get_db()
    if db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone() is not None:
        return (
            jsonify({"error": "An account with this email already exists. Try logging in instead."}),
            409,
        )

    temp_password = generate_temp_password()
    password_hash = generate_password_hash(temp_password)

    try:
        cur = db.execute(
            "INSERT INTO users (email, password_hash, must_change_password) VALUES (?, ?, 1)",
            (email, password_hash),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return (
            jsonify({"error": "An account with this email already exists. Try logging in instead."}),
            409,
        )

    user_id = cur.lastrowid
    adopt_orphan_projects_if_first_user(user_id)

    subject = "Your Timesheet password"
    body = (
        "Welcome to Timesheet!\n\n"
        f"Your temporary password is: {temp_password}\n\n"
        "Log in with this password -- you'll be asked to choose a new one "
        "the first time you sign in.\n"
    )
    sent = send_email(email, subject, body)

    response = {
        "ok": True,
        "message": (
            "Account created. Check your email for your temporary password."
            if sent
            else "Account created. Email delivery isn't configured on this server, "
            "so here is your temporary password -- use it to log in."
        ),
    }
    if not sent:
        response["dev_password"] = temp_password
    return jsonify(response), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(force=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if user is None or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid email or password."}), 401

    session.clear()
    session["user_id"] = user["id"]
    session.permanent = True

    adopt_orphan_projects_if_first_user(user["id"])

    return jsonify(
        {
            "ok": True,
            "must_change_password": bool(user["must_change_password"]),
            "user": user_public(user),
        }
    )


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@auth_bp.route("/me")
def me():
    user = get_current_user()
    if user is None:
        return jsonify({"error": "Not authenticated."}), 401
    return jsonify(user_public(user))


@auth_bp.route("/change-password", methods=["POST"])
@login_required
def change_password():
    data = request.get_json(force=True) or {}
    current_password = data.get("current_password") or ""
    new_password = data.get("new_password") or ""

    user = get_current_user()
    if not check_password_hash(user["password_hash"], current_password):
        return jsonify({"error": "Current password is incorrect."}), 400
    if len(new_password) < 8:
        return jsonify({"error": "New password must be at least 8 characters."}), 400
    if check_password_hash(user["password_hash"], new_password):
        return jsonify({"error": "New password must be different from the current password."}), 400

    db = get_db()
    db.execute(
        "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
        (generate_password_hash(new_password), user["id"]),
    )
    db.commit()
    return jsonify({"ok": True})
