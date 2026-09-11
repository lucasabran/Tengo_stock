import sqlite3

from flask import Blueprint, jsonify, render_template, request

from db import get_db, now_iso

bp = Blueprint("customers", __name__)


def row_to_dict(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "phone": row["phone"],
        "email": row["email"],
        "doc_number": row["doc_number"],
        "note": row["note"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "total_spent": row["total_spent"] if "total_spent" in row.keys() else 0,
        "purchase_count": row["purchase_count"] if "purchase_count" in row.keys() else 0,
    }


CUSTOMERS_WITH_STATS_QUERY = """
    SELECT customers.*,
           COALESCE(stats.total_spent, 0) AS total_spent,
           COALESCE(stats.purchase_count, 0) AS purchase_count
    FROM customers
    LEFT JOIN (
        SELECT customer_id, SUM(total) AS total_spent, COUNT(*) AS purchase_count
        FROM sales
        WHERE customer_id IS NOT NULL
        GROUP BY customer_id
    ) stats ON stats.customer_id = customers.id
"""


@bp.route("/clientes")
def clientes_page():
    return render_template("clientes.html", active="clientes")


@bp.route("/api/customers", methods=["GET"])
def list_customers():
    q = request.args.get("q", "").strip()
    db = get_db()
    query = CUSTOMERS_WITH_STATS_QUERY
    params = []
    if q:
        query += " WHERE customers.name LIKE ? OR customers.phone LIKE ?"
        params = [f"%{q}%", f"%{q}%"]
    query += " ORDER BY customers.name"
    rows = db.execute(query, params).fetchall()
    return jsonify([row_to_dict(r) for r in rows])


@bp.route("/api/customers", methods=["POST"])
def create_customer():
    data = request.get_json(force=True) or {}
    name = str(data.get("name", "")).strip()
    if not name:
        return jsonify({"error": "name es obligatorio"}), 400

    now = now_iso()
    db = get_db()
    cur = db.execute(
        "INSERT INTO customers (name, phone, email, doc_number, note, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            name,
            str(data.get("phone", "")).strip(),
            str(data.get("email", "")).strip(),
            str(data.get("doc_number", "")).strip(),
            str(data.get("note", "")).strip(),
            now,
            now,
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM customers WHERE id = ?", (cur.lastrowid,)).fetchone()
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

    db.execute(
        "UPDATE customers SET name=?, phone=?, email=?, doc_number=?, note=?, updated_at=? WHERE id=?",
        (
            name,
            str(data.get("phone", row["phone"])).strip(),
            str(data.get("email", row["email"])).strip(),
            str(data.get("doc_number", row["doc_number"])).strip(),
            str(data.get("note", row["note"])).strip(),
            now_iso(),
            customer_id,
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    return jsonify(row_to_dict(row))


@bp.route("/api/customers/<int:customer_id>", methods=["DELETE"])
def delete_customer(customer_id):
    db = get_db()
    try:
        db.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        return jsonify({"error": "no se puede eliminar, el cliente tiene ventas asociadas"}), 409
    return jsonify({"ok": True})
