import contextlib
import os
from datetime import datetime

from flask import Flask

import auth
import jobs
import ml_multi
import tn_sync
from db import close_db, init_db
from blueprints import accounts, admin, alerts, auth_bp, bulk, channels, customers, dashboard, expenses, mercadolibre, movements, offices, ops, products, returns, sales, tiendanube

app = Flask(__name__)
app.teardown_appcontext(close_db)


@app.template_filter("money")
def format_money(value, currency="ARS"):
    formatted = format(value or 0, ",.2f").replace(",", "X").replace(".", ",").replace("X", ".")
    symbol = "US$" if currency == "USD" else "$"
    return f"{symbol} {formatted}"


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
app.register_blueprint(accounts.bp)
app.register_blueprint(auth_bp.bp)
app.register_blueprint(admin.bp)
app.register_blueprint(bulk.bp)
app.register_blueprint(offices.bp)
app.register_blueprint(alerts.bp)
app.register_blueprint(tiendanube.bp)
app.register_blueprint(ops.bp)
app.register_blueprint(mercadolibre.bp)

auth.install(app)


@app.route("/healthz", endpoint="healthcheck")
def healthcheck():
    return "ok"



init_db()
with contextlib.closing(tn_sync.connect()) as _db:
    tn_sync.ensure_schema(_db)
    ml_multi.ensure_schema(_db)
    _db.commit()
auth.seed_auth()
app.secret_key = auth.load_secret_key()
jobs.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=os.environ.get("FLASK_DEBUG") == "1")
