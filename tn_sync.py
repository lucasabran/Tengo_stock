"""Ventas de Tienda Nube -> Tengo Stock.

Cada pedido PAGADO de la tienda se registra como una venta del canal "Tienda Nube": descuenta el
stock de la oficina elegida, crea (o reutiliza) al cliente y queda vinculado al pedido para no
cargarlo dos veces.

Reglas de seguridad (no se toca el stock "a ciegas"):
- Solo se importan pedidos pagados DESPUES de la fecha de activacion (`tn_since`). Lo anterior se
  ignora, porque ese stock ya se descontó a mano.
- Un pedido se importa completo o no se importa: si un producto no se encuentra por SKU, o no hay
  stock, el pedido queda en "para revisar" con el motivo y se reintenta solo cuando se arregla.
- Si un pedido ya importado se cancela o reembolsa en Tienda Nube, NO se deshace solo: se marca
  para que una persona decida (devolucion o eliminar la venta).

Configuracion en el servidor (variables de entorno, nunca en el codigo):
  TN_STORE_ID, TN_ACCESS_TOKEN  (y opcional TN_CONTACT para el User-Agent que pide la API)
"""
import json
import os
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import stock as stk
from db import DB_PATH, now_iso

CHANNEL_NAME = "Tienda Nube"
WARRANTY = {"G1": "12 meses", "G2": "24 meses", "G3": "36 meses", "G5": "60 meses"}
_WARRANTY_RE = re.compile(r"^(.+)-(G[1-9]\d*)$", re.IGNORECASE)
_SENSITIVE = ("client_details", "payment_details", "token")
SYNC_EVERY_SECONDS = 600
OVERLAP = timedelta(hours=2)
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------------
def ensure_schema(db):
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS tn_orders (
            tn_id INTEGER PRIMARY KEY,
            number INTEGER,
            status TEXT NOT NULL,              -- importado | revisar | ignorado
            sale_id INTEGER,
            reason TEXT DEFAULT '',            -- por que quedo para revisar / se ignoro
            flag TEXT DEFAULT '',              -- aviso sobre un pedido ya importado (cancelado, reembolsado)
            customer TEXT DEFAULT '',
            total REAL DEFAULT 0,
            paid_at TEXT DEFAULT '',
            tn_status TEXT DEFAULT '',
            payment_status TEXT DEFAULT '',
            payload TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS tn_sku_map (
            tn_sku TEXT PRIMARY KEY COLLATE NOCASE,
            sku TEXT NOT NULL
        )
        """
    )


def connect():
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def get_setting(db, key, default=""):
    row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(db, key, value):
    db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )


def _audit(db, action, entity_id, detail):
    db.execute(
        "INSERT INTO audit_log (user_id, username, action, entity, entity_id, detail, ip, created_at) "
        "VALUES (NULL, 'tienda-nube', ?, 'tn_order', ?, ?, '', ?)",
        (action, str(entity_id), str(detail)[:500], now_iso()),
    )


def configured():
    return bool(os.environ.get("TN_STORE_ID") and os.environ.get("TN_ACCESS_TOKEN"))


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def parse_dt(value):
    """Fecha de la API (ej. 2026-11-05T14:20:11+0000) o ISO propio -> datetime con zona, o None."""
    if not value:
        return None
    text = str(value).strip()
    text = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", text)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def to_server_naive(dt):
    """Pasa a la hora del servidor sin zona, igual que now_iso(), para que las ventas queden coherentes."""
    return dt.astimezone().replace(tzinfo=None).isoformat(timespec="seconds")


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _clean_order(order):
    return {k: v for k, v in order.items() if k not in _SENSITIVE}


# ---------------------------------------------------------------------------
# API de Tienda Nube
# ---------------------------------------------------------------------------
def _api_get(path):
    base = f"https://api.tiendanube.com/v1/{os.environ['TN_STORE_ID']}"
    headers = {
        "Authentication": f"bearer {os.environ['TN_ACCESS_TOKEN']}",
        "User-Agent": f"TengoStockSync ({os.environ.get('TN_CONTACT', 'tengostockarg.com.ar')})",
        "Content-Type": "application/json",
    }
    for attempt in range(5):
        req = urllib.request.Request(base + path, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                text = resp.read().decode()
                return json.loads(text) if text else []
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return []
            if exc.code == 429 or exc.code >= 500:
                time.sleep(2 * (attempt + 1))
                continue
            raise RuntimeError(f"Tienda Nube respondio {exc.code}: {exc.read().decode()[:200]}")
        except urllib.error.URLError:
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("No se pudo conectar con Tienda Nube (demasiados reintentos)")


def fetch_orders(updated_min):
    """Pedidos modificados desde `updated_min` (datetime con zona)."""
    page = 1
    stamp = updated_min.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000")
    while page <= 60:
        query = urllib.parse.urlencode({"per_page": 200, "page": page, "updated_at_min": stamp})
        batch = _api_get(f"/orders?{query}")
        if not batch:
            return
        yield from batch
        if len(batch) < 200:
            return
        page += 1
        time.sleep(0.6)


# ---------------------------------------------------------------------------
# Productos y clientes
# ---------------------------------------------------------------------------
def _product_exists(db, sku):
    return db.execute("SELECT sku FROM products WHERE sku = ?", (sku,)).fetchone() is not None


def line_key(item):
    """Identificador del producto en la tienda: su SKU o, si no tiene, 'id:<product_id>'."""
    sku = (item.get("sku") or "").strip()
    if sku:
        return sku
    return f"id:{item['product_id']}" if item.get("product_id") else ""


def resolve_sku(db, tn_sku):
    """(sku propio, garantia o '') para el SKU que trae el pedido; (None, '') si no se encuentra.
    Las variantes de garantia de la tienda (ABC-G2) se vuelven al producto base (ABC).
    Un producto de la tienda sin SKU se identifica como 'id:<product_id>' y solo se resuelve por asociacion manual."""
    raw = (tn_sku or "").strip()
    if not raw:
        return None, ""
    if raw.startswith("id:"):
        mapped = db.execute("SELECT sku FROM tn_sku_map WHERE tn_sku = ?", (raw,)).fetchone()
        return (mapped[0], "") if mapped and _product_exists(db, mapped[0]) else (None, "")
    candidates = [(raw, "")]
    match = _WARRANTY_RE.match(raw)
    if match:
        candidates.append((match.group(1), WARRANTY.get(match.group(2).upper(), match.group(2).upper())))
    for code, warranty in candidates:
        mapped = db.execute("SELECT sku FROM tn_sku_map WHERE tn_sku = ?", (code,)).fetchone()
        if mapped and _product_exists(db, mapped[0]):
            return mapped[0], warranty
        row = db.execute("SELECT sku FROM products WHERE sku = ? COLLATE NOCASE", (code,)).fetchone()
        if row:
            return row[0], warranty
    return None, ""


def _customer_for(db, order, now):
    cust = order.get("customer") or {}
    email = (order.get("contact_email") or cust.get("email") or "").strip().lower()
    if email:
        row = db.execute("SELECT id FROM customers WHERE lower(email) = ? ORDER BY id LIMIT 1", (email,)).fetchone()
        if row:
            return row[0]
    name = (order.get("contact_name") or cust.get("name") or email or "Cliente Tienda Nube").strip()
    phone = (order.get("contact_phone") or cust.get("phone") or "").strip()
    doc = str(order.get("contact_identification") or cust.get("identification") or "").strip()
    addr = order.get("shipping_address") or {}
    street = " ".join(str(x) for x in (addr.get("address"), addr.get("number"), addr.get("floor")) if x)
    cur = db.execute(
        "INSERT INTO customers (name, phone, email, doc_number, note, created_at, updated_at, address, city, province, customer_type) "
        "VALUES (?, ?, ?, ?, 'Creado desde Tienda Nube', ?, ?, ?, ?, ?, 'minorista')",
        (name, phone, email, doc, now, now, street, addr.get("city") or addr.get("locality") or "", addr.get("province") or ""),
    )
    return cur.lastrowid


def _channel_id(db, now):
    db.execute(
        "INSERT OR IGNORE INTO channels (name, type, active, created_at) VALUES (?, 'tiendanube', 1, ?)",
        (CHANNEL_NAME, now),
    )
    return db.execute("SELECT id FROM channels WHERE name = ?", (CHANNEL_NAME,)).fetchone()[0]


def _office_id(db):
    value = get_setting(db, "tn_office_id", "")
    if value:
        row = db.execute("SELECT id FROM offices WHERE id = ?", (value,)).fetchone()
        if row:
            return row[0]
    row = db.execute("SELECT id FROM offices WHERE active = 1 ORDER BY id LIMIT 1").fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Importacion de un pedido
# ---------------------------------------------------------------------------
def _upsert_order(db, order, status, reason="", sale_id=None, flag=None):
    now = now_iso()
    cust = order.get("customer") or {}
    customer = order.get("contact_name") or cust.get("name") or ""
    existing = db.execute("SELECT flag FROM tn_orders WHERE tn_id = ?", (order["id"],)).fetchone()
    flag_value = flag if flag is not None else (existing["flag"] if existing else "")
    db.execute(
        """
        INSERT INTO tn_orders (tn_id, number, status, sale_id, reason, flag, customer, total, paid_at, tn_status,
                               payment_status, payload, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(tn_id) DO UPDATE SET status = excluded.status, sale_id = COALESCE(excluded.sale_id, tn_orders.sale_id),
            reason = excluded.reason, flag = excluded.flag, customer = excluded.customer, total = excluded.total,
            paid_at = excluded.paid_at, tn_status = excluded.tn_status, payment_status = excluded.payment_status,
            payload = excluded.payload, updated_at = excluded.updated_at
        """,
        (
            order["id"], order.get("number"), status, sale_id, reason, flag_value, customer, _num(order.get("total")),
            order.get("paid_at") or "", order.get("status") or "", order.get("payment_status") or "",
            json.dumps(_clean_order(order), ensure_ascii=False), now, now,
        ),
    )


def import_order(db, order):
    """Intenta registrar la venta de un pedido pagado. Devuelve ('importado'|'revisar', texto)."""
    now = now_iso()
    office_id = _office_id(db)
    if not office_id:
        _upsert_order(db, order, "revisar", "No hay ninguna oficina activa para descontar el stock")
        db.commit()
        return "revisar", "sin oficina"
    office_name = db.execute("SELECT name FROM offices WHERE id = ?", (office_id,)).fetchone()["name"]

    problems, lines, needed, warranties = [], [], {}, []
    for item in order.get("products") or []:
        tn_sku = line_key(item)
        name = item.get("name") or tn_sku or "producto"
        if isinstance(name, dict):
            name = name.get("es") or next(iter(name.values()), "producto")
        try:
            qty = int(float(item.get("quantity") or 0))
        except (TypeError, ValueError):
            qty = 0
        if qty <= 0:
            problems.append(f"{name}: cantidad invalida")
            continue
        if not tn_sku:
            problems.append(f"{name}: el producto de la tienda no tiene SKU ni ID")
            continue
        sku, warranty = resolve_sku(db, tn_sku)
        if not sku:
            if tn_sku.startswith("id:"):
                problems.append(f"{name}: el producto de la tienda no tiene SKU, asocialo una vez a un producto del sistema")
            else:
                problems.append(f"SKU {tn_sku} ({name}): no existe en el sistema")
            continue
        needed[sku] = needed.get(sku, 0) + qty
        price = _num(item.get("price"))
        lines.append({"sku": sku, "qty": qty, "price": price})
        if warranty:
            warranties.append(f"{sku} con garantia extendida de {warranty}")

    for sku, qty in needed.items():
        available = stk.level(db, sku, office_id)
        if available < qty:
            problems.append(f"{sku}: en {office_name} hay {available} y el pedido pide {qty}")

    if not lines and not problems:
        problems.append("El pedido no tiene productos")
    if problems:
        _upsert_order(db, order, "revisar", "; ".join(problems))
        db.commit()
        return "revisar", "; ".join(problems)

    names = {r["sku"]: r["name"] for r in db.execute(
        f"SELECT sku, name FROM products WHERE sku IN ({','.join('?' for _ in needed)})", list(needed)).fetchall()}
    subtotal = round(sum(l["price"] * l["qty"] for l in lines), 2)
    shipping = _num(order.get("shipping_cost_customer"))
    net = _num(order.get("total")) - shipping
    discount = max(0.0, round(subtotal - net, 2))
    total = round(subtotal - discount, 2)
    paid = parse_dt(order.get("paid_at")) or datetime.now(timezone.utc)
    created_at = to_server_naive(paid)
    number = order.get("number") or order["id"]
    note_parts = [f"Pedido Tienda Nube #{number}"]
    if shipping:
        note_parts.append(f"envio cobrado ${shipping:,.2f}")
    coupons = ",".join(c.get("code", "") for c in (order.get("coupon") or []) if isinstance(c, dict) and c.get("code"))
    if coupons:
        note_parts.append(f"cupon {coupons}")
    note_parts.extend(warranties)
    note = " - ".join(note_parts)

    try:
        customer_id = _customer_for(db, order, now)
        channel_id = _channel_id(db, now)
        cur = db.execute(
            "INSERT INTO sales (channel_id, customer_id, status, subtotal, discount, total, payment_method, currency, note, "
            "created_at, created_by, office_id, sale_type) VALUES (?, ?, 'completed', ?, ?, ?, ?, 'ARS', ?, ?, 'tienda-nube', ?, 'minorista')",
            (channel_id, customer_id, subtotal, discount, total, order.get("gateway_name") or "Tienda Nube", note,
             created_at, office_id),
        )
        sale_id = cur.lastrowid
        for line in lines:
            if not stk.adjust(db, line["sku"], office_id, -line["qty"], now):
                raise ValueError(f"{line['sku']}: sin stock suficiente en {office_name} (venta concurrente)")
            db.execute(
                "INSERT INTO sale_items (sale_id, sku, product_name, unit_price, quantity, line_total) VALUES (?, ?, ?, ?, ?, ?)",
                (sale_id, line["sku"], names.get(line["sku"], line["sku"]), line["price"], line["qty"],
                 round(line["price"] * line["qty"], 2)),
            )
            stk.record_movement(db, line["sku"], office_id, -line["qty"], "venta", f"Tienda Nube #{number}", "sale",
                                sale_id, now, "tienda-nube")
        _upsert_order(db, order, "importado", "", sale_id)
        _audit(db, "venta_tienda_nube", order["id"], f"#{number} -> V-{sale_id:06d} total {total:,.2f} ({office_name})")
        db.commit()
    except Exception as exc:  # no dejar nada a medias
        db.rollback()
        _upsert_order(db, order, "revisar", f"No se pudo registrar: {exc}")
        db.commit()
        return "revisar", str(exc)
    return "importado", f"V-{sale_id:06d}"


def _flag_text(order):
    status = order.get("status")
    payment = order.get("payment_status")
    if status == "cancelled":
        return "Pedido CANCELADO en Tienda Nube"
    if payment in ("refunded", "voided"):
        return "Pago reembolsado o anulado en Tienda Nube"
    return ""


def handle_order(db, order, since, counters):
    """Decide que hacer con un pedido que llego de la API (o de un reintento)."""
    tn_id = order["id"]
    existing = db.execute("SELECT status, flag, reason FROM tn_orders WHERE tn_id = ?", (tn_id,)).fetchone()
    flag = _flag_text(order)

    if existing and existing["status"] == "importado":
        # reason = 'aviso visto' lo deja la persona al tocar "Ya lo resolvi": no volver a avisar
        if flag and not existing["flag"] and existing["reason"] != "aviso visto":
            sale = db.execute("SELECT sale_id FROM tn_orders WHERE tn_id = ?", (tn_id,)).fetchone()["sale_id"]
            _upsert_order(db, order, "importado", "", None, f"{flag}: revisa la venta V-{sale:06d} (devolucion o eliminar)")
            _audit(db, "pedido_tienda_nube_cancelado", tn_id, flag)
            db.commit()
            counters["flagged"] += 1
        return
    if existing and existing["status"] == "ignorado":
        return
    if flag:
        if existing:  # estaba para revisar y se cancelo: ya no hay nada que importar
            _upsert_order(db, order, "ignorado", f"{flag}; no se importo")
            db.commit()
        return
    if order.get("payment_status") != "paid":
        return
    paid = parse_dt(order.get("paid_at"))
    if paid is None or paid < since:
        return
    status, _ = import_order(db, order)
    counters["imported" if status == "importado" else "review"] += 1


def retry_review(db, counters=None, skip=()):
    """Reintenta los pedidos que quedaron para revisar (despues de asociar un SKU, cargar stock, etc.)."""
    counters = counters if counters is not None else {"imported": 0, "review": 0, "flagged": 0}
    for row in db.execute("SELECT tn_id, payload FROM tn_orders WHERE status = 'revisar' ORDER BY tn_id").fetchall():
        if row["tn_id"] in skip:
            continue
        try:
            order = json.loads(row["payload"])
        except (TypeError, ValueError):
            continue
        status, _ = import_order(db, order)
        counters["imported" if status == "importado" else "review"] += 1
    return counters


# ---------------------------------------------------------------------------
# Corrida completa
# ---------------------------------------------------------------------------
def status_summary(db):
    ensure_schema(db)
    counts = {r["status"]: r["n"] for r in db.execute("SELECT status, COUNT(*) AS n FROM tn_orders GROUP BY status")}
    return {
        "configured": configured(),
        "enabled": get_setting(db, "tn_enabled") == "1",
        "since": get_setting(db, "tn_since"),
        "office_id": int(_office_id(db) or 0) or None,
        "last_sync": get_setting(db, "tn_last_sync"),
        "last_error": get_setting(db, "tn_last_error"),
        "imported": counts.get("importado", 0),
        "review": counts.get("revisar", 0),
        "ignored": counts.get("ignorado", 0),
        "flagged": db.execute("SELECT COUNT(*) FROM tn_orders WHERE flag != ''").fetchone()[0],
    }


def run_sync():
    """Trae los pedidos nuevos y los registra. Seguro de llamar desde cualquier hilo (uno a la vez)."""
    if not _lock.acquire(blocking=False):
        return {"busy": True}
    db = None
    try:
        db = connect()
        ensure_schema(db)
        if get_setting(db, "tn_enabled") != "1":
            return {"disabled": True}
        if not configured():
            msg = "Faltan las variables TN_STORE_ID y TN_ACCESS_TOKEN en el servidor"
            set_setting(db, "tn_last_error", msg)
            db.commit()
            return {"error": msg}
        since = parse_dt(get_setting(db, "tn_since")) or datetime.now(timezone.utc)
        started = datetime.now(timezone.utc)
        last = parse_dt(get_setting(db, "tn_last_sync_utc"))
        updated_min = (last - OVERLAP) if last else (since - timedelta(days=1))
        counters = {"imported": 0, "review": 0, "flagged": 0}
        seen = set()
        for order in fetch_orders(updated_min):
            seen.add(order["id"])
            handle_order(db, order, since, counters)
        retry_review(db, counters, skip=seen)
        set_setting(db, "tn_last_sync_utc", started.isoformat(timespec="seconds"))
        set_setting(db, "tn_last_sync", now_iso())
        set_setting(db, "tn_last_error", "")
        db.commit()
        return counters
    except Exception as exc:
        if db is not None:
            try:
                db.rollback()
                set_setting(db, "tn_last_error", f"{now_iso()}: {exc}"[:400])
                db.commit()
            except sqlite3.Error:
                pass
        return {"error": str(exc)}
    finally:
        if db is not None:
            db.close()
        _lock.release()
