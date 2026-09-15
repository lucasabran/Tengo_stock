"""
scraper_manual.py
==================
Script AUTOCONTENIDO (no depende de ningun otro archivo del proyecto) para
bajar TODO el catalogo de rodo.com.ar a un excel, con todos los datos que
despues hacen falta para publicar en Mercado Libre: titulo, descripcion
(armada con la ficha tecnica de Rodo), precio con margen, fotos, categoria,
marca, y una estimacion de peso/dimensiones de paquete.

No necesita login ni credenciales de nada -- Rodo expone esta informacion
publicamente via su API GraphQL (la misma que usa su propio sitio web).

Requisitos (una sola vez):
    pip install requests openpyxl

Uso basico (baja TODO el catalogo):
    python scraper_manual.py

Uso con opciones:
    python scraper_manual.py --out mi_catalogo.xlsx --markup 1.02
    python scraper_manual.py --limit 50              # prueba chica primero
    python scraper_manual.py --category-id 495        # solo una subcategoria

Que hacer con el excel que genera este script:
    Se lo pasas tal cual a ml_upload.py para publicar en Mercado Libre:
        python ml_upload.py --in productos_rodo.xlsx --dry-run --limit 5
    Ver MANUAL.md para el resto del proceso.
"""
import argparse
import re
import sys
import time
import unicodedata

import requests
from openpyxl import Workbook

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_URL_DEFAULT = "https://www.rodo.com.ar"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
REQUEST_DELAY_SECONDS = 0.5
REQUEST_TIMEOUT = 30
PAGE_SIZE = 50
ATTRIBUTE_CODES_TO_SKIP = {"atencion"}

# ---------------------------------------------------------------------------
# Queries GraphQL contra la API publica de Rodo (Magento)
# ---------------------------------------------------------------------------

PRODUCTS_QUERY = """
query ($categoryId: String!, $pageSize: Int!, $currentPage: Int!) {
  products(filter: {category_id: {eq: $categoryId}}, pageSize: $pageSize, currentPage: $currentPage) {
    total_count
    items {
      sku
      name
      url_key
      stock_status
      description { html }
      short_description { html }
      media_gallery { url }
      categories { id name }
      price_range {
        minimum_price {
          regular_price { value currency }
          final_price { value }
        }
      }
      custom_attributesV2(filters: {is_visible_on_front: true}) {
        items {
          code
          ... on AttributeValue { value }
          ... on AttributeSelectedOptions { selected_options { label } }
        }
      }
    }
  }
}
"""

CATEGORY_QUERY = """
{
  categoryList(filters: {ids: {eq: "2"}}) {
    children {
      id
      name
      url_path
      product_count
    }
  }
}
"""

ATTRIBUTE_LABELS_QUERY = """
query ($attrs: [AttributeInput!]!) {
  customAttributeMetadataV2(attributes: $attrs) {
    items { code label }
  }
}
"""

# ---------------------------------------------------------------------------
# Estimacion de peso/dimensiones de paquete (Mercado Libre lo exige para
# publicar y Rodo no lo publica). Mismos valores que usa ml_upload.py --
# si los cambias aca, cambialos alla tambien para que no queden distintos.
# (alto_cm, ancho_cm, largo_cm, peso_g) -- estimaciones conservadoras.
# ---------------------------------------------------------------------------

PACKAGE_DEFAULT = (20, 20, 20, 1000)

PACKAGE_KEYWORDS = [
    (("heladera", "freezer", "refrigerador"), (160, 70, 70, 60000)),
    (("lavarropas", "lavaseca", "secarropas"), (90, 60, 65, 40000)),
    (("aire acondicionado", "split", "acondicionado"), (35, 80, 30, 15000)),
    (("lavavajillas",), (85, 60, 60, 35000)),
    (("cocina", "horno empotrable", "anafe"), (90, 60, 60, 30000)),
    (("tv", "smart tv", "televisor", "qled"), (10, 100, 60, 9000)),
    (("notebook", "laptop"), (5, 35, 25, 2200)),
    (("celular", "smartphone", "iphone"), (5, 16, 8, 300)),
    (("tablet",), (8, 25, 18, 600)),
    (("microondas",), (30, 45, 35, 12000)),
    (("licuadora", "batidora", "mixer"), (25, 20, 20, 2000)),
    (("cafetera",), (30, 25, 20, 2500)),
    (("impresora",), (30, 40, 40, 5000)),
    (("consola",), (18, 40, 30, 3000)),
    (("auricular", "parlante", "speaker"), (15, 20, 15, 800)),
]

