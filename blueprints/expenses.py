from flask import Blueprint, Response, jsonify, render_template, request

from db import get_db, now_iso
from helpers import build_csv

bp = Blueprint("expenses", __name__)


def row_to_dict(row):
    return {
        "id": row["id"],
        "category": row["category"],
        "amount": row["amount"],
        "expense_date": row["expense_date"],
        "vendor": row["vendor"],
        "note": row["note"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@bp.route("/gastos")
def gastos_page():
    return render_template("gastos.html", active="gastos")


def expenses_filters_from_request():
    where = []
    params = []

    category = request.args.get("category", "").strip()
    if category:
        where.append("category = ?")
        params.append(category)

    q = request.args.get("q", "").strip()
    if q:
        where.append("(vendor LIKE ? OR note LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]

    date_from = request.args.get("date_from")
    if date_from:
        where.append("expense_date >= ?")
        params.append(date_from)

    date_to = request.args.get("date_to")
    if date_to:
        where.append("expense_date <= ?")
        params.append(date_to)

    return where, params


@bp.route("/api/expenses", methods=["GET"])
def list_expenses():
    db = get_db()
    where, params = expenses_filters_from_request()

    query = "SELECT * FROM expenses"
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY expense_date DESC, id DESC"

    rows = db.execute(query, params).fetchall()
    return jsonify([row_to_dict(r) for r in rows])


@bp.route("/api/expenses/export.csv")
def export_expenses():
    db = get_db()
    where, params = expenses_filters_from_request()

    query = "SELECT * FROM expenses"
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY expense_date DESC, id DESC"

    rows = db.execute(query, params).fetchall()
    content = build_csv(
        ["categoria", "monto", "fecha", "proveedor", "nota"],
        [[r["category"], r["amount"], r["expense_date"], r["vendor"] or "", r["note"] or ""] for r in rows],
    )
    return Response(
        content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=gastos.csv"},
    )


@bp.route("/api/expenses", methods=["POST"])
def create_expense():
    data = request.get_json(force=True) or {}
    category = str(data.get("category", "")).strip()
    expense_date = str(data.get("expense_date", "")).strip()
    if not category or not expense_date:
        return jsonify({"error": "category y expense_date son obligatorios"}), 400

    try:
        amount = float(data.get("amount", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "amount debe ser numerico"}), 400

    now = now_iso()
    db = get_db()
    cur = db.execute(
        "INSERT INTO expenses (category, amount, expense_date, vendor, note, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            category,
            amount,
            expense_date,
            str(data.get("vendor", "")).strip(),
            str(data.get("note", "")).strip(),
            now,
            now,
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM expenses WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route("/api/expenses/<int:expense_id>", methods=["PUT"])
def update_expense(expense_id):
    db = get_db()
    row = db.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
    if not row:
        return jsonify({"error": "gasto no encontrado"}), 404

    data = request.get_json(force=True) or {}
    try:
        amount = float(data.get("amount", row["amount"]))
    except (TypeError, ValueError):
        return jsonify({"error": "amount debe ser numerico"}), 400

    db.execute(
        "UPDATE expenses SET category=?, amount=?, expense_date=?, vendor=?, note=?, updated_at=? WHERE id=?",
        (
            str(data.get("category", row["category"])).strip(),
            amount,
            str(data.get("expense_date", row["expense_date"])).strip(),
            str(data.get("vendor", row["vendor"])).strip(),
            str(data.get("note", row["note"])).strip(),
            now_iso(),
            expense_id,
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
    return jsonify(row_to_dict(row))


@bp.route("/api/expenses/<int:expense_id>", methods=["DELETE"])
def delete_expense(expense_id):
    db = get_db()
    db.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    db.commit()
    return jsonify({"ok": True})
