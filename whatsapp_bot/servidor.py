"""Servidor propio del bot de WhatsApp (servicio de Render separado del sistema de gestión).

El bot vende con los datos de la tienda online (Tiendanube). No usa ni toca el sistema de gestión.

Render (desde la raíz del repositorio):
  Build:  pip install -r whatsapp_bot/requirements.txt
  Start:  gunicorn whatsapp_bot.servidor:app --workers 1 --threads 8 --timeout 120
(un solo worker: las conversaciones viven en memoria)
"""
import logging
import os

from flask import Flask

from .webhook import crear_blueprint

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

app = Flask(__name__)
_bp = crear_blueprint()
if _bp is None:
    raise SystemExit("Faltan variables de entorno del bot (ver whatsapp_bot/.env.example)")
app.register_blueprint(_bp)


@app.get("/")
def salud():
    return "Bot de WhatsApp de Tengo Stock: ok"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
