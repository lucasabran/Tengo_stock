import sqlite3

from flask import Blueprint, Response, jsonify, render_template, request

from db import get_db, now_iso
from helpers import build_csv, normalize_currency, parse_csv_file, parse_number, parse_xlsx_file

bp = Blueprint("products", __name__)

STOCK_ENTRY_REASONS = {
    "ajuste_manual",
    "compra_proveedor",
    "ajuste_inventario",
    "devolucion_proveedor",
    "otro",
}

DEFAULT_CATEGORIES = [
    "General",
    "Celulares",
    "Accesorios para celulares",
    "Tecnologia",
    "Consolas y Videojuegos",
    "Tablets",
    "Imagen y Sonido",
    "Electrodomesticos",
    "Electronica",
    "Otro",
]


def row_to_dict(row):
    return {
        "sku": row["sku"],
        "name": row["name"],
        "description": row["description"],
        "category": row["category"] or "",
        "currency": row["currency"] or "ARS",
        "price": row["price"],
        "quantity": row["quantity"],
        "updated_at": row["updated_at"],
    }


@bp.route("/stock")
def stock_page():
    return render_template("stock.html", active="stock")


@bp.route("/api/products", methods=["GET"])
def list_products():
    db = get_db()
    where = []
    params = []

    q = request.args.get("q", "").strip()
    if q:
        where.append("(sku LIKE ? OR name LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]

    category = request.args.get("category", "").strip()
    if category:
        where.append("category = ?")
        params.append(category)

    query = "SELECT * FROM products"
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY name"

    rows = db.execute(query, params).fetchall()
    return jsonify([row_to_dict(r) for r in rows])


@bp.route("/api/categories", methods=["GET"])
def list_categories():
    db = get_db()
    rows = db.execute("SELECT DISTINCT category FROM products WHERE category != ''").fetchall()
    used = {r["category"] for r in rows}
    all_categories = sorted(set(DEFAULT_CATEGORIES) | used, key=str.casefold)
    return jsonify(all_categories)


@bp.route("/api/products/<sku>", methods=["GET"])
def get_product(sku):
    db = get_db()
    row = db.execute("SELECT * FROM products WHERE sku = ?", (sku,)).fetchone()
    if not row:
        return jsonify({"error": "producto no encontrado"}), 404
    return jsonify(row_to_dict(row))


@bp.route("/api/products", methods=["POST"])
def create_product():
    data = request.get_json(force=True) or {}
    sku = str(data.get("sku", "")).strip()
    name = str(data.get("name", "")).strip()
    if not sku or not name:
        return jsonify({"error": "sku y name son obligatorios"}), 400

    try:
        price = float(data.get("price", 0))
        quantity = int(data.get("quantity", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "price y quantity deben ser numericos"}), 400

    description = str(data.get("description", "")).strip()
    category = str(data.get("category", "")).strip()
    currency = normalize_currency(data.get("currency", "ARS"))

    db = get_db()
    exists = db.execute("SELECT 1 FROM products WHERE sku = ?", (sku,)).fetchone()
    if exists:
        return jsonify({"error": f"ya existe un producto con sku {sku}"}), 409

    db.execute(
        "INSERT INTO products (sku, name, description, category, currency, price, quantity, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (sku, name, description, category, currency, price, quantity, now_iso()),
    )
    db.commit()
    row = db.execute("SELECT * FROM products WHERE sku = ?", (sku,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@bp.route("/api/products/<sku>", methods=["PUT"])
def update_product(sku):
    db = get_db()
    row = db.execute("SELECT * FROM products WHERE sku = ?", (sku,)).fetchone()
    if not row:
        return jsonify({"error": "producto no encontrado"}), 404

    data = request.get_json(force=True) or {}
    name = str(data.get("name", row["name"])).strip()
    description = str(data.get("description", row["description"]))
    category = str(data.get("category", row["category"])).strip()
    currency = normalize_currency(data.get("currency", row["currency"]))
    try:
        price = float(data.get("price", row["price"]))
        quantity = int(data.get("quantity", row["quantity"]))
    except (TypeError, ValueError):
        return jsonify({"error": "price y quantity deben ser numericos"}), 400

    db.execute(
        "UPDATE products SET name=?, description=?, category=?, currency=?, price=?, quantity=?, updated_at=? WHERE sku=?",
        (name, description, category, currency, price, quantity, now_iso(), sku),
    )
    db.commit()
    row = db.execute("SELECT * FROM products WHERE sku = ?", (sku,)).fetchone()
    return jsonify(row_to_dict(row))


@bp.route("/api/products/<sku>/add-stock", methods=["POST"])
def add_stock(sku):
    data = request.get_json(force=True) or {}
    try:
        amount = int(data.get("amount", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "amount debe ser numerico"}), 400

    reason = str(data.get("reason", "ajuste_manual")).strip() or "ajuste_manual"
    if reason not in STOCK_ENTRY_REASONS:
        return jsonify({"error": f"motivo invalido: {reason}"}), 400
    note = str(data.get("note", "")).strip()

    db = get_db()
    row = db.execute("SELECT * FROM products WHERE sku = ?", (sku,)).fetchone()
    if not row:
        return jsonify({"error": "producto no encontrado"}), 404

    new_qty = row["quantity"] + amount
    db.execute(
        "UPDATE products SET quantity=?, updated_at=? WHERE sku=?",
        (new_qty, now_iso(), sku),
    )
    db.execute(
        "INSERT INTO stock_movements (sku, change_qty, reason, note, reference_type, reference_id, created_at) "
        "VALUES (?, ?, ?, ?, '', NULL, ?)",
        (sku, amount, reason, note, now_iso()),
    )
    db.commit()
    row = db.execute("SELECT * FROM products WHERE sku = ?", (sku,)).fetchone()
    return jsonify(row_to_dict(row))


@bp.route("/api/products/template.csv")
def download_template():
    content = "sku,name,price,currency,quantity,description,category\n"
    return Response(
        content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=plantilla_stock.csv"},
    )


@bp.route("/api/products/export.csv")
def export_products():
    db = get_db()
    rows = db.execute("SELECT * FROM products ORDER BY name").fetchall()
    content = build_csv(
        ["sku", "name", "price", "currency", "quantity", "description", "category"],
        [
            [r["sku"], r["name"], r["price"], r["currency"] or "ARS", r["quantity"], r["description"], r["category"] or ""]
            for r in rows
        ],
    )
    return Response(
        content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=stock.csv"},
    )


@bp.route("/api/products/import", methods=["POST"])
def import_products():
    if "file" not in request.files or not request.files["file"].filename:
        return jsonify({"error": "no se recibio ningun archivo"}), 400

    file = request.files["file"]
    filename = file.filename.lower()

    try:
        if filename.endswith(".csv"):
            rows = parse_csv_file(file)
        elif filename.endswith(".xlsx") or filename.endswith(".xlsm"):
            rows = parse_xlsx_file(file)
        else:
            return jsonify({"error": "formato no soportado, usa .csv o .xlsx"}), 400
    except Exception as exc:
        return jsonify({"error": f"no se pudo leer el archivo: {exc}"}), 400

    db = get_db()
    created = 0
    updated = 0
    errors = []
    now = now_iso()

    for i, row in enumerate(rows, start=2):
        sku_raw = row.get("sku", "")
        if isinstance(sku_raw, float) and sku_raw.is_integer():
            sku_raw = int(sku_raw)
        sku = str(sku_raw or "").strip()
        name = str(row.get("name", "") or "").strip()
        if not sku or not name:
            errors.append(f"fila {i}: falta sku o nombre")
            continue
        try:
            price = parse_number(row.get("price", 0))
            quantity = int(parse_number(row.get("quantity", 0)))
        except (TypeError, ValueError):
            errors.append(f"fila {i}: precio o cantidad invalido")
            continue
        description = str(row.get("description", "") or "").strip()
        category = str(row.get("category", "") or "").strip()
        currency = normalize_currency(row.get("currency", "ARS"))

        exists = db.execute("SELECT 1 FROM products WHERE sku = ?", (sku,)).fetchone()
        if exists:
            db.execute(
                "UPDATE products SET name=?, description=?, category=?, currency=?, price=?, quantity=?, updated_at=? WHERE sku=?",
                (name, description, category, currency, price, quantity, now, sku),
            )
            updated += 1
        else:
            db.execute(
                "INSERT INTO products (sku, name, description, category, currency, price, quantity, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (sku, name, description, category, currency, price, quantity, now),
            )
            created += 1

    db.commit()
    return jsonify({"created": created, "updated": updated, "errors": errors})


@bp.route("/api/products/<sku>", methods=["DELETE"])
def delete_product(sku):
    db = get_db()
    try:
        db.execute("DELETE FROM products WHERE sku = ?", (sku,))
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        return jsonify({"error": "no se puede eliminar, el producto tiene ventas o movimientos asociados"}), 409
    return jsonify({"ok": True})
