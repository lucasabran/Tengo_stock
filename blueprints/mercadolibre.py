"""Pantalla y API de Mercado Libre multicuenta (la lógica está en ml_multi.py)."""
import json
import threading
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, render_template, request

import auth
import ml_multi
from db import get_db

bp = Blueprint("mercadolibre", __name__)
MAX_ANSWER = 2000
MAX_MESSAGE = 350  # límite de Mercado Libre para mensajes de posventa


def _db():
    db = get_db()
    ml_multi.ensure_schema(db)
    return db


def _names(db):
    return {r["user_id"]: (r["alias"] or r["nickname"] or str(r["user_id"]))
            for r in db.execute("SELECT user_id, alias, nickname FROM ml_accounts")}


@bp.route("/mercado-libre")
def ml_page():
    return render_template("mercadolibre.html", active="mercadolibre")


@bp.route("/api/ml/overview", methods=["GET"])
def ml_overview():
    db = _db()
    names = _names(db)
    week = (datetime.now() - timedelta(days=7)).isoformat()
    today = datetime.now().date().isoformat()
    accounts = []
    for a in db.execute("SELECT * FROM ml_accounts ORDER BY COALESCE(NULLIF(alias, ''), nickname)"):
        uid = a["user_id"]
        sales = db.execute("SELECT COUNT(*) n, COALESCE(SUM(total), 0) t FROM ml_orders WHERE user_id = ? AND "
                           "date_created >= ? AND status = 'paid'", (uid, week)).fetchone()
        accounts.append({
            "user_id": uid, "name": names[uid], "nickname": a["nickname"], "alias": a["alias"],
            "status": a["status"], "last_error": a["last_error"], "last_sync": a["last_sync"],
            "reputation": json.loads(a["reputation"] or "{}"),
            "questions": db.execute("SELECT COUNT(*) FROM ml_questions WHERE user_id = ? AND status = 'UNANSWERED'", (uid,)).fetchone()[0],
            "claims": db.execute("SELECT COUNT(*) FROM ml_claims WHERE user_id = ?", (uid,)).fetchone()[0],
            "messages": db.execute("SELECT COUNT(*) FROM ml_conversations WHERE user_id = ? AND unread > 0", (uid,)).fetchone()[0],
            "to_ship": db.execute("SELECT COUNT(*) FROM ml_orders WHERE user_id = ? AND ship_status IN ('ready_to_ship', 'pending', "
                                  "'handling') AND status = 'paid'", (uid,)).fetchone()[0],
            "sales_week": sales["n"], "total_week": sales["t"],
            "sales_today": db.execute("SELECT COUNT(*) FROM ml_orders WHERE user_id = ? AND substr(date_created, 1, 10) = ? "
                                      "AND status = 'paid'", (uid, today)).fetchone()[0],
        })
    return jsonify({"configured": ml_multi.configured(), "accounts": accounts,
                    "can_answer": auth.has_any(("ml.answer",)), "can_manage": auth.has_any(("ml.manage",))})


@bp.route("/api/ml/questions", methods=["GET"])
def ml_questions():
    db = _db()
    names = _names(db)
    pending = [dict(r, account=names.get(r["user_id"], "")) for r in db.execute(
        "SELECT * FROM ml_questions WHERE status = 'UNANSWERED' ORDER BY date_created")]
    answered = [dict(r, account=names.get(r["user_id"], "")) for r in db.execute(
        "SELECT * FROM ml_questions WHERE status = 'ANSWERED' ORDER BY answered_at DESC LIMIT 30")]
    return jsonify({"pending": pending, "answered": answered})


@bp.route("/api/ml/questions/<int:qid>/answer", methods=["POST"])
def ml_answer(qid):
    text = str((request.get_json(force=True) or {}).get("text") or "").strip()
    if not text or len(text) > MAX_ANSWER:
        return jsonify({"error": f"La respuesta no puede estar vacía ni pasar {MAX_ANSWER} caracteres"}), 400
    db = _db()
    try:
        ml_multi.answer_question(db, qid, text, auth.actor())
    except ml_multi.MLError as exc:
        return jsonify({"error": f"Mercado Libre no la aceptó: {exc}"}), 400
    auth.audit("ml_responder_pregunta", "ml_question", qid, text[:200])
    return jsonify({"ok": True})


@bp.route("/api/ml/orders", methods=["GET"])
def ml_orders():
    db = _db()
    names = _names(db)
    days = min(max(int(request.args.get("days", 30) or 30), 1), ml_multi.ORDERS_KEEP_DAYS)
    since = (datetime.now() - timedelta(days=days)).isoformat()
    sql, args = "SELECT * FROM ml_orders WHERE date_created >= ?", [since]
    if request.args.get("account"):
        sql += " AND user_id = ?"
        args.append(int(request.args["account"]))
    rows = db.execute(sql + " ORDER BY date_created DESC LIMIT 500", args).fetchall()
    return jsonify({"orders": [dict(r, account=names.get(r["user_id"], "")) for r in rows]})


