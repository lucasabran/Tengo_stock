import sqlite3

from flask import Blueprint, jsonify, render_template, request

import auth
from db import get_db, now_iso

bp = Blueprint("offices", __name__)


def office_dict(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "active": bool(row["active"]),
        "products": row["products"],
        "units": row["units"],
    }


OFFICES_QUERY = """
    SELECT o.*,
           (SELECT COUNT(*) FROM stock_levels sl WHERE sl.office_id = o.id AND sl.quantity != 0) AS products,
           (SELECT COALESCE(SUM(sl.quantity), 0) FROM stock_levels sl WHERE sl.office_id = o.id) AS units
    FROM offices o
"""


@bp.route("/oficinas")
def offices_page():
    return render_template("oficinas.html", active="oficinas")


@bp.route("/api/offices", methods=["GET"])
def list_offices():
    db = get_db()
    rows = db.execute(OFFICES_QUERY + " ORDER BY o.id").fetchall()
    return jsonify([office_dict(r) for r in rows])


@bp.route("/api/offices", methods=["POST"])
def create_office():
    data = request.get_json(force=True) or {}
    name = str(data.get("name", "")).strip()
    if not name:
        return jsonify({"error": "El nombre de la oficina es obligatorio"}), 400
    db = get_db()
    try:
        cur = db.execute("INSERT INTO offices (name, active, created_at) VALUES (?, 1, ?)", (name, now_iso()))
    except sqlite3.IntegrityError:
        return jsonify({"error": f"Ya existe una oficina llamada {name}"}), 409
    db.commit()
    auth.audit("oficina_creada", "office", cur.lastrowid, name)
    return jsonify(office_dict(db.execute(OFFICES_QUERY + " WHERE o.id = ?", (cur.lastrowid,)).fetchone())), 201


@bp.route("/api/offices/<int:office_id>", methods=["PUT"])
def update_office(office_id):
    db = get_db()
    row = db.execute("SELECT * FROM offices WHERE id = ?", (office_id,)).fetchone()
    if not row:
        return jsonify({"error": "oficina no encontrada"}), 404
    data = request.get_json(force=True) or {}
    name = str(data.get("name", row["name"])).strip() or row["name"]
    active = 1 if data.get("active", bool(row["active"])) else 0
    if not active:
        # No se desactiva la ultima oficina activa ni una que todavia tiene stock
        others = db.execute("SELECT COUNT(*) FROM offices WHERE active = 1 AND id != ?", (office_id,)).fetchone()[0]
        if others == 0:
            return jsonify({"error": "Tiene que quedar al menos una oficina activa"}), 409
        units = db.execute("SELECT COALESCE(SUM(ABS(quantity)), 0) FROM stock_levels WHERE office_id = ?", (office_id,)).fetchone()[0]
        if units:
            return jsonify({"error": "Esta oficina todavia tiene stock. Transferilo a otra oficina antes de desactivarla."}), 409
    try:
        db.execute("UPDATE offices SET name = ?, active = ? WHERE id = ?", (name, active, office_id))
    except sqlite3.IntegrityError:
        return jsonify({"error": f"Ya existe una oficina llamada {name}"}), 409
    db.commit()
    auth.audit("oficina_editada", "office", office_id, f"{row['name']} -> {name}, activa={active}")
    return jsonify(office_dict(db.execute(OFFICES_QUERY + " WHERE o.id = ?", (office_id,)).fetchone()))
