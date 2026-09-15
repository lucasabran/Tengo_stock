from flask import Blueprint, Response, abort, jsonify, render_template, request

from db import get_db, now_iso
from helpers import ACCOUNT_PAYMENT_METHOD, build_csv

bp = Blueprint("sales", __name__)


def sale_summary_dict(row):
    return {
        "id": row["id"],
        "number": f"V-{row['id']:06d}",
        "channel_id": row["channel_id"],
        "channel_name": row["channel_name"],
        "customer_id": row["customer_id"],
        "customer_name": row["customer_name"],
        "status": row["status"],
        "subtotal": row["subtotal"],
        "discount": row["discount"],
        "total": row["total"],
        "payment_method": row["payment_method"],
        "currency": row["currency"] or "ARS",
        "note": row["note"],
        "created_at": row["created_at"],
    }


SUMMARY_QUERY = """
    SELECT sales.*, channels.name AS channel_name, customers.name AS customer_name
    FROM sales
    JOIN channels ON channels.id = sales.channel_id
    LEFT JOIN customers ON customers.id = sales.customer_id
"""


@bp.route("/ventas")
def ventas_page():
    return render_template("ventas.html", active="ventas")


@bp.route("/ventas/nueva")
def venta_nueva_page():
    return render_template("venta_nueva.html", active="ventas")


@bp.route("/ventas/<int:sale_id>")
def venta_detalle_page(sale_id):
    return render_template("venta_detalle.html", active="ventas", sale_id=sale_id)


