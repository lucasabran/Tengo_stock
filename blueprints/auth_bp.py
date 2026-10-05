from datetime import datetime

from flask import Blueprint, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import auth
from db import get_db, now_iso

bp = Blueprint("auth", __name__)


def _safe_next(target):
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return None


@bp.route("/login", methods=["GET"])
def login_page():
    if session.get("uid"):
        return redirect("/")
    return render_template("login.html", error=None, username="", next_url=_safe_next(request.args.get("next")) or "")


@bp.route("/login", methods=["POST"])
def login():
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    next_url = _safe_next(request.form.get("next"))

    def fail(message, status=401):
        return render_template("login.html", error=message, username=username, next_url=next_url or ""), status

    if auth.is_locked(username):
        auth.audit("login_bloqueado", "user", username, "demasiados intentos", username=username)
        return fail("Demasiados intentos. Proba de nuevo en unos minutos.", 429)

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    stored_hash = user["password_hash"] if user else auth._DUMMY_HASH
    ok = check_password_hash(stored_hash, password) and user is not None and user["active"]
    if not ok:
        auth.register_fail(username)
        auth.audit("login_fallido", "user", username, "", username=username)
        return fail("Usuario o clave incorrectos")

    auth.clear_fails(username)
    auth.start_session(user)
    db.execute("UPDATE users SET last_login = ? WHERE id = ?", (now_iso(), user["id"]))
    db.commit()
    g.user = user
    auth.audit("login", "user", user["id"], "")
    if user["must_change_password"]:
        return redirect(url_for("auth.account_page", forced=1))
    return redirect(next_url or "/")


@bp.route("/logout", methods=["POST"])
def logout():
    auth.audit("logout", "user", g.user["id"], "")
    session.clear()
    return redirect(url_for("auth.login_page"))


@bp.route("/cuenta")
def account_page():
    return render_template("cuenta.html", forced=bool(request.args.get("forced")), active="cuenta")


@bp.route("/api/me")
def me():
    user = g.user
    return jsonify(
        {
            "username": user["username"],
            "full_name": user["full_name"],
            "role": "Dueño" if user["is_owner"] else user["role_name"],
            "is_owner": bool(user["is_owner"]),
            "permissions": sorted(g.permissions),
        }
    )


@bp.route("/api/me/password", methods=["POST"])
def change_password():
    data = request.get_json(force=True) or {}
    current = data.get("current", "")
    new = data.get("new", "")
    if not check_password_hash(g.user["password_hash"], current):
        return jsonify({"error": "La clave actual no es correcta"}), 400
    problem = auth.validate_new_password(new)
    if problem:
        return jsonify({"error": problem}), 400
    if new == current:
        return jsonify({"error": "La clave nueva tiene que ser distinta de la actual"}), 400

    db = get_db()
    new_version = g.user["token_version"] + 1
    db.execute(
        "UPDATE users SET password_hash = ?, must_change_password = 0, token_version = ? WHERE id = ?",
        (generate_password_hash(new), new_version, g.user["id"]),
    )
    db.commit()
    session["tv"] = new_version
    auth.audit("cambio_clave", "user", g.user["id"], "")
    return jsonify({"ok": True})
