"""
Server-rendered page routes (as opposed to the /api/* JSON routes), with
the login-state redirects that gate them.
"""
from flask import Blueprint, redirect, render_template, url_for

from auth import get_current_user

pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/")
def index():
    user = get_current_user()
    if user is None:
        return redirect(url_for("pages.login_page"))
    if user["must_change_password"]:
        return redirect(url_for("pages.change_password_page"))
    return render_template("index.html")


@pages_bp.route("/login")
def login_page():
    user = get_current_user()
    if user is not None:
        return redirect(
            url_for("pages.change_password_page") if user["must_change_password"] else url_for("pages.index")
        )
    return render_template("login.html")


@pages_bp.route("/change-password")
def change_password_page():
    if get_current_user() is None:
        return redirect(url_for("pages.login_page"))
    return render_template("change_password.html")


@pages_bp.route("/profile")
def profile_page():
    if get_current_user() is None:
        return redirect(url_for("pages.login_page"))
    return render_template("profile.html")
