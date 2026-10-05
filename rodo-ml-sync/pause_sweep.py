"""
pause_sweep.py
===============
Red de seguridad: revisa TODAS las publicaciones registradas en
published_skus.json y pausa cualquiera que haya quedado "active" sin que
lo hayamos pedido.

Por que existe este script: se detecto en produccion que Mercado Libre
puede pasar una publicacion de "paused" a "active" por su cuenta un rato
despues de creada (aparentemente al terminar de procesar las fotos),
incluso habiendo pedido status=paused al crearla. ml_upload.py ya hace un
PUT de confirmacion inmediatamente despues de publicar (ver force_pause en
ml_upload.py), pero como capa extra de seguridad conviene correr este
script de tanto en tanto -- sobre todo despues de una tanda grande, o si
no se va a revisar el excel de resultado enseguida.

Uso:
    python pause_sweep.py                # barrido normal
    python pause_sweep.py --dry-run       # solo muestra que pausaria, no toca nada
"""
import argparse
import json
import sys
import time

import requests

from ml_auth import get_valid_token

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API_BASE = "https://api.mercadolibre.com"
PUBLISHED_STATE_FILE = "published_skus.json"


def main():
    parser = argparse.ArgumentParser(description="Pausa cualquier publicacion registrada que haya quedado activa")
    parser.add_argument("--dry-run", action="store_true", help="Solo mostrar, no pausar nada")
    args = parser.parse_args()

    with open(PUBLISHED_STATE_FILE, encoding="utf-8") as f:
        state = json.load(f)
    ids = list(set(state.values()))
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

    active = [r["body"]["id"] for r in results if r.get("body", {}).get("status") == "active"]

    if not active:
        print("Todo en orden: ninguna publicacion registrada esta activa.")
        return

    print(f"\n¡ATENCION! {len(active)} publicaciones estan ACTIVAS (publicas) sin que lo hayamos pedido:")
    for item_id in active:
        print(" ", item_id)

    if args.dry_run:
        print("\n(--dry-run: no se pauso nada, correr sin esa opcion para pausarlas)")
        return

    print("\nPausando...")
    ok, fail = 0, 0
    for item_id in active:
        resp = session.put(f"{API_BASE}/items/{item_id}", json={"status": "paused"})
        if resp.ok:
            ok += 1
        else:
            fail += 1
            print(f"  FALLO {item_id}: {resp.status_code} {resp.text[:150]}")
        time.sleep(0.3)
    print(f"\nListo. Pausadas: {ok} | Fallaron: {fail}")


if __name__ == "__main__":
    main()
