"""Catálogo de Tiendanube en memoria, con búsqueda por palabras clave.

Se carga al arrancar y se refresca solo cada REFRESCO_MIN minutos, así el bot
siempre da precios y stock actuales (incluida la garantía extendida).
"""
import html
import json
import logging
import math
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.request

ATRIBUTO_GARANTIA = "Extendé tu garantía"
SIN_EXTENSION = "Sin extensión"
VACIAS = {"de", "la", "el", "los", "las", "para", "con", "un", "una", "que", "y", "en", "por",
          "del", "al", "mas", "tenes", "tienen", "hay", "precio", "quiero", "busco", "algun", "alguna"}

log = logging.getLogger("catalogo")


def txt(v):
    if isinstance(v, dict):
        return v.get("es") or next(iter(v.values()), "") or ""
    return v or ""


def normalizar(s):
    s = unicodedata.normalize("NFKD", str(s).lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def palabras(s):
    return [p for p in normalizar(s).split() if p not in VACIAS]


def coincide(q, t):
    """'heladeras' ~ 'heladera', 'televisores' ~ 'televisor'; palabras cortas deben ser iguales."""
    if q == t:
        return True
    return len(q) >= 4 and len(t) >= 4 and (t.startswith(q) or q.startswith(t))


def _precio(v):
    promo = v.get("promotional_price")
    if promo not in (None, "") and float(promo) > 0:
        return float(promo)
    return float(v.get("price") or 0)


def _disponible(v):
    if not v.get("stock_management") or v.get("stock") is None:
        return True
    return v["stock"] > 0


def resumir(p):
    """Producto de la API -> dict compacto con opciones, precio y planes de garantía."""
    attrs = [txt(a) for a in p.get("attributes") or []]
    gi = attrs.index(ATRIBUTO_GARANTIA) if ATRIBUTO_GARANTIA in attrs else None
    opciones = {}
    for v in p.get("variants") or []:
        vals = [txt(x) for x in v.get("values") or []]
        if gi is not None and gi < len(vals):
            plan = vals[gi]
            clave = " / ".join(x for j, x in enumerate(vals) if j != gi)
        else:
            plan, clave = SIN_EXTENSION, " / ".join(vals)
        o = opciones.setdefault(clave, {"opcion": clave or "única", "garantia_extendida": {}})
        if plan == SIN_EXTENSION:
            o["precio"] = _precio(v)
            if _precio(v) < float(v.get("price") or 0):
                o["precio_antes"] = float(v["price"])
            o["disponible"] = _disponible(v)
        else:
            o["garantia_extendida"][plan] = _precio(v)
    lista = []
    for o in opciones.values():
        if "precio" not in o:
            continue
        o["garantia_extendida"] = {
            plan: {"precio_total": round(total), "adicional": round(total - o["precio"])}
            for plan, total in o["garantia_extendida"].items()}
        o["precio"] = round(o["precio"])
        lista.append(o)
    desc = re.sub(r"<[^>]+>", " ", html.unescape(txt(p.get("description"))))
    return {
        "id": p["id"],
        "nombre": txt(p.get("name")),
        "marca": p.get("brand") or "",
        "categorias": [txt(c.get("name")) for c in p.get("categories") or []],
        "url": p.get("canonical_url") or "",
        "envio_gratis": bool(p.get("free_shipping")),
        "descripcion": " ".join(desc.split())[:1500],
        "opciones": lista,
    }


class Catalogo:
    def __init__(self, store_id, token, email, refresco_min=30):
        self.base = f"https://api.tiendanube.com/v1/{store_id}"
        self.headers = {"Authentication": f"bearer {token}",
                        "User-Agent": f"TengoStockBot ({email})"}
        self.refresco = refresco_min * 60
        self.productos = {}
        self._indice = []

    def _get(self, ruta):
        for i in range(5):
            req = urllib.request.Request(self.base + ruta, headers=self.headers)
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    time.sleep(0.5)  # límite de la API de Tiendanube: ~2 pedidos por segundo
                    return json.loads(r.read().decode() or "null")
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None
                if e.code == 429 or e.code >= 500:
                    time.sleep(2 * (i + 1))
                    continue
                raise
            except urllib.error.URLError:
                time.sleep(2 * (i + 1))
        raise RuntimeError(f"Tiendanube no responde: {ruta}")

    def cargar(self):
        nuevos, pagina = {}, 1
        while True:
            lote = self._get(f"/products?published=true&per_page=200&page={pagina}")
            if not lote:
                break
            for p in lote:
                if p.get("published"):
                    r = resumir(p)
                    if r["opciones"]:
                        nuevos[r["id"]] = r
            pagina += 1
        indice = []
        for r in nuevos.values():
            nombre = set(palabras(r["nombre"]))
            resto = set(palabras(r["marca"] + " " + " ".join(r["categorias"]))) - nombre
            indice.append((r, nombre, resto))
        self.productos, self._indice = nuevos, indice  # reemplazo atómico
        log.info("catálogo cargado: %d productos", len(nuevos))

    def iniciar(self):
        """Carga y refresca el catálogo en segundo plano (no demora el arranque de la app)."""
        def bucle():
            espera = 0
            while True:
                time.sleep(espera)
                try:
                    self.cargar()
                    espera = self.refresco
                except Exception:
                    log.exception("no se pudo cargar el catálogo (reintento en 1 minuto)")
                    espera = 60

        threading.Thread(target=bucle, daemon=True).start()

    def buscar(self, consulta, precio_maximo=0, limite=8):
        q = palabras(consulta)
        if not q:
            return []
        # al menos la mitad de las palabras deben aparecer (en el nombre valen el doble)
        umbral = 1 if len(q) == 1 else 2 * math.ceil(len(q) / 2) - 1
        hallados = []
        for r, nombre, resto in self._indice:
            puntos = 0
            for w in q:
                if any(coincide(w, t) for t in nombre):
                    puntos += 2
                elif any(coincide(w, t) for t in resto):
                    puntos += 1
            if puntos < umbral:
                continue
            mejor = min(r["opciones"], key=lambda o: (not o["disponible"], o["precio"]))
            if precio_maximo and mejor["precio"] > precio_maximo:
                continue
            hallados.append((puntos, mejor["disponible"], mejor["precio"], r))
        hallados.sort(key=lambda x: (-x[0], not x[1], x[2]))
        return [{
            "id": r["id"], "nombre": r["nombre"], "marca": r["marca"],
            "precio_desde": precio, "hay_stock": disp, "url": r["url"],
            "opciones": len(r["opciones"]),
            "tiene_garantia_extendida": any(o["garantia_extendida"] for o in r["opciones"]),
        } for _, disp, precio, r in hallados[:limite]]

    def detalle(self, producto_id):
        return self.productos.get(int(producto_id))
