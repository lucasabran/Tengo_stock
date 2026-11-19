"""Catalogo de Tienda Nube -> Tengo Stock.

Para que las ventas de la tienda entren solas, el sistema tiene que conocer los productos de la tienda.
Este modulo:
1. Trae el catalogo de la tienda y lo resume en UNA entrada por SKU (las variantes de garantia se ignoran;
   varios colores con el mismo SKU suman su stock; un producto sin SKU se identifica por su ID).
2. Arma un plan SIN tocar nada: que productos ya existen en el sistema, cuales parecen ser el mismo producto
   con otro codigo (sugerencia por nombre, para que una persona confirme) y cuales faltan.
3. Aplica solo lo que la persona aprobo: crear productos nuevos (con el stock de la tienda, opcional) o
   asociar un producto de la tienda a uno que ya existe (sin tocar su stock).
"""
import html
import json
import re
import threading
import unicodedata

import stock as stk
import tn_sync
from db import now_iso

_STOP = {"de", "la", "el", "los", "las", "con", "para", "y", "en", "del", "por", "un", "una", "the", "and", "cm", "mm"}
_WARRANTY_ATTR = "garant"
SUGGEST_MIN_CONTAINMENT = 0.8
_state = {"running": False, "error": ""}
_state_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Esquema y estado
# ---------------------------------------------------------------------------
def ensure_schema(db):
    db.execute("CREATE TABLE IF NOT EXISTS tn_catalog (key TEXT PRIMARY KEY, data TEXT NOT NULL)")


def fetch_state(db):
    return {"running": _state["running"], "error": _state["error"], "fetched_at": tn_sync.get_setting(db, "tn_catalog_fetched")}


# ---------------------------------------------------------------------------
# Lectura del catalogo de la tienda
# ---------------------------------------------------------------------------
def txt(value):
    if isinstance(value, dict):
        return str(value.get("es") or next(iter(value.values()), "") or "")
    return str(value or "")


def _plain(text):
    text = re.sub(r"<[^>]+>", " ", txt(text))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _fold(text):
    return "".join(c for c in unicodedata.normalize("NFD", str(text)) if unicodedata.category(c) != "Mn").lower()


def _is_warranty_variant(product, variant, base_skus):
    attrs = [_fold(txt(a)) for a in product.get("attributes") or []]
    values = variant.get("values") or []
    for i, attr in enumerate(attrs):
        if _WARRANTY_ATTR in attr and i < len(values):
            return "sin extension" not in _fold(txt(values[i]))
    sku = (variant.get("sku") or "").strip()
    match = re.match(r"^(.+)-G[1-9]\d*$", sku, re.IGNORECASE)
    return bool(match and match.group(1).strip() in base_skus)


def entries_from_products(products):
    """Devuelve (entradas, omitidos): una entrada por SKU de la tienda. Omite productos no publicados."""
    entries, skipped = [], 0
    for product in products:
        if not product.get("published", True):
            skipped += 1
            continue
        variants = product.get("variants") or []
        base_skus = {(v.get("sku") or "").strip() for v in variants if (v.get("sku") or "").strip()}
        base = [v for v in variants if not _is_warranty_variant(product, v, base_skus)] or variants[:1]
        groups = {}
        for v in base:
            sku = (v.get("sku") or "").strip()
            key = sku or f"id:{product.get('id')}"
            groups.setdefault(key, []).append(v)
        categories = product.get("categories") or []
        category = txt(categories[0].get("name")) if categories and isinstance(categories[0], dict) else ""
        base_name = txt(product.get("name")).strip()
        for key, vs in groups.items():
            stocks = [v.get("stock") for v in vs]
            unlimited = any(s is None for s in stocks)
            prices = [float(v["price"]) for v in vs if v.get("price") not in (None, "")]
            name = base_name
            if len(groups) > 1:  # un producto con varios SKU (talles, modelos): distinguirlos por la variante
                extra = [txt(x) for x in (vs[0].get("values") or []) if "sin extension" not in _fold(txt(x))]
                name = f"{base_name} - {' / '.join(extra)}" if extra else base_name
            entries.append({
                "key": key,
                "tn_sku": "" if key.startswith("id:") else key,
                "product_id": product.get("id"),
                "name": name[:200],
                "category": category,
                "price": prices[0] if prices else 0,
                "stock": 0 if unlimited else sum(max(int(s or 0), 0) for s in stocks),
                "unlimited_stock": unlimited,
                "url": product.get("canonical_url") or "",
                "description": _plain(product.get("description"))[:600],
                "shared_sku": False,
            })
    # Un mismo SKU en DOS productos distintos de la tienda es un error de carga de la tienda: el sistema no podria
    # distinguirlos. Se deja una sola entrada y se marca para no crearla sola.
    seen = {}
    unique = []
    for e in entries:
        first = seen.get(e["key"])
        if first is None:
            seen[e["key"]] = e
            unique.append(e)
        elif first["product_id"] != e["product_id"]:
            first["shared_sku"] = True
            first["shared_with"] = f"{first.get('shared_with', '')} | {e['name']}".strip(" |")[:200]
    return unique, skipped


