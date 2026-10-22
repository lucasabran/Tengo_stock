"""
Sección CYBERMONDAY: reutiliza la categoría del Día de la Madre (mismo ID).

  python cyber.py armar [--aplicar]   renombra categoría y subcategorías y elige productos
  python cyber.py vaciar [--aplicar]  saca todos los productos de la sección (al terminar el Cyber)

No cambia ningún precio.
"""
import re
import sys

import garantia as g
from dia_madre import base_variant, cats, con_stock, precio, repartidos, t

CYBER = 41063731
NOMBRE, HANDLE = "CYBERMONDAY", "cybermonday"
TECNO, ELECTRO, CLIMA, HOGAR, CUIDADO = 30783413, 30783491, 30783650, 30783583, 34076862
IPHONE, CONSOLAS = 34316680, 35241954
COCINA_RX = r"freidora|air ?fryer|batidora|multiprocesadora|tostadora|sandwichera|licuadora|cafetera|pava el|microondas|horno|anafe|procesadora|exprimidor"
# subcategoría existente -> (nombre, handle, categorías de origen, regex obligatoria, regex excluida)
SUBS = {
    41327103: ("Tecnología", "cyber-tecnologia", {TECNO, IPHONE, CONSOLAS}, None, r"soporte|cable|funda|cargador|adaptador"),
    41327104: ("Electrodomésticos", "cyber-electrodomesticos", {ELECTRO}, None, COCINA_RX),
    41327105: ("Climatización", "cyber-climatizacion", {CLIMA, ELECTRO, HOGAR}, r"aire acondicionado|ventilador|climatizador|purificador|deshumidificador", r"soporte"),
    41327106: ("Cocina", "cyber-cocina", {ELECTRO, HOGAR}, COCINA_RX, None),
    41513371: ("Hogar", "cyber-hogar", {HOGAR}, None, COCINA_RX),
    41513372: ("Cuidado personal", "cyber-cuidado-personal", {CUIDADO}, None, None),
}
POR_SUB = 16
PRECIO_MAX = 5000000
PRECIO_MIN = 100000  # foco en tickets que alcanzan los cupones CYBER (desde $300.000)


def subarbol(todas, raiz):
    ids, cambio = {raiz}, True
    while cambio:
        hijas = {c["id"] for c in todas if c.get("parent") in ids} - ids
        cambio = bool(hijas)
        ids |= hijas
    return ids


def armar(api, productos, aplicar):
    todas = api.req("GET", "/categories?per_page=200")
    seccion = {CYBER} | set(SUBS)
    cambios = {}

    # 1) vaciar la sección
    for p in productos:
        if set(cats(p)) & seccion:
            cambios[p["id"]] = [c for c in cats(p) if c not in seccion]

    # 2) elegir productos por subcategoría
    usados = set()
    for sid, (nombre, _, origen, rx_si, rx_no) in SUBS.items():
        origen_ids = set().union(*(subarbol(todas, o) for o in origen))
        cand = sorted((p for p in productos
                       if p["id"] not in usados and p.get("published") and con_stock(p)
                       and PRECIO_MIN <= precio(p) <= PRECIO_MAX and set(cats(p)) & origen_ids
                       and (not rx_si or re.search(rx_si, t(p["name"]), re.I))
                       and not (rx_no and re.search(rx_no, t(p["name"]), re.I))),
                      key=precio)
        elegidos = repartidos(cand, POR_SUB)
        print(f"\n== {nombre}: {len(elegidos)} (de {len(cand)} candidatos)")
        for p in elegidos:
            usados.add(p["id"])
            base = cambios.get(p["id"], cats(p))
            cambios[p["id"]] = list(dict.fromkeys(base + [CYBER, sid]))
            print(f"   ${precio(p):>11,.0f}  {t(p['name'])[:65]}")

    print(f"\nCategoría {CYBER} -> {NOMBRE} (/{HANDLE}/)")
    if aplicar:
        api.req("PUT", f"/categories/{CYBER}", {"name": {g.IDIOMA: NOMBRE}, "handle": {g.IDIOMA: HANDLE}})
        for sid, (nombre, handle, *_) in SUBS.items():
            api.req("PUT", f"/categories/{sid}", {"name": {g.IDIOMA: nombre}, "handle": {g.IDIOMA: handle},
                                                   "parent": CYBER})  # sin parent, la API la pasa al nivel principal
        for pid, nuevas in cambios.items():
            api.req("PUT", f"/products/{pid}", {"categories": nuevas})
    print(f"{len(cambios)} productos {'actualizados' if aplicar else 'a actualizar (simulación)'}")


def vaciar(api, productos, aplicar):
    seccion = {CYBER} | set(SUBS)
    n = 0
    for p in productos:
        if set(cats(p)) & seccion:
            n += 1
            if aplicar:
                api.req("PUT", f"/products/{p['id']}", {"categories": [c for c in cats(p) if c not in seccion]})
    print(f"{n} productos {'sacados de la sección' if aplicar else 'a sacar (simulación)'}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2 or sys.argv[1] not in ("armar", "vaciar"):
        sys.exit(__doc__)
    aplicar = "--aplicar" in sys.argv
    api = g.Api(g.cargar_env())
    productos = list(api.productos())
    (armar if sys.argv[1] == "armar" else vaciar)(api, productos, aplicar)


if __name__ == "__main__":
    main()
