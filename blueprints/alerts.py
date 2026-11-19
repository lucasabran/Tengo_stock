"""Alertas de inventario y rentabilidad (inspirado en alertService / inventoryInconsistencyService /
catalogQualityService del sistema rodo-scraper) y configuracion de las reglas de margen."""
from collections import defaultdict

from flask import Blueprint, jsonify, render_template, request

import auth
import profitability
import stock as stk
import tn_sync
from db import get_db

bp = Blueprint("alerts", __name__)

MAX_ITEMS = 200
SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


@bp.route("/alertas")
def alertas_page():
    return render_template("alertas.html", active="alertas")


@bp.route("/api/alerts", methods=["GET"])
def list_alerts():
    db = get_db()
    costs = auth.has_any(("stock.costs",))
    cfg = profitability.load_config(db)
    products = db.execute("SELECT * FROM products ORDER BY sku COLLATE NOCASE").fetchall()

    groups = {}

    def add(key, title, severity, hint, product, detail=""):
        group = groups.setdefault(key, {"key": key, "title": title, "severity": severity, "hint": hint, "count": 0, "items": []})
        group["count"] += 1
        if len(group["items"]) < MAX_ITEMS:
            group["items"].append({"sku": product["sku"], "name": product["name"], "detail": detail})

    # Stock negativo por oficina e inconsistencias del consolidado
    by_sku = {p["sku"]: p for p in products}
    for r in db.execute(
        "SELECT sl.sku, sl.quantity, o.name FROM stock_levels sl JOIN offices o ON o.id = sl.office_id WHERE sl.quantity < 0"
    ).fetchall():
        if r["sku"] in by_sku:
            add("negative", "Stock negativo en una oficina", "critical",
                "Se vendio o transfirio mas de lo que habia. Revisa los movimientos y corregi la cantidad.",
                by_sku[r["sku"]], f"{r['name']}: {r['quantity']}")
    for r in stk.check_consistency(db):
        if r["sku"] in by_sku:
            add("inconsistent", "El consolidado no coincide con la suma de oficinas", "critical",
                "El total del producto no es la suma de sus oficinas. Edita la cantidad de una oficina para que se recalcule.",
                by_sku[r["sku"]], f"total {r['total']} / oficinas {r['by_office']}")

    seen_names = defaultdict(list)
    for p in products:
        qty = p["quantity"] or 0
        min_stock = p["min_stock"] or 0
        if min_stock > 0 and qty <= min_stock:
            add("low_stock", "Stock en el minimo o por debajo", "critical" if qty <= 0 else "warning",
                "Productos que llegaron al stock minimo que definiste. Conviene reponer.",
                p, f"hay {qty}, minimo {min_stock}")
        if (p["price"] or 0) <= 0:
            add("no_price", "Sin precio de venta", "warning", "No se puede vender bien un producto con precio 0.", p)
        wholesale = p["price_wholesale"] or 0
        if wholesale > 0 and (p["price"] or 0) > 0 and wholesale > p["price"]:
            add("wholesale_higher", "Precio mayorista mayor al minorista", "warning",
                "Casi seguro es un error de carga.", p, f"mayorista {wholesale:,.2f} > minorista {p['price']:,.2f}")

        if costs:
            analysis = profitability.analyze(p["cost_price"], p["price"], cfg, p["currency"])
            if (p["cost_price"] or 0) <= 0:
                add("no_cost", "Sin precio de costo", "info", "Sin costo no se puede calcular el margen.", p)
            elif analysis and analysis["is_negative"]:
                add("margin_negative", "No cubre el costo (ganancia negativa)", "critical",
                    "Con la comision y los costos configurados, cada venta pierde plata.",
                    p, f"ganancia {analysis['net_profit']:,.2f}; precio sugerido {analysis['suggested_price'] or '-'}")
            elif analysis and analysis["is_low"]:
                add("margin_low", f"Margen por debajo del minimo ({cfg['min_margin']:g}%)", "warning",
                    "Conviene revisar el precio.", p,
                    f"margen {analysis['margin_percent']}%; precio sugerido {analysis['suggested_price'] or '-'}")

        if not (p["photo"] or ""):
            add("no_photo", "Sin foto", "info", "Las publicaciones con foto venden mas.", p)
        if len((p["description"] or "").strip()) < 20:
            add("short_description", "Sin descripcion o muy corta", "info", "Menos de 20 caracteres.", p)
        if (p["category"] or "") in ("", "General"):
            add("no_category", "Sin categoria definida", "info", "Esta como General o vacia.", p)
        if not (p["supplier"] or ""):
            add("no_supplier", "Sin proveedor", "info", "", p)
        if not (p["product_url"] or ""):
            add("no_url", "Sin link de producto", "info", "", p)
        seen_names[(p["name"] or "").strip().casefold()].append(p)

    for plist in seen_names.values():
        if len(plist) > 1:
            for p in plist:
                others = ", ".join(x["sku"] for x in plist if x["sku"] != p["sku"])
                add("duplicate_name", "Nombre repetido en otro SKU", "info",
                    "Puede ser normal (por ejemplo Nuevo y Usado), pero a veces es un producto cargado dos veces.", p, f"tambien: {others}")

    # Pedidos de Tienda Nube que necesitan una persona (solo para quien administra esa integracion)
    if auth.has_any(("tiendanube.manage",)):
        tn_sync.ensure_schema(db)
        for r in db.execute("SELECT number, customer, reason FROM tn_orders WHERE status = 'revisar' ORDER BY tn_id DESC").fetchall():
            group = groups.setdefault("tn_review", {"key": "tn_review", "title": "Pedidos de Tienda Nube sin cargar", "severity": "critical",
                                                    "hint": "No se pudieron cargar solos. Resolvelos en la pestaña Tienda Nube.", "count": 0, "items": []})
            group["count"] += 1
            if len(group["items"]) < MAX_ITEMS:
                group["items"].append({"sku": f"#{r['number']}", "name": r["customer"] or "Pedido", "detail": r["reason"], "href": "/tienda-nube"})
        for r in db.execute("SELECT number, customer, flag FROM tn_orders WHERE flag != '' ORDER BY tn_id DESC").fetchall():
            group = groups.setdefault("tn_flag", {"key": "tn_flag", "title": "Pedidos de Tienda Nube cancelados despues de cargarse", "severity": "warning",
                                                  "hint": "La venta sigue registrada y el stock descontado: decidi si corresponde una devolucion.", "count": 0, "items": []})
            group["count"] += 1
            if len(group["items"]) < MAX_ITEMS:
                group["items"].append({"sku": f"#{r['number']}", "name": r["customer"] or "Pedido", "detail": r["flag"], "href": "/tienda-nube"})

    ordered = sorted(groups.values(), key=lambda g: (SEVERITY_ORDER[g["severity"]], -g["count"]))
    return jsonify({
        "total": sum(g["count"] for g in ordered),
        "critical": sum(g["count"] for g in ordered if g["severity"] == "critical"),
        "products": len(products),
        "groups": ordered,
    })


@bp.route("/api/pricing-config", methods=["GET"])
def get_pricing_config():
    return jsonify(profitability.load_config(get_db()))


@bp.route("/api/pricing-config", methods=["PUT"])
def update_pricing_config():
    data = request.get_json(force=True) or {}
    cfg, err = profitability.clean_config(data)
    if err:
        return jsonify({"error": err}), 400
    db = get_db()
    profitability.save_config(db, cfg)
    db.commit()
    auth.audit("reglas_rentabilidad", "settings", "pricing_config",
               f"comision {cfg['fee_percent']:g}%, objetivo {cfg['target_margin']:g}%, minimo {cfg['min_margin']:g}%")
    return jsonify(cfg)
