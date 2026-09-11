import os
import secrets
from datetime import datetime

from flask import Flask, Response, request

from db import close_db, init_db
from blueprints import channels, customers, dashboard, expenses, movements, products, returns, sales

STOCK_USER = os.environ.get("STOCK_USER", "admin")
STOCK_PASSWORD = os.environ.get("STOCK_PASSWORD", "admin1234")

app = Flask(__name__)
app.teardown_appcontext(close_db)


@app.template_filter("money")
def format_money(value):
    formatted = format(value or 0, ",.2f").replace(",", "X").replace(".", ",").replace("X", ".")
    return f"$ {formatted}"


@app.template_filter("datetime")
def format_datetime(value):
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return value
    return dt.strftime("%d/%m/%Y %H:%M")

app.register_blueprint(dashboard.bp)
app.register_blueprint(products.bp)
app.register_blueprint(channels.bp)
app.register_blueprint(customers.bp)
app.register_blueprint(sales.bp)
app.register_blueprint(returns.bp)
app.register_blueprint(expenses.bp)
app.register_blueprint(movements.bp)


@app.before_request
def require_login():
    auth = request.authorization
    valid = (
        auth is not None
        and secrets.compare_digest(auth.username, STOCK_USER)
        and secrets.compare_digest(auth.password, STOCK_PASSWORD)
    )
    if not valid:
        return Response(
            "Acceso restringido. Usuario y clave requeridos.",
            401,
            {"WWW-Authenticate": 'Basic realm="Stock"'},
        )


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
