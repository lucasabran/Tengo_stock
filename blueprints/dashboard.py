from datetime import datetime, timedelta

from flask import Blueprint, jsonify, render_template

from db import get_db

bp = Blueprint("dashboard", __name__)

LOW_STOCK_THRESHOLD = 3


@bp.route("/")
def dashboard_page():
    return render_template("dashboard.html", active="dashboard")


def _currency_clause(currency):
    return ("currency = 'USD'", []) if currency == "USD" else ("(currency IS NULL OR currency = 'ARS')", [])


def _sales_totals(db, currency, like_pattern):
    clause, extra = _currency_clause(currency)
    row = db.execute(
        f"SELECT COUNT(*) AS c, COALESCE(SUM(total), 0) AS s FROM sales WHERE created_at LIKE ? AND {clause}",
        [like_pattern, *extra],
    ).fetchone()
    return row["c"], row["s"]


def _sales_last_7_days(db, currency, today_date, week_ago):
    clause, extra = _currency_clause(currency)
    rows = db.execute(
        f"SELECT substr(created_at, 1, 10) AS day, COALESCE(SUM(total), 0) AS total "
        f"FROM sales WHERE created_at >= ? AND {clause} GROUP BY day",
        [week_ago, *extra],
    ).fetchall()
    totals_by_day = {r["day"]: r["total"] for r in rows}
    return [
        {
            "date": (today_date - timedelta(days=i)).isoformat(),
            "total": totals_by_day.get((today_date - timedelta(days=i)).isoformat(), 0),
        }
        for i in range(6, -1, -1)
    ]


@bp.route("/api/dashboard/summary")
def summary():
    db = get_db()
    today_date = datetime.now().date()
    today = today_date.isoformat()
    month = today[:7]
    week_ago = (today_date - timedelta(days=6)).isoformat()

    sales_today_count_ars, sales_today_total_ars = _sales_totals(db, "ARS", f"{today}%")
    sales_today_count_usd, sales_today_total_usd = _sales_totals(db, "USD", f"{today}%")
    _, sales_month_total_ars = _sales_totals(db, "ARS", f"{month}%")
    _, sales_month_total_usd = _sales_totals(db, "USD", f"{month}%")

    expenses_month = db.execute(
        "SELECT COALESCE(SUM(amount), 0) AS s FROM expenses WHERE expense_date LIKE ?",
        (f"{month}%",),
    ).fetchone()
    expenses_month_total = expenses_month["s"]

    low_stock_rows = db.execute(
        "SELECT sku, name, quantity FROM products WHERE quantity <= ? ORDER BY quantity ASC LIMIT 10",
        (LOW_STOCK_THRESHOLD,),
    ).fetchall()

    recent = db.execute(
        """
        SELECT sales.id, sales.total, sales.currency, sales.created_at, channels.name AS channel_name,
               customers.name AS customer_name
        FROM sales
        JOIN channels ON channels.id = sales.channel_id
        LEFT JOIN customers ON customers.id = sales.customer_id
        ORDER BY sales.id DESC LIMIT 5
        """
    ).fetchall()

    thirty_days_ago = (today_date - timedelta(days=29)).isoformat()
    top_products = db.execute(
        """
        SELECT sale_items.sku, sale_items.product_name, SUM(sale_items.quantity) AS qty
        FROM sale_items
        JOIN sales ON sales.id = sale_items.sale_id
        WHERE sales.created_at >= ?
        GROUP BY sale_items.sku
        ORDER BY qty DESC
        LIMIT 5
        """,
        (thirty_days_ago,),
    ).fetchall()

    return jsonify(
        {
            "ars": {
                "sales_today_total": sales_today_total_ars,
                "sales_today_count": sales_today_count_ars,
                "sales_month_total": sales_month_total_ars,
                "expenses_month_total": expenses_month_total,
                "balance_month": round(sales_month_total_ars - expenses_month_total, 2),
                "sales_last_7_days": _sales_last_7_days(db, "ARS", today_date, week_ago),
            },
            "usd": {
                "sales_today_total": sales_today_total_usd,
                "sales_today_count": sales_today_count_usd,
                "sales_month_total": sales_month_total_usd,
                "sales_last_7_days": _sales_last_7_days(db, "USD", today_date, week_ago),
            },
            "low_stock_count": len(low_stock_rows),
            "low_stock_products": [
                {"sku": r["sku"], "name": r["name"], "quantity": r["quantity"]} for r in low_stock_rows
            ],
            "top_products": [
                {"sku": r["sku"], "name": r["product_name"], "quantity": r["qty"]} for r in top_products
            ],
            "recent_sales": [
                {
                    "id": r["id"],
                    "number": f"V-{r['id']:06d}",
                    "total": r["total"],
                    "currency": r["currency"] or "ARS",
                    "created_at": r["created_at"],
                    "channel_name": r["channel_name"],
                    "customer_name": r["customer_name"],
                }
                for r in recent
            ],
        }
    )
