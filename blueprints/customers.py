import sqlite3

from flask import Blueprint, Response, jsonify, render_template, request

import auth
import stock as stk
from db import get_db, now_iso
from helpers import build_csv

bp = Blueprint("customers", __name__)


def row_to_dict(row):
    keys = row.keys()
    return {
        "id": row["id"],
        "name": row["name"],
        "phone": row["phone"],
        "email": row["email"],
        "doc_number": row["doc_number"],
        "address": row["address"] or "",
        "city": row["city"] or "",
        "province": row["province"] or "",
        "office_id": row["office_id"],
        "office_name": row["office_name"] if "office_name" in keys else "",
        "customer_type": row["customer_type"] or "minorista",
        "note": row["note"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "total_spent": row["total_spent"] if "total_spent" in keys else 0,
        "purchase_count": row["purchase_count"] if "purchase_count" in keys else 0,
    }


CUSTOMERS_WITH_STATS_QUERY = """
    SELECT customers.*, offices.name AS office_name,
           COALESCE(stats.total_spent, 0) AS total_spent,
           COALESCE(stats.purchase_count, 0) AS purchase_count
    FROM customers
    LEFT JOIN offices ON offices.id = customers.office_id
    LEFT JOIN (
        SELECT customer_id, SUM(total) AS total_spent, COUNT(*) AS purchase_count
        FROM sales
        WHERE customer_id IS NOT NULL
        GROUP BY customer_id
    ) stats ON stats.customer_id = customers.id
"""


def _filters():
    where, params = [], []
    q = request.args.get("q", "").strip()
    if q:
        where.append("(customers.name LIKE ? OR customers.phone LIKE ? OR customers.email LIKE ? OR customers.doc_number LIKE ?)")
        params += [f"%{q}%"] * 4
    office_id = request.args.get("office_id", "").strip()
    if office_id.isdigit():
        where.append("customers.office_id = ?")
        params.append(int(office_id))
    elif office_id == "none":
        where.append("customers.office_id IS NULL")
    ctype = request.args.get("customer_type", "").strip()
    if ctype in stk.SALE_TYPES:
        where.append("customers.customer_type = ?")
        params.append(ctype)
    product = request.args.get("product", "").strip()
    if product:
        where.append(
            "customers.id IN (SELECT s.customer_id FROM sales s JOIN sale_items si ON si.sale_id = s.id "
            "WHERE s.customer_id IS NOT NULL AND (si.sku LIKE ? OR si.product_name LIKE ?))"
        )
        params += [f"%{product}%", f"%{product}%"]
    return where, params


@bp.route("/clientes")
def clientes_page():
    return render_template("clientes.html", active="clientes")


@bp.route("/api/customers", methods=["GET"])
def list_customers():
    db = get_db()
    where, params = _filters()
    query = CUSTOMERS_WITH_STATS_QUERY
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY customers.name COLLATE NOCASE"
    rows = db.execute(query, params).fetchall()
    return jsonify([row_to_dict(r) for r in rows])


@bp.route("/api/customers/export.csv")
def export_customers():
    db = get_db()
    where, params = _filters()
    rows = db.execute(
        CUSTOMERS_WITH_STATS_QUERY + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY customers.name COLLATE NOCASE",
        params,
    ).fetchall()
    products = {}
    for r in db.execute(
        "SELECT s.customer_id, GROUP_CONCAT(DISTINCT si.product_name) AS names "
        "FROM sales s JOIN sale_items si ON si.sale_id = s.id WHERE s.customer_id IS NOT NULL GROUP BY s.customer_id"
    ).fetchall():
        products[r["customer_id"]] = r["names"]
    content = build_csv(
        ["nombre", "telefono", "email", "documento", "domicilio", "localidad", "provincia", "oficina", "tipo",
         "compras", "total_comprado", "productos_comprados", "nota"],
        [
            [
                r["name"], r["phone"], r["email"], r["doc_number"], r["address"] or "", r["city"] or "",
                r["province"] or "", r["office_name"] or "", r["customer_type"] or "minorista",
                r["purchase_count"], r["total_spent"], products.get(r["id"], ""), r["note"] or "",
            ]
            for r in rows
        ],
    )
    return Response(content, mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=clientes.csv"})


@bp.route("/api/customers/<int:customer_id>/purchases", methods=["GET"])
def customer_purchases(customer_id):
    db = get_db()
    if not db.execute("SELECT 1 FROM customers WHERE id = ?", (customer_id,)).fetchone():
        return jsonify({"error": "cliente no encontrado"}), 404
    rows = db.execute(
        """
        SELECT si.sku, si.product_name, s.currency,
               SUM(si.quantity - COALESCE((SELECT SUM(ri.quantity) FROM return_items ri WHERE ri.sale_item_id = si.id), 0)) AS net_qty,
               SUM(si.line_total) AS total,
               COUNT(DISTINCT s.id) AS purchases,
               MAX(s.created_at) AS last_date
        FROM sale_items si JOIN sales s ON s.id = si.sale_id
        WHERE s.customer_id = ?
        GROUP BY si.sku, s.currency
        ORDER BY last_date DESC
        """,
        (customer_id,),
    ).fetchall()
    return jsonify(
        [
            {
                "sku": r["sku"], "product_name": r["product_name"], "currency": r["currency"] or "ARS",
                "quantity": r["net_qty"], "total": r["total"], "purchases": r["purchases"], "last_date": r["last_date"],
            }
            for r in rows
        ]
    )


def _clean_office(db, value):
    if value in (None, "", "null"):
        return None, None
    try:
        office_id = int(value)
    except (TypeError, ValueError):
        return None, "oficina invalida"
    if not db.execute("SELECT 1 FROM offices WHERE id = ?", (office_id,)).fetchone():
        return None, "oficina inexistente"
    return office_id, None


def _clean_type(value):
    value = str(value or "minorista").strip().lower()
    return value if value in stk.SALE_TYPES else None


@bp.route("/api/customers", methods=["POST"])
def create_customer():
    data = request.get_json(force=True) or {}
    name = str(data.get("name", "")).strip()
    if not name:
        return jsonify({"error": "name es obligatorio"}), 400

    now = now_iso()
    db = get_db()
    office_id, err = _clean_office(db, data.get("office_id"))
    if err:
        return jsonify({"error": err}), 400
    ctype = _clean_type(data.get("customer_type"))
    if not ctype:
        return jsonify({"error": "tipo de cliente invalido (minorista o mayorista)"}), 400
    cur = db.execute(
        "INSERT INTO customers (name, phone, email, doc_number, address, city, province, office_id, customer_type, note, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            name,
            str(data.get("phone", "")).strip(),
            str(data.get("email", "")).strip(),
            str(data.get("doc_number", "")).strip(),
            str(data.get("address", "")).strip(),
            str(data.get("city", "")).strip(),
            str(data.get("province", "")).strip(),
            office_id,
            ctype,
            str(data.get("note", "")).strip(),
            now,
            now,
        ),
    )
    db.commit()
    auth.audit("cliente_creado", "customer", cur.lastrowid, name)
    row = db.execute(CUSTOMERS_WITH_STATS_QUERY + " WHERE customers.id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route("/api/customers/<int:customer_id>", methods=["PUT"])
def update_customer(customer_id):
    db = get_db()
    row = db.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    if not row:
        return jsonify({"error": "cliente no encontrado"}), 404

    data = request.get_json(force=True) or {}
    name = str(data.get("name", row["name"])).strip()
    if not name:
        return jsonify({"error": "name es obligatorio"}), 400
    office_id, err = _clean_office(db, data["office_id"]) if "office_id" in data else (row["office_id"], None)
    if err:
        return jsonify({"error": err}), 400
    ctype = _clean_type(data.get("customer_type", row["customer_type"]))
    if not ctype:
        return jsonify({"error": "tipo de cliente invalido (minorista o mayorista)"}), 400

    db.execute(
        "UPDATE customers SET name=?, phone=?, email=?, doc_number=?, address=?, city=?, province=?, office_id=?, "
        "customer_type=?, note=?, updated_at=? WHERE id=?",
        (
            name,
            str(data.get("phone", row["phone"])).strip(),
            str(data.get("email", row["email"])).strip(),
            str(data.get("doc_number", row["doc_number"])).strip(),
            str(data.get("address", row["address"] or "")).strip(),
            str(data.get("city", row["city"] or "")).strip(),
            str(data.get("province", row["province"] or "")).strip(),
            office_id,
            ctype,
            str(data.get("note", row["note"])).strip(),
            now_iso(),
            customer_id,
        ),
    )
    db.commit()
    auth.audit("cliente_editado", "customer", customer_id, name)
    row = db.execute(CUSTOMERS_WITH_STATS_QUERY + " WHERE customers.id = ?", (customer_id,)).fetchone()
    return jsonify(row_to_dict(row))


@bp.route("/api/customers/<int:customer_id>", methods=["DELETE"])
def delete_customer(customer_id):
    db = get_db()
    old = db.execute("SELECT name FROM customers WHERE id = ?", (customer_id,)).fetchone()
    try:
        db.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
        db.commit()
        if old:
            auth.audit("cliente_eliminado", "customer", customer_id, old["name"])
    except sqlite3.IntegrityError:
        db.rollback()
        return jsonify({"error": "no se puede eliminar, el cliente tiene ventas asociadas"}), 409
    return jsonify({"ok": True})
