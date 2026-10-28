"""Stock por oficina.

Regla de oro: products.quantity siempre es la suma de stock_levels.quantity de ese producto
(el consolidado). Todo cambio de stock tiene que pasar por adjust() para mantener esa igualdad.
"""
from flask import g

from db import now_iso

CONDITIONS = ["Nuevo", "Usado", "Reacondicionado", "RMA"]
SALE_TYPES = ["minorista", "mayorista"]


def default_office_id(db):
    row = db.execute("SELECT id FROM offices WHERE active = 1 ORDER BY id LIMIT 1").fetchone()
    if row:
        return row["id"]
    row = db.execute("SELECT id FROM offices ORDER BY id LIMIT 1").fetchone()
    return row["id"] if row else None


def user_office_id():
    """Oficina fija del usuario actual, o None si puede operar en todas."""
    user = g.get("user")
    return user["office_id"] if user and user["office_id"] else None


def resolve_office(db, requested=None):
    """Devuelve (office_id, error). Un usuario con oficina asignada opera siempre en la suya."""
    fixed = user_office_id()
    if fixed:
        return fixed, None
    if requested in (None, "", "all"):
        return default_office_id(db), None
    try:
        office_id = int(requested)
    except (TypeError, ValueError):
        return None, "oficina invalida"
    row = db.execute("SELECT id, active FROM offices WHERE id = ?", (office_id,)).fetchone()
    if not row:
        return None, "oficina inexistente"
    return row["id"], None


def office_by_name(db, name):
    row = db.execute("SELECT id FROM offices WHERE lower(name) = lower(?)", (str(name).strip(),)).fetchone()
    return row["id"] if row else None


def level(db, sku, office_id):
    row = db.execute("SELECT quantity FROM stock_levels WHERE sku = ? AND office_id = ?", (sku, office_id)).fetchone()
    return row["quantity"] if row else 0


def adjust(db, sku, office_id, delta, now=None):
    """Suma delta al stock de la oficina y al consolidado. Un descuento nunca deja la oficina en negativo.
    Devuelve False (sin cambiar nada) si no alcanza el stock."""
    now = now or now_iso()
    if delta == 0:
        return True
    db.execute("INSERT OR IGNORE INTO stock_levels (sku, office_id, quantity) VALUES (?, ?, 0)", (sku, office_id))
    if delta < 0:
        cur = db.execute(
            "UPDATE stock_levels SET quantity = quantity + ? WHERE sku = ? AND office_id = ? AND quantity >= ?",
            (delta, sku, office_id, -delta),
        )
        if cur.rowcount == 0:
            return False
    else:
        db.execute("UPDATE stock_levels SET quantity = quantity + ? WHERE sku = ? AND office_id = ?", (delta, sku, office_id))
    db.execute("UPDATE products SET quantity = quantity + ?, updated_at = ? WHERE sku = ?", (delta, now, sku))
    return True


def record_movement(db, sku, office_id, change, reason, note="", ref_type="", ref_id=None, created_at=None, created_by=""):
    db.execute(
        "INSERT INTO stock_movements (sku, change_qty, reason, note, reference_type, reference_id, created_at, created_by, office_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (sku, change, reason, note, ref_type, ref_id, created_at or now_iso(), created_by, office_id),
    )


def breakdown(db, skus):
    """{sku: [{office_id, office_name, quantity}]} solo con oficinas que tienen stock distinto de 0."""
    if not skus:
        return {}
    marks = ",".join("?" for _ in skus)
    rows = db.execute(
        f"SELECT sl.sku, sl.office_id, o.name, sl.quantity FROM stock_levels sl JOIN offices o ON o.id = sl.office_id "
        f"WHERE sl.sku IN ({marks}) AND sl.quantity != 0 ORDER BY o.id",
        list(skus),
    ).fetchall()
    result = {}
    for r in rows:
        result.setdefault(r["sku"], []).append({"office_id": r["office_id"], "office_name": r["name"], "quantity": r["quantity"]})
    return result


def check_consistency(db):
    """Devuelve la lista de SKUs donde el consolidado no coincide con la suma por oficina (para tests y mantenimiento)."""
    return db.execute(
        "SELECT p.sku, p.quantity AS total, COALESCE(SUM(sl.quantity), 0) AS by_office "
        "FROM products p LEFT JOIN stock_levels sl ON sl.sku = p.sku "
        "GROUP BY p.sku HAVING p.quantity != COALESCE(SUM(sl.quantity), 0)"
    ).fetchall()
