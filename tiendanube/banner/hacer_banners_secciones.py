"""Banners de las secciones de la landing Cyber Week (computadora 1560x465 y celular 820x820)
y banner de la categoría PREPARATE PARA EL VERANO."""
import os

from PIL import Image, ImageDraw

from hacer_banner_cyber import AMARILLO, BLANCO, BOLD, CELESTE, NEGRA, SEMI, fuente, tarjeta

AQUI = os.path.dirname(os.path.abspath(__file__))
FOTOS = os.path.join(AQUI, "..", "pmax")

SECCIONES = [  # (archivo, título, subtítulo, fotos, color 1, color 2, color del título)
    ("megaofertas", "MEGAOFERTAS", "Lo más buscado al mejor precio", ["tv", "lavarropas", "heladera2"],
     (90, 10, 30), (200, 30, 60), AMARILLO),
    ("novedades", "NOVEDADES", "Lo último que llegó a Tengo Stock", ["cocina", "heladera2", "notebook"],
     (10, 40, 60), (20, 120, 140), BLANCO),
    ("tecno", "TECNO", "Celulares, TV, audio y notebooks", ["iphone", "tv", "notebook"],
     (8, 12, 32), (60, 30, 140), CELESTE),
    ("verano", "VERANO", "Aires acondicionados y ventiladores", ["aire", "ventilador"],
     (0, 90, 160), (0, 170, 210), AMARILLO),
]


def fondo(w, h, c1, c2):
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for x in range(w):
        k = x / (w - 1)
        d.line([(x, 0), (x, h)], fill=tuple(round(c1[i] + (c2[i] - c1[i]) * k) for i in range(3)))
    return img


def escritorio(nombre, titulo, sub, fotos, c1, c2, ct, etiqueta="CYBER WEEK · 2 AL 8 DE NOVIEMBRE", tam=84):
    W, H = 1560, 465
    img = fondo(W, H, c1, c2)
    d = ImageDraw.Draw(img)
    x = 230  # zona segura: el carrusel recorta los costados en pantallas chicas
    d.text((x, 95), etiqueta, font=fuente(BOLD, 26), fill=CELESTE if ct != CELESTE else BLANCO)
    d.text((x, 135), titulo, font=fuente(NEGRA, tam), fill=ct)
    d.text((x, 250), sub, font=fuente(SEMI, 30), fill=BLANCO)
    f = fuente(BOLD, 26)
    w = d.textlength("VER PRODUCTOS  →", font=f) + 70
    d.rounded_rectangle([x, 330, x + w, 392], 31, fill=AMARILLO if ct != AMARILLO else BLANCO)
    d.text((x + w / 2, 361), "VER PRODUCTOS  →", font=f, fill=(10, 15, 35), anchor="mm")
    lado = 215  # en computadora van 2 fotos, a la derecha del texto
    x0 = 1345 - 2 * (lado + 10)
    for i, ruta in enumerate(fotos[:2]):
        c = tarjeta(os.path.join(FOTOS, ruta + ".jpg"), lado - 20)
        img.paste(c, (x0 + i * (lado + 10), 110), c)
    img.save(os.path.join(AQUI, f"seccion_{nombre}_escritorio.jpg"), quality=90)


def celular(nombre, titulo, sub, fotos, c1, c2, ct, etiqueta="CYBER WEEK · 2 AL 8/11"):
    W = H = 820
    img = fondo(W, H, c1, c2)
    d = ImageDraw.Draw(img)
    d.text((W / 2, 70), etiqueta, font=fuente(BOLD, 28), fill=CELESTE if ct != CELESTE else BLANCO, anchor="mm")
    d.text((W / 2, 160), titulo, font=fuente(NEGRA, 96), fill=ct, anchor="mm")
    d.text((W / 2, 245), sub, font=fuente(SEMI, 32), fill=BLANCO, anchor="mm")
    lado = 330 if len(fotos) == 2 else 240
    total = len(fotos) * lado + (len(fotos) - 1) * 10
    for i, ruta in enumerate(fotos):
        c = tarjeta(os.path.join(FOTOS, ruta + ".jpg"), lado - 20)
        img.paste(c, (int((W - total) / 2 + i * (lado + 10) - 15), 300), c)
    f = fuente(BOLD, 30)
    w = d.textlength("VER PRODUCTOS  →", font=f) + 80
    y = 300 + lado + 40
    d.rounded_rectangle([(W - w) / 2, y, (W + w) / 2, y + 72], 36, fill=AMARILLO if ct != AMARILLO else BLANCO)
    d.text((W / 2, y + 36), "VER PRODUCTOS  →", font=f, fill=(10, 15, 35), anchor="mm")
    img.save(os.path.join(AQUI, f"seccion_{nombre}_celular.jpg"), quality=90)


if __name__ == "__main__":
    for s in SECCIONES:
        escritorio(*s)
        celular(*s)
    # banner de la categoría de temporada (sin fechas de Cyber)
    escritorio("preparate_verano", "LLEGÓ EL CALOR", "Aires y ventiladores con stock",
               ["aire", "ventilador"], (0, 90, 160), (0, 170, 210), AMARILLO, etiqueta="PREPARATE PARA EL VERANO", tam=72)
    print("ok")
