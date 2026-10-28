import os
import sqlite3
import uuid

from flask import Blueprint, Response, jsonify, render_template, request, send_from_directory

import auth
import stock as stk
from db import DB_PATH, get_db, now_iso
from helpers import (
    build_csv,
    normalize_currency,
    parse_csv_file,
    parse_number,
    parse_number_lenient,
    parse_xlsx_file,
)

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

# Orden natural por SKU: los numericos primero y en orden numerico (2 antes que 10), despues los alfanumericos
SORTS = {
    "sku": "CASE WHEN p.sku NOT GLOB '*[^0-9]*' THEN 0 ELSE 1 END, "
           "CASE WHEN p.sku NOT GLOB '*[^0-9]*' THEN CAST(p.sku AS INTEGER) END, p.sku COLLATE NOCASE",
    "name": "p.name COLLATE NOCASE",
    "recent": "p.updated_at DESC",
}


def row_to_dict(row, view_qty=None, offices=None):
    quantity = row["quantity"] if view_qty is None else view_qty
    data = {
        "sku": row["sku"],
        "name": row["name"],
        "description": row["description"],
        "category": row["category"] or "",
        "condition": row["condition"] or "Nuevo",
        "currency": row["currency"] or "ARS",
        "price": row["price"],
        "price_wholesale": row["price_wholesale"] or 0,
        "quantity": quantity,
        "min_stock": row["min_stock"] or 0,
        "photo_url": f"/media/products/{row['photo']}" if row["photo"] else "",
        "updated_at": row["updated_at"],
    }
    if offices is not None:
        data["total_quantity"] = row["quantity"]
        data["stock_by_office"] = offices
    return data


