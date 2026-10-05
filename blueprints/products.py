import os
import sqlite3
import uuid

from flask import Blueprint, Response, jsonify, render_template, request, send_from_directory

from db import DB_PATH, get_db, now_iso
import auth
from helpers import build_csv, normalize_currency, parse_csv_file, parse_number, parse_xlsx_file

bp = Blueprint("products", __name__)

UPLOAD_DIR = os.path.join(os.environ.get("STOCK_UPLOAD_DIR") or os.path.join(os.path.dirname(str(DB_PATH)), "uploads"), "products")
MAX_PHOTO_BYTES = 5 * 1024 * 1024

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
        "min_stock": row["min_stock"] or 0,
        "photo_url": f"/media/products/{row['photo']}" if row["photo"] else "",
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
    try:
        min_stock = max(int(data.get("min_stock") or 0), 0)
    except (TypeError, ValueError):
        return jsonify({"error": "stock minimo debe ser numerico"}), 400

    db = get_db()
    exists = db.execute("SELECT 1 FROM products WHERE sku = ?", (sku,)).fetchone()
    if exists:
        return jsonify({"error": f"ya existe un producto con sku {sku}"}), 409

    db.execute(
        "INSERT INTO products (sku, name, description, category, currency, price, quantity, min_stock, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (sku, name, description, category, currency, price, quantity, min_stock, now_iso()),
    )
    db.commit()
    auth.audit("producto_creado", "product", sku, f"{name} - {quantity} u. a {price:,.2f}")
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
        min_stock = max(int(data.get("min_stock", row["min_stock"]) or 0), 0)
    except (TypeError, ValueError):
        return jsonify({"error": "price, quantity y stock minimo deben ser numericos"}), 400

    db.execute(
        "UPDATE products SET name=?, description=?, category=?, currency=?, price=?, quantity=?, min_stock=?, updated_at=? WHERE sku=?",
        (name, description, category, currency, price, quantity, min_stock, now_iso(), sku),
    )
    db.commit()
    changes = []
    if price != row["price"]:
        changes.append(f"precio {row['price']:,.2f} -> {price:,.2f}")
    if quantity != row["quantity"]:
        changes.append(f"cantidad {row['quantity']} -> {quantity}")
    if name != row["name"]:
        changes.append(f"nombre {row['name']} -> {name}")
    auth.audit("producto_editado", "product", sku, "; ".join(changes) or "sin cambios de precio/cantidad")
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
        "INSERT INTO stock_movements (sku, change_qty, reason, note, reference_type, reference_id, created_at, created_by) "
        "VALUES (?, ?, ?, ?, '', NULL, ?, ?)",
        (sku, amount, reason, note, now_iso(), auth.actor()),
    )
    db.commit()
    auth.audit("stock_cargado", "product", sku, f"{amount:+d} ({reason}) -> {new_qty}")
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
    auth.audit("productos_importados", "product", "", f"{created} nuevos, {updated} actualizados, {len(errors)} errores")
    return jsonify({"created": created, "updated": updated, "errors": errors})


@bp.route("/api/products/<sku>", methods=["DELETE"])
def delete_product(sku):
    db = get_db()
    old = db.execute("SELECT * FROM products WHERE sku = ?", (sku,)).fetchone()
    try:
        db.execute("DELETE FROM products WHERE sku = ?", (sku,))
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        return jsonify({"error": "no se puede eliminar, el producto tiene ventas o movimientos asociados"}), 409
    if old:
        _remove_photo_file(old["photo"])
        auth.audit("producto_eliminado", "product", sku, f"{old['name']} (stock {old['quantity']})")
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Fotos de producto
# ---------------------------------------------------------------------------
def _detect_image_ext(head):
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def _remove_photo_file(filename):
    if not filename:
        return
    try:
        os.remove(os.path.join(UPLOAD_DIR, os.path.basename(filename)))
    except OSError:
        pass


@bp.route("/media/products/<path:filename>")
def product_photo(filename):
    resp = send_from_directory(UPLOAD_DIR, os.path.basename(filename), max_age=3600)
    resp.headers["Cache-Control"] = "private, max-age=3600"
    return resp


@bp.route("/api/products/<sku>/photo", methods=["POST"])
def upload_photo(sku):
    db = get_db()
    row = db.execute("SELECT * FROM products WHERE sku = ?", (sku,)).fetchone()
    if not row:
        return jsonify({"error": "producto no encontrado"}), 404
    file = request.files.get("photo")
    if not file:
        return jsonify({"error": "no se recibio ninguna foto"}), 400
    data = file.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        return jsonify({"error": "la foto pesa mas de 5 MB"}), 400
    ext = _detect_image_ext(data[:16])
    if not ext:
        return jsonify({"error": "formato no soportado, usa JPG, PNG o WEBP"}), 400

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{ext}"
    with open(os.path.join(UPLOAD_DIR, filename), "wb") as fh:
        fh.write(data)
    _remove_photo_file(row["photo"])
    db.execute("UPDATE products SET photo = ?, updated_at = ? WHERE sku = ?", (filename, now_iso(), sku))
    db.commit()
    auth.audit("foto_subida", "product", sku, filename)
    return jsonify(row_to_dict(db.execute("SELECT * FROM products WHERE sku = ?", (sku,)).fetchone()))


@bp.route("/api/products/<sku>/photo", methods=["DELETE"])
def delete_photo(sku):
    db = get_db()
    row = db.execute("SELECT * FROM products WHERE sku = ?", (sku,)).fetchone()
    if not row:
        return jsonify({"error": "producto no encontrado"}), 404
    _remove_photo_file(row["photo"])
    db.execute("UPDATE products SET photo = '', updated_at = ? WHERE sku = ?", (now_iso(), sku))
    db.commit()
    auth.audit("foto_eliminada", "product", sku, "")
    return jsonify(row_to_dict(db.execute("SELECT * FROM products WHERE sku = ?", (sku,)).fetchone()))
