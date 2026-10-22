"""Genera imágenes y logos para la campaña Performance Max de Tengo Stock (sin texto superpuesto)."""
from PIL import Image, ImageChops, ImageDraw, ImageFilter

FONDO = (241, 246, 252)
BLANCO = (255, 255, 255)


def recortar(ruta, umbral=245):
    """Recorta el borde blanco sobrante alrededor del producto."""
    im = Image.open(ruta).convert("RGB")
    fondo = Image.new("RGB", im.size, BLANCO)
    diff = ImageChops.difference(im, fondo).convert("L").point(lambda p: 255 if p > 255 - umbral + 10 else 0)
    caja = diff.getbbox()
    return im.crop(caja) if caja else im


def tarjeta(ruta, w, h, radio=36):
    prod = recortar(ruta)
    prod.thumbnail((int(w * 0.82), int(h * 0.82)))
    capa = Image.new("RGBA", (w + 40, h + 40), (0, 0, 0, 0))
    sombra = Image.new("RGBA", capa.size, (0, 0, 0, 0))
    ImageDraw.Draw(sombra).rounded_rectangle([20, 28, w + 20, h + 28], radio, fill=(20, 60, 120, 45))
    capa.alpha_composite(sombra.filter(ImageFilter.GaussianBlur(14)))
    caja = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(caja).rounded_rectangle([0, 0, w - 1, h - 1], radio, fill=BLANCO)
    capa.alpha_composite(caja, (20, 20))
    capa.paste(prod, (20 + (w - prod.width) // 2, 20 + (h - prod.height) // 2))
    return capa


def collage(nombre, W, H, productos, cols, rows, margen=56, gap=36):
    img = Image.new("RGBA", (W, H), FONDO + (255,))
    cw = (W - 2 * margen - (cols - 1) * gap) // cols
    ch = (H - 2 * margen - (rows - 1) * gap) // rows
    for i, p in enumerate(productos[: cols * rows]):
        x = margen + (i % cols) * (cw + gap) - 20
        y = margen + (i // cols) * (ch + gap) - 20
        img.alpha_composite(tarjeta(p + ".jpg", cw, ch), (x, y))
    img.convert("RGB").save(nombre, quality=92)


def logos():
    logo = Image.open("logo.webp").convert("RGBA")
    alfa = logo.getchannel("A").point(lambda p: 255 if p > 40 else 0)
    logo = logo.crop(alfa.getbbox())
    # cuadrado 1200x1200, fondo blanco
    sq = Image.new("RGBA", (1200, 1200), BLANCO + (255,))
    r = min(900 / logo.width, 900 / logo.height)
    l = logo.resize((int(logo.width * r), int(logo.height * r)), Image.LANCZOS)
    sq.alpha_composite(l, ((1200 - l.width) // 2, (1200 - l.height) // 2))
    sq.convert("RGB").save("logo_cuadrado_1200.png")
    # horizontal 1200x300
    hz = Image.new("RGBA", (1200, 300), BLANCO + (255,))
    r = min(1000 / logo.width, 240 / logo.height)
    l = logo.resize((int(logo.width * r), int(logo.height * r)), Image.LANCZOS)
    hz.alpha_composite(l, ((1200 - l.width) // 2, (300 - l.height) // 2))
    hz.convert("RGB").save("logo_horizontal_1200x300.png")


if __name__ == "__main__":
    logos()
    collage("horizontal_1_hogar.jpg", 1200, 628, ["tv", "heladera", "lavarropas"], 3, 1)
    collage("horizontal_2_tecno.jpg", 1200, 628, ["iphone", "tv", "cafetera"], 3, 1)
    collage("horizontal_3_clima.jpg", 1200, 628, ["aire", "lavarropas", "cafetera"], 3, 1)
    collage("cuadrada_1.jpg", 1200, 1200, ["tv", "heladera", "iphone", "cafetera"], 2, 2)
    collage("cuadrada_2.jpg", 1200, 1200, ["aire", "lavarropas", "tv", "iphone"], 2, 2)
    collage("cuadrada_3_tv.jpg", 1200, 1200, ["tv"], 1, 1, margen=90)
    collage("vertical_1.jpg", 960, 1200, ["heladera", "cafetera"], 1, 2)
    print("ok")
