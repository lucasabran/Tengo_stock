from flask import Blueprint, jsonify, render_template, request

from db import get_db, now_iso

bp = Blueprint("returns", __name__)


def return_dict(row):
    return {
        "id": row["id"],
        "sale_id": row["sale_id"],
        "sale_number": f"V-{row['sale_id']:06d}",
        "reason": row["reason"],
        "note": row["note"],
        "created_at": row["created_at"],
    }


@bp.route("/devoluciones")
def devoluciones_page():
    return render_template("devoluciones.html", active="devoluciones")


@bp.route("/devoluciones/nueva")
def devolucion_nueva_page():
    return render_template("devolucion_nueva.html", active="devoluciones")


@bp.route("/api/returns", methods=["GET"])
def list_returns():
    db = get_db()
    where = []
    params = []
    sale_id = request.args.get("sale_id")
    if sale_id:
        where.append("sale_id = ?")
        params.append(sale_id)

    query = "SELECT * FROM returns"
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY id DESC"

    rows = db.execute(query, params).fetchall()
    return jsonify([return_dict(r) for r in rows])


@bp.route("/api/returns/<int:return_id>", methods=["GET"])
def get_return(return_id):
    db = get_db()
    row = db.execute("SELECT * FROM returns WHERE id = ?", (return_id,)).fetchone()
    if not row:
        return jsonify({"error": "devolucion no encontrada"}), 404
    items = db.execute(
        """
        SELECT return_items.*, sale_items.sku, sale_items.product_name, sale_items.unit_price
        FROM return_items JOIN sale_items ON sale_items.id = return_items.sale_item_id
        WHERE return_items.return_id = ?
        """,
        (return_id,),
    ).fetchall()
    result = return_dict(row)
    result["items"] = [
        {
            "sale_item_id": i["sale_item_id"],
            "sku": i["sku"],
            "product_name": i["product_name"],
            "unit_price": i["unit_price"],
            "quantity": i["quantity"],
        }
        for i in items
    ]
    return jsonify(result)


@bp.route("/api/returns", methods=["POST"])
def create_return():
    data = request.get_json(force=True) or {}
    items_in = data.get("items") or []
    if not items_in:
        return jsonify({"error": "la devolucion necesita al menos un producto"}), 400

    try:
        sale_id = int(data.get("sale_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "sale_id es obligatorio"}), 400

    reason = str(data.get("reason", "")).strip()
    note = str(data.get("note", "")).strip()

    db = get_db()
    sale = db.execute("SELECT id FROM sales WHERE id = ?", (sale_id,)).fetchone()
    if not sale:
        return jsonify({"error": "venta no encontrada"}), 404

    lines = []
    errors = []
    for idx, item in enumerate(items_in):
        try:
            sale_item_id = int(item.get("sale_item_id"))
            quantity = int(item.get("quantity", 0))
        except (TypeError, ValueError):
            errors.append(f"item {idx + 1}: datos invalidos")
            continue
        if quantity <= 0:
            errors.append(f"item {idx + 1}: cantidad debe ser mayor a 0")
            continue

        sale_item = db.execute(
            "SELECT * FROM sale_items WHERE id = ? AND sale_id = ?", (sale_item_id, sale_id)
        ).fetchone()
        if not sale_item:
            errors.append(f"item {idx + 1}: no pertenece a esta venta")
            continue

        already_returned = db.execute(
            "SELECT COALESCE(SUM(quantity), 0) AS qty FROM return_items WHERE sale_item_id = ?",
            (sale_item_id,),
        ).fetchone()["qty"]

        available = sale_item["quantity"] - already_returned
        if quantity > available:
            errors.append(
                f"{sale_item['sku']}: vendido {sale_item['quantity']}, ya devuelto {already_returned}, "
                f"pedido devolver {quantity}"
            )
            continue

        lines.append({"sale_item_id": sale_item_id, "sku": sale_item["sku"], "quantity": quantity})

    if errors:
        return jsonify({"error": "No se puede registrar la devolucion", "details": errors}), 409

    now = now_iso()
    try:
        cur = db.execute(
            "INSERT INTO returns (sale_id, reason, note, created_at) VALUES (?, ?, ?, ?)",
            (sale_id, reason, note, now),
        )
        return_id = cur.lastrowid

        for line in lines:
            db.execute(
                "INSERT INTO return_items (return_id, sale_item_id, quantity) VALUES (?, ?, ?)",
                (return_id, line["sale_item_id"], line["quantity"]),
            )
            db.execute(
                "UPDATE products SET quantity = quantity + ?, updated_at = ? WHERE sku = ?",
                (line["quantity"], now, line["sku"]),
            )
            db.execute(
                "INSERT INTO stock_movements (sku, change_qty, reason, reference_type, reference_id, created_at) "
                "VALUES (?, ?, 'devolucion', 'return', ?, ?)",
                (line["sku"], line["quantity"], return_id, now),
            )

        db.commit()
    except Exception as exc:
        db.rollback()
        return jsonify({"error": "No se pudo registrar la devolucion", "details": [str(exc)]}), 409

    row = db.execute("SELECT * FROM returns WHERE id = ?", (return_id,)).fetchone()
    return jsonify(return_dict(row)), 201