def fetch_catalog_from_api():
    """Descarga todos los productos publicados de la tienda (varias paginas)."""
    import time
    import urllib.parse

    page, out = 1, []
    fields = "id,name,published,canonical_url,categories,description,attributes,variants"
    while page <= 60:
        query = urllib.parse.urlencode({"per_page": 200, "page": page, "fields": fields})
        batch = tn_sync._api_get(f"/products?{query}")
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 200:
            break
        page += 1
        time.sleep(0.6)
    return out


def store_entries(db, entries, skipped):
    ensure_schema(db)
    db.execute("DELETE FROM tn_catalog")
    db.executemany("INSERT OR REPLACE INTO tn_catalog (key, data) VALUES (?, ?)", [(e["key"], json.dumps(e, ensure_ascii=False)) for e in entries])
    tn_sync.set_setting(db, "tn_catalog_fetched", now_iso())
    tn_sync.set_setting(db, "tn_catalog_skipped", skipped)
    db.commit()


def run_fetch():
    """Descarga y guarda el catalogo (pensado para correr en un hilo)."""
    with _state_lock:
        if _state["running"]:
            return
        _state["running"], _state["error"] = True, ""
    db = None
    try:
        db = tn_sync.connect()
        entries, skipped = entries_from_products(fetch_catalog_from_api())
        store_entries(db, entries, skipped)
    except Exception as exc:
        _state["error"] = str(exc)[:300]
    finally:
        _state["running"] = False
        if db is not None:
            db.close()


def load_entries(db):
    ensure_schema(db)
    return [json.loads(r[0]) for r in db.execute("SELECT data FROM tn_catalog ORDER BY key")]


# ---------------------------------------------------------------------------
# Plan: que existe, que se parece, que falta
# ---------------------------------------------------------------------------
def tokens(name):
    return {t for t in re.findall(r"[a-z0-9]+", _fold(name)) if t not in _STOP and len(t) > 1}


def _score(sys_tokens, tn_tokens):
    """Que tanto del nombre del sistema esta contenido en el de la tienda (None si no parece el mismo)."""
    if len(sys_tokens) < 2:
        return None
    # sin un codigo de modelo (algo con numeros) el nombre es ambiguo: "parlante joog" calza con muchos productos distintos
    if not any(any(ch.isdigit() for ch in t) for t in sys_tokens):
        return None
    common = sys_tokens & tn_tokens
    containment = len(common) / len(sys_tokens)
    if containment < SUGGEST_MIN_CONTAINMENT:
        return None
    # los codigos de modelo (tokens con numeros) tienen que estar si o si
    if any(any(ch.isdigit() for ch in t) and t not in tn_tokens for t in sys_tokens):
        return None
    return containment * 0.7 + (len(common) / len(sys_tokens | tn_tokens)) * 0.3


