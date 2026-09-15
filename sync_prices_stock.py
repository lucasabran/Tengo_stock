"""
sync_prices_stock.py
=====================
Revisa TODAS las publicaciones ya hechas en Mercado Libre (registradas en
published_skus.json) contra el precio y el stock ACTUAL de Rodo, y
actualiza lo que haya cambiado:

- Si el precio de Rodo cambio, recalcula el precio de venta (mismo markup
  chico/grande que se uso al publicar) y actualiza el precio en ML.
- Si Rodo quedo SIN STOCK, pausa la publicacion en ML (para no vender algo
  que no se puede conseguir).
- Si Rodo volvio a tener stock pero la publicacion esta pausada (tipico:
  se vendio la ultima unidad y quedo en 0), repone stock a DEFAULT_STOCK
  unidades (3 por defecto, ver ml_upload.DEFAULT_STOCK) y la reactiva --
  asi una sola venta no vuelve a pausarla. Los items pausados por otro
  motivo (fotos en proceso, en revision de ML, descontinuados) ya se
  filtran antes de llegar aca, asi que esto solo actua sobre pausas por
  stock.
- Si el SKU ya NO existe en Rodo (producto discontinuado/retirado), pausa
  la publicacion en ML. Para evitar pausar por un error de red pasajero,
  solo lo hace si la consulta a Rodo confirma "no encontrado" dos veces
  seguidas (no ante un timeout o error de conexion). Los SKUs pausados
  por este motivo quedan registrados en discontinued_skus.json.

No toca publicaciones en revision de ML (under_review) -- esas no se
pueden modificar por API de todos modos.

Uso:
    python sync_prices_stock.py                    # revisa y actualiza
    python sync_prices_stock.py --dry-run           # solo muestra que cambiaria
"""
import argparse
import json
import os
import sys
import time

import requests

import ml_upload as mu
from ml_auth import get_valid_token

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RODO_BASE_URL = "https://www.rodo.com.ar"
API_BASE = "https://api.mercadolibre.com"
PRICE_CHANGE_THRESHOLD = 1.0  # pesos; ignorar diferencias de redondeo
STOCK_PAUSED_FILE = "stock_paused_skus.json"
DISCONTINUED_FILE = "discontinued_skus.json"


