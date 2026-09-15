from flask import Blueprint, abort, jsonify, render_template, request

from db import get_db, now_iso
from helpers import ACCOUNT_PAYMENT_METHOD

bp = Blueprint("accounts", __name__)

MOVEMENT_TYPES = {"charge", "payment"}

ACCOUNTS_QUERY = """
    SELECT customers.id, customers.name,
           COALESCE(sales_ars.total, 0) AS sales_charged_ars,
           COALESCE(manual_charges_ars.total, 0) AS manual_charged_ars,
           COALESCE(payments_ars.total, 0) AS paid_ars,
           COALESCE(sales_usd.total, 0) AS sales_charged_usd,
           COALESCE(manual_charges_usd.total, 0) AS manual_charged_usd,
           COALESCE(payments_usd.total, 0) AS paid_usd
    FROM customers
    LEFT JOIN (
        SELECT customer_id, SUM(total) AS total FROM sales
        WHERE payment_method = ? AND (currency IS NULL OR currency = 'ARS') AND customer_id IS NOT NULL
        GROUP BY customer_id
    ) sales_ars ON sales_ars.customer_id = customers.id
    LEFT JOIN (
        SELECT customer_id, SUM(amount) AS total FROM account_payments
        WHERE type = 'charge' AND (currency IS NULL OR currency = 'ARS')
        GROUP BY customer_id
    ) manual_charges_ars ON manual_charges_ars.customer_id = customers.id
    LEFT JOIN (
        SELECT customer_id, SUM(amount) AS total FROM account_payments
        WHERE type = 'payment' AND (currency IS NULL OR currency = 'ARS')
        GROUP BY customer_id
    ) payments_ars ON payments_ars.customer_id = customers.id
    LEFT JOIN (
        SELECT customer_id, SUM(total) AS total FROM sales
        WHERE payment_method = ? AND currency = 'USD' AND customer_id IS NOT NULL
        GROUP BY customer_id
    ) sales_usd ON sales_usd.customer_id = customers.id
    LEFT JOIN (
        SELECT customer_id, SUM(amount) AS total FROM account_payments
        WHERE type = 'charge' AND currency = 'USD'
        GROUP BY customer_id
    ) manual_charges_usd ON manual_charges_usd.customer_id = customers.id
    LEFT JOIN (
        SELECT customer_id, SUM(amount) AS total FROM account_payments
        WHERE type = 'payment' AND currency = 'USD'
        GROUP BY customer_id
    ) payments_usd ON payments_usd.customer_id = customers.id
"""

ACCOUNTS_HAS_ACTIVITY = (
    "(COALESCE(sales_ars.total, 0) + COALESCE(manual_charges_ars.total, 0) > 0 "
    "OR COALESCE(sales_usd.total, 0) + COALESCE(manual_charges_usd.total, 0) > 0)"
)


def account_row_to_dict(row):
    charged_ars = row["sales_charged_ars"] + row["manual_charged_ars"]
    charged_usd = row["sales_charged_usd"] + row["manual_charged_usd"]
    return {
        "customer_id": row["id"],
        "customer_name": row["name"],
        "ars": {
            "charged": charged_ars,
            "paid": row["paid_ars"],
            "balance": round(charged_ars - row["paid_ars"], 2),
        },
        "usd": {
            "charged": charged_usd,
            "paid": row["paid_usd"],
            "balance": round(charged_usd - row["paid_usd"], 2),
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
        ACCOUNTS_QUERY + f" WHERE {ACCOUNTS_HAS_ACTIVITY} ORDER BY customers.name",
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
    movements = db.execute(
        "SELECT id, amount, currency, type, payment_method, note, created_at FROM account_payments "
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
            "type": m["type"] or "payment",
            "date": m["created_at"],
            "amount": m["amount"],
            "currency": m["currency"] or "ARS",
            "label": (
                f"Cargo manual ({m['payment_method']})" if m["type"] == "charge" and m["payment_method"]
                else "Cargo manual" if m["type"] == "charge"
                else f"Pago ({m['payment_method']})" if m["payment_method"]
                else "Pago"
            ),
            "note": m["note"] or "",
            "sale_id": None,
        }
        for m in movements
    ]
    ledger.sort(key=lambda x: x["date"])

    result = account_row_to_dict(row) if row else account_row_to_dict(
        {
            "id": customer_id,
            "name": customer["name"],
            "sales_charged_ars": 0,
            "manual_charged_ars": 0,
            "paid_ars": 0,
            "sales_charged_usd": 0,
            "manual_charged_usd": 0,
            "paid_usd": 0,
        }
    )
    result["ledger"] = ledger
    return jsonify(result)


@bp.route("/api/accounts/<int:customer_id>/movements", methods=["POST"])
def create_movement(customer_id):
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

    movement_type = str(data.get("type", "payment")).strip().lower()
    if movement_type not in MOVEMENT_TYPES:
        return jsonify({"error": f"tipo de movimiento invalido: {movement_type}"}), 400

    db.execute(
        "INSERT INTO account_payments (customer_id, amount, currency, type, payment_method, note, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            customer_id,
            amount,
            currency,
            movement_type,
            str(data.get("payment_method", "")).strip(),
            str(data.get("note", "")).strip(),
            now_iso(),
        ),
    )
    db.commit()
    return get_account(customer_id)
