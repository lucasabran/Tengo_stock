"""
Garantía extendida para Tiendanube.

Agrega a cada producto una propiedad de variante "Garantía" con las opciones
Sin garantía / 1 / 2 / 3 / 5 años, y calcula el precio de cada una como
porcentaje sobre el precio base. Si el producto ya tiene la garantía,
re-sincroniza precios y stock con la variante base (usar tras cambiar precios).

Uso:
  python garantia.py --categorias                 # lista categorías con su ID
  python garantia.py --producto 123456            # simula en un producto
  python garantia.py --producto 123456 --aplicar  # aplica en un producto
  python garantia.py --categoria 789              # simula en una categoría
  python garantia.py --todos --aplicar            # aplica en toda la tienda

Sin --aplicar nunca se modifica nada (modo simulación).
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

# --- Configuración de planes -------------------------------------------------
ATRIBUTO = "Extendé tu garantía"
SIN_GARANTIA = "Sin extensión"
PLANES = [  # (texto de la variante, recargo, sufijo de SKU)
    ("12 meses", 0.12, "G1"),
    ("24 meses", 0.18, "G2"),
    ("36 meses", 0.25, "G3"),
    ("60 meses", 0.40, "G5"),
]
REDONDEO = 100  # redondea el precio final a múltiplos de $100 (1 = sin redondeo)
IDIOMA = "es"
# -----------------------------------------------------------------------------

AQUI = os.path.dirname(os.path.abspath(__file__))


def cargar_env():
    ruta = os.path.join(AQUI, ".env")
    if not os.path.exists(ruta):
        sys.exit("Falta el archivo .env (copiá config.example.env como .env y completalo).")
    env = {}
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if linea and not linea.startswith("#") and "=" in linea:
                k, v = linea.split("=", 1)
                env[k.strip()] = v.strip()
    for clave in ("STORE_ID", "ACCESS_TOKEN", "CONTACT_EMAIL"):
        if not env.get(clave):
            sys.exit(f"Falta {clave} en .env")
    return env


class Api:
    def __init__(self, env):
        self.base = f"https://api.tiendanube.com/v1/{env['STORE_ID']}"
        self.headers = {
            "Authentication": f"bearer {env['ACCESS_TOKEN']}",
            "User-Agent": f"GarantiaExtendida ({env['CONTACT_EMAIL']})",
            "Content-Type": "application/json",
        }

    def req(self, metodo, ruta, cuerpo=None, intentos=5):
        data = json.dumps(cuerpo).encode() if cuerpo is not None else None
        for i in range(intentos):
            r = urllib.request.Request(self.base + ruta, data=data, method=metodo, headers=self.headers)
            try:
                with urllib.request.urlopen(r, timeout=60) as resp:
                    time.sleep(0.5)  # límite de la API: ~2 pedidos por segundo
                    texto = resp.read().decode()
                    return json.loads(texto) if texto else None
            except urllib.error.HTTPError as e:
                if e.code == 429 or e.code >= 500:
                    time.sleep(2 * (i + 1))
                    continue
                if e.code == 404 and metodo == "GET":
                    return None
                raise RuntimeError(f"{metodo} {ruta} -> {e.code}: {e.read().decode()}")
        raise RuntimeError(f"{metodo} {ruta}: demasiados reintentos")

    def productos(self, desde=None):
        pagina = 1
        while True:
            q = f"/products?per_page=200&page={pagina}"
            if desde:
                q += f"&updated_at_min={desde}"
            lote = self.req("GET", q)
            if not lote:
                return
            yield from lote
            pagina += 1


def txt(v):
    return (v or {}).get(IDIOMA) or next(iter((v or {}).values()), "")


def calcular(precio, recargo):
    if precio in (None, ""):
        return None
    valor = float(precio) * (1 + recargo)
    return f"{round(valor / REDONDEO) * REDONDEO:.2f}"


def datos_variante(base, valores, recargo, sufijo):
    d = {
        "values": valores,
        "price": calcular(base.get("price"), recargo),
        "promotional_price": calcular(base.get("promotional_price"), recargo),
        "stock": base.get("stock"),
    }
    if base.get("sku"):
        d["sku"] = f"{base['sku']}-{sufijo}"
    for campo in ("weight", "width", "height", "depth"):
        if base.get(campo) is not None:
            d[campo] = base[campo]
    return d


def procesar(api, prod, aplicar):
    nombre = txt(prod.get("name"))
    pid = prod["id"]
    atributos = prod.get("attributes") or []
    nombres_attr = [txt(a) for a in atributos]
    variantes = prod.get("variants") or []
    log = []

    if ATRIBUTO in nombres_attr:
        # --- Ya tiene garantía: re-sincronizar precios y stock ---
        idx = nombres_attr.index(ATRIBUTO)
        # Reparar variantes que quedaron sin valor de garantía (proceso interrumpido)
        for v in variantes:
            if len(v["values"]) < len(atributos):
                v["values"] = list(v["values"]) + [{IDIOMA: SIN_GARANTIA}]
                log.append(f"  ! reparar variante {v['id']} -> {SIN_GARANTIA}")
                if aplicar:
                    api.req("PUT", f"/products/{pid}/variants/{v['id']}", {"values": v["values"]})
        clave = lambda v: tuple(txt(x) for j, x in enumerate(v["values"]) if j != idx)
        bases = {clave(v): v for v in variantes if txt(v["values"][idx]) == SIN_GARANTIA}
        existentes = {(clave(v), txt(v["values"][idx])): v for v in variantes}
        for k, base in bases.items():
            for texto, recargo, sufijo in PLANES:
                valores = list(base["values"])
                valores[idx] = {IDIOMA: texto}
                nuevo = datos_variante(base, valores, recargo, sufijo)
                actual = existentes.get((k, texto))
                if actual is None:
                    log.append(f"  + crear {texto} {k or ''} -> ${nuevo['price']}")
                    if aplicar:
                        api.req("POST", f"/products/{pid}/variants", nuevo)
                elif (actual.get("price"), actual.get("promotional_price"), actual.get("stock")) != (
                    nuevo["price"], nuevo["promotional_price"], nuevo["stock"]):
                    log.append(f"  ~ actualizar {texto} {k or ''}: ${actual.get('price')} -> ${nuevo['price']}")
                    if aplicar:
                        cambios = {c: nuevo[c] for c in ("price", "promotional_price", "stock")}
                        if cambios["promotional_price"] is None:
                            cambios["promotional_price"] = ""  # la API ignora None; "" borra la promo
                        api.req("PUT", f"/products/{pid}/variants/{actual['id']}", cambios)
        estado = "sincronizado" if log else "sin cambios"
    else:
        # --- Primera vez: agregar la propiedad "Garantía" ---
        if len(atributos) >= 3:
            print(f"[OMITIDO] {pid} {nombre}: ya tiene 3 propiedades de variante (máximo de Tiendanube)")
            return
        if any(not v.get("price") or float(v["price"]) <= 0 for v in variantes):
            print(f"[OMITIDO] {pid} {nombre}: tiene variantes sin precio")
            return
        if len(variantes) * (len(PLANES) + 1) > 1000:
            print(f"[OMITIDO] {pid} {nombre}: quedarían demasiadas variantes")
            return
        log.append(f"  agregar propiedad '{ATRIBUTO}' (propiedades actuales: {nombres_attr or 'ninguna'})")
        if aplicar:
            api.req("PUT", f"/products/{pid}", {"attributes": atributos + [{IDIOMA: ATRIBUTO}]})
        for base in variantes:
            etiqueta = " / ".join(txt(x) for x in base["values"]) or "única"
            valores_base = list(base["values"]) + [{IDIOMA: SIN_GARANTIA}]
            log.append(f"  variante {etiqueta}: base ${base.get('price')}")
            if aplicar:
                api.req("PUT", f"/products/{pid}/variants/{base['id']}", {"values": valores_base})
            for texto, recargo, sufijo in PLANES:
                nuevo = datos_variante(base, list(base["values"]) + [{IDIOMA: texto}], recargo, sufijo)
                log.append(f"    + {texto}: ${nuevo['price']}")
                if aplicar:
                    api.req("POST", f"/products/{pid}/variants", nuevo)
        estado = "garantía agregada"

    modo = "" if aplicar else " (simulación)"
    print(f"[{estado.upper()}{modo}] {pid} {nombre}")
    for l in log:
        print(l)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Garantía extendida como variante en Tiendanube")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--producto", type=int, help="ID de un producto")
    g.add_argument("--categoria", type=int, nargs="+", help="ID de una o más categorías (incluye subcategorías)")
    g.add_argument("--todos", action="store_true", help="todos los productos de la tienda")
    g.add_argument("--recientes", type=float, metavar="HORAS",
                   help="solo productos modificados en las últimas HORAS que ya tienen garantía")
    g.add_argument("--categorias", action="store_true", help="listar categorías y salir")
    p.add_argument("--aplicar", action="store_true", help="aplicar cambios (si no, solo simula)")
    a = p.parse_args()

    api = Api(cargar_env())

    if a.categorias:
        for c in api.req("GET", "/categories?per_page=200") or []:
            print(f"{c['id']:>10}  {txt(c.get('name'))}")
        return

    if a.producto:
        prod = api.req("GET", f"/products/{a.producto}")
        if not prod:
            sys.exit("Producto no encontrado")
        productos = [prod]
    elif a.recientes:
        import datetime
        desde = (datetime.datetime.now(datetime.timezone.utc)
                 - datetime.timedelta(hours=a.recientes)).strftime("%Y-%m-%dT%H:%M:%SZ")
        productos = (pr for pr in api.productos(desde)
                     if ATRIBUTO in [txt(x) for x in pr.get("attributes") or []])
    elif a.categoria:
        cats = api.req("GET", "/categories?per_page=200") or []
        ids = set(a.categoria)
        while True:  # sumar subcategorías de cualquier nivel
            hijas = {c["id"] for c in cats if c.get("parent") in ids} - ids
            if not hijas:
                break
            ids |= hijas
        productos = (pr for pr in api.productos()
                     if ids & {c["id"] for c in pr.get("categories") or []})
    else:
        productos = api.productos()

    errores = 0
    for prod in productos:
        try:
            procesar(api, prod, a.aplicar)
        except RuntimeError as e:
            errores += 1
            print(f"[ERROR] {prod['id']} {txt(prod.get('name'))}: {e}")
    if not a.aplicar:
        print("\nModo simulación: no se cambió nada. Agregá --aplicar para ejecutar.")
    if errores:
        print(f"\n{errores} producto(s) con error.")


if __name__ == "__main__":
    main()