def load_json_map(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json_map(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_stock_paused():
    return load_json_map(STOCK_PAUSED_FILE)


def save_stock_paused(data):
    save_json_map(STOCK_PAUSED_FILE, data)

SKU_QUERY = """
query ($sku: String!) {
  products(filter: {sku: {eq: $sku}}) {
    items {
      sku
      stock_status
      price_range {
        minimum_price {
          regular_price { value }
          final_price { value }
        }
      }
    }
  }
}
"""


def fetch_rodo_current(session, sku):
    """Devuelve un dict {price_original, in_stock} si encuentra el SKU,
    "NOT_FOUND" si Rodo respondio bien pero no tiene ese SKU (posible
    descontinuacion), o None si hubo un error de red/consulta (estado
    indeterminado -- no debe interpretarse como descontinuado)."""
    try:
        resp = session.post(f"{RODO_BASE_URL}/graphql", json={"query": SKU_QUERY, "variables": {"sku": sku}},
                             timeout=20)
    except requests.exceptions.RequestException:
        return None
    if not resp.ok:
        return None
    items = (resp.json().get("data") or {}).get("products", {}).get("items") or []
    if not items:
        return "NOT_FOUND"
    item = items[0]
    price = item["price_range"]["minimum_price"]["final_price"]["value"] or \
        item["price_range"]["minimum_price"]["regular_price"]["value"]
    return {"price_original": price, "in_stock": item.get("stock_status") == "IN_STOCK"}


def main():
    parser = argparse.ArgumentParser(description="Sincroniza precio y stock de publicaciones activas con Rodo")
    parser.add_argument("--markup-chico", type=float, default=1.8)
    parser.add_argument("--markup-grande", type=float, default=2.0)
    parser.add_argument("--dry-run", action="store_true", help="Solo mostrar cambios, no aplicarlos")
    args = parser.parse_args()

    with open("published_skus.json", encoding="utf-8") as f:
        state = json.load(f)
    # invertir: item_id -> sku (por si un item_id se repite, nos quedamos con uno)
    item_to_sku = {}
    for sku, item_id in state.items():
        item_to_sku.setdefault(item_id, sku)

    token = get_valid_token()
    ml_session = mu.TimeoutSession()
    ml_session.headers.update({"Authorization": f"Bearer {token}"})
    rodo_session = requests.Session()
    rodo_session.headers.update({"User-Agent": "Mozilla/5.0"})

    ids = list(item_to_sku.keys())
    ml_items = []
    for i in range(0, len(ids), 20):
        batch = ids[i:i + 20]
        resp = ml_session.get(f"{API_BASE}/items", params={"ids": ",".join(batch)})
        ml_items.extend(resp.json())

    updated_price, paused_stock, restocked_reactivated, errors, skipped_review = 0, 0, 0, 0, 0
    discontinued_count = 0
    stock_paused = load_stock_paused()
    discontinued = load_json_map(DISCONTINUED_FILE)

    for i, res in enumerate(ml_items, 1):
        body = res.get("body") or {}
        item_id = body.get("id")
        sku = item_to_sku.get(item_id)
        status = body.get("status")
        title = body.get("title", "")

        if not item_id or not sku:
            continue
        if status == "under_review":
            skipped_review += 1
            continue
        if "picture_download_pending" in (body.get("sub_status") or []):
            # ML todavia esta procesando las fotos -- no es un problema real de stock,
            # va a quedar "paused" hasta que termine solo (ver activate_sweep.py).
            skipped_review += 1
            continue

        rodo = fetch_rodo_current(rodo_session, sku)
        if rodo == "NOT_FOUND":
            # confirmar con un segundo intento antes de dar por descontinuado,
            # para no pausar por una falla pasajera de la consulta a Rodo
            time.sleep(1)
            rodo = fetch_rodo_current(rodo_session, sku)

        if rodo is None:
            print(f"[{i}/{len(ml_items)}] ERROR consultando Rodo (sku {sku}) -- se revisa de nuevo la proxima corrida "
                  f"-- {title[:45]}")
            errors += 1
            time.sleep(0.3)
            continue

        if rodo == "NOT_FOUND":
            print(f"[{i}/{len(ml_items)}] DESCONTINUADO EN RODO (sku {sku}, ya no existe) -> pausando "
                  f"{item_id} -- {title[:45]}")
            if not args.dry_run and status != "paused":
                mu.force_status(ml_session, item_id, "paused")
            discontinued[sku] = item_id
            if not args.dry_run:
                save_json_map(DISCONTINUED_FILE, discontinued)
            discontinued_count += 1
            time.sleep(0.3)
            continue

        # --- Stock ---
        if not rodo["in_stock"] and status == "active":
            print(f"[{i}/{len(ml_items)}] SIN STOCK en Rodo -> pausando {item_id} -- {title[:45]}")
            if not args.dry_run:
                mu.force_status(ml_session, item_id, "paused")
                stock_paused[sku] = item_id
                save_stock_paused(stock_paused)
            paused_stock += 1
        elif rodo["in_stock"] and status == "paused":
            print(f"[{i}/{len(ml_items)}] Volvio a tener stock en Rodo -> reponiendo {mu.DEFAULT_STOCK} unidades "
                  f"y reactivando {item_id} -- {title[:45]}")
            if not args.dry_run:
                r = ml_session.put(f"{API_BASE}/items/{item_id}", json={"available_quantity": mu.DEFAULT_STOCK})
                if r.ok:
                    mu.force_status(ml_session, item_id, "active")
                else:
                    print(f"    FALLO reponer stock: {r.status_code} {r.text[:150]}")
                if sku in stock_paused:
                    del stock_paused[sku]
                    save_stock_paused(stock_paused)
            restocked_reactivated += 1
        elif rodo["in_stock"] and status == "active" and sku in stock_paused:
            # ya no esta pausada (alguien la reactivo a mano) -- sacar la marca
            del stock_paused[sku]
            if not args.dry_run:
                save_stock_paused(stock_paused)

        # --- Precio ---
        markup = mu.pick_markup(title, args.markup_chico, args.markup_grande)
        new_price = round(rodo["price_original"] * markup, 2)
        current_price = body.get("price")
        if current_price and abs(new_price - current_price) > PRICE_CHANGE_THRESHOLD:
            print(f"[{i}/{len(ml_items)}] Precio Rodo cambio -> ${current_price} => ${new_price} "
                  f"({item_id} -- {title[:45]})")
            if not args.dry_run:
                r = ml_session.put(f"{API_BASE}/items/{item_id}", json={"price": new_price})
                if not r.ok:
                    print(f"    FALLO actualizar precio: {r.status_code} {r.text[:150]}")
                    errors += 1
                else:
                    updated_price += 1
            else:
                updated_price += 1

        time.sleep(0.3)

    print()
    print(f"Listo. Precios actualizados: {updated_price} | Pausadas por falta de stock: {paused_stock} | "
          f"Pausadas por descontinuadas en Rodo: {discontinued_count} | "
          f"Repuestas y reactivadas (volvieron a stock): {restocked_reactivated} | En revision de ML (no tocadas): {skipped_review} | "
          f"Errores: {errors}")


if __name__ == "__main__":
    main()
