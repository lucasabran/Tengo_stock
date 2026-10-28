"""Banners Cyber Week (escritorio 1920x640 y celular 800x1000) para el carrusel de la home.
Sirven antes y durante el evento: dicen las fechas, no los códigos."""
import os
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "pmax"))
from hacer_recursos import recortar  # noqa: E402

F = "C:/Windows/Fonts/"
NEGRA, BOLD, SEMI = F + "seguibl.ttf", F + "segoeuib.ttf", F + "seguisb.ttf"
EVENTO = ("CYBER", "WEEK")
FECHAS = "DEL 2 AL 8 DE NOVIEMBRE"
FONDO_1, FONDO_2 = (8, 12, 32), (18, 40, 110)
AMARILLO, CELESTE, BLANCO = (255, 214, 0), (90, 200, 255), (255, 255, 255)
FOTOS = [os.path.join(AQUI, "..", "pmax", f) for f in ("tv.jpg", "aire.jpg", "iphone.jpg", "lavarropas.jpg")]


def fuente(ruta, tam):
    return ImageFont.truetype(ruta, tam)


def fondo(w, h):
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        for_x = y / (h - 1)
        c = tuple(round(FONDO_1[i] + (FONDO_2[i] - FONDO_1[i]) * for_x) for i in range(3))
        d.line([(0, y), (w, y)], fill=c)
    # brillo diagonal
    luz = Image.new("L", (w, h), 0)
    ImageDraw.Draw(luz).ellipse([int(w * 0.45), -h // 2, int(w * 1.2), int(h * 1.2)], fill=90)
    luz = luz.filter(ImageFilter.GaussianBlur(120))
    img.paste(Image.new("RGB", (w, h), (40, 90, 220)), (0, 0), luz)
    return img


def rayo(d, x, y, s, color=AMARILLO):
    d.polygon([(x + 0.55 * s, y), (x + 0.1 * s, y + 0.58 * s), (x + 0.45 * s, y + 0.58 * s),
               (x + 0.3 * s, y + s), (x + 0.9 * s, y + 0.38 * s), (x + 0.52 * s, y + 0.38 * s),
               (x + 0.75 * s, y)], fill=color)


def tarjeta(ruta, lado):
    prod = recortar(ruta)
    prod.thumbnail((int(lado * 0.82), int(lado * 0.82)))
    card = Image.new("RGBA", (lado + 30, lado + 30), (0, 0, 0, 0))
    sombra = Image.new("RGBA", card.size, (0, 0, 0, 0))
    ImageDraw.Draw(sombra).rounded_rectangle([15, 22, lado + 15, lado + 22], 28, fill=(0, 0, 0, 110))
    card.alpha_composite(sombra.filter(ImageFilter.GaussianBlur(12)))
    blanco = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    ImageDraw.Draw(blanco).rounded_rectangle([0, 0, lado - 1, lado - 1], 28, fill=BLANCO)
    card.alpha_composite(blanco, (15, 15))
    card.paste(prod, (15 + (lado - prod.width) // 2, 15 + (lado - prod.height) // 2))
    return card


def boton(d, x, y, texto, f):
    w = d.textlength(texto, font=f) + 80
    d.rounded_rectangle([x, y, x + w, y + 76], 38, fill=AMARILLO)
    d.text((x + w / 2, y + 38), texto, font=f, fill=FONDO_1, anchor="mm")
    return w


def chip(d, x, y, texto, f):
    w = d.textlength(texto, font=f) + 40
    d.rounded_rectangle([x, y, x + w, y + 48], 24, outline=CELESTE, width=2)
    d.text((x + 20, y + 24), texto, font=f, fill=BLANCO, anchor="lm")
    return w


def escritorio():
    # Tamaño recomendado por el tema. El carrusel "a todo el ancho" recorta los costados en
    # pantallas chicas, así que todo el contenido va en la zona central (x 250 a 1340).
    W, H = 1580, 700
    img = fondo(W, H)
    d = ImageDraw.Draw(img)
    x = 250
    d.text((x, 92), FECHAS, font=fuente(BOLD, 30), fill=CELESTE)
    d.text((x, 125), EVENTO[0], font=fuente(NEGRA, 118), fill=BLANCO)
    d.text((x, 245), EVENTO[1], font=fuente(NEGRA, 118), fill=AMARILLO)
    d.text((x, 400), "Hasta 10% OFF extra con tu código", font=fuente(SEMI, 34), fill=BLANCO)
    cx = x
    for t in ["3 y 6 cuotas sin interés", "Garantía extendida"]:
        cx += chip(d, cx, 462, t, fuente(SEMI, 22)) + 12
    boton(d, x, 548, "VER OFERTAS  →", fuente(BOLD, 28))
    lado = 230
    for ruta, (px, py) in zip(FOTOS, [(870, 100), (1110, 100), (870, 350), (1110, 350)]):
        c = tarjeta(ruta, lado - 10)
        img.paste(c, (px, py), c)
    img.save(os.path.join(AQUI, "banner_cyberweek_escritorio.jpg"), quality=90)


def celular():
    W, H = 800, 1000
    img = fondo(W, H)
    d = ImageDraw.Draw(img)
    d.text((W / 2, 64), FECHAS, font=fuente(BOLD, 30), fill=CELESTE, anchor="mm")
    f = fuente(NEGRA, 104)
    total = d.textlength("".join(EVENTO), font=f)
    x0 = (W - total) / 2
    d.text((x0, 150), EVENTO[0], font=f, fill=BLANCO, anchor="lm")
    d.text((x0 + d.textlength(EVENTO[0], font=f), 150), EVENTO[1], font=f, fill=AMARILLO, anchor="lm")
    d.text((W / 2, 246), "Hasta 10% OFF extra", font=fuente(SEMI, 44), fill=BLANCO, anchor="mm")
    d.text((W / 2, 298), "con tu código · 3 y 6 cuotas sin interés", font=fuente(SEMI, 28), fill=CELESTE, anchor="mm")
    lado = 270
    for ruta, (px, py) in zip(FOTOS, [(125, 345), (415, 345), (125, 625), (415, 625)]):
        c = tarjeta(ruta, lado - 30)
        img.paste(c, (px, py), c)
    fb = fuente(BOLD, 30)
    w = d.textlength("VER OFERTAS  →", font=fb) + 80
    boton(d, (W - w) / 2, 906, "VER OFERTAS  →", fb)
    img.save(os.path.join(AQUI, "banner_cyberweek_celular.jpg"), quality=90)


if __name__ == "__main__":
    escritorio()
    celular()
    print("ok")
