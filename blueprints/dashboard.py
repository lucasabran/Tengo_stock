from datetime import datetime, timedelta

from flask import Blueprint, jsonify, render_template

from db import get_db

bp = Blueprint("dashboard", __name__)

LOW_STOCK_THRESHOLD = 3


@bp.route("/")
def dashboard_page():
    return render_template("dashboard.html", active="dashboard")


@bp.route("/api/dashboard/summary")
def summary():
    db = get_db()
    today_date = datetime.now().date()
    today = today_date.isoformat()
    month = today[:7]

    sales_today = db.execute(
        "SELECT COUNT(*) AS c, COALESCE(SUM(total), 0) AS s FROM sales WHERE created_at LIKE ?",
        (f"{today}%",),
    ).fetchone()

    sales_month = db.execute(
        "SELECT COALESCE(SUM(total), 0) AS s FROM sales WHERE created_at LIKE ?",
        (f"{month}%",),
    ).fetchone()

    expenses_month = db.execute(
        "SELECT COALESCE(SUM(amount), 0) AS s FROM expenses WHERE expense_date LIKE ?",
        (f"{month}%",),
    ).fetchone()

    low_stock_rows = db.execute(
        "SELECT sku, name, quantity FROM products WHERE quantity <= ? ORDER BY quantity ASC LIMIT 10",
        (LOW_STOCK_THRESHOLD,),
    ).fetchall()

    recent = db.execute(
        """
        SELECT sales.id, sales.total, sales.created_at, channels.name AS channel_name,
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

    week_ago = (today_date - timedelta(days=6)).isoformat()
    sales_by_day = db.execute(
        "SELECT substr(created_at, 1, 10) AS day, COALESCE(SUM(total), 0) AS total "
        "FROM sales WHERE created_at >= ? GROUP BY day",
        (week_ago,),
    ).fetchall()
    totals_by_day = {r["day"]: r["total"] for r in sales_by_day}
    sales_last_7_days = [
        {
            "date": (today_date - timedelta(days=i)).isoformat(),
            "total": totals_by_day.get((today_date - timedelta(days=i)).isoformat(), 0),
        }
        for i in range(6, -1, -1)
    ]

    sales_month_total = sales_month["s"]
    expenses_month_total = expenses_month["s"]

    return jsonify(
        {
            "sales_today_total": sales_today["s"],
            "sales_today_count": sales_today["c"],
            "sales_month_total": sales_month_total,
            "expenses_month_total": expenses_month_total,
            "balance_month": round(sales_month_total - expenses_month_total, 2),
            "low_stock_count": len(low_stock_rows),
            "low_stock_products": [
                {"sku": r["sku"], "name": r["name"], "quantity": r["quantity"]} for r in low_stock_rows
            ],
            "top_products": [
                {"sku": r["sku"], "name": r["product_name"], "quantity": r["qty"]} for r in top_products
            ],
            "sales_last_7_days": sales_last_7_days,
            "recent_sales": [
                {
                    "id": r["id"],
                    "number": f"V-{r['id']:06d}",
                    "total": r["total"],
                    "created_at": r["created_at"],
                    "channel_name": r["channel_name"],
                    "customer_name": r["customer_name"],
                }
                for r in recent
            ],
        }
    )