CATEGORY_ESTIMATES = {
    "celulares": (5, 16, 8, 300),
    "telefonia": (8, 20, 15, 500),
    "imagen y sonido": (15, 60, 40, 8000),
    "electrodomesticos": (35, 40, 35, 6000),
    "electro hogar": (25, 30, 25, 3000),
    "informatica": (10, 40, 30, 2500),
    "climatizacion": (40, 70, 30, 12000),
    "cuidado personal": (10, 15, 10, 500),
    "deporte y aire libre": (25, 30, 20, 2000),
}

BRAND_ATTR_LINE = re.compile(r"^\s*Marca\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)


def strip_accents(text):
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def estimate_package(title, category_name):
    text = (title or "").lower()
    for keywords, dims in PACKAGE_KEYWORDS:
        if any(re.search(rf"\b{re.escape(k.strip())}\b", text) for k in keywords):
            return dims
    return CATEGORY_ESTIMATES.get((category_name or "").strip().lower(), PACKAGE_DEFAULT)


def guess_brand(description):
    m = BRAND_ATTR_LINE.search(description or "")
    return m.group(1).strip() if m else ""


# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------

def make_session():
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "es-AR,es;q=0.9"})
    return s


def graphql(session, base_url, query, variables=None):
    resp = session.post(f"{base_url}/graphql", json={"query": query, "variables": variables or {}},
                         timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    return data.get("data") or {}, data.get("errors")


def discover_root_category(session, base_url):
    data, _ = graphql(session, base_url, CATEGORY_QUERY)
    children = data["categoryList"][0]["children"]
    if not children:
        raise RuntimeError("No se encontraron categorias debajo de Home")
    return max(children, key=lambda c: c["product_count"])


def strip_html(html):
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class AttributeLabelCache:
    """Traduce codigos internos de atributo (ej. 'tam_pantalla') a su nombre
    legible (ej. 'Tamaño de Pantalla'), consultando la API de a lotes."""

    def __init__(self, session, base_url):
        self.session = session
        self.base_url = base_url
        self.labels = {}

    def ensure(self, codes):
        missing = sorted({c for c in codes if c not in self.labels})
        if not missing:
            return
        attrs = [{"attribute_code": c, "entity_type": "catalog_product"} for c in missing]
        data, _ = graphql(self.session, self.base_url, ATTRIBUTE_LABELS_QUERY, {"attrs": attrs})
        for item in (data.get("customAttributeMetadataV2") or {}).get("items", []):
            self.labels[item["code"]] = item["label"]
        for code in missing:
            self.labels.setdefault(code, code.replace("_", " ").strip().capitalize())

    def label(self, code):
        return self.labels.get(code, code.replace("_", " ").strip().capitalize())


def attribute_value_text(attr):
    if attr.get("value"):
        return attr["value"]
    options = attr.get("selected_options") or []
    labels = [o["label"] for o in options if o.get("label")]
    return ", ".join(labels)


def build_description(custom_attrs, label_cache):
    """Arma la descripcion con la ficha tecnica (Marca, Modelo, Pantalla,
    etc.) porque el campo 'descripcion larga' de Rodo viene vacio para la
    mayoria de los productos de este catalogo."""
    items = (custom_attrs or {}).get("items") or []
    lines = []
    for attr in items:
        code = attr["code"]
        if code in ATTRIBUTE_CODES_TO_SKIP:
            continue
        value = attribute_value_text(attr)
        if not value:
            continue
        lines.append(f"{label_cache.label(code)}: {value}")
    return "\n".join(lines)


def fetch_all_products(session, base_url, category_id, label_cache, limit=0):
    rows_raw = []
    page = 1
    total = None
    while True:
        data, errors = graphql(session, base_url, PRODUCTS_QUERY,
                                {"categoryId": str(category_id), "pageSize": PAGE_SIZE, "currentPage": page})
        block = data.get("products")
        if not block:
            print(f"  pagina {page}: sin datos ({errors})")
            break
        total = block["total_count"]
        items = block["items"]

        codes = set()
        for item in items:
            for attr in (item.get("custom_attributesV2") or {}).get("items") or []:
                codes.add(attr["code"])
        label_cache.ensure(codes)

        rows_raw.extend(items)
        print(f"  pagina {page}: {len(rows_raw)}/{total}")
        if limit and len(rows_raw) >= limit:
            rows_raw = rows_raw[:limit]
            break
        if len(rows_raw) >= total or not items:
            break
        page += 1
        time.sleep(REQUEST_DELAY_SECONDS)
    return rows_raw


def to_row(base_url, item, markup, label_cache):
    regular = item["price_range"]["minimum_price"]["regular_price"]["value"]
    final = item["price_range"]["minimum_price"]["final_price"]["value"]
    currency = item["price_range"]["minimum_price"]["regular_price"]["currency"]
    price_original = final or regular
    price_ml = round(price_original * markup, 2) if price_original else ""

    description = build_description(item.get("custom_attributesV2"), label_cache)
    if not description:
        description = strip_html(item["description"]["html"]) or strip_html(item["short_description"]["html"])

    images = [img["url"] for img in (item.get("media_gallery") or []) if img.get("url")]
    url = f"{base_url}/{item['url_key']}.html"
    categories = item.get("categories") or []
    category_name = categories[-1]["name"] if categories else ""

    brand = guess_brand(description)
    height, width, length, weight = estimate_package(item["name"], category_name)

    return [
        url, item["sku"], item["name"], description,
        price_original or "", price_ml, currency,
        "|".join(images), category_name, item.get("stock_status", ""),
        brand, height, width, length, weight,
    ]


# Caracteres de control que XML/openpyxl no aceptan en una celda (a veces
# aparecen colados en el texto scrapeado de Rodo, ej. un nebulizador con un
# caracter invisible en las "Caracteristicas Adicionales").
ILLEGAL_XLSX_CHARS_RE = re.compile(
    "[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\ud800-\udfff￾￿]"
)


def sanitize_for_xlsx(value):
    if isinstance(value, str):
        return ILLEGAL_XLSX_CHARS_RE.sub("", value)
    return value


def export_xlsx(rows, out_path):
    wb = Workbook()
    ws = wb.active
    ws.title = "productos"
    headers = [
        "url", "sku", "title", "description", "price_original",
        "price_ml", "currency", "images", "category", "availability",
        "brand", "package_height_cm", "package_width_cm",
        "package_length_cm", "package_weight_g",
    ]
    ws.append(headers)
    for row in rows:
        ws.append([sanitize_for_xlsx(v) for v in row])
    wb.save(out_path)


def main():
    parser = argparse.ArgumentParser(
        description="Baja TODO el catalogo de rodo.com.ar (autocontenido, sin dependencias del proyecto)")
    parser.add_argument("--base-url", default=BASE_URL_DEFAULT)
    parser.add_argument("--out", default="productos_rodo.xlsx",
                         help="Archivo excel de salida (default: productos_rodo.xlsx)")
    parser.add_argument("--markup", type=float, default=1.8,
                         help="Multiplicador de precio de referencia (1.8 = +80%%, default). Es"
                              " solo informativo: ml_upload.py recalcula el precio real al"
                              " publicar (con markup distinto para chico/grande, ver MANUAL.md).")
    parser.add_argument("--limit", type=int, default=0,
                         help="Limite de productos a bajar (0 = TODO el catalogo, default)")
    parser.add_argument("--category-id", type=int, default=0,
                         help="ID de categoria de Rodo puntual a recorrer (0 = todo el catalogo, default)")
    args = parser.parse_args()

    session = make_session()
    label_cache = AttributeLabelCache(session, args.base_url)

    if args.category_id:
        category_id = args.category_id
    else:
        print("Detectando categoria raiz del catalogo...")
        cat = discover_root_category(session, args.base_url)
        category_id = cat["id"]
        print(f"Usando categoria '{cat['name']}' (id={category_id}, {cat['product_count']} productos)")

    print("Descargando productos via GraphQL (puede tardar varios minutos para el catalogo completo)...")
    items = fetch_all_products(session, args.base_url, category_id, label_cache, args.limit)

    rows = [to_row(args.base_url, item, args.markup, label_cache) for item in items]
    export_xlsx(rows, args.out)
    print(f"\nListo. {len(rows)} productos exportados a {args.out}")
    print("Siguiente paso: python ml_upload.py --in", args.out, "--dry-run --limit 5")


if __name__ == "__main__":
    main()
