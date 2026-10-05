"""
moderation_sweep.py
====================
Chequeo periodico de publicaciones ocultas por moderacion de ML
(status=under_review, sub_status=waiting_for_patch). A diferencia de
picture_download_pending (que se resuelve solo), esto NO se resuelve solo
-- si se deja, escala a "forbidden" (bloqueo permanente). Correrlo seguido
(se recomienda semanal) evita que se acumule un backlog invisible como paso
la primera vez (49 publicaciones llevaban semanas ocultas sin que nadie lo
supiera).

Para cada publicacion en ese estado, consulta el motivo real
(GET /moderations/last_moderation/{id}-ITM):

- OPT_OBEY: ML sugiere un producto de catalogo especifico (viene en la
  moderacion, no hay que buscarlo). Se verifica con el mismo chequeo
  estricto de marca (atributo BRAND real, no adivinado) + codigo de modelo
  mas especifico que catalog_optin.py. Si confirma, con --create hace el
  opt-in (POST /items/catalog_listings) que reactiva la tradicional Y crea
  la de catalogo.
- INCONSISTENCY_CHECK: titulo y/o fotos no coinciden -- no se puede
  verificar ni arreglar de forma segura por API (hay que MIRAR las fotos),
  se reporta para revision manual.
- Otros motivos: se reportan sin tocar.

Uso:
    python moderation_sweep.py                # solo reporta
    python moderation_sweep.py --create        # confirma los OPT_OBEY verificados
"""
import argparse
import json
import re
import sys
import time

import requests

import ml_upload as mu
from ml_auth import get_valid_token

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API_BASE = "https://api.mercadolibre.com"
PUBLISHED_STATE_FILE = "published_skus.json"
CATALOG_LISTINGS_FILE = "catalog_listings.json"

UNIT_ONLY_TOKEN_RE = re.compile(
    r"^\d+([.,]\d+)?(lts?|l|kg|gr?|g|mg|w|kw|v|cm|mm|m|ml|hz|pa|min|hs|h)$", re.IGNORECASE
)


def verify_match(session, title, brand, catalog_product_id):
    """True si marca + codigo de modelo mas especifico de nuestro titulo
    aparecen literal en el nombre del producto de catalogo sugerido."""
    if not catalog_product_id:
        return False, None
    cand_name = mu.fetch_catalog_product_name(session, catalog_product_id)
    if not cand_name:
        return False, None
    name_norm = mu.strip_accents(cand_name.lower())
    brand_norm = mu.strip_accents((brand or "").lower())
    model_tokens = {t for t in mu.extract_model_tokens(title) if not UNIT_ONLY_TOKEN_RE.match(t)}
    if not model_tokens or not brand_norm:
        return False, cand_name
    primary = max(model_tokens, key=len)
    if len(primary) < 4:
        return False, cand_name
    ok = (brand_norm in name_norm) and (primary in name_norm)
    return ok, cand_name