def sales_filters_from_request():
    where = []
    params = []

    q = request.args.get("q", "").strip()
    if q:
        where.append("(customers.name LIKE ? OR channels.name LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]

    channel_id = request.args.get("channel_id")
    if channel_id:
        where.append("sales.channel_id = ?")
        params.append(channel_id)

    customer_id = request.args.get("customer_id")
    if customer_id:
        where.append("sales.customer_id = ?")
        params.append(customer_id)

    date_from = request.args.get("date_from")
    if date_from:
        where.append("sales.created_at >= ?")
        params.append(date_from)

    date_to = request.args.get("date_to")
    if date_to:
        where.append("sales.created_at <= ?")
        params.append(date_to + "T23:59:59")

    return where, params


@bp.route("/api/sales", methods=["GET"])
def list_sales():
    db = get_db()
    where, params = sales_filters_from_request()

    query = SUMMARY_QUERY
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY sales.id DESC"

    rows = db.execute(query, params).fetchall()
    return jsonify([sale_summary_dict(r) for r in rows])


@bp.route("/api/sales/export.csv")
def export_sales():
    db = get_db()
    where, params = sales_filters_from_request()

    query = SUMMARY_QUERY
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY sales.id DESC"

    rows = db.execute(query, params).fetchall()
    content = build_csv(
        ["numero", "fecha", "canal", "cliente", "forma_pago", "moneda", "subtotal", "descuento", "total", "nota"],
        [
            [
                f"V-{r['id']:06d}",
                r["created_at"],
                r["channel_name"],
                r["customer_name"] or "",
                r["payment_method"] or "",
                r["currency"] or "ARS",
                r["subtotal"],
                r["discount"],
                r["total"],
                r["note"] or "",
            ]
            for r in rows
        ],
    )
    return Response(
        content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=ventas.csv"},
    )


@bp.route("/api/sales/<int:sale_id>", methods=["GET"])
def get_sale(sale_id):
    db = get_db()
    row = db.execute(SUMMARY_QUERY + " WHERE sales.id = ?", (sale_id,)).fetchone()
    if not row:
        return jsonify({"error": "venta no encontrada"}), 404

    items = db.execute(
        """
        SELECT sale_items.*,
               COALESCE((SELECT SUM(return_items.quantity) FROM return_items
                         WHERE return_items.sale_item_id = sale_items.id), 0) AS already_returned
        FROM sale_items WHERE sale_items.sale_id = ?
        ORDER BY sale_items.id
        """,
        (sale_id,),
    ).fetchall()

    result = sale_summary_dict(row)
    result["items"] = [
        {
            "id": i["id"],
            "sku": i["sku"],
            "product_name": i["product_name"],
            "unit_price": i["unit_price"],
            "quantity": i["quantity"],
            "line_total": i["line_total"],
            "already_returned": i["already_returned"],
        }
        for i in items
    ]
    return jsonify(result)


@bp.route("/api/sales", methods=["POST"])
def create_sale():
    data = request.get_json(force=True) or {}
    items_in = data.get("items") or []
    if not items_in:
        return jsonify({"error": "la venta necesita al menos un producto"}), 400

    try:
        channel_id = int(data.get("channel_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "channel_id es obligatorio"}), 400

    customer_id = data.get("customer_id")
    customer_id = int(customer_id) if customer_id not in (None, "", "null") else None

    try:
        discount = float(data.get("discount", 0) or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "discount invalido"}), 400

    payment_method = str(data.get("payment_method", "")).strip()
    note = str(data.get("note", "")).strip()
    currency = str(data.get("currency", "ARS")).strip().upper()
    if currency not in ("ARS", "USD"):
        currency = "ARS"

    db = get_db()

    channel = db.execute("SELECT 1 FROM channels WHERE id = ?", (channel_id,)).fetchone()
    if not channel:
        return jsonify({"error": "canal invalido"}), 400
    if customer_id is not None:
        customer = db.execute("SELECT 1 FROM customers WHERE id = ?", (customer_id,)).fetchone()
        if not customer:
            return jsonify({"error": "cliente invalido"}), 400

    if payment_method == ACCOUNT_PAYMENT_METHOD and customer_id is None:
        return jsonify({"error": "para vender a cuenta corriente hay que elegir un cliente"}), 400

    # Pre-check: read-only pass, collect every problem before writing anything
    lines = []
    errors = []
    for idx, item in enumerate(items_in):
        sku = str(item.get("sku", "")).strip()
        try:
            quantity = int(item.get("quantity", 0))
        except (TypeError, ValueError):
            errors.append(f"item {idx + 1}: cantidad invalida")
            continue
        if quantity <= 0:
            errors.append(f"item {idx + 1}: cantidad debe ser mayor a 0")
            continue

        product = db.execute("SELECT * FROM products WHERE sku = ?", (sku,)).fetchone()
        if not product:
            errors.append(f"{sku}: producto no encontrado")
            continue
        if product["quantity"] < quantity:
            errors.append(f"{sku}: disponible {product['quantity']}, pedido {quantity}")
            continue

        unit_price = item.get("unit_price")
        unit_price = float(unit_price) if unit_price not in (None, "") else product["price"]
        lines.append(
            {
                "sku": sku,
                "product_name": product["name"],
                "unit_price": unit_price,
                "quantity": quantity,
                "line_total": round(unit_price * quantity, 2),
            }
        )

    if errors:
        return jsonify({"error": "Stock insuficiente o datos invalidos", "details": errors}), 409

    subtotal = round(sum(l["line_total"] for l in lines), 2)
    total = round(subtotal - discount, 2)
    now = now_iso()

    try:
        for line in lines:
            cur = db.execute(
                "UPDATE products SET quantity = quantity - ?, updated_at = ? WHERE sku = ? AND quantity >= ?",
                (line["quantity"], now, line["sku"], line["quantity"]),
            )
            if cur.rowcount == 0:
                raise ValueError(f"{line['sku']}: sin stock suficiente (venta concurrente)")

        cur = db.execute(
            "INSERT INTO sales (channel_id, customer_id, status, subtotal, discount, total, "
            "payment_method, currency, note, created_at) VALUES (?, ?, 'completed', ?, ?, ?, ?, ?, ?, ?)",
            (channel_id, customer_id, subtotal, discount, total, payment_method, currency, note, now),
        )
        sale_id = cur.lastrowid

        for line in lines:
            db.execute(
                "INSERT INTO sale_items (sale_id, sku, product_name, unit_price, quantity, line_total) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (sale_id, line["sku"], line["product_name"], line["unit_price"], line["quantity"], line["line_total"]),
            )
            db.execute(
                "INSERT INTO stock_movements (sku, change_qty, reason, reference_type, reference_id, created_at) "
                "VALUES (?, ?, 'venta', 'sale', ?, ?)",
                (line["sku"], -line["quantity"], sale_id, now),
            )

        db.commit()
    except Exception as exc:
        db.rollback()
        return jsonify({"error": "No se pudo registrar la venta", "details": [str(exc)]}), 409

    row = db.execute(SUMMARY_QUERY + " WHERE sales.id = ?", (sale_id,)).fetchone()
    return jsonify(sale_summary_dict(row)), 201


@bp.route("/ventas/<int:sale_id>/comprobante")
def comprobante(sale_id):
    db = get_db()
    row = db.execute(SUMMARY_QUERY + " WHERE sales.id = ?", (sale_id,)).fetchone()
    if not row:
        abort(404)
    items = db.execute(
        "SELECT * FROM sale_items WHERE sale_id = ? ORDER BY id", (sale_id,)
    ).fetchall()
    return render_template("venta_comprobante.html", sale=sale_summary_dict(row), items=items)
