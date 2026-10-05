"""
catalog_optin.py
=================
Resuelve el aviso de ML "pausamos tus publicaciones porque debes competir
en catalogo": para cada publicacion elegible (catalog_listing_eligibility
== READY_FOR_OPTIN), busca con confianza alta el producto de catalogo que
le corresponde y crea la publicacion de catalogo asociada -- la tradicional
sigue existiendo en paralelo (lo pide el usuario y lo permite ML).

A diferencia del intento anterior que causo el incidente de matching
(ver MANUAL.md), esta version:
  1. Usa el domain_id que ML YA le asigno a nuestra propia publicacion
     (via catalog_listing_eligibility) para acotar la busqueda de productos
     de catalogo -- estructuralmente no puede cruzar a un dominio
     completamente distinto (ej. aire acondicionado -> control remoto).
  2. Ademas exige el mismo match estricto de marca + codigo de modelo que
     ya usa ml_upload.find_confident_catalog_matches.
  3. Por defecto corre en modo REPORTE (no crea nada) -- listar los
     matches propuestos para poder revisarlos antes de confirmar en masa.

Uso:
    python catalog_optin.py                # modo reporte, no crea nada
    python catalog_optin.py --create        # crea las publicaciones de catalogo confirmadas
"""
import argparse
import json
import os
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


# Tokens como "50lts", "220v", "1200w" pasan la regex de mu.extract_model_tokens
# (tienen letras+numero) pero son una CAPACIDAD/POTENCIA, no un codigo de modelo
# -- dos productos de marcas distintas pueden compartir "50lts" por pura
# coincidencia. Si se elige uno de estos como "token mas especifico" el
# chequeo de confianza deja de servir (fue justamente lo que paso con un
# termotanque: emparejo por "50lts" con un producto de otra marca).
UNIT_ONLY_TOKEN_RE = re.compile(
    r"^\d+([.,]\d+)?(lts?|l|kg|gr?|g|mg|w|kw|v|cm|mm|m|ml|hz|pa|min|hs|h)$", re.IGNORECASE
)


def find_confident_match_in_domain(session, item_id, title, brand, domain_id):
    """Como mu.find_confident_catalog_matches, pero acotado al domain_id
    que ML ya le asigno a esta publicacion (mas seguro que buscar libre).
    brand debe venir del atributo BRAND que ya tiene la publicacion en ML
    (no adivinado de texto libre)."""
    brand = mu.strip_accents((brand or "").lower())
    model_tokens = {t for t in mu.extract_model_tokens(title) if not UNIT_ONLY_TOKEN_RE.match(t)}
    if not model_tokens:
        return []
    primary_token = max(model_tokens, key=len)
    if len(primary_token) < 4:
        return []
    if not brand:
        return []  # sin marca declarada no arriesgamos el match

    resp = session.get(f"{API_BASE}/products/search",
                        params={"site_id": "MLA", "q": title[:60], "domain_id": domain_id})
    if not resp.ok:
        return []

    candidates = []
    for result in resp.json().get("results", [])[:5]:
        children = result.get("children_ids") or []
        candidate_id = children[0] if children else result["id"]
        candidate_name = (mu.fetch_catalog_product_name(session, candidate_id)
                           if children else result.get("name", ""))
        if not candidate_name:
            continue
        name_norm = mu.strip_accents(candidate_name.lower())
        if primary_token not in name_norm:
            continue
        if brand and brand not in name_norm:
            continue
        name_tokens = set(name_norm.split())
        our_tokens = set(mu.strip_accents(title.lower()).split())
        extra = {t for t in name_tokens if t not in our_tokens and len(t) > 2}
        if extra & mu.BUNDLE_RISK_WORDS:
            continue
        candidates.append((candidate_id, candidate_name))
    return candidates


