"""Pantalla y API de la sincronizacion de ventas de Tienda Nube (la logica esta en tn_sync.py)."""
import json
import threading
from datetime import datetime, timezone

from flask import Blueprint, jsonify, render_template, request

import auth
import stock as stk
import tn_catalog
import tn_sync
from db import get_db, now_iso

bp = Blueprint("tiendanube", __name__)


@bp.route("/tienda-nube")
def tn_page():
    return render_template("tiendanube.html", active="tiendanube")


def _order_dict(row, with_lines=False, db=None):
    d = {
        "tn_id": row["tn_id"],
        "number": row["number"],
        "status": row["status"],
        "sale_id": row["sale_id"],
        "sale_number": f"V-{row['sale_id']:06d}" if row["sale_id"] else "",
        "reason": row["reason"] or "",
        "flag": row["flag"] or "",
        "customer": row["customer"] or "",
        "total": row["total"],
        "paid_at": row["paid_at"] or "",
        "updated_at": row["updated_at"],
    }
    if with_lines:
        try:
            order = json.loads(row["payload"])
        except (TypeError, ValueError):
            order = {}
        lines = []
        for p in order.get("products") or []:
            name = p.get("name")
            if isinstance(name, dict):
                name = name.get("es") or next(iter(name.values()), "")
            tn_sku = tn_sync.line_key(p)
            resolved = bool(db is not None and tn_sync.resolve_sku(db, tn_sku)[0])
            lines.append({"tn_sku": tn_sku, "name": name or "", "quantity": p.get("quantity"), "price": p.get("price"), "resolved": resolved})
        d["lines"] = lines
    return d


@bp.route("/api/tiendanube/status", methods=["GET"])
def tn_status():
    db = get_db()
    tn_sync.ensure_schema(db)
    result = tn_sync.status_summary(db)
    result["review_orders"] = [
        _order_dict(r, True, db) for r in db.execute("SELECT * FROM tn_orders WHERE status = 'revisar' ORDER BY tn_id DESC LIMIT 100")
    ]
    result["flagged_orders"] = [
        _order_dict(r) for r in db.execute("SELECT * FROM tn_orders WHERE flag != '' ORDER BY tn_id DESC LIMIT 50")
    ]
    result["recent_orders"] = [
        _order_dict(r) for r in db.execute("SELECT * FROM tn_orders WHERE status = 'importado' ORDER BY updated_at DESC LIMIT 15")
    ]
    result["offices"] = [
        {"id": r["id"], "name": r["name"]} for r in db.execute("SELECT id, name FROM offices WHERE active = 1 ORDER BY id")
    ]
    return jsonify(result)


@bp.route("/api/tiendanube/config", methods=["POST"])
def tn_config():
    data = request.get_json(force=True) or {}
    db = get_db()
    tn_sync.ensure_schema(db)
    enabled = bool(data.get("enabled"))

    office_id = data.get("office_id")
    if office_id not in (None, ""):
        row = db.execute("SELECT id FROM offices WHERE id = ? AND active = 1", (office_id,)).fetchone()
        if not row:
            return jsonify({"error": "oficina invalida"}), 400
        tn_sync.set_setting(db, "tn_office_id", row["id"])

    if enabled:
        if not tn_sync.configured():
            return jsonify({"error": "Falta cargar TN_STORE_ID y TN_ACCESS_TOKEN en el servidor (Render > Environment)"}), 400
        since_raw = str(data.get("since") or "").strip()
        was_enabled = tn_sync.get_setting(db, "tn_enabled") == "1"
        if since_raw:
            since = tn_sync.parse_dt(since_raw)
            if since is None:
                return jsonify({"error": "fecha de inicio invalida"}), 400
            if len(since_raw) <= 10:  # solo fecha: desde las 00:00 de Argentina (UTC-3)
                since = datetime.fromisoformat(since_raw).replace(tzinfo=timezone.utc).replace(hour=3)
            tn_sync.set_setting(db, "tn_since", since.astimezone(timezone.utc).isoformat(timespec="seconds"))
            tn_sync.set_setting(db, "tn_last_sync_utc", "")
        elif not was_enabled or not tn_sync.get_setting(db, "tn_since"):
            tn_sync.set_setting(db, "tn_since", datetime.now(timezone.utc).isoformat(timespec="seconds"))
            tn_sync.set_setting(db, "tn_last_sync_utc", "")
        tn_sync.set_setting(db, "tn_enabled", "1")
    else:
        tn_sync.set_setting(db, "tn_enabled", "0")
    db.commit()
    auth.audit("tienda_nube_config", "settings", "tn", f"{'activada' if enabled else 'desactivada'}; desde {tn_sync.get_setting(db, 'tn_since')}")
    return jsonify(tn_sync.status_summary(db))


@bp.route("/api/tiendanube/sync", methods=["POST"])
def tn_sync_now():
    if not tn_tick_ok():
        return jsonify({"error": "La sincronizacion esta desactivada o falta configurar el servidor"}), 400
    threading.Thread(target=tn_sync.run_sync, daemon=True).start()
    return jsonify({"started": True}), 202


def tn_tick_ok():
    db = get_db()
    return tn_sync.get_setting(db, "tn_enabled") == "1" and tn_sync.configured()


