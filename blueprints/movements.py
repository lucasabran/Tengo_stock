from flask import Blueprint, jsonify, render_template, request

from db import get_db

bp = Blueprint("movements", __name__)

MOVEMENTS_QUERY = """
    SELECT stock_movements.*, products.name AS product_name
    FROM stock_movements
    JOIN products ON products.sku = stock_movements.sku
"""
DEFAULT_LIMIT = 200
MAX_LIMIT = 500


def movement_dict(row):
    return {
        "id": row["id"],
        "sku": row["sku"],
        "product_name": row["product_name"],
        "change_qty": row["change_qty"],
        "reason": row["reason"],
        "note": row["note"],
        "reference_type": row["reference_type"],
        "reference_id": row["reference_id"],
        "created_at": row["created_at"],
    }


@bp.route("/movimientos")
def movimientos_page():
    return render_template("movimientos.html", active="movimientos")


@bp.route("/api/stock-movements", methods=["GET"])
def list_movements():
    db = get_db()
    where = []
    params = []

    sku = request.args.get("sku", "").strip()
    if sku:
        where.append("stock_movements.sku = ?")
        params.append(sku)

    date_from = request.args.get("date_from")
    if date_from:
        where.append("stock_movements.created_at >= ?")
        params.append(date_from)

    date_to = request.args.get("date_to")
    if date_to:
        where.append("stock_movements.created_at <= ?")
        params.append(date_to + "T23:59:59")

    try:
        limit = min(int(request.args.get("limit", DEFAULT_LIMIT)), MAX_LIMIT)
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT

    query = MOVEMENTS_QUERY
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY stock_movements.id DESC LIMIT ?"
    params.append(limit)

    rows = db.execute(query, params).fetchall()
    return jsonify([movement_dict(r) for r in rows])
