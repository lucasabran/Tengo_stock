from flask import Blueprint, jsonify, request

from db import get_db, now_iso

bp = Blueprint("channels", __name__)


def row_to_dict(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "type": row["type"],
        "external_account_id": row["external_account_id"],
        "active": bool(row["active"]),
        "created_at": row["created_at"],
    }


@bp.route("/api/channels", methods=["GET"])
def list_channels():
    db = get_db()
    if request.args.get("active") == "1":
        rows = db.execute("SELECT * FROM channels WHERE active = 1 ORDER BY name").fetchall()
    else:
        rows = db.execute("SELECT * FROM channels ORDER BY name").fetchall()
    return jsonify([row_to_dict(r) for r in rows])


@bp.route("/api/channels", methods=["POST"])
def create_channel():
    data = request.get_json(force=True) or {}
    name = str(data.get("name", "")).strip()
    type_ = str(data.get("type", "other")).strip() or "other"
    if not name:
        return jsonify({"error": "name es obligatorio"}), 400

    db = get_db()
    exists = db.execute("SELECT 1 FROM channels WHERE name = ?", (name,)).fetchone()
    if exists:
        return jsonify({"error": f"ya existe un canal llamado {name}"}), 409

    cur = db.execute(
        "INSERT INTO channels (name, type, external_account_id, active, created_at) VALUES (?, ?, '', 1, ?)",
        (name, type_, now_iso()),
    )
    db.commit()
    row = db.execute("SELECT * FROM channels WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route("/api/channels/<int:channel_id>", methods=["PUT"])
def update_channel(channel_id):
    db = get_db()
    row = db.execute("SELECT * FROM channels WHERE id = ?", (channel_id,)).fetchone()
    if not row:
        return jsonify({"error": "canal no encontrado"}), 404

    data = request.get_json(force=True) or {}
    name = str(data.get("name", row["name"])).strip()
    type_ = str(data.get("type", row["type"])).strip() or "other"
    active = 1 if data.get("active", bool(row["active"])) else 0

    db.execute(
        "UPDATE channels SET name=?, type=?, active=? WHERE id=?",
        (name, type_, active, channel_id),
    )
    db.commit()
    row = db.execute("SELECT * FROM channels WHERE id = ?", (channel_id,)).fetchone()
    return jsonify(row_to_dict(row))
