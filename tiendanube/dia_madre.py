"""
Campaña Día de la Madre en Tiendanube.

  python dia_madre.py armar [--aplicar]        rearma la sección (subcategorías + productos)
  python dia_madre.py descuento [--aplicar]    5% real en ~30 destacados (guarda lista para revertir)
  python dia_madre.py revertir [--aplicar]     quita el descuento de los productos de la lista
"""
import json
import os
import re
import sys

import garantia as g

DDLM = 41063731
SUBS = {  # clave: (id existente o None, nombre, regex, máximo a agregar)
    "mimarse": (41327104, "Mamá que quiere mimarse",
                r"secador|plancha de cabello|planchita|rizador|ondulador|buclera|depiladora|cepillo secador|estilizador|alisador", 15),
    "relajarse": (41327103, "Mamá que necesita relajarse",
                  r"cafetera|nespresso|espumador|pava el", 15),
    "desconectar": (41327105, "Mamá que necesita desconectar",
                    r"^(?!.*(soporte|tr[ií]pode)).*(parlante|auricular|tablet|proyector)", 10),
    "cocina": (None, "Mamá en la cocina",
               r"freidora|air ?fryer|batidora|multiprocesadora|tostadora|sandwichera|licuadora|exprimidor", 15),
    "casa": (None, "Casa sin esfuerzo",
             r"aspiradora robot|robot aspiradora|aspiradora de mano|aspiradora vertical", 10),
}
PRECIO_MAX = 600000
DESCUENTO = 0.05
DESTACADOS_POR_SUB = 6
LISTA = os.path.join(g.AQUI, "dia_madre_descuentos.json")


def t(v):
    return g.txt(v) or ""


def base_variant(p):
    for v in p["variants"]:
        vals = [t(x) for x in v.get("values") or []]
        if not vals or g.SIN_GARANTIA in vals:
            return v
    return p["variants"][0]


def con_stock(p):
    v = base_variant(p)
    return v.get("stock") is None or v.get("stock", 0) > 0


def precio(p):
    return float(base_variant(p).get("price") or 0)


def cats(p):
    return [c["id"] for c in p.get("categories") or []]


def repartidos(lista, n):
    """n elementos repartidos a lo largo de la lista ordenada por precio."""
    if len(lista) <= n:
        return lista
    paso = (len(lista) - 1) / (n - 1)
    return [lista[round(i * paso)] for i in range(n)]


def armar(api, productos, aplicar):
    sub_ids = {}
    for clave, (cid, nombre, _, _) in SUBS.items():
        if cid is None:
            print(f"+ crear subcategoría '{nombre}'")
            if aplicar:
                c = api.req("POST", "/categories", {"name": {g.IDIOMA: nombre}, "parent": DDLM})
                cid = c["id"]
        sub_ids[clave] = cid

    todas_ddlm = {DDLM} | {c for c in sub_ids.values() if c}
    cambios = {}  # product_id -> nueva lista de categorías

    # 1) sacar los que no tienen stock o están ocultos
    for p in productos:
        if set(cats(p)) & todas_ddlm and (not p.get("published") or not con_stock(p)):
            nuevas = [c for c in cats(p) if c not in todas_ddlm]
            cambios[p["id"]] = nuevas
            print(f"- quitar (sin stock/oculto): {t(p['name'])[:70]}")

    # 2) agregar candidatos por subcategoría
    usados = {p["id"] for p in productos if set(cats(p)) & todas_ddlm}
    for clave, (_, nombre, rx, maximo) in SUBS.items():
        cand = sorted((p for p in productos
                       if p.get("published") and con_stock(p) and p["id"] not in usados
                       and 0 < precio(p) <= PRECIO_MAX and re.search(rx, t(p["name"]), re.I)),
                      key=precio)
        elegidos = repartidos(cand, maximo)
        print(f"\n== {nombre}: +{len(elegidos)} (de {len(cand)} candidatos)")
        for p in elegidos:
            usados.add(p["id"])
            nuevas = cats(p) + [DDLM] + ([sub_ids[clave]] if sub_ids[clave] else [])
            cambios[p["id"]] = list(dict.fromkeys(nuevas))
            print(f"   ${precio(p):>11,.0f}  {t(p['name'])[:65]}")

    if aplicar:
        for pid, nuevas in cambios.items():
            if None in nuevas:
                continue
            api.req("PUT", f"/products/{pid}", {"categories": nuevas})
    print(f"\n{len(cambios)} productos {'actualizados' if aplicar else 'a actualizar (simulación)'}")


def descuento(api, productos, aplicar):
    hijos = {c["id"] for c in api.req("GET", "/categories?per_page=200") if c.get("parent") == DDLM}
    lista = []
    for cid in sorted(hijos):
        en_sub = sorted((p for p in productos
                         if cid in cats(p) and p.get("published") and con_stock(p)
                         and not base_variant(p).get("promotional_price") and precio(p) > 0),
                        key=precio, reverse=True)
        lista += en_sub[:DESTACADOS_POR_SUB]
    guardado = []
    for p in lista:
        v = base_variant(p)
        nuevo = f"{round(precio(p) * (1 - DESCUENTO) / 100) * 100:.2f}"
        print(f"  {t(p['name'])[:60]}: ${precio(p):,.0f} -> ${float(nuevo):,.0f}")
        guardado.append({"product_id": p["id"], "variant_id": v["id"]})
        if aplicar:
            api.req("PUT", f"/products/{p['id']}/variants/{v['id']}", {"promotional_price": nuevo})
    if aplicar:
        json.dump(guardado, open(LISTA, "w"))
    print(f"\n{len(lista)} productos con 5% off {'aplicado' if aplicar else '(simulación)'}")


def revertir(api, aplicar):
    lista = json.load(open(LISTA)) if os.path.exists(LISTA) else []
    for item in lista:
        print(f"  quitar promo variante {item['variant_id']}")
        if aplicar:
            api.req("PUT", f"/products/{item['product_id']}/variants/{item['variant_id']}",
                    {"promotional_price": ""})  # "" borra la promo; None la ignora la API
    print(f"{len(lista)} descuentos {'quitados' if aplicar else 'a quitar (simulación)'}"
          " — después corré: python garantia.py --recientes 2 --aplicar")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2 or sys.argv[1] not in ("armar", "descuento", "revertir"):
        sys.exit(__doc__)
    aplicar = "--aplicar" in sys.argv
    api = g.Api(g.cargar_env())
    if sys.argv[1] == "revertir":
        return revertir(api, aplicar)
    productos = list(api.productos())
    (armar if sys.argv[1] == "armar" else descuento)(api, productos, aplicar)


if __name__ == "__main__":
    main()
