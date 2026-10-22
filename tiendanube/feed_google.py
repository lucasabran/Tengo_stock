"""
Genera feed_google_complementario.tsv para Merchant Center (fuente complementaria).

- Variantes de garantía (12/24/36/60 meses): se excluyen de anuncios y fichas gratuitas.
- Variante "Sin extensión": se limpia el título (sin "(Sin extensión)").

El ID de producto en Merchant Center es el ID de la variante en Tiendanube.

Uso: python feed_google.py
"""
import sys

import garantia as g

EXCLUIR = "Shopping_ads,Display_ads,Free_listings"
CAMPANAS = {41063731: "cyber"}  # categoría de Tiendanube -> custom_label_0 (vaciar al terminar la campaña)
SALIDA = "feed_google_complementario.tsv"


def limpio(texto):
    return " ".join(str(texto).replace("\t", " ").split())


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    api = g.Api(g.cargar_env())
    excluidas = titulos = etiquetados = 0
    with open(SALIDA, "w", encoding="utf-8", newline="") as f:
        f.write("id\texcluded_destination\ttitle\tcustom_label_0\n")
        for p in api.productos():
            nombres = [g.txt(a) for a in p.get("attributes") or []]
            nombre = limpio(g.txt(p.get("name")))
            etiqueta = next((CAMPANAS[c["id"]] for c in p.get("categories") or [] if c["id"] in CAMPANAS), "")
            if g.ATRIBUTO not in nombres:
                if etiqueta:  # producto sin garantía que igual entra en una campaña
                    for v in p["variants"]:
                        f.write(f"{v['id']}\t\t\t{etiqueta}\n")
                        etiquetados += 1
                continue
            idx = nombres.index(g.ATRIBUTO)
            for v in p["variants"]:
                valores = [g.txt(x) for x in v.get("values") or []]
                if len(valores) <= idx:
                    continue
                if valores[idx] == g.SIN_GARANTIA:
                    otros = [x for j, x in enumerate(valores) if j != idx]
                    titulo = f"{nombre} ({', '.join(otros)})" if otros else nombre
                    f.write(f"{v['id']}\t\t{limpio(titulo)[:150]}\t{etiqueta}\n")
                    titulos += 1
                    etiquetados += bool(etiqueta)
                else:
                    f.write(f"{v['id']}\t{EXCLUIR}\t\t\n")
                    excluidas += 1
    print(f"{SALIDA}: {excluidas} variantes de garantía excluidas, {titulos} títulos limpios, "
          f"{etiquetados} etiquetados para campaña")


if __name__ == "__main__":
    main()
