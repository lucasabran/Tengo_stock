"""
Mejoras de catálogo para Tiendanube.

  python mejoras.py seo [--aplicar]     acorta títulos SEO a <=60 caracteres sin cortar palabras
  python mejoras.py stock [--aplicar]   oculta productos sin stock y re-publica los que repusieron
  python mejoras.py fotos               genera fotos_pendientes.csv (productos con 1 foto, por precio)
"""
import json
import os
import re
import sys

import garantia as g

MAX_SEO = 60
OCULTOS = os.path.join(g.AQUI, "ocultos_sin_stock.json")
CONECTORES = {"con", "y", "de", "del", "para", "en", "a", "la", "el", "-", "|", "–", "/", "+", "e", "o"}


def t(v):
    return g.txt(v) or ""


def acortar(titulo):
    titulo = re.sub(r"\s+", " ", titulo).strip()
    if len(titulo) <= MAX_SEO:
        return titulo
    # 1) cortar en un separador natural si lo que queda es suficientemente descriptivo
    for sep in (" | ", " – ", " - ", ": ", ", "):
        cabeza = titulo.split(sep)[0].strip()
        if 30 <= len(cabeza) <= MAX_SEO:
            return cabeza
    # 2) cortar en límite de palabra y sacar conectores colgando al final
    palabras = titulo[:MAX_SEO + 1].split(" ")
    if len(titulo) > MAX_SEO:
        palabras = palabras[:-1]
    while palabras and palabras[-1].lower().strip(",.:") in CONECTORES:
        palabras.pop()
    return " ".join(palabras).rstrip(",.:-–| ")


def cmd_seo(api, productos, aplicar):
    cambios = 0
    for p in productos:
        actual = t(p.get("seo_title"))
        base = actual or t(p.get("name"))
        nuevo = acortar(base)
        if nuevo and nuevo != actual:
            cambios += 1
            print(f"{p['id']}  [{len(actual)}] {actual or '(vacío)'}\n            -> [{len(nuevo)}] {nuevo}")
            if aplicar:
                api.req("PUT", f"/products/{p['id']}", {"seo_title": {g.IDIOMA: nuevo}})
    print(f"\n{cambios} títulos SEO {'actualizados' if aplicar else 'a actualizar (simulación)'}")


def sin_stock(p):
    return all(v.get("stock") == 0 for v in p["variants"])


def cmd_stock(api, productos, aplicar):
    ocultos = set(json.load(open(OCULTOS))) if os.path.exists(OCULTOS) else set()
    ocultar = [p for p in productos if p.get("published") and sin_stock(p)]
    republicar = [p for p in productos if p["id"] in ocultos and not p.get("published") and not sin_stock(p)]
    for p in ocultar:
        print(f"ocultar     {p['id']}  {t(p['name'])[:70]}")
        if aplicar:
            api.req("PUT", f"/products/{p['id']}", {"published": False})
            ocultos.add(p["id"])
    for p in republicar:
        print(f"republicar  {p['id']}  {t(p['name'])[:70]}")
        if aplicar:
            api.req("PUT", f"/products/{p['id']}", {"published": True})
            ocultos.discard(p["id"])
    if aplicar:
        json.dump(sorted(ocultos), open(OCULTOS, "w"))
    print(f"\n{len(ocultar)} a ocultar, {len(republicar)} a republicar"
          f"{'' if aplicar else ' (simulación)'}")


def cmd_fotos(productos, tienda):
    filas = []
    for p in productos:
        if p.get("published") and len(p.get("images") or []) <= 1:
            precio = max(float(v.get("price") or 0) for v in p["variants"])
            filas.append((precio, p))
    filas.sort(key=lambda x: -x[0])
    with open("fotos_pendientes.csv", "w", encoding="utf-8-sig") as f:
        f.write("precio;producto;fotos;editar en el admin;ver en la tienda\n")
        for precio, p in filas:
            f.write(f"{precio:.0f};{t(p['name'])};{len(p.get('images') or [])};"
                    f"https://{tienda}/admin/products/{p['id']}/;{p.get('canonical_url', '')}\n")
    print(f"{len(filas)} productos con 1 foto o menos -> fotos_pendientes.csv")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2 or sys.argv[1] not in ("seo", "stock", "fotos"):
        sys.exit(__doc__)
    aplicar = "--aplicar" in sys.argv
    api = g.Api(g.cargar_env())
    productos = list(api.productos())
    if sys.argv[1] == "seo":
        cmd_seo(api, [p for p in productos if p.get("published")], aplicar)
    elif sys.argv[1] == "stock":
        cmd_stock(api, productos, aplicar)
    else:
        cmd_fotos(productos, "tengostockarg.mitiendanube.com")


if __name__ == "__main__":
    main()
