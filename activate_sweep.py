"""
activate_sweep.py
==================
Red de seguridad complementaria a pause_sweep.py: activa cualquier
publicacion registrada que haya quedado "paused" por no haberse podido
confirmar el estado 'active' a tiempo justo despues de crearla (ML tarda
unos segundos en terminar de procesar una publicacion nueva antes de
aceptar activarla -- ver force_status en ml_upload.py).

NO activa:
  - publicaciones pausadas a proposito por falta de stock en Rodo
    (registradas en stock_paused_skus.json por sync_prices_stock.py)
  - publicaciones que ML todavia esta procesando (fotos en cola,
    sub_status picture_download_pending) -- reintentar no sirve, solo
    hay que esperar
  - publicaciones que se quedaron en 0 stock porque se vendio la ultima
    unidad -- ML no deja activar sin stock; correr sync_prices_stock.py
    para reponerlas segun el stock real de Rodo
  - publicaciones de productos que ya no existen en Rodo (descontinuados,
    registrados en discontinued_skus.json por sync_prices_stock.py)

Uso:
    python activate_sweep.py                # barrido normal
    python activate_sweep.py --dry-run       # solo muestra que activaria
"""
import argparse
import json
import os
import sys

import requests

import ml_upload as mu
from ml_auth import get_valid_token

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API_BASE = "https://api.mercadolibre.com"
PUBLISHED_STATE_FILE = "published_skus.json"
STOCK_PAUSED_FILE = "stock_paused_skus.json"
DISCONTINUED_FILE = "discontinued_skus.json"


def main():
    parser = argparse.ArgumentParser(description="Activa publicaciones registradas que quedaron pausadas sin querer")
    parser.add_argument("--dry-run", action="store_true", help="Solo mostrar, no activar nada")
    args = parser.parse_args()

    with open(PUBLISHED_STATE_FILE, encoding="utf-8") as f:
        state = json.load(f)
    item_to_sku = {}
    for sku, item_id in state.items():
        item_to_sku.setdefault(item_id, sku)

    stock_paused_ids = set()
    if os.path.exists(STOCK_PAUSED_FILE):
        with open(STOCK_PAUSED_FILE, encoding="utf-8") as f:
            stock_paused_ids = set(json.load(f).values())

    discontinued_ids = set()
    if os.path.exists(DISCONTINUED_FILE):
        with open(DISCONTINUED_FILE, encoding="utf-8") as f:
            discontinued_ids = set(json.load(f).values())
    stock_paused_ids |= discontinued_ids

    ids = list(item_to_sku.keys())
    print(f"Revisando {len(ids)} publicaciones registradas...")

    token = get_valid_token()
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {token}"})

    results = []
    for i in range(0, len(ids), 20):
        batch = ids[i:i + 20]
        resp = session.get(f"{API_BASE}/items", params={"ids": ",".join(batch)})
        resp.raise_for_status()
        results.extend(resp.json())

    paused_bodies = [r["body"] for r in results if r.get("body", {}).get("status") == "paused"]
    paused_bodies = [b for b in paused_bodies if b["id"] not in stock_paused_ids]

    # ML todavia esta bajando/procesando las fotos -- reintentar el PUT no sirve de nada,
    # solo hay que esperar a que ML termine (puede tardar minutos u horas en lotes grandes).
    waiting_pictures = [b["id"] for b in paused_bodies if "picture_download_pending" in (b.get("sub_status") or [])]
    # Se vendio la ultima unidad y quedo en 0 stock -- ML no deja activar sin stock.
    # No es cosa nuestra reponer cantidad a ciegas; eso lo maneja sync_prices_stock.py
    # mirando el stock real de Rodo.
    sold_out = [b["id"] for b in paused_bodies if (b.get("available_quantity") or 0) <= 0]
    skip_ids = set(waiting_pictures) | set(sold_out)
    to_activate = [b["id"] for b in paused_bodies if b["id"] not in skip_ids]

    if waiting_pictures:
        print(f"({len(waiting_pictures)} pausadas porque ML todavia esta procesando las fotos "
              f"-- no se tocan, van a poder activarse solas mas tarde, correr este script de nuevo despues)")
    if sold_out:
        print(f"({len(sold_out)} pausadas porque se vendio la ultima unidad (0 stock) "
              f"-- no se tocan, correr sync_prices_stock.py para revisar contra el stock real de Rodo)")

    if not to_activate:
        print("Nada mas para activar por ahora.")
        return

    print(f"\n{len(to_activate)} publicaciones pausadas que deberian estar activas:")
    for item_id in to_activate:
        print(" ", item_id)

    if args.dry_run:
        print("\n(--dry-run: no se activo nada, correr sin esa opcion para activarlas)")
        return

    print("\nActivando...")
    ok, fail = 0, 0
    for item_id in to_activate:
        if mu.force_status(session, item_id, "active"):
            ok += 1
        else:
            fail += 1
    print(f"\nListo. Activadas: {ok} | Fallaron: {fail}")


if __name__ == "__main__":
    main()
