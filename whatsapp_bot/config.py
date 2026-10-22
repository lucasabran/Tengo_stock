"""Variables de entorno del bot.

En Render se cargan en el panel (Environment). Para probar en la PC se leen de
whatsapp_bot/.env y, si existe, de tiendanube/.env (datos de la tienda).
"""
import os

AQUI = os.path.dirname(os.path.abspath(__file__))

WHATSAPP = ("WHATSAPP_TOKEN", "WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_VERIFY_TOKEN", "META_APP_SECRET")


def cargar_env():
    for ruta in (os.path.join(AQUI, ".env"), os.path.join(AQUI, "..", "tiendanube", ".env")):
        if not os.path.exists(ruta):
            continue
        with open(ruta, encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if linea and not linea.startswith("#") and "=" in linea:
                    k, v = linea.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


def tiendanube():
    """(store_id, token, email). Acepta los nombres de Render o los del .env de tiendanube/."""
    e = os.environ
    return (e.get("TIENDANUBE_STORE_ID") or e.get("STORE_ID"),
            e.get("TIENDANUBE_TOKEN") or e.get("ACCESS_TOKEN"),
            e.get("TIENDANUBE_EMAIL") or e.get("CONTACT_EMAIL"))


def faltantes(*claves):
    falta = [c for c in claves if not os.environ.get(c)]
    if not all(tiendanube()):
        falta.append("TIENDANUBE_STORE_ID / TIENDANUBE_TOKEN / TIENDANUBE_EMAIL")
    return falta
