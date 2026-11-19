"""Mantenimiento y automatizacion: copias de seguridad diarias y resumen diario."""
from datetime import date

from flask import Blueprint, jsonify, request, send_file

import auth
import jobs
import tn_sync
from db import get_db

bp = Blueprint("ops", __name__)


# --- Copias de seguridad (solo el dueño) -----------------------------------
@bp.route("/api/admin/backups", methods=["GET"])
def list_backups():
    db = get_db()
    return jsonify({
        "backups": jobs.list_backups(),
        "last_error": tn_sync.get_setting(db, "backup_last_error"),
        "keep_daily": jobs.KEEP_DAILY_BACKUPS,
    })


@bp.route("/api/admin/backups/<name>", methods=["GET"])
def download_backup_file(name):
    if name not in {b["name"] for b in jobs.list_backups()}:  # solo archivos de la lista: nada de rutas raras
        return jsonify({"error": "copia no encontrada"}), 404
    auth.audit("backup_descargado", "file", name, "")
    return send_file(jobs.backup_dir() / name, as_attachment=True, download_name=name, mimetype="application/octet-stream")


# --- Resumen diario ---------------------------------------------------------
@bp.route("/api/daily-summary", methods=["GET"])
def daily_summary():
    day = None
    raw = request.args.get("date")
    if raw:
        try:
            day = date.fromisoformat(raw)
        except ValueError:
            return jsonify({"error": "fecha invalida"}), 400
    summary = jobs.build_summary(
        get_db(), day, sales=auth.has_any(("sales.view",)), costs=auth.has_any(("stock.costs",))
    )
    if not auth.has_any(("tiendanube.manage",)):
        summary["tienda_nube"] = None
    return jsonify(summary)


@bp.route("/api/admin/summary-settings", methods=["GET"])
def get_summary_settings():
    db = get_db()
    return jsonify({
        "enabled": tn_sync.get_setting(db, "summary_enabled") == "1",
        "recipients": tn_sync.get_setting(db, "summary_to"),
        "smtp_configured": jobs.smtp_configured(),
        "last_result": tn_sync.get_setting(db, "summary_last_result"),
    })


@bp.route("/api/admin/summary-settings", methods=["PUT"])
def update_summary_settings():
    data = request.get_json(force=True) or {}
    recipients = jobs.parse_recipients(data.get("recipients"))
    enabled = bool(data.get("enabled"))
    if enabled and not recipients:
        return jsonify({"error": "Carga al menos un mail para recibir el resumen"}), 400
    db = get_db()
    tn_sync.set_setting(db, "summary_enabled", "1" if enabled else "0")
    tn_sync.set_setting(db, "summary_to", ", ".join(recipients))
    db.commit()
    auth.audit("resumen_diario_config", "settings", "summary", f"{'activado' if enabled else 'desactivado'}: {', '.join(recipients)}")
    return get_summary_settings()


@bp.route("/api/admin/summary-send", methods=["POST"])
def send_summary_now():
    db = get_db()
    try:
        ok, message = jobs.send_summary(db)
    except Exception as exc:
        ok, message = False, f"No se pudo enviar: {exc}"
    return jsonify({"ok": ok, "message": message}), (200 if ok else 400)