@bp.route("/api/ml/claims", methods=["GET"])
def ml_claims():
    db = _db()
    names = _names(db)
    rows = db.execute("SELECT c.*, o.items FROM ml_claims c LEFT JOIN ml_orders o ON o.id = c.order_id "
                      "ORDER BY CASE WHEN c.due_date = '' THEN 1 ELSE 0 END, c.due_date, c.date_created").fetchall()
    return jsonify({"claims": [dict(r, account=names.get(r["user_id"], "")) for r in rows]})


@bp.route("/api/ml/messages", methods=["GET"])
def ml_messages():
    db = _db()
    names = _names(db)
    rows = db.execute("SELECT m.*, o.items FROM ml_conversations m LEFT JOIN ml_orders o ON o.user_id = m.user_id AND "
                      "(o.pack_id = m.pack_id OR o.id = m.pack_id) GROUP BY m.user_id, m.pack_id "
                      "ORDER BY m.last_date").fetchall()
    return jsonify({"conversations": [dict(r, account=names.get(r["user_id"], "")) for r in rows]})


@bp.route("/api/ml/messages/<int:user_id>/<int:pack_id>", methods=["GET"])
def ml_conversation(user_id, pack_id):
    try:
        return jsonify({"messages": ml_multi.conversation(_db(), user_id, pack_id)})
    except ml_multi.MLError as exc:
        return jsonify({"error": str(exc)}), 400


@bp.route("/api/ml/messages/<int:user_id>/<int:pack_id>/reply", methods=["POST"])
def ml_reply(user_id, pack_id):
    text = str((request.get_json(force=True) or {}).get("text") or "").strip()
    if not text or len(text) > MAX_MESSAGE:
        return jsonify({"error": f"El mensaje no puede estar vacío ni pasar {MAX_MESSAGE} caracteres"}), 400
    try:
        ml_multi.reply_message(_db(), user_id, pack_id, text)
    except ml_multi.MLError as exc:
        return jsonify({"error": f"Mercado Libre no lo aceptó: {exc}"}), 400
    auth.audit("ml_responder_mensaje", "ml_pack", pack_id, text[:200])
    return jsonify({"ok": True})


# --- cuentas -----------------------------------------------------------------------------
@bp.route("/api/ml/link", methods=["POST"])
def ml_new_link():
    if not ml_multi.configured():
        return jsonify({"error": "Falta cargar ML_CLIENT_ID y ML_CLIENT_SECRET en el servidor (Render > Environment)"}), 400
    alias = str((request.get_json(silent=True) or {}).get("alias") or "").strip()
    url = ml_multi.new_link(_db(), alias, auth.actor(), request.host)
    auth.audit("ml_link_creado", "ml_account", "", alias)
    return jsonify({"url": url, "days": ml_multi.LINK_DAYS})


@bp.route("/api/ml/accounts/<int:user_id>", methods=["POST"])
def ml_update_account(user_id):
    alias = str((request.get_json(force=True) or {}).get("alias") or "").strip()[:60]
    db = _db()
    cur = db.execute("UPDATE ml_accounts SET alias = ? WHERE user_id = ?", (alias, user_id))
    db.commit()
    if not cur.rowcount:
        return jsonify({"error": "cuenta no encontrada"}), 404
    auth.audit("ml_cuenta_alias", "ml_account", user_id, alias)
    return jsonify({"ok": True})


@bp.route("/api/ml/accounts/<int:user_id>/delete", methods=["POST"])
def ml_delete_account(user_id):
    db = _db()
    row = db.execute("SELECT nickname FROM ml_accounts WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        return jsonify({"error": "cuenta no encontrada"}), 404
    for table in ("ml_orders", "ml_questions", "ml_claims", "ml_conversations", "ml_accounts"):
        db.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
    db.commit()
    auth.audit("ml_cuenta_desconectada", "ml_account", user_id, row["nickname"])
    return jsonify({"ok": True})


@bp.route("/api/ml/sync", methods=["POST"])
def ml_sync_now():
    if not ml_multi.configured():
        return jsonify({"error": "Falta configurar la app de Mercado Libre en el servidor"}), 400
    threading.Thread(target=ml_multi.sync_all, daemon=True).start()
    return jsonify({"started": True}), 202


# --- públicas (sin sesión): las usa Mercado Libre -------------------------------------
@bp.route("/ml/callback", methods=["GET"])
def ml_callback():
    if request.args.get("error"):
        return render_template("ml_conectada.html", ok=False,
                               message="No se dio el permiso. Si fue un error, volvé a abrir el link."), 400
    if not ml_multi.configured():
        return render_template("ml_conectada.html", ok=False, message="El sistema todavía no está configurado."), 400
    nickname, error = ml_multi.complete_link(_db(), request.args.get("state"), request.args.get("code", ""), request.host)
    if error:
        return render_template("ml_conectada.html", ok=False, message=error), 400
    return render_template("ml_conectada.html", ok=True, message=f"La cuenta {nickname} quedó conectada. Ya podés cerrar esta ventana.")


@bp.route("/ml/notificaciones", methods=["POST"])
def ml_notification():
    ml_multi.on_notification(request.get_json(silent=True) or {})
    return "", 200  # Mercado Libre reintenta si no recibe 200 rápido
