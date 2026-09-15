from flask import Blueprint, abort, jsonify, render_template, request

from db import get_db, now_iso
from helpers import ACCOUNT_PAYMENT_METHOD

bp = Blueprint("accounts", __name__)

ACCOUNTS_QUERY = """
    SELECT customers.id, customers.name,
           COALESCE(charges_ars.total, 0) AS charged_ars,
           COALESCE(payments_ars.total, 0) AS paid_ars,
           COALESCE(charges_usd.total, 0) AS charged_usd,
           COALESCE(payments_usd.total, 0) AS paid_usd
    FROM customers
    LEFT JOIN (
        SELECT customer_id, SUM(total) AS total FROM sales
        WHERE payment_method = ? AND (currency IS NULL OR currency = 'ARS') AND customer_id IS NOT NULL
        GROUP BY customer_id
    ) charges_ars ON charges_ars.customer_id = customers.id
    LEFT JOIN (
        SELECT customer_id, SUM(amount) AS total FROM account_payments
        WHERE currency IS NULL OR currency = 'ARS'
        GROUP BY customer_id
    ) payments_ars ON payments_ars.customer_id = customers.id
    LEFT JOIN (
        SELECT customer_id, SUM(total) AS total FROM sales
        WHERE payment_method = ? AND currency = 'USD' AND customer_id IS NOT NULL
        GROUP BY customer_id
    ) charges_usd ON charges_usd.customer_id = customers.id
    LEFT JOIN (
        SELECT customer_id, SUM(amount) AS total FROM account_payments
        WHERE currency = 'USD'
        GROUP BY customer_id
    ) payments_usd ON payments_usd.customer_id = customers.id
"""


def account_row_to_dict(row):
    return {
        "customer_id": row["id"],
        "customer_name": row["name"],
        "ars": {
            "charged": row["charged_ars"],
            "paid": row["paid_ars"],
            "balance": round(row["charged_ars"] - row["paid_ars"], 2),
        },
        "usd": {
            "charged": row["charged_usd"],
            "paid": row["paid_usd"],
            "balance": round(row["charged_usd"] - row["paid_usd"], 2),
        },
    }


@bp.route("/cuentas")
def accounts_page():
    return render_template("cuentas.html", active="cuentas")


@bp.route("/cuentas/<int:customer_id>")
def account_detail_page(customer_id):
    return render_template("cuenta_detalle.html", active="cuentas", customer_id=customer_id)


@bp.route("/api/accounts", methods=["GET"])
def list_accounts():
    db = get_db()
    rows = db.execute(
        ACCOUNTS_QUERY + " WHERE COALESCE(charges_ars.total, 0) > 0 OR COALESCE(charges_usd.total, 0) > 0 "
        "ORDER BY customers.name",
        (ACCOUNT_PAYMENT_METHOD, ACCOUNT_PAYMENT_METHOD),
    ).fetchall()
    return jsonify([account_row_to_dict(r) for r in rows])


@bp.route("/api/accounts/<int:customer_id>", methods=["GET"])
def get_account(customer_id):
    db = get_db()
    customer = db.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    if not customer:
        abort(404)

    row = db.execute(
        ACCOUNTS_QUERY + " WHERE customers.id = ?",
        (ACCOUNT_PAYMENT_METHOD, ACCOUNT_PAYMENT_METHOD, customer_id),
    ).fetchone()

    charges = db.execute(
        "SELECT id, total, currency, created_at, note FROM sales WHERE customer_id = ? AND payment_method = ? ORDER BY id",
        (customer_id, ACCOUNT_PAYMENT_METHOD),
    ).fetchall()
    payments = db.execute(
        "SELECT id, amount, currency, payment_method, note, created_at FROM account_payments "
        "WHERE customer_id = ? ORDER BY id",
        (customer_id,),
    ).fetchall()

    ledger = [
        {
            "type": "charge",
            "date": c["created_at"],
            "amount": c["total"],
            "currency": c["currency"] or "ARS",
            "label": f"Venta V-{c['id']:06d}",
            "note": c["note"] or "",
            "sale_id": c["id"],
        }
        for c in charges
    ] + [
        {
            "type": "payment",
            "date": p["created_at"],
            "amount": p["amount"],
            "currency": p["currency"] or "ARS",
            "label": f"Pago ({p['payment_method']})" if p["payment_method"] else "Pago",
            "note": p["note"] or "",
            "sale_id": None,
        }
        for p in payments
    ]
    ledger.sort(key=lambda x: x["date"])

    result = account_row_to_dict(row) if row else account_row_to_dict(
        {"id": customer_id, "name": customer["name"], "charged_ars": 0, "paid_ars": 0, "charged_usd": 0, "paid_usd": 0}
    )
    result["ledger"] = ledger
    return jsonify(result)


@bp.route("/api/accounts/<int:customer_id>/payments", methods=["POST"])
def create_payment(customer_id):
    db = get_db()
    customer = db.execute("SELECT 1 FROM customers WHERE id = ?", (customer_id,)).fetchone()
    if not customer:
        return jsonify({"error": "cliente no encontrado"}), 404

    data = request.get_json(force=True) or {}
    try:
        amount = float(data.get("amount", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "amount debe ser numerico"}), 400
    if amount <= 0:
        return jsonify({"error": "el monto debe ser mayor a 0"}), 400

    currency = str(data.get("currency", "ARS")).strip().upper()
    if currency not in ("ARS", "USD"):
        currency = "ARS"

    db.execute(
        "INSERT INTO account_payments (customer_id, amount, currency, payment_method, note, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            customer_id,
            amount,
            currency,
            str(data.get("payment_method", "")).strip(),
            str(data.get("note", "")).strip(),
            now_iso(),
        ),
    )
    db.commit()
    return get_account(customer_id)
