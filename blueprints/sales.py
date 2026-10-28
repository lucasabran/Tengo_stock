from flask import Blueprint, Response, abort, jsonify, render_template, request

from db import get_db, now_iso
import auth
import stock as stk
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
        "office_id": row["office_id"],
        "office_name": row["office_name"] or "",
        "sale_type": row["sale_type"] or "minorista",
        "created_by": row["created_by"] or "",
    }


SUMMARY_QUERY = """
    SELECT sales.*, channels.name AS channel_name, customers.name AS customer_name, offices.name AS office_name
    FROM sales
    JOIN channels ON channels.id = sales.channel_id
    LEFT JOIN customers ON customers.id = sales.customer_id
    LEFT JOIN offices ON offices.id = sales.office_id
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

    fixed_office = stk.user_office_id()
    office_id = fixed_office or request.args.get("office_id")
    if office_id:
        where.append("sales.office_id = ?")
        params.append(office_id)

    sale_type = request.args.get("sale_type")
    if sale_type in stk.SALE_TYPES:
        where.append("sales.sale_type = ?")
        params.append(sale_type)

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
        ["numero", "fecha", "oficina", "tipo", "canal", "cliente", "forma_pago", "moneda", "subtotal", "descuento", "total", "nota"],
        [
            [
                f"V-{r['id']:06d}",
                r["created_at"],
                r["office_name"] or "",
                r["sale_type"] or "minorista",
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
    if not row or (stk.user_office_id() and row["office_id"] != stk.user_office_id()):
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
    sale_type = str(data.get("sale_type", "minorista")).strip().lower()
    if sale_type not in stk.SALE_TYPES:
        return jsonify({"error": "tipo de venta invalido (minorista o mayorista)"}), 400
    note = str(data.get("note", "")).strip()
    currency = str(data.get("currency", "ARS")).strip().upper()
    if currency not in ("ARS", "USD"):
        currency = "ARS"

    db = get_db()

    channel = db.execute("SELECT 1 FROM channels WHERE id = ?", (channel_id,)).fetchone()
    if not channel:
        return jsonify({"error": "canal invalido"}), 400
    office_id, office_err = stk.resolve_office(db, data.get("office_id"))
    if office_err:
        return jsonify({"error": office_err}), 400
    office_name = db.execute("SELECT name FROM offices WHERE id = ?", (office_id,)).fetchone()["name"]
    if customer_id is not None:
        customer = db.execute("SELECT 1 FROM customers WHERE id = ?", (customer_id,)).fetchone()
        if not customer:
            return jsonify({"error": "cliente invalido"}), 400

    if payment_method == ACCOUNT_PAYMENT_METHOD and customer_id is None:
        return jsonify({"error": "para vender a cuenta corriente hay que elegir un cliente"}), 400

    # Pre-check: read-only pass, collect every problem before writing anything
    lines = []
    errors = []
    needed = {}
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
        needed[sku] = needed.get(sku, 0) + quantity
        available = stk.level(db, sku, office_id)
        if available < needed[sku]:
            errors.append(f"{sku}: disponible en {office_name} {available}, pedido {needed[sku]}")
            continue

        unit_price = item.get("unit_price")
        if unit_price in (None, ""):
            unit_price = product["price_wholesale"] if sale_type == "mayorista" and (product["price_wholesale"] or 0) > 0 else product["price"]
        unit_price = float(unit_price)
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
            if not stk.adjust(db, line["sku"], office_id, -line["quantity"], now):
                raise ValueError(f"{line['sku']}: sin stock suficiente en {office_name} (venta concurrente)")

        cur = db.execute(
            "INSERT INTO sales (channel_id, customer_id, status, subtotal, discount, total, "
            "payment_method, currency, note, created_at, created_by, office_id, sale_type) VALUES (?, ?, 'completed', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (channel_id, customer_id, subtotal, discount, total, payment_method, currency, note, now, auth.actor(), office_id, sale_type),
        )
        sale_id = cur.lastrowid

        for line in lines:
            db.execute(
                "INSERT INTO sale_items (sale_id, sku, product_name, unit_price, quantity, line_total) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (sale_id, line["sku"], line["product_name"], line["unit_price"], line["quantity"], line["line_total"]),
            )
            stk.record_movement(db, line["sku"], office_id, -line["quantity"], "venta", "", "sale", sale_id, now, auth.actor())

        db.commit()
    except Exception as exc:
        db.rollback()
        return jsonify({"error": "No se pudo registrar la venta", "details": [str(exc)]}), 409

    auth.audit("venta_creada", "sale", sale_id, f"{currency} {total:,.2f} - {len(lines)} item(s) - {office_name} ({sale_type})")

    row = db.execute(SUMMARY_QUERY + " WHERE sales.id = ?", (sale_id,)).fetchone()
    return jsonify(sale_summary_dict(row)), 201


@bp.route("/ventas/<int:sale_id>/comprobante")
def comprobante(sale_id):
    db = get_db()
    row = db.execute(SUMMARY_QUERY + " WHERE sales.id = ?", (sale_id,)).fetchone()
    if not row or (stk.user_office_id() and row["office_id"] != stk.user_office_id()):
        abort(404)
    items = db.execute(
        "SELECT * FROM sale_items WHERE sale_id = ? ORDER BY id", (sale_id,)
    ).fetchall()
    return render_template("venta_comprobante.html", sale=sale_summary_dict(row), items=items)


def _revert_return_stock(db, return_id, now):
    """Deshace el efecto en stock de una devolucion. Devuelve un mensaje de error o None."""
    items = db.execute(
        "SELECT ri.quantity, si.sku FROM return_items ri JOIN sale_items si ON si.id = ri.sale_item_id WHERE ri.return_id = ?",
        (return_id,),
    ).fetchall()
    office_row = db.execute(
        "SELECT sales.office_id FROM returns JOIN sales ON sales.id = returns.sale_id WHERE returns.id = ?", (return_id,)
    ).fetchone()
    office_id = (office_row["office_id"] if office_row else None) or stk.default_office_id(db)
    for it in items:
        if not stk.adjust(db, it["sku"], office_id, -it["quantity"], now):
            return f"{it['sku']}: no hay stock suficiente para deshacer la devolucion (ya se vendio)"
    db.execute("DELETE FROM stock_movements WHERE reference_type = 'return' AND reference_id = ?", (return_id,))
    db.execute("DELETE FROM return_items WHERE return_id = ?", (return_id,))
    db.execute("DELETE FROM returns WHERE id = ?", (return_id,))
    return None


@bp.route("/api/sales/<int:sale_id>", methods=["DELETE"])
def delete_sale(sale_id):
    db = get_db()
    sale = db.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone()
    if not sale:
        return jsonify({"error": "venta no encontrada"}), 404

    now = now_iso()
    try:
        # primero se deshacen las devoluciones de esta venta (devuelven stock al deposito)
        for r in db.execute("SELECT id FROM returns WHERE sale_id = ?", (sale_id,)).fetchall():
            problem = _revert_return_stock(db, r["id"], now)
            if problem:
                raise ValueError(problem)
        # despues se repone el stock que desconto la venta
        if sale["stock_deducted"]:
            office_id = sale["office_id"] or stk.default_office_id(db)
            for it in db.execute("SELECT sku, quantity FROM sale_items WHERE sale_id = ?", (sale_id,)).fetchall():
                stk.adjust(db, it["sku"], office_id, it["quantity"], now)
        db.execute("DELETE FROM stock_movements WHERE reference_type = 'sale' AND reference_id = ?", (sale_id,))
        db.execute("DELETE FROM sale_items WHERE sale_id = ?", (sale_id,))
        db.execute("DELETE FROM sales WHERE id = ?", (sale_id,))
        db.commit()
    except ValueError as exc:
        db.rollback()
        return jsonify({"error": "No se pudo eliminar la venta", "details": [str(exc)]}), 409

    auth.audit(
        "venta_eliminada", "sale", sale_id,
        f"V-{sale_id:06d} {sale['currency']} {sale['total']:,.2f} ({sale['created_at'][:10]})"
        + (" - stock repuesto" if sale["stock_deducted"] else ""),
    )
    return jsonify({"ok": True})