def main():
    parser = argparse.ArgumentParser(description="Opt-in a catalogo para publicaciones elegibles")
    parser.add_argument("--create", action="store_true",
                         help="Crear de verdad las publicaciones de catalogo (si no, solo reporta)")
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
    print(f"Revisando elegibilidad de catalogo para {len(ids)} publicaciones...")

    elig = []
    for i in range(0, len(ids), 20):
        batch = ids[i:i + 20]
        resp = session.get(f"{API_BASE}/multiget/catalog_listing_eligibility", params={"ids": ",".join(batch)})
        resp.raise_for_status()
        elig.extend(resp.json())

    ready = [r["body"] for r in elig if r.get("body", {}).get("status") == "READY_FOR_OPTIN"]
    print(f"{len(ready)} publicaciones elegibles (READY_FOR_OPTIN).")

    confirmed, no_match, ambiguous = [], [], []
    for i, body in enumerate(ready, 1):
        item_id = body["id"]
        domain_id = body.get("domain_id")
        item_resp = session.get(f"{API_BASE}/items/{item_id}", params={"attributes": "title,attributes"})
        if not item_resp.ok:
            continue
        item_data = item_resp.json()
        title = item_data.get("title", "")
        brand = next((a.get("value_name") for a in item_data.get("attributes", []) if a.get("id") == "BRAND"), None)

        candidates = find_confident_match_in_domain(session, item_id, title, brand, domain_id)
        if len(candidates) == 1:
            cand_id, cand_name = candidates[0]
            confirmed.append({"item_id": item_id, "sku": item_to_sku.get(item_id), "title": title,
                               "domain_id": domain_id, "catalog_product_id": cand_id, "catalog_name": cand_name})
        elif len(candidates) == 0:
            no_match.append(item_id)
        else:
            ambiguous.append(item_id)

        if i % 25 == 0:
            print(f"  ...{i}/{len(ready)} revisadas")
        time.sleep(0.1)

    print()
    print(f"Matches confirmados (marca+modelo dentro del dominio correcto): {len(confirmed)}")
    print(f"Sin match confiable (se deja como tradicional nada mas, sin riesgo): {len(no_match)}")
    print(f"Ambiguos (mas de 1 candidato, se saltan por seguridad): {len(ambiguous)}")
    print()
    for c in confirmed:
        print(f"  {c['item_id']} | nuestro: {c['title'][:50]}")
        print(f"    -> catalogo: {c['catalog_name'][:70]} (product_id={c['catalog_product_id']})")

    with open("catalog_optin_report.json", "w", encoding="utf-8") as f:
        json.dump({"confirmed": confirmed, "no_match_count": len(no_match), "ambiguous_count": len(ambiguous)},
                   f, ensure_ascii=False, indent=2)
    print(f"\nReporte guardado en catalog_optin_report.json")

    if not args.create:
        print("\n(modo reporte -- no se creo ninguna publicacion. Correr con --create para confirmarlas)")
        return

    print("\nCreando publicaciones de catalogo...")
    listings = {}
    if os.path.exists(CATALOG_LISTINGS_FILE):
        with open(CATALOG_LISTINGS_FILE, encoding="utf-8") as f:
            listings = json.load(f)
    ok, fail = 0, 0
    for c in confirmed:
        if c["item_id"] in listings:
            continue  # ya tiene publicacion de catalogo creada (corrida anterior)
        resp = session.post(f"{API_BASE}/items/catalog_listings", json={
            "item_id": c["item_id"],
            "catalog_product_id": c["catalog_product_id"],
        })
        if resp.ok:
            new_id = resp.json().get("id")
            listings[c["item_id"]] = new_id
            # available_quantity no se acepta en el POST de opt-in -- se pone aparte
            session.put(f"{API_BASE}/items/{new_id}", json={"available_quantity": mu.DEFAULT_STOCK})
            ok += 1
        else:
            print(f"  FALLO {c['item_id']}: {resp.status_code} {resp.text[:200]}")
            fail += 1
        time.sleep(0.3)

    with open(CATALOG_LISTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(listings, f, ensure_ascii=False, indent=2)

    print(f"\nListo. Creadas: {ok} | Fallaron: {fail}")


if __name__ == "__main__":
    main()