def _check_condition(value):
    value = str(value or "Nuevo").strip()
    for c in stk.CONDITIONS:
        if c.lower() == value.lower():
            return c
    return None


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
        where.append("(p.sku LIKE ? OR p.name LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]

    category = request.args.get("category", "").strip()
    if category:
        where.append("p.category = ?")
        params.append(category)

    condition = request.args.get("condition", "").strip()
    if condition:
        where.append("p.condition = ?")
        params.append(condition)

    fixed_office = stk.user_office_id()
    office_arg = request.args.get("office_id", "")
    view_office = fixed_office or (int(office_arg) if office_arg.isdigit() else None)

    if view_office:
        select = "SELECT p.*, COALESCE(sl.quantity, 0) AS view_qty FROM products p LEFT JOIN stock_levels sl ON sl.sku = p.sku AND sl.office_id = ?"
        params = [view_office] + params
    else:
        select = "SELECT p.*, p.quantity AS view_qty FROM products p"

    query = select
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY " + SORTS.get(request.args.get("sort", "sku"), SORTS["sku"])

    rows = db.execute(query, params).fetchall()
    offices = None if fixed_office else stk.breakdown(db, [r["sku"] for r in rows])
    return jsonify([row_to_dict(r, r["view_qty"], None if offices is None else offices.get(r["sku"], [])) for r in rows])


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
    fixed = stk.user_office_id()
    if fixed:
        return jsonify(row_to_dict(row, stk.level(db, sku, fixed)))
    return jsonify(row_to_dict(row, None, stk.breakdown(db, [sku]).get(sku, [])))


@bp.route("/api/products", methods=["POST"])
def create_product():
    data = request.get_json(force=True) or {}
    sku = str(data.get("sku", "")).strip()
    name = str(data.get("name", "")).strip()
    if not sku or not name:
        return jsonify({"error": "sku y name son obligatorios"}), 400

    try:
        price = float(data.get("price", 0))
        price_wholesale = float(data.get("price_wholesale") or 0)
        quantity = int(data.get("quantity", 0))
        min_stock = max(int(data.get("min_stock") or 0), 0)
    except (TypeError, ValueError):
        return jsonify({"error": "precios, cantidad y stock minimo deben ser numericos"}), 400
    if quantity < 0:
        return jsonify({"error": "la cantidad inicial no puede ser negativa"}), 400

    condition = _check_condition(data.get("condition"))
    if not condition:
        return jsonify({"error": "condicion invalida (Nuevo, Usado, Reacondicionado o RMA)"}), 400

    description = str(data.get("description", "")).strip()
    category = str(data.get("category", "")).strip()
    currency = normalize_currency(data.get("currency", "ARS"))

    db = get_db()
    office_id, err = stk.resolve_office(db, data.get("office_id"))
    if err:
        return jsonify({"error": err}), 400
    if db.execute("SELECT 1 FROM products WHERE sku = ?", (sku,)).fetchone():
        return jsonify({"error": f"ya existe un producto con sku {sku}"}), 409

    now = now_iso()
    db.execute(
        "INSERT INTO products (sku, name, description, category, condition, currency, price, price_wholesale, quantity, min_stock, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
        (sku, name, description, category, condition, currency, price, price_wholesale, min_stock, now),
    )
    if quantity:
        stk.adjust(db, sku, office_id, quantity, now)
        stk.record_movement(db, sku, office_id, quantity, "stock_inicial", "", "", None, now, auth.actor())
    db.commit()
    auth.audit("producto_creado", "product", sku, f"{name} [{condition}] - {quantity} u. a {price:,.2f}")
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
    condition = _check_condition(data.get("condition", row["condition"]))
    if not condition:
        return jsonify({"error": "condicion invalida (Nuevo, Usado, Reacondicionado o RMA)"}), 400
    try:
        price = float(data.get("price", row["price"]))
        price_wholesale = float(data.get("price_wholesale", row["price_wholesale"]) or 0)
        min_stock = max(int(data.get("min_stock", row["min_stock"]) or 0), 0)
        new_qty = int(data["quantity"]) if data.get("quantity") not in (None, "") else None
    except (TypeError, ValueError):
        return jsonify({"error": "precios, cantidad y stock minimo deben ser numericos"}), 400
    if new_qty is not None and new_qty < 0:
        return jsonify({"error": "la cantidad no puede ser negativa"}), 400

    now = now_iso()
    changes = []
    db.execute(
        "UPDATE products SET name=?, description=?, category=?, condition=?, currency=?, price=?, price_wholesale=?, min_stock=?, updated_at=? WHERE sku=?",
        (name, description, category, condition, currency, price, price_wholesale, min_stock, now, sku),
    )

    # La cantidad se edita para UNA oficina; el consolidado se recalcula solo
    if new_qty is not None:
        office_id, err = stk.resolve_office(db, data.get("office_id"))
        if err:
            db.rollback()
            return jsonify({"error": err}), 400
        current = stk.level(db, sku, office_id)
        if new_qty != current:
            stk.adjust(db, sku, office_id, new_qty - current, now)
            stk.record_movement(db, sku, office_id, new_qty - current, "ajuste_inventario", "Edicion del producto", "", None, now, auth.actor())
            changes.append(f"cantidad {current} -> {new_qty}")
    db.commit()

    if price != row["price"]:
        changes.append(f"precio {row['price']:,.2f} -> {price:,.2f}")
    if price_wholesale != (row["price_wholesale"] or 0):
        changes.append(f"mayorista {row['price_wholesale'] or 0:,.2f} -> {price_wholesale:,.2f}")
    if condition != (row["condition"] or "Nuevo"):
        changes.append(f"condicion {row['condition']} -> {condition}")
    if name != row["name"]:
        changes.append(f"nombre {row['name']} -> {name}")
    auth.audit("producto_editado", "product", sku, "; ".join(changes) or "sin cambios de precio/cantidad")
    row = db.execute("SELECT * FROM products WHERE sku = ?", (sku,)).fetchone()
    return jsonify(row_to_dict(row))


@bp.route("/api/products/<sku>/sku", methods=["PUT"])
def rename_sku(sku):
    data = request.get_json(force=True) or {}
    new_sku = str(data.get("new_sku", "")).strip()
    if not new_sku:
        return jsonify({"error": "escribi el SKU nuevo"}), 400
    db = get_db()
    if not db.execute("SELECT 1 FROM products WHERE sku = ?", (sku,)).fetchone():
        return jsonify({"error": "producto no encontrado"}), 404
    if new_sku == sku:
        return jsonify({"error": "el SKU nuevo es igual al actual"}), 400
    if db.execute("SELECT 1 FROM products WHERE sku = ?", (new_sku,)).fetchone():
        return jsonify({"error": f"ya existe un producto con SKU {new_sku}"}), 409

    try:
        db.execute("PRAGMA defer_foreign_keys = ON")
        for table in ("products", "sale_items", "stock_movements", "stock_levels"):
            db.execute(f"UPDATE {table} SET sku = ? WHERE sku = ?", (new_sku, sku))
        db.commit()
    except sqlite3.Error as exc:
        db.rollback()
        return jsonify({"error": f"no se pudo cambiar el SKU: {exc}"}), 500

    auth.audit("sku_cambiado", "product", new_sku, f"{sku} -> {new_sku}")
    row = db.execute("SELECT * FROM products WHERE sku = ?", (new_sku,)).fetchone()
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
    office_id, err = stk.resolve_office(db, data.get("office_id"))
    if err:
        return jsonify({"error": err}), 400
    office = db.execute("SELECT name FROM offices WHERE id = ?", (office_id,)).fetchone()["name"]

    now = now_iso()
    if not stk.adjust(db, sku, office_id, amount, now):
        db.rollback()
        return jsonify({"error": f"No hay stock suficiente en {office} (hay {stk.level(db, sku, office_id)})"}), 409
    stk.record_movement(db, sku, office_id, amount, reason, note, "", None, now, auth.actor())
    db.commit()
    auth.audit("stock_cargado", "product", sku, f"{amount:+d} en {office} ({reason})")
    row = db.execute("SELECT * FROM products WHERE sku = ?", (sku,)).fetchone()
    return jsonify(row_to_dict(row, stk.level(db, sku, office_id)))


@bp.route("/api/stock-transfers", methods=["POST"])
def transfer_stock():
    data = request.get_json(force=True) or {}
    sku = str(data.get("sku", "")).strip()
    try:
        quantity = int(data.get("quantity", 0))
        from_id = int(data.get("from_office_id"))
        to_id = int(data.get("to_office_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "datos de transferencia invalidos"}), 400
    if quantity <= 0:
        return jsonify({"error": "la cantidad tiene que ser mayor a 0"}), 400
    if from_id == to_id:
        return jsonify({"error": "elegi oficinas distintas"}), 400

    db = get_db()
    if not db.execute("SELECT 1 FROM products WHERE sku = ?", (sku,)).fetchone():
        return jsonify({"error": "producto no encontrado"}), 404
    offices = {r["id"]: r["name"] for r in db.execute("SELECT id, name FROM offices").fetchall()}
    if from_id not in offices or to_id not in offices:
        return jsonify({"error": "oficina inexistente"}), 400

    now = now_iso()
    note = str(data.get("note", "")).strip()
    if not stk.adjust(db, sku, from_id, -quantity, now):
        db.rollback()
        return jsonify({"error": f"No hay stock suficiente en {offices[from_id]} (hay {stk.level(db, sku, from_id)})"}), 409
    stk.adjust(db, sku, to_id, quantity, now)
    stk.record_movement(db, sku, from_id, -quantity, "transferencia", f"A {offices[to_id]}. {note}".strip(), "transfer", None, now, auth.actor())
    stk.record_movement(db, sku, to_id, quantity, "transferencia", f"Desde {offices[from_id]}. {note}".strip(), "transfer", None, now, auth.actor())
    db.commit()
    auth.audit("stock_transferido", "product", sku, f"{quantity} u. de {offices[from_id]} a {offices[to_id]}")
    return jsonify({"ok": True})


@bp.route("/api/products/template.csv")
def download_template():
    content = "sku,name,price,price_wholesale,currency,condition,quantity,office,min_stock,description,category\n"
    return Response(
        content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=plantilla_stock.csv"},
    )


@bp.route("/api/products/export.csv")
def export_products():
    db = get_db()
    offices = db.execute("SELECT id, name FROM offices WHERE active = 1 ORDER BY id").fetchall()
    levels = {}
    for r in db.execute("SELECT sku, office_id, quantity FROM stock_levels").fetchall():
        levels[(r["sku"], r["office_id"])] = r["quantity"]
    rows = db.execute("SELECT p.* FROM products p ORDER BY " + SORTS["sku"]).fetchall()
    content = build_csv(
        ["sku", "name", "condition", "price", "price_wholesale", "currency", "quantity_total"]
        + [f"stock_{o['name']}" for o in offices]
        + ["min_stock", "description", "category"],
        [
            [r["sku"], r["name"], r["condition"] or "Nuevo", r["price"], r["price_wholesale"] or 0, r["currency"] or "ARS", r["quantity"]]
            + [levels.get((r["sku"], o["id"]), 0) for o in offices]
            + [r["min_stock"] or 0, r["description"], r["category"] or ""]
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
    # Oficina elegida en pantalla para las filas que no traen la columna 'oficina'
    default_office, err = stk.resolve_office(db, request.form.get("office_id"))
    if err:
        return jsonify({"error": err}), 400

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
            price = parse_number_lenient(row.get("price", 0))
            price_wholesale = parse_number_lenient(row.get("price_wholesale", 0))
            quantity = int(parse_number_lenient(row.get("quantity", 0)))
            min_stock = max(int(parse_number_lenient(row.get("min_stock", 0))), 0)
        except (TypeError, ValueError):
            errors.append(f"fila {i} (SKU {sku}): hay un texto donde tiene que ir un numero (precio, cantidad o minimo)")
            continue
        if quantity < 0:
            errors.append(f"fila {i} (SKU {sku}): la cantidad no puede ser negativa")
            continue
        condition = _check_condition(row.get("condition") or "Nuevo")
        if not condition:
            errors.append(f"fila {i} (SKU {sku}): condicion invalida ({row.get('condition')}). Usa Nuevo, Usado, Reacondicionado o RMA")
            continue
        office_id = default_office
        office_name = str(row.get("office") or "").strip()
        if office_name and not stk.user_office_id():
            office_id = stk.office_by_name(db, office_name)
            if not office_id:
                errors.append(f"fila {i} (SKU {sku}): la oficina '{office_name}' no existe")
                continue
        description = str(row.get("description", "") or "").strip()
        category = str(row.get("category", "") or "").strip()
        currency = normalize_currency(row.get("currency", "ARS"))

        exists = db.execute("SELECT 1 FROM products WHERE sku = ?", (sku,)).fetchone()
        if exists:
            db.execute(
                "UPDATE products SET name=?, description=?, category=?, condition=?, currency=?, price=?, price_wholesale=?, min_stock=?, updated_at=? WHERE sku=?",
                (name, description, category, condition, currency, price, price_wholesale, min_stock, now, sku),
            )
            current = stk.level(db, sku, office_id)
            if quantity != current:
                stk.adjust(db, sku, office_id, quantity - current, now)
                stk.record_movement(db, sku, office_id, quantity - current, "ajuste_inventario", "Importacion de stock", "", None, now, auth.actor())
            updated += 1
        else:
            db.execute(
                "INSERT INTO products (sku, name, description, category, condition, currency, price, price_wholesale, quantity, min_stock, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
                (sku, name, description, category, condition, currency, price, price_wholesale, min_stock, now),
            )
            if quantity:
                stk.adjust(db, sku, office_id, quantity, now)
                stk.record_movement(db, sku, office_id, quantity, "stock_inicial", "Importacion de stock", "", None, now, auth.actor())
            created += 1

    db.commit()
    auth.audit("productos_importados", "product", "", f"{created} nuevos, {updated} actualizados, {len(errors)} errores")
    return jsonify({"created": created, "updated": updated, "errors": errors})


@bp.route("/api/products/<sku>", methods=["DELETE"])
def delete_product(sku):
    db = get_db()
    old = db.execute("SELECT * FROM products WHERE sku = ?", (sku,)).fetchone()
    try:
        db.execute("DELETE FROM stock_levels WHERE sku = ?", (sku,))
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
