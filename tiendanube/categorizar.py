"""Propone (y con --aplicar asigna) categorías a productos publicados sin categoría."""
import json, re, sys
import garantia as g

REGLAS = [  # (regex sobre el nombre, id de categoría hoja) — gana la primera que coincide
    (r"iphone", 34317749),
    (r"samsung (galaxy|s2\d)", 39877577),
    (r"cable usb", 30783414),
    (r"smart tv|tv led", 33934482),
    (r"soundbar|barra de sonido", 30783772),
    (r"parlante|sistema de audio", 30783771),
    (r"\bradio\b", 34342233),
    (r"monitor", 30783774),
    (r"soporte tv", 33236252),
    (r"consola|playstation", 35241954),
    (r"pc box|all in one", 30783450),
    (r"grabador de voz|mochila|cerradura", 30783440),
    (r"lavasecarropas|lavarropas", 30783492),
    (r"secarropas", 33304988),
    (r"lavavajillas", 30783494),
    (r"heladera", 30783495),
    (r"cava de vino", 30783496),
    (r"freezer", 30783497),
    (r"microondas", 30783499),
    (r"horno el[eé]ctrico(?!.*empotrar)", 33742530),
    (r"horno|anafe|cocina a gas", 30783498),
    (r"termotanque|calef[oó]n", 30783500),
    (r"aspiradora|vaporizador de pisos", 33236289),
    (r"campana", 34802793),
    (r"purificador", 33302692),
    (r"aire acondicionado", 30783651),
    (r"ventilador", 30783652),
    (r"estufa a gas", 30783655),
    (r"calefactor", 30783654),
    (r"cafetera", 30783584),
    (r"tostadora", 30783585),
    (r"plancha de cabello", 34076904),
    (r"plancha", 30783589),
    (r"pava", 30783590),
    (r"licuadora|mixer", 30841330),
    (r"exprimidor", 33237599),
    (r"parrilla", 33238503),
    (r"batidora", 33301713),
    (r"picadora", 33447086),
    (r"termo el[eé]ctrico", 33847961),
    (r"cuchillo el[eé]ctrico", 30783583),
    (r"secador de cabello|estilizador", 30783777),
    (r"depiladora", 30783780),
    (r"cortabarba|cortadora|clipper|trimmer", 33237084),
    (r"afeitadora", 30783779),
    (r"tensi[oó]metro|term[oó]metro", 34076862),
]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    aplicar = "--aplicar" in sys.argv
    api = g.Api(g.cargar_env())
    cats = {c["id"]: c for c in api.req("GET", "/categories?per_page=200")}

    def ancestros(cid):
        ids = []
        while cid:
            ids.insert(0, cid)
            cid = cats[cid].get("parent")
        return ids

    ruta = lambda cid: " > ".join(g.txt(cats[i]["name"]).strip() for i in ancestros(cid))
    sin = [p for p in api.productos() if p.get("published") and not p.get("categories")]
    propuesta, sin_regla = [], []
    for p in sin:
        nombre = g.txt(p["name"])
        cid = next((c for rx, c in REGLAS if re.search(rx, nombre, re.I)), None)
        (propuesta if cid else sin_regla).append((p["id"], nombre, cid))

    filas = sorted(propuesta, key=lambda x: ruta(x[2]))
    with open("propuesta_categorias.csv", "w", encoding="utf-8-sig") as f:
        f.write("id;producto;categoria\n")
        for pid, nombre, cid in filas:
            f.write(f"{pid};{nombre};{ruta(cid)}\n")
        for pid, nombre, _ in sin_regla:
            f.write(f"{pid};{nombre};SIN CLASIFICAR\n")

    resumen = {}
    for _, _, cid in filas:
        resumen[ruta(cid)] = resumen.get(ruta(cid), 0) + 1
    for r, n in sorted(resumen.items()):
        print(f"{n:>4}  {r}")
    print(f"\nClasificados: {len(propuesta)}  Sin clasificar: {len(sin_regla)}")
    for pid, nombre, _ in sin_regla:
        print("  ?", pid, nombre)

    if aplicar:
        for pid, nombre, cid in propuesta:
            api.req("PUT", f"/products/{pid}", {"categories": ancestros(cid)})
        print(f"\nAsignadas {len(propuesta)} categorías.")


if __name__ == "__main__":
    main()
