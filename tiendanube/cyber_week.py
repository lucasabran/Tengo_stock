"""
Cyber Week (2 al 8/11): reorganiza la sección y la categoría de temporada. No cambia ningún precio.

  python cyber_week.py armar [--aplicar]

- CYBERMONDAY -> CYBER WEEK (/cyber-week/), con subcategorías:
  Megaofertas, Novedades, Tecno, Electro, Verano, Cocina, Hogar, Cuidado personal.
- PREPARATE PARA EL INVIERNO (/calor/) -> PREPARATE PARA EL VERANO (/verano/) con aires,
  ventiladores y climatizadores (se sacan las estufas).
"""
import re
import sys

import garantia as g
from cyber import CYBER, PRECIO_MAX, SUBS, subarbol
from dia_madre import base_variant, cats, con_stock, precio, repartidos, t

NOMBRE, HANDLE = "CYBER WEEK", "cyber-week"
RENOMBRAR = {  # subcategorías existentes: (nombre, handle)
    41327103: ("Tecno", "cyber-tecno"),
    41327104: ("Electro", "cyber-electro"),
    41327105: ("Verano: aires y ventiladores", "cyber-verano"),
    41327106: ("Cocina", "cyber-cocina"),
    41513371: ("Hogar", "cyber-hogar"),
    41513372: ("Cuidado personal", "cyber-cuidado-personal"),
}
NUEVAS = {"megaofertas": ("Megaofertas", "cyber-megaofertas"), "novedades": ("Novedades", "cyber-novedades")}
TEMPORADA = 35119556
TEMPORADA_NOMBRE, TEMPORADA_HANDLE = "PREPARATE PARA EL VERANO", "verano"
VERANO_RX = r"aire acondicionado|ventilador|climatizador|purificador|deshumidificador"
TOPE_MEGA_ALTO = 1500000  # desde acá aplica CYBER10


def promo_pct(p):
    v = base_variant(p)
    pr, pp = float(v.get("price") or 0), v.get("promotional_price")
    return 1 - float(pp) / pr if pp and float(pp) > 0 and pr > 0 and float(pp) < pr else 0


def armar(api, productos, aplicar):
    todas = api.req("GET", "/categories?per_page=200")
    por_nombre = {g.txt(c["name"]): c["id"] for c in todas if c.get("parent") == CYBER}
    activos = [p for p in productos if p.get("published") and con_stock(p) and precio(p) > 0]

    # 1) categorías de la sección
    ids_nuevas = {}
    for clave, (nombre, handle) in NUEVAS.items():
        cid = por_nombre.get(nombre)
        print(f"{'=' if cid else '+'} subcategoría '{nombre}'")
        if not cid and aplicar:
            cid = api.req("POST", "/categories", {"name": {g.IDIOMA: nombre}, "handle": {g.IDIOMA: handle},
                                                  "parent": CYBER})["id"]
        ids_nuevas[clave] = cid
    if aplicar:
        api.req("PUT", f"/categories/{CYBER}", {"name": {g.IDIOMA: NOMBRE}, "handle": {g.IDIOMA: HANDLE}})
        for sid, (nombre, handle) in RENOMBRAR.items():
            api.req("PUT", f"/categories/{sid}", {"name": {g.IDIOMA: nombre}, "handle": {g.IDIOMA: handle},
                                                   "parent": CYBER})
        api.req("PUT", f"/categories/{TEMPORADA}", {"name": {g.IDIOMA: TEMPORADA_NOMBRE},
                                                     "handle": {g.IDIOMA: TEMPORADA_HANDLE}})  # con "parent": 0 la API falla
    print(f"CYBERMONDAY -> {NOMBRE} (/{HANDLE}/) · {len(RENOMBRAR)} subcategorías renombradas")

    cambios = {}

    def agregar(p, *nuevas):
        base = cambios.get(p["id"], cats(p))
        cambios[p["id"]] = list(dict.fromkeys(base + [c for c in nuevas if c]))

    # 2) Megaofertas: rebajas de 10% o más + productos de valor alto (donde rinde CYBER10)
    rebajas = sorted((p for p in activos if promo_pct(p) >= 0.10), key=promo_pct, reverse=True)
    altos = sorted((p for p in activos if set(cats(p)) & {CYBER, *SUBS}
                    and TOPE_MEGA_ALTO <= precio(p) <= PRECIO_MAX), key=precio)
    mega = rebajas + [p for p in repartidos(altos, 16) if p not in rebajas]
    print(f"\n== Megaofertas: {len(mega)}")
    for p in mega:
        agregar(p, CYBER, ids_nuevas["megaofertas"])
        extra = f" ({promo_pct(p)*100:.0f}% off)" if promo_pct(p) else ""
        print(f"   ${precio(p):>11,.0f}{extra}  {t(p['name'])[:60]}")

    # 3) Novedades: lo último cargado con stock
    nuevos = sorted((p for p in activos if 50000 <= precio(p) <= PRECIO_MAX),
                    key=lambda p: p["created_at"], reverse=True)[:16]
    print(f"\n== Novedades: {len(nuevos)}")
    for p in nuevos:
        agregar(p, CYBER, ids_nuevas["novedades"])
        print(f"   {p['created_at'][:10]}  ${precio(p):>11,.0f}  {t(p['name'])[:55]}")

    # 4) Temporada: sacar estufas, poner verano
    sale = verano = 0
    for p in productos:
        es_verano = p.get("published") and con_stock(p) and re.search(VERANO_RX, t(p["name"]), re.I) \
            and not re.search(r"soporte|repuesto|control remoto", t(p["name"]), re.I)
        if TEMPORADA in cats(p) and not es_verano:
            base = cambios.get(p["id"], cats(p))
            cambios[p["id"]] = [c for c in base if c != TEMPORADA]
            sale += 1
        elif es_verano and TEMPORADA not in cats(p):
            agregar(p, TEMPORADA)
            verano += 1
    print(f"\n== {TEMPORADA_NOMBRE}: salen {sale} de invierno, entran {verano} de verano")

    if aplicar:
        for pid, nuevas in cambios.items():
            api.req("PUT", f"/products/{pid}", {"categories": nuevas})
    print(f"\n{len(cambios)} productos {'actualizados' if aplicar else 'a actualizar (simulación)'}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2 or sys.argv[1] != "armar":
        sys.exit(__doc__)
    api = g.Api(g.cargar_env())
    armar(api, list(api.productos()), "--aplicar" in sys.argv)


if __name__ == "__main__":
    main()
