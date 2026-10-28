"""Banner de categoría Climatización (930x465): mismo diseño, con aire y ventilador en lugar de la estufa."""
import os
import sys

from PIL import Image, ImageFilter

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "pmax"))
from hacer_recursos import recortar  # noqa: E402


def sin_fondo(im, umbral=238):
    """Vuelve transparente el fondo blanco de la foto del producto."""
    im = im.convert("RGBA")
    alfa = im.convert("L").point(lambda v: 0 if v > umbral else 255)
    im.putalpha(alfa)
    return im


def con_sombra(lienzo, im, x, y):
    sombra = Image.new("RGBA", lienzo.size, (0, 0, 0, 0))
    mascara = im.getchannel("A").point(lambda a: 70 if a else 0)
    sombra.paste(Image.new("RGBA", im.size, (0, 0, 0, 255)), (x + 4, y + 8), mascara)
    lienzo.alpha_composite(sombra.filter(ImageFilter.GaussianBlur(8)))
    lienzo.alpha_composite(im, (x, y))


base = Image.open(os.path.join(AQUI, "clima_original.png")).convert("RGB")
W, H = base.size
x0 = 572  # el panel claro empieza después de la franja roja
fondo = base.getpixel((W - 10, 10))
pw = W - x0
panel = Image.new("RGBA", (pw, H), fondo + (255,))

aire = sin_fondo(recortar(os.path.join(AQUI, "..", "pmax", "aire.jpg")))
aire.thumbnail((250, 90))
vent = sin_fondo(recortar(os.path.join(AQUI, "..", "pmax", "ventilador.jpg")))
vent.thumbnail((150, 215))
alto = aire.height + 30 + vent.height
y = (H - alto) // 2
con_sombra(panel, aire, (pw - aire.width) // 2, y)
con_sombra(panel, vent, (pw - vent.width) // 2, y + aire.height + 30)

base.paste(panel.convert("RGB"), (x0, 0))
base.save(os.path.join(AQUI, "categoria_climatizacion_verano.png"))
print("ok")
