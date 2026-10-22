"""Probá el bot en la consola, sin WhatsApp (usa el catálogo real de la tienda y la API de Claude).

  python -m whatsapp_bot.probar        (desde la carpeta stock-app)

Escribí como si fueras un cliente. "salir" para terminar, "nuevo" para empezar otra charla.
"""
import logging
import sys

from . import config


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.WARNING)
    config.cargar_env()
    falta = config.faltantes("ANTHROPIC_API_KEY")
    if falta:
        sys.exit(f"Faltan variables: {', '.join(falta)} (ver whatsapp_bot/.env.example)")

    from .asistente import Asistente
    from .catalogo import Catalogo

    print("Cargando catálogo de la tienda…")
    catalogo = Catalogo(*config.tiendanube())
    catalogo.cargar()
    print(f"{len(catalogo.productos)} productos. Escribí como cliente ('salir' para terminar).\n")

    def derivar(tel, nombre, motivo):
        print(f"\n   [🔔 DERIVADO A UNA PERSONA: {motivo}]")

    bot = Asistente(catalogo, al_derivar=derivar)
    tel = "5491100000000"
    while True:
        try:
            texto = input("Vos: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if texto.lower() == "salir":
            break
        if texto.lower() == "nuevo":
            bot.conversaciones.clear()
            print("— conversación nueva —\n")
            continue
        if not texto:
            continue
        respuesta = bot.responder(tel, texto, "Cliente de prueba")
        print(f"\nBot: {respuesta if respuesta else '(en pausa: atiende una persona; escribí nuevo)'}\n")


if __name__ == "__main__":
    main()