def build_plan(db, entries):
    system = [(r["sku"], r["name"], tokens(r["name"])) for r in db.execute("SELECT sku, name FROM products")]
    existing, suggested, new = [], [], []
    for e in entries:
        sku, _ = tn_sync.resolve_sku(db, e["key"])
        if sku:
            existing.append({**e, "system_sku": sku})
            continue
        tn_tokens = tokens(e["name"])
        best, best_score = None, 0.0
        for s_sku, s_name, s_tokens in system:
            score = _score(s_tokens, tn_tokens)
            if score is not None and score > best_score:
                best, best_score = (s_sku, s_name), score
        if best:
            suggested.append({**e, "suggestion": {"sku": best[0], "name": best[1], "score": round(best_score, 2)}})
        else:
            new.append(e)
    return {"existing": existing, "suggested": suggested, "new": new}


# ---------------------------------------------------------------------------
# Aplicar lo que la persona aprobo
# ---------------------------------------------------------------------------
def _safe_sku(sku):
    return re.sub(r"[/\\?#%]", "-", sku).strip()[:80]


def apply_plan(db, create_keys, maps, office_id, load_stock, actor="tienda-nube"):
    """Crea productos y asocia SKUs. Todo en una transaccion. Devuelve un resumen con lo omitido y por que."""
    entries = {e["key"]: e for e in load_entries(db)}
    now = now_iso()
    result = {"created": 0, "mapped": 0, "stock_units": 0, "skipped": []}
    try:
        for key in create_keys:
            e = entries.get(key)
            if not e:
                result["skipped"].append({"key": key, "reason": "no esta en el catalogo traido (volve a traerlo)"})
                continue
            if tn_sync.resolve_sku(db, key)[0]:
                result["skipped"].append({"key": key, "reason": "ya existe en el sistema"})
                continue
            if e.get("shared_sku"):
                result["skipped"].append({"key": key, "reason": "el SKU esta repetido en 2 productos de la tienda: corregilo en Tienda Nube primero"})
                continue
            sku = _safe_sku(e["tn_sku"]) if e["tn_sku"] else f"TN-{e['product_id']}"
            if not sku or db.execute("SELECT 1 FROM products WHERE sku = ? COLLATE NOCASE", (sku,)).fetchone():
                result["skipped"].append({"key": key, "reason": f"el SKU {sku or '(vacio)'} ya lo usa otro producto: asocialo a mano"})
                continue
            db.execute(
                "INSERT INTO products (sku, name, description, category, condition, currency, price, price_wholesale, cost_price, "
                "supplier, product_url, quantity, min_stock, updated_at) VALUES (?, ?, ?, ?, 'Nuevo', 'ARS', ?, 0, 0, '', ?, 0, 0, ?)",
                (sku, e["name"], e["description"], e["category"] or "General", e["price"], e["url"][:500], now),
            )
            qty = int(e["stock"]) if load_stock and not e["unlimited_stock"] else 0
            if qty > 0:
                stk.adjust(db, sku, office_id, qty, now)
                stk.record_movement(db, sku, office_id, qty, "stock_inicial", "Catalogo de Tienda Nube", "", None, now, actor)
                result["stock_units"] += qty
            if sku != key:  # el SKU del sistema no es igual al de la tienda: dejar la asociacion
                db.execute("INSERT INTO tn_sku_map (tn_sku, sku) VALUES (?, ?) ON CONFLICT(tn_sku) DO UPDATE SET sku = excluded.sku", (key, sku))
            result["created"] += 1
        for m in maps:
            key, sku = str(m.get("key", "")), str(m.get("sku", ""))
            if key not in entries:
                result["skipped"].append({"key": key, "reason": "no esta en el catalogo traido"})
                continue
            if not db.execute("SELECT 1 FROM products WHERE sku = ?", (sku,)).fetchone():
                result["skipped"].append({"key": key, "reason": f"el producto {sku} no existe"})
                continue
            db.execute("INSERT INTO tn_sku_map (tn_sku, sku) VALUES (?, ?) ON CONFLICT(tn_sku) DO UPDATE SET sku = excluded.sku", (key, sku))
            result["mapped"] += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    return result
