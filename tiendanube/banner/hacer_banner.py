"""Genera los banners del Día de la Madre (escritorio y celular) para la home de Tengo Stock."""
from PIL import Image, ImageDraw, ImageFilter, ImageFont

F = "C:/Windows/Fonts/"
NEGRA = F + "seguibl.ttf"
BOLD = F + "segoeuib.ttf"
SEMI = F + "seguisb.ttf"
REG = F + "segoeui.ttf"

ROSA_1 = (253, 236, 242)
ROSA_2 = (248, 199, 218)
VINO = (122, 30, 72)
FUCSIA = (214, 51, 108)
AZUL = (21, 101, 192)
BLANCO = (255, 255, 255)
PRODUCTOS = ["p1.jpg", "p2.jpg", "p3.jpg", "p4.jpg"]


def fuente(ruta, tam):
    return ImageFont.truetype(ruta, tam)


def degradado(w, h):
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for x in range(w):
        t = x / (w - 1)
        c = tuple(round(ROSA_1[i] + (ROSA_2[i] - ROSA_1[i]) * t) for i in range(3))
        d.line([(x, 0), (x, h)], fill=c)
    return img


def corazones(img, puntos):
    capa = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    for x, y, r in puntos:
        d.ellipse([x - r, y - r, x, y], fill=(255, 255, 255, 70))
        d.ellipse([x, y - r, x + r, y], fill=(255, 255, 255, 70))
        d.polygon([(x - r, y - r / 2), (x + r, y - r / 2), (x, y + r)], fill=(255, 255, 255, 70))
    img.paste(capa, (0, 0), capa)


def tarjeta(ruta, lado):
    """Foto del producto sobre tarjeta blanca redondeada con sombra."""
    foto = Image.open(ruta).convert("RGB")
    foto.thumbnail((lado - 40, lado - 40))
    card = Image.new("RGBA", (lado + 30, lado + 30), (0, 0, 0, 0))
    sombra = Image.new("RGBA", card.size, (0, 0, 0, 0))
    ImageDraw.Draw(sombra).rounded_rectangle([15, 22, lado + 15, lado + 22], 28, fill=(122, 30, 72, 60))
    sombra = sombra.filter(ImageFilter.GaussianBlur(10))
    card.alpha_composite(sombra)
    blanco = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    ImageDraw.Draw(blanco).rounded_rectangle([0, 0, lado - 1, lado - 1], 28, fill=BLANCO)
    card.alpha_composite(blanco, (15, 15))
    card.paste(foto, (15 + (lado - foto.width) // 2, 15 + (lado - foto.height) // 2))
    return card


def chip(d, x, y, texto, f):
    w = d.textlength(texto, font=f) + 40
    d.rounded_rectangle([x, y, x + w, y + 48], 24, fill=BLANCO)
    d.text((x + 20, y + 24), texto, font=f, fill=VINO, anchor="lm")
    return w


def boton(d, x, y, texto, f):
    w = d.textlength(texto, font=f) + 80
    d.rounded_rectangle([x, y, x + w, y + 76], 38, fill=AZUL)
    d.text((x + w / 2, y + 38), texto, font=f, fill=BLANCO, anchor="mm")


def escritorio():
    W, H = 1920, 640
    img = degradado(W, H)
    corazones(img, [(1080, 90, 40), (1830, 560, 55), (980, 560, 28), (1860, 110, 30)])
    d = ImageDraw.Draw(img)
    x = 140
    d.text((x, 92), "DÍA DE LA MADRE  ·  DOMINGO 18/10", font=fuente(BOLD, 30), fill=FUCSIA)
    d.text((x, 136), "Regalos que mamá", font=fuente(NEGRA, 86), fill=VINO)
    d.text((x, 236), "va a amar", font=fuente(NEGRA, 86), fill=VINO)
    d.text((x, 352), "5% OFF extra con el cupón ", font=fuente(SEMI, 40), fill=VINO)
    ancho = d.textlength("5% OFF extra con el cupón ", font=fuente(SEMI, 40))
    d.text((x + ancho, 352), "MAMA", font=fuente(NEGRA, 40), fill=FUCSIA)
    fc = fuente(SEMI, 24)
    cx = x
    for t in ["3 y 6 cuotas sin interés", "Envío a todo el país", "Garantía extendida hasta 60 meses"]:
        cx += chip(d, cx, 424, t, fc) + 14
    boton(d, x, 504, "VER REGALOS  →", fuente(BOLD, 30))
    lado = 300
    pos = [(1150, 40), (1490, 40), (1150, 330), (1490, 330)]
    for ruta, (px, py) in zip(PRODUCTOS, pos):
        img.paste(tarjeta(ruta, lado - 30), (px, py), tarjeta(ruta, lado - 30))
    img.save("banner_dia_madre_escritorio.jpg", quality=90)


def celular():
    W, H = 800, 1000
    img = degradado(W, H)
    corazones(img, [(700, 80, 34), (90, 930, 40), (740, 900, 24)])
    d = ImageDraw.Draw(img)
    d.text((W / 2, 70), "DÍA DE LA MADRE · DOMINGO 18/10", font=fuente(BOLD, 28), fill=FUCSIA, anchor="mm")
    d.text((W / 2, 150), "Regalos que mamá", font=fuente(NEGRA, 66), fill=VINO, anchor="mm")
    d.text((W / 2, 230), "va a amar", font=fuente(NEGRA, 66), fill=VINO, anchor="mm")
    t1, t2 = "5% OFF extra con el cupón ", "MAMA"
    f1, f2 = fuente(SEMI, 34), fuente(NEGRA, 34)
    total = d.textlength(t1, font=f1) + d.textlength(t2, font=f2)
    x0 = (W - total) / 2
    d.text((x0, 300), t1, font=f1, fill=VINO, anchor="lm")
    d.text((x0 + d.textlength(t1, font=f1), 300), t2, font=f2, fill=FUCSIA, anchor="lm")
    lado = 270
    pos = [(125, 345), (415, 345), (125, 625), (415, 625)]
    for ruta, (px, py) in zip(PRODUCTOS, pos):
        c = tarjeta(ruta, lado - 30)
        img.paste(c, (px, py), c)
    f = fuente(BOLD, 30)
    w = d.textlength("VER REGALOS  →", font=f) + 80
    boton(d, (W - w) / 2, 908, "VER REGALOS  →", f)
    img.save("banner_dia_madre_celular.jpg", quality=90)


if __name__ == "__main__":
    escritorio()
    celular()
    print("ok")
