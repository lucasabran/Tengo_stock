import time

from flask import Blueprint, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import auth
import totp
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

    if user["totp_enabled"]:
        # La clave estaba bien, pero falta el codigo de la app: todavia NO hay sesion iniciada
        session.clear()
        session["pre2fa"] = {"uid": user["id"], "next": next_url or "", "ts": int(time.time())}
        return redirect(url_for("auth.login_2fa_page"))
    return _finish_login(db, user, next_url)


def _finish_login(db, user, next_url):
    auth.clear_fails(user["username"])
    auth.start_session(user)
    db.execute("UPDATE users SET last_login = ? WHERE id = ?", (now_iso(), user["id"]))
    db.commit()
    g.user = user
    auth.audit("login", "user", user["id"], "")
    if user["must_change_password"]:
        return redirect(url_for("auth.account_page", forced=1))
    return redirect(next_url or "/")


PRE2FA_SECONDS = 300


def _pending_2fa():
    pending = session.get("pre2fa")
    if not pending or time.time() - pending.get("ts", 0) > PRE2FA_SECONDS:
        session.pop("pre2fa", None)
        return None, None
    user = get_db().execute("SELECT * FROM users WHERE id = ?", (pending["uid"],)).fetchone()
    if not user or not user["active"] or not user["totp_enabled"]:
        session.pop("pre2fa", None)
        return None, None
    return pending, user


@bp.route("/login/2fa", methods=["GET"])
def login_2fa_page():
    pending, user = _pending_2fa()
    if not pending:
        return redirect(url_for("auth.login_page"))
    return render_template("login_2fa.html", error=None, username=user["username"])


@bp.route("/login/2fa", methods=["POST"])
def login_2fa():
    pending, user = _pending_2fa()
    if not pending:
        return redirect(url_for("auth.login_page"))
    username = user["username"]
    if auth.is_locked(username):
        auth.audit("login_bloqueado", "user", username, "demasiados intentos (2FA)", username=username)
        return render_template("login_2fa.html", error="Demasiados intentos. Proba de nuevo en unos minutos.", username=username), 429
    counter = totp.verify(user["totp_secret"], request.form.get("code"), user["totp_last"])
    if counter is None:
        auth.register_fail(username)
        auth.audit("login_2fa_fallido", "user", username, "", username=username)
        return render_template("login_2fa.html", error="Codigo incorrecto o vencido", username=username), 401
    db = get_db()
    db.execute("UPDATE users SET totp_last = ? WHERE id = ?", (counter, user["id"]))
    return _finish_login(db, user, _safe_next(pending.get("next")))


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


# ---------------------------------------------------------------------------
# Verificacion en dos pasos (cada usuario la activa para si mismo)
# ---------------------------------------------------------------------------
@bp.route("/api/me/2fa", methods=["GET"])
def twofa_status():
    return jsonify({"enabled": bool(g.user["totp_enabled"])})


@bp.route("/api/me/2fa/setup", methods=["POST"])
def twofa_setup():
    if g.user["totp_enabled"]:
        return jsonify({"error": "La verificacion en dos pasos ya esta activa"}), 400
    secret = totp.new_secret()
    db = get_db()
    db.execute("UPDATE users SET totp_secret = ?, totp_last = 0 WHERE id = ?", (secret, g.user["id"]))
    db.commit()
    return jsonify({"secret": secret, "uri": totp.provisioning_uri(secret, g.user["username"])})


@bp.route("/api/me/2fa/enable", methods=["POST"])
def twofa_enable():
    data = request.get_json(force=True) or {}
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (g.user["id"],)).fetchone()
    if user["totp_enabled"] or not user["totp_secret"]:
        return jsonify({"error": "Primero genera la clave con 'Activar'"}), 400
    counter = totp.verify(user["totp_secret"], data.get("code"), 0)
    if counter is None:
        return jsonify({"error": "Codigo incorrecto. Revisa la hora del celular y proba con el codigo nuevo."}), 400
    db.execute("UPDATE users SET totp_enabled = 1, totp_last = ? WHERE id = ?", (counter, g.user["id"]))
    db.commit()
    auth.audit("2fa_activado", "user", g.user["id"], "")
    return jsonify({"ok": True})


@bp.route("/api/me/2fa/disable", methods=["POST"])
def twofa_disable():
    data = request.get_json(force=True) or {}
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (g.user["id"],)).fetchone()
    if not user["totp_enabled"]:
        return jsonify({"error": "La verificacion en dos pasos no esta activa"}), 400
    if not check_password_hash(user["password_hash"], data.get("password", "")):
        return jsonify({"error": "La clave no es correcta"}), 400
    if totp.verify(user["totp_secret"], data.get("code"), user["totp_last"]) is None:
        return jsonify({"error": "Codigo incorrecto o vencido"}), 400
    db.execute("UPDATE users SET totp_enabled = 0, totp_secret = '', totp_last = 0 WHERE id = ?", (g.user["id"],))
    db.commit()
    auth.audit("2fa_desactivado", "user", g.user["id"], "")
    return jsonify({"ok": True})