@bp.route("/api/tiendanube/map", methods=["POST"])
def tn_map_sku():
    data = request.get_json(force=True) or {}
    tn_sku = str(data.get("tn_sku", "")).strip()
    sku = str(data.get("sku", "")).strip()
    if not tn_sku or not sku:
        return jsonify({"error": "falta el SKU de la tienda o el SKU del sistema"}), 400
    db = get_db()
    tn_sync.ensure_schema(db)
    product = db.execute("SELECT sku FROM products WHERE sku = ?", (sku,)).fetchone()
    if not product:
        return jsonify({"error": f"el SKU {sku} no existe en el sistema"}), 400
    db.execute(
        "INSERT INTO tn_sku_map (tn_sku, sku) VALUES (?, ?) ON CONFLICT(tn_sku) DO UPDATE SET sku = excluded.sku",
        (tn_sku, product["sku"]),
    )
    db.commit()
    auth.audit("tienda_nube_asociar_sku", "tn_sku", tn_sku, f"-> {product['sku']}")
    counters = tn_sync.retry_review(db)
    return jsonify({"ok": True, **counters})


@bp.route("/api/tiendanube/retry", methods=["POST"])
def tn_retry():
    db = get_db()
    tn_sync.ensure_schema(db)
    return jsonify({"ok": True, **tn_sync.retry_review(db)})


@bp.route("/api/tiendanube/orders/<int:tn_id>/ignore", methods=["POST"])
def tn_ignore(tn_id):
    db = get_db()
    row = db.execute("SELECT status FROM tn_orders WHERE tn_id = ?", (tn_id,)).fetchone()
    if not row or row["status"] != "revisar":
        return jsonify({"error": "pedido no encontrado o ya resuelto"}), 404
    data = request.get_json(silent=True) or {}
    reason = str(data.get("reason") or "Marcado como ya cargado a mano").strip()[:200]
    db.execute("UPDATE tn_orders SET status = 'ignorado', reason = ?, updated_at = ? WHERE tn_id = ?", (reason, now_iso(), tn_id))
    db.commit()
    auth.audit("tienda_nube_ignorar", "tn_order", tn_id, reason)
    return jsonify({"ok": True})


@bp.route("/api/tiendanube/orders/<int:tn_id>/ack", methods=["POST"])
def tn_ack(tn_id):
    db = get_db()
    cur = db.execute("UPDATE tn_orders SET flag = '', reason = 'aviso visto' WHERE tn_id = ? AND flag != ''", (tn_id,))
    db.commit()
    if cur.rowcount == 0:
        return jsonify({"error": "pedido no encontrado"}), 404
    auth.audit("tienda_nube_aviso_visto", "tn_order", tn_id, "")
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Catalogo de la tienda: traerlo, ver el plan y aplicar solo lo aprobado
# ---------------------------------------------------------------------------
def _slim(entry):
    keys = ("key", "tn_sku", "name", "category", "price", "stock", "unlimited_stock", "suggestion", "shared_sku", "shared_with")
    return {k: entry[k] for k in keys if k in entry}


@bp.route("/api/tiendanube/catalog", methods=["GET"])
def tn_catalog_get():
    db = get_db()
    entries = tn_catalog.load_entries(db)
    plan = tn_catalog.build_plan(db, entries) if entries else {"existing": [], "suggested": [], "new": []}
    return jsonify({
        **tn_catalog.fetch_state(db),
        "total": len(entries),
        "existing_count": len(plan["existing"]),
        "suggested": [_slim(e) for e in plan["suggested"]],
        "new": [_slim(e) for e in plan["new"]],
        "skipped_unpublished": int(tn_sync.get_setting(db, "tn_catalog_skipped", "0") or 0),
    })


@bp.route("/api/tiendanube/catalog/fetch", methods=["POST"])
def tn_catalog_fetch():
    if not tn_sync.configured():
        return jsonify({"error": "Falta cargar TN_STORE_ID y TN_ACCESS_TOKEN en el servidor (Render > Environment)"}), 400
    threading.Thread(target=tn_catalog.run_fetch, daemon=True).start()
    return jsonify({"started": True}), 202


@bp.route("/api/tiendanube/catalog/apply", methods=["POST"])
def tn_catalog_apply():
    if not auth.has_any(("stock.edit",)):
        return jsonify({"error": "Necesitas permiso para crear productos (stock.edit)"}), 403
    data = request.get_json(force=True) or {}
    create = [str(k) for k in (data.get("create") or [])]
    maps = [m for m in (data.get("maps") or []) if isinstance(m, dict)]
    if not create and not maps:
        return jsonify({"error": "No elegiste nada para aplicar"}), 400
    db = get_db()
    office_id, err = stk.resolve_office(db, data.get("office_id"))
    if err:
        return jsonify({"error": err}), 400
    result = tn_catalog.apply_plan(db, create, maps, office_id, bool(data.get("load_stock")), auth.actor())
    auth.audit("catalogo_tienda_nube", "catalogo", "", f"{result['created']} creados ({result['stock_units']} u.), {result['mapped']} asociados, {len(result['skipped'])} omitidos")
    result["orders"] = tn_sync.retry_review(db)  # los pedidos que esperaban estos productos se reintentan
    return jsonify(result)