def main():
    parser = argparse.ArgumentParser(description="Chequeo periodico de publicaciones en waiting_for_patch")
    parser.add_argument("--create", action="store_true",
                         help="Confirmar (opt-in) los matches de catalogo verificados. Sin esto, solo reporta.")
    args = parser.parse_args()

    with open(PUBLISHED_STATE_FILE, encoding="utf-8") as f:
        state = json.load(f)
    item_to_sku = {}
    for sku, item_id in state.items():
        item_to_sku.setdefault(item_id, sku)

    token = get_valid_token()
    session = mu.TimeoutSession()
    session.headers.update({"Authorization": f"Bearer {token}"})

    ids = list(item_to_sku.keys())
    results = []
    for i in range(0, len(ids), 20):
        batch = ids[i:i + 20]
        resp = session.get(f"{API_BASE}/items", params={"ids": ",".join(batch)})
        resp.raise_for_status()
        results.extend(resp.json())
    bodies = [r["body"] for r in results if r.get("body")]

    stuck = [b for b in bodies if b.get("status") == "under_review"
             and "waiting_for_patch" in (b.get("sub_status") or [])]
    print(f"Publicaciones en waiting_for_patch: {len(stuck)}")
    if not stuck:
        print("Nada para revisar.")
        return

    confirmed, revisar, inconsistency, other = [], [], [], []
    errors = 0
    for i, b in enumerate(stuck, 1):
        item_id = b["id"]
        title = b.get("title", "")
        brand = next((a.get("value_name") for a in b.get("attributes", []) if a.get("id") == "BRAND"), None)

        try:
            r = session.get(f"{API_BASE}/moderations/last_moderation/{item_id}-ITM")
            mods = r.json() if r.ok else []
            reason = mods[0].get("name") if mods else "SIN_DATOS"

            if reason == "OPT_OBEY":
                evid = next((e["text_matched"] for e in mods[0].get("evidence", []) if e.get("section_name") == "item"), None)
                ok, cand_name = verify_match(session, title, brand, evid)
                entry = {"item_id": item_id, "sku": item_to_sku.get(item_id), "title": title,
                          "candidate": evid, "cand_name": cand_name}
                (confirmed if ok else revisar).append(entry)
            elif reason == "INCONSISTENCY_CHECK":
                inconsistency.append({"item_id": item_id, "title": title})
            else:
                other.append({"item_id": item_id, "title": title, "reason": reason})
        except requests.exceptions.RequestException as e:
            print(f"  ERROR DE RED revisando {item_id}: {e} -- se reintenta en la proxima corrida")
            errors += 1

        if i % 25 == 0:
            print(f"  ...{i}/{len(stuck)}")
        time.sleep(0.1)

    if errors:
        print(f"({errors} publicaciones no se pudieron revisar por error de red -- reintentar corriendo de nuevo)")

    print()
    print(f"Catalogo confirmado (marca + modelo exacto): {len(confirmed)}")
    print(f"Catalogo a revisar a mano (no matchea seguro): {len(revisar)}")
    print(f"Titulo/fotos no coinciden (revisar fotos a mano): {len(inconsistency)}")
    print(f"Otros motivos: {len(other)}")
    print()

    for c in confirmed:
        print(f"  CONFIRMAR {c['item_id']} | {c['title'][:50]} -> {(c['cand_name'] or '')[:60]}")
    for r in revisar:
        print(f"  REVISAR   {r['item_id']} | {r['title'][:50]} -> {(r['cand_name'] or 'sin nombre')[:60]}")
    for x in inconsistency:
        print(f"  FOTOS     {x['item_id']} | {x['title'][:60]}")
    for o in other:
        print(f"  OTRO({o['reason']}) {o['item_id']} | {o['title'][:50]}")

    with open("moderation_sweep_report.json", "w", encoding="utf-8") as f:
        json.dump({"confirmed": confirmed, "revisar": revisar,
                    "inconsistency": inconsistency, "other": other}, f, ensure_ascii=False, indent=2)
    print("\nReporte guardado en moderation_sweep_report.json")

    if not args.create:
        print("\n(modo reporte -- correr con --create para confirmar los de catalogo verificados)")
        return

    if not confirmed:
        print("\nNada verificado para confirmar.")
        return

    listings = {}
    try:
        with open(CATALOG_LISTINGS_FILE, encoding="utf-8") as f:
            listings = json.load(f)
    except FileNotFoundError:
        pass

    print("\nConfirmando matches de catalogo...")
    ok, fail = 0, 0
    for c in confirmed:
        item_id = c["item_id"]
        if item_id in listings:
            continue  # ya confirmado en una corrida anterior
        try:
            resp = session.post(f"{API_BASE}/items/catalog_listings",
                                 json={"item_id": item_id, "catalog_product_id": c["candidate"]})
        except requests.exceptions.RequestException as e:
            print(f"  ERROR DE RED en {item_id}: {e} -- se reintenta en la proxima corrida")
            fail += 1
            time.sleep(0.3)
            continue
        if resp.ok:
            new_id = resp.json().get("id")
            listings[item_id] = new_id
            with open(CATALOG_LISTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(listings, f, ensure_ascii=False, indent=2)
            try:
                session.put(f"{API_BASE}/items/{new_id}", json={"available_quantity": mu.DEFAULT_STOCK})
            except requests.exceptions.RequestException:
                pass  # la publicacion de catalogo ya quedo creada y registrada; el stock se puede ajustar despues
            ok += 1
            print(f"  OK {item_id} -> {new_id}")
        elif "already been created" in resp.text:
            # se creo en una corrida anterior que se corto antes de guardar el tracking
            # -- no es un fallo real, ML no duplica nada. Queda sin id de catalogo
            # registrado (no se puede recuperar por API), pero no bloquea nada.
            print(f"  YA EXISTIA {item_id} (creado antes, no registrado -- no se duplico)")
            ok += 1
        else:
            print(f"  FALLO {item_id}: {resp.status_code} {resp.text[:200]}")
            fail += 1
        time.sleep(0.3)
    print(f"\nListo. Confirmadas: {ok} | Fallaron: {fail}")


if __name__ == "__main__":
    main()
