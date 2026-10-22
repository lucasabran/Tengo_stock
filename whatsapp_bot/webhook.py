"""Webhook de WhatsApp (WhatsApp Cloud API de Meta), montado dentro de la app de gestión.

  GET  /whatsapp/webhook   verificación que hace Meta al configurar el webhook
  POST /whatsapp/webhook   mensajes entrantes (responde 200 enseguida y atiende en segundo plano)
  GET  /whatsapp/estado    chequeo rápido: {"ok": true, "productos": N}

Estas rutas no piden login: el POST se valida con la firma de Meta (META_APP_SECRET).

Comandos del dueño (escribiéndole al número del bot desde OWNER_PHONE):
  #bot 5491122334455     el bot vuelve a atender a ese cliente
  #pausa 5491122334455   el bot deja de responderle (atendés vos)
  #pausados              lista de clientes en pausa
"""
import collections
import hashlib
import hmac
import json
import logging
import os
import threading
import urllib.error
import urllib.request

from flask import Blueprint, abort, request

from . import config

log = logging.getLogger("whatsapp")
bp = Blueprint("whatsapp", __name__, url_prefix="/whatsapp")
_bot = {}  # catalogo, asistente
_vistos = collections.deque(maxlen=2000)  # Meta reenvía si tardamos: evita responder dos veces
_vistos_lock = threading.Lock()


def crear_blueprint():
    """Devuelve el blueprint listo, o None si faltan variables (la app sigue funcionando igual)."""
    config.cargar_env()
    falta = config.faltantes("ANTHROPIC_API_KEY", *config.WHATSAPP)
    if falta:
        log.error("Bot de WhatsApp desactivado. Faltan variables: %s", ", ".join(falta))
        return None
    from .asistente import Asistente
    from .catalogo import Catalogo

    catalogo = Catalogo(*config.tiendanube(), refresco_min=int(os.environ.get("REFRESCO_MIN", "30")))
    catalogo.iniciar()
    _bot["catalogo"] = catalogo
    _bot["asistente"] = Asistente(catalogo, al_derivar=avisar_duenio)
    log.info("Bot de WhatsApp activo en /whatsapp/webhook")
    return bp


# --- envío de mensajes -----------------------------------------------------------------
def _graph(payload):
    e = os.environ
    url = f"https://graph.facebook.com/{e.get('GRAPH_VERSION', 'v23.0')}/{e['WHATSAPP_PHONE_NUMBER_ID']}/messages"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST", headers={
        "Authorization": f"Bearer {e['WHATSAPP_TOKEN']}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as err:
        log.error("WhatsApp respondió %s: %s", err.code, err.read().decode()[:500])
    except urllib.error.URLError as err:
        log.error("No se pudo contactar a WhatsApp: %s", err)


def _destino(tel):
    # Solo para el número de prueba de Meta con celulares argentinos (ver LEEME)
    if os.environ.get("AR_QUITAR_9") == "1" and tel.startswith("549"):
        return "54" + tel[3:]
    return tel


def partir(texto, largo=3500):
    partes, actual = [], ""
    for parrafo in texto.split("\n\n"):
        if actual and len(actual) + len(parrafo) + 2 > largo:
            partes.append(actual)
            actual = ""
        actual = f"{actual}\n\n{parrafo}" if actual else parrafo
        while len(actual) > largo:
            partes.append(actual[:largo])
            actual = actual[largo:]
    if actual:
        partes.append(actual)
    return partes


def enviar(tel, texto):
    for parte in partir(texto):
        _graph({"messaging_product": "whatsapp", "to": _destino(tel), "type": "text",
                "text": {"body": parte, "preview_url": True}})


def _duenio():
    return os.environ.get("OWNER_PHONE", "").lstrip("+")


def avisar_duenio(tel, nombre, motivo):
    log.info("DERIVACIÓN +%s (%s): %s", tel, nombre, motivo)
    if _duenio():
        # WhatsApp solo deja mandar texto libre si el dueño le escribió al bot en las últimas 24 h
        enviar(_duenio(), f"🔔 Cliente para atender\n{nombre or 'Sin nombre'} · +{tel}\n{motivo}\n"
                          f"https://wa.me/{tel}\n\nCuando termines: #bot {tel}")


# --- atención ----------------------------------------------------------------------------
def comando_duenio(texto):
    asistente = _bot["asistente"]
    partes = texto.split()
    orden, tel = partes[0].lower(), (partes[1].lstrip("+") if len(partes) > 1 else "")
    if orden == "#bot" and tel:
        asistente.reanudar(tel)
        return f"✅ El bot vuelve a atender a +{tel}"
    if orden == "#pausa" and tel:
        asistente.pausar(tel)
        return f"⏸️ El bot no le responde a +{tel} por unas horas"
    if orden == "#pausados":
        lista = asistente.pausados()
        return "En pausa:\n" + "\n".join(f"+{t}" for t in lista) if lista else "No hay chats en pausa."
    return "Comandos: #bot NUMERO · #pausa NUMERO · #pausados"


def atender(tel, msg_id, texto, nombre):
    asistente = _bot["asistente"]
    try:
        # marca como leído y muestra "escribiendo…"
        _graph({"messaging_product": "whatsapp", "status": "read", "message_id": msg_id,
                "typing_indicator": {"type": "text"}})
        if _duenio() and tel == _duenio() and texto.startswith("#"):
            enviar(tel, comando_duenio(texto))
            return
        if not texto:
            if asistente.conversacion(tel).pausado_hasta == 0:
                enviar(tel, "Por ahora solo puedo leer mensajes de texto 🙂 ¿Me lo escribís?")
            return
        respuesta = asistente.responder(tel, texto, nombre)
        if respuesta:
            enviar(tel, respuesta)
    except Exception:
        log.exception("error atendiendo a +%s", tel)


def _firma_valida(cuerpo):
    recibida = request.headers.get("X-Hub-Signature-256", "")
    esperada = "sha256=" + hmac.new(os.environ["META_APP_SECRET"].encode(), cuerpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(recibida, esperada)


@bp.get("/estado")
def estado():
    return {"ok": True, "productos": len(_bot["catalogo"].productos)}


@bp.get("/webhook")
def verificar():
    if (request.args.get("hub.mode") == "subscribe"
            and request.args.get("hub.verify_token") == os.environ["WHATSAPP_VERIFY_TOKEN"]):
        return request.args.get("hub.challenge", "")
    abort(403)


@bp.post("/webhook")
def recibir():
    cuerpo = request.get_data()
    if not _firma_valida(cuerpo):
        abort(403)
    datos = json.loads(cuerpo or b"{}")
    for entrada in datos.get("entry", []):
        for cambio in entrada.get("changes", []):
            valor = cambio.get("value", {})
            nombres = {c.get("wa_id"): c.get("profile", {}).get("name", "") for c in valor.get("contacts", [])}
            for m in valor.get("messages", []):
                with _vistos_lock:
                    if m["id"] in _vistos:
                        continue
                    _vistos.append(m["id"])
                tipo = m.get("type")
                texto = (m.get("text", {}).get("body") if tipo == "text"
                         else m.get("button", {}).get("text") if tipo == "button"
                         else m.get("interactive", {}).get("button_reply", {}).get("title") if tipo == "interactive"
                         else "") or ""
                threading.Thread(target=atender, daemon=True, args=(
                    m["from"], m["id"], texto.strip(), nombres.get(m["from"], ""))).start()
    return "ok"
