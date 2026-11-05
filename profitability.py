"""Rentabilidad por producto: ganancia neta, margen y precio sugerido.

Portado de la logica de utils/profitability.js del sistema rodo-scraper, adaptado a nuestro
modelo (el margen se calcula SOBRE EL PRECIO DE VENTA, igual que el precio sugerido, para que
ambos numeros sean coherentes).
"""
import json
import math

DEFAULTS = {
    "fee_percent": 3.0,       # comision del medio de pago / canal (% del precio de venta)
    "fixed_cost": 0.0,        # costo fijo por unidad (embalaje, etc.), en pesos
    "shipping_cost": 0.0,     # envio por unidad que paga el vendedor, en pesos
    "target_margin": 25.0,    # margen objetivo (%) para calcular el precio sugerido
    "min_margin": 10.0,       # por debajo de este margen (%) se avisa
}
SETTINGS_KEY = "pricing_config"


def _num(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def clean_config(raw):
    """Valida y completa la configuracion. Devuelve (config, error)."""
    cfg = dict(DEFAULTS)
    raw = raw or {}
    for key in DEFAULTS:
        if key in raw and raw[key] not in (None, ""):
            try:
                cfg[key] = float(raw[key])
            except (TypeError, ValueError):
                return None, f"{key} tiene que ser un numero"
    for key in ("fee_percent", "target_margin", "min_margin"):
        if not 0 <= cfg[key] < 100:
            return None, "los porcentajes tienen que estar entre 0 y 99"
    for key in ("fixed_cost", "shipping_cost"):
        if cfg[key] < 0:
            return None, "los costos no pueden ser negativos"
    if cfg["fee_percent"] + cfg["target_margin"] >= 95:
        return None, "comision + margen objetivo no pueden sumar 95% o mas"
    return cfg, None


def load_config(db):
    row = db.execute("SELECT value FROM settings WHERE key = ?", (SETTINGS_KEY,)).fetchone()
    stored = {}
    if row:
        try:
            stored = json.loads(row["value"])
        except (TypeError, ValueError):
            stored = {}
    cfg, _ = clean_config(stored)
    return cfg or dict(DEFAULTS)


def save_config(db, cfg):
    db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (SETTINGS_KEY, json.dumps(cfg)),
    )


def _extra_costs(cfg, currency):
    # Los costos fijos y de envio estan en pesos: no se aplican a productos en dolares
    if (currency or "ARS") != "ARS":
        return 0.0
    return cfg["fixed_cost"] + cfg["shipping_cost"]


def suggest_price(cost, cfg, currency="ARS"):
    """Precio de venta que deja el margen objetivo despues de comision y costos. None si no se puede calcular."""
    cost = _num(cost, 0.0)
    if cost <= 0:
        return None
    denominator = 1 - cfg["fee_percent"] / 100 - cfg["target_margin"] / 100
    if denominator <= 0.05:
        return None
    raw = (cost + _extra_costs(cfg, currency)) / denominator
    step = 10 if (currency or "ARS") == "ARS" else 0.5
    return math.ceil(raw / step) * step


def analyze(cost, price, cfg, currency="ARS"):
    """Ganancia neta y margen de un producto. Devuelve None si no hay costo cargado."""
    cost = _num(cost, 0.0)
    price = _num(price, 0.0)
    if cost <= 0:
        return None
    suggested = suggest_price(cost, cfg, currency)
    if price <= 0:
        return {"net_profit": None, "margin_percent": None, "suggested_price": suggested,
                "is_low": False, "is_negative": False, "no_price": True}
    fee = price * cfg["fee_percent"] / 100
    net = price - fee - _extra_costs(cfg, currency) - cost
    margin = net / price * 100
    return {
        "net_profit": round(net, 2),
        "margin_percent": round(margin, 1),
        "suggested_price": suggested,
        "is_low": margin < cfg["min_margin"],
        "is_negative": net < 0,
        "no_price": False,
    }
