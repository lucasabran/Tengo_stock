"""Mercado Libre multicuenta: ventas, preguntas, reclamos y mensajes de varias cuentas en un solo lugar.

Cómo funciona:
- Una sola app de Mercado Libre (ML_CLIENT_ID / ML_CLIENT_SECRET). Cada vendedor la autoriza una vez
  desde un link que se genera en la pestaña "Mercado Libre" (nadie pasa su contraseña). Los permisos
  quedan guardados en la base y se renuevan solos.
- Cada 5 minutos (y al instante si llega un aviso de Mercado Libre) se trae de cada cuenta: reputación,
  últimas ventas y su envío, preguntas sin responder, reclamos abiertos y mensajes sin leer.
- Desde el panel se responden preguntas y mensajes de posventa. Los reclamos se ven con su plazo, pero
  se responden en Mercado Libre.

No publica, no cambia precios ni stock: solo lee y responde.

Variables en el servidor (Render > Environment):
  ML_CLIENT_ID, ML_CLIENT_SECRET    de la app creada en developers.mercadolibre.com.ar
  ML_REDIRECT_URI                   https://<servidor>/ml/callback (igual que en la app)
"""
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from db import DB_PATH, now_iso

API = "https://api.mercadolibre.com"
AUTH_URL = "https://auth.mercadolibre.com.ar/authorization"
SYNC_EVERY_SECONDS = 300
LINK_DAYS = 7
BACKFILL_DAYS = 30
ORDERS_KEEP_DAYS = 120
SHIP_FINAL = {"delivered", "cancelled", "not_delivered", "lost", "returned"}
_locks = {}
_locks_guard = threading.Lock()
_sync_all_lock = threading.Lock()


class MLError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------------
def ensure_schema(db):
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS ml_accounts (
            user_id INTEGER PRIMARY KEY,
            nickname TEXT DEFAULT '',
            alias TEXT DEFAULT '',
            access_token TEXT DEFAULT '',
            refresh_token TEXT DEFAULT '',
            expires_at REAL DEFAULT 0,
            status TEXT DEFAULT 'ok',            -- ok | error | reconectar
            last_error TEXT DEFAULT '',
            last_sync TEXT DEFAULT '',
            reputation TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ml_links (
            state TEXT PRIMARY KEY,
            alias TEXT DEFAULT '',
            created_by TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            expires_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ml_orders (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            date_created TEXT,
            status TEXT,
            total REAL DEFAULT 0,
            buyer TEXT DEFAULT '',
            buyer_id INTEGER,
            items TEXT DEFAULT '',
            units INTEGER DEFAULT 0,
            pack_id INTEGER,
            shipping_id INTEGER,
            ship_status TEXT DEFAULT '',
            ship_substatus TEXT DEFAULT '',
            tags TEXT DEFAULT '',
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_ml_orders_user_date ON ml_orders (user_id, date_created);
        CREATE TABLE IF NOT EXISTS ml_questions (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            item_id TEXT,
            item_title TEXT DEFAULT '',
            item_link TEXT DEFAULT '',
            text TEXT DEFAULT '',
            date_created TEXT,
            status TEXT,                         -- UNANSWERED | ANSWERED | CERRADA
            answer TEXT DEFAULT '',
            answered_by TEXT DEFAULT '',
            answered_at TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS ml_claims (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            order_id INTEGER,
            type TEXT DEFAULT '',
            stage TEXT DEFAULT '',
            status TEXT DEFAULT '',
            reason_id TEXT DEFAULT '',
            action TEXT DEFAULT '',
            due_date TEXT DEFAULT '',
            date_created TEXT,
            last_updated TEXT
        );
        CREATE TABLE IF NOT EXISTS ml_conversations (
            user_id INTEGER NOT NULL,
            pack_id INTEGER NOT NULL,
            unread INTEGER DEFAULT 0,
            buyer_id INTEGER,
            last_text TEXT DEFAULT '',
            last_from_buyer INTEGER DEFAULT 1,
            last_date TEXT DEFAULT '',
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, pack_id)
        );
        """
    )


def connect():
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    return db


def configured():
    return bool(os.environ.get("ML_CLIENT_ID") and os.environ.get("ML_CLIENT_SECRET"))


def _account_lock(user_id):
    with _locks_guard:
        return _locks.setdefault(int(user_id), threading.Lock())


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def http(method, path, token=None, body=None, form=None, headers=None):
    """Llama a la API. Devuelve el JSON. Lanza MLError con el mensaje de Mercado Libre si falla."""
    url = path if path.startswith("http") else API + path
    hdrs = {"Accept": "application/json", **(headers or {})}
    data = None
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        hdrs["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as err:
            raw = err.read().decode("utf-8", "replace")
            if err.code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            try:
                info = json.loads(raw)
                msg = info.get("message") or info.get("error") or raw
            except ValueError:
                msg = raw
            raise MLError(err.code, f"{err.code}: {str(msg)[:300]}")
        except urllib.error.URLError as err:
            if attempt < 2:
                time.sleep(2)
                continue
            raise MLError(0, f"sin conexion con Mercado Libre: {err.reason}")
    raise MLError(0, "sin respuesta de Mercado Libre")


# ---------------------------------------------------------------------------
# Conectar cuentas (OAuth)
# ---------------------------------------------------------------------------
def redirect_uri(fallback_host=None):
    uri = os.environ.get("ML_REDIRECT_URI")
    if uri:
        return uri
    return f"https://{fallback_host}/ml/callback" if fallback_host else ""


def new_link(db, alias, created_by, host):
    """Crea un link de autorización (vale LINK_DAYS días, se usa una sola vez)."""
    db.execute("DELETE FROM ml_links WHERE expires_at < ?", (time.time(),))
    state = secrets.token_urlsafe(24)
    db.execute("INSERT INTO ml_links (state, alias, created_by, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
               (state, alias[:60], created_by, now_iso(), time.time() + LINK_DAYS * 86400))
    db.commit()
    query = urllib.parse.urlencode({"response_type": "code", "client_id": os.environ["ML_CLIENT_ID"],
                                    "redirect_uri": redirect_uri(host), "state": state})
    return f"{AUTH_URL}?{query}"


def _save_tokens(db, user_id, tok):
    db.execute("UPDATE ml_accounts SET access_token = ?, refresh_token = ?, expires_at = ?, status = 'ok', "
               "last_error = '', updated_at = ? WHERE user_id = ?",
               (tok["access_token"], tok.get("refresh_token") or "", time.time() + int(tok.get("expires_in", 21600)),
                now_iso(), user_id))


def complete_link(db, state, code, host):
    """Cambia el código por los permisos y guarda la cuenta. Devuelve (nickname, error)."""
    row = db.execute("SELECT * FROM ml_links WHERE state = ?", (state or "",)).fetchone()
    if not row or row["expires_at"] < time.time():
        return None, "El link venció o ya se usó. Pedí uno nuevo."
    db.execute("DELETE FROM ml_links WHERE state = ?", (state,))
    db.commit()
    try:
        tok = http("POST", "/oauth/token", form={
            "grant_type": "authorization_code", "client_id": os.environ["ML_CLIENT_ID"],
            "client_secret": os.environ["ML_CLIENT_SECRET"], "code": code, "redirect_uri": redirect_uri(host)})
        me = http("GET", "/users/me", token=tok["access_token"])
    except MLError as exc:
        return None, f"Mercado Libre no aceptó la autorización ({exc})."
    if not tok.get("refresh_token"):
        return None, "La app de Mercado Libre no tiene el permiso offline_access: sin eso no se puede renovar sola."
    now = now_iso()
    db.execute(
        "INSERT INTO ml_accounts (user_id, nickname, alias, created_at, updated_at) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET nickname = excluded.nickname, "
        "alias = CASE WHEN excluded.alias != '' THEN excluded.alias ELSE ml_accounts.alias END",
        (me["id"], me.get("nickname", ""), row["alias"], now, now))
    _save_tokens(db, me["id"], tok)
    db.execute("INSERT INTO audit_log (user_id, username, action, entity, entity_id, detail, ip, created_at) "
               "VALUES (NULL, ?, 'ml_cuenta_conectada', 'ml_account', ?, ?, '', ?)",
               (row["created_by"] or "mercado-libre", str(me["id"]), me.get("nickname", ""), now))
    db.commit()
    threading.Thread(target=sync_account, args=(me["id"],), daemon=True).start()
    return me.get("nickname", ""), None


def token_for(db, user_id):
    """Token vigente de la cuenta; lo renueva si vence en menos de 10 minutos."""
    acc = db.execute("SELECT * FROM ml_accounts WHERE user_id = ?", (user_id,)).fetchone()
    if not acc:
        raise MLError(404, "cuenta no conectada")
    if acc["access_token"] and acc["expires_at"] - time.time() > 600:
        return acc["access_token"]
    if not acc["refresh_token"]:
        raise MLError(401, "hay que volver a conectar la cuenta")
    try:
        tok = http("POST", "/oauth/token", form={
            "grant_type": "refresh_token", "client_id": os.environ["ML_CLIENT_ID"],
            "client_secret": os.environ["ML_CLIENT_SECRET"], "refresh_token": acc["refresh_token"]})
    except MLError as exc:
        if exc.status in (400, 401, 403):  # permiso revocado o vencido (más de 6 meses sin uso)
            db.execute("UPDATE ml_accounts SET status = 'reconectar', last_error = ?, updated_at = ? WHERE user_id = ?",
                       (f"Hay que volver a conectar la cuenta ({exc})"[:300], now_iso(), user_id))
            db.commit()
        raise
    _save_tokens(db, user_id, tok)  # Mercado Libre entrega un refresh_token nuevo cada vez: se guarda ya
    db.commit()
    return tok["access_token"]


# ---------------------------------------------------------------------------
# Sincronización
# ---------------------------------------------------------------------------
def _iso(value):
    return str(value or "")[:19]


def _sync_orders(db, uid, token):
    known = db.execute("SELECT COUNT(*) FROM ml_orders WHERE user_id = ?", (uid,)).fetchone()[0]
    since = (datetime.now(timezone.utc) - timedelta(days=BACKFILL_DAYS)).strftime("%Y-%m-%dT%H:%M:%S.000-00:00")
    offset, pages = 0, (10 if not known else 1)  # la primera vez trae 30 días; después las últimas 50
    for _ in range(pages):
        q = {"seller": uid, "sort": "date_desc", "limit": 50, "offset": offset}
        if not known:
            q["order.date_created.from"] = since
        data = http("GET", "/orders/search?" + urllib.parse.urlencode(q), token)
        results = data.get("results") or []
        for o in results:
            items = o.get("order_items") or []
            db.execute(
                "INSERT INTO ml_orders (id, user_id, date_created, status, total, buyer, buyer_id, items, units, pack_id, "
                "shipping_id, tags, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET status = excluded.status, total = excluded.total, tags = excluded.tags, "
                "shipping_id = excluded.shipping_id, pack_id = excluded.pack_id, updated_at = excluded.updated_at",
                (o["id"], uid, o.get("date_created"), o.get("status"), o.get("total_amount") or 0,
                 (o.get("buyer") or {}).get("nickname", ""), (o.get("buyer") or {}).get("id"),
                 " + ".join(f"{i.get('quantity', 1)} x {(i.get('item') or {}).get('title', '')}" for i in items)[:500],
                 sum(int(i.get("quantity") or 0) for i in items), o.get("pack_id"),
                 (o.get("shipping") or {}).get("id"), ",".join(o.get("tags") or []), now_iso()))
        offset += len(results)
        if len(results) < 50 or offset >= (data.get("paging") or {}).get("total", 0):
            break
    # estado del envío de las ventas de los últimos 20 días que todavía no terminaron
    cutoff = (datetime.now() - timedelta(days=20)).isoformat()
    for row in db.execute("SELECT id, shipping_id FROM ml_orders WHERE user_id = ? AND shipping_id IS NOT NULL "
                          "AND date_created >= ? AND status != 'cancelled' AND ship_status NOT IN (%s) LIMIT 40"
                          % ",".join("?" * len(SHIP_FINAL)), (uid, cutoff, *SHIP_FINAL)).fetchall():
        try:
            sh = http("GET", f"/shipments/{row['shipping_id']}", token, headers={"x-format-new": "true"})
        except MLError:
            continue
        db.execute("UPDATE ml_orders SET ship_status = ?, ship_substatus = ? WHERE id = ?",
                   (sh.get("status") or "", sh.get("substatus") or "", row["id"]))
    db.execute("DELETE FROM ml_orders WHERE user_id = ? AND date_created < ?",
               (uid, (datetime.now() - timedelta(days=ORDERS_KEEP_DAYS)).isoformat()))


def _item_info(token, item_ids):
    info = {}
    ids = sorted({i for i in item_ids if i})
    for k in range(0, len(ids), 20):
        try:
            data = http("GET", "/items?" + urllib.parse.urlencode({"ids": ",".join(ids[k:k + 20]),
                                                                    "attributes": "id,title,permalink"}), token)
        except MLError:
            continue
        for entry in data or []:
            body = entry.get("body") or {}
            if body.get("id"):
                info[body["id"]] = (body.get("title", ""), body.get("permalink", ""))
    return info


def _sync_questions(db, uid, token):
    pending, offset = [], 0
    while offset < 500:
        data = http("GET", "/questions/search?" + urllib.parse.urlencode({
            "seller_id": uid, "status": "UNANSWERED", "api_version": 4, "limit": 50, "offset": offset,
            "sort_fields": "date_created", "sort_types": "ASC"}), token)
        batch = data.get("questions") or []
        pending += batch
        offset += len(batch)
        if len(batch) < 50 or offset >= data.get("total", 0):
            break
    known = {r[0] for r in db.execute("SELECT item_id FROM ml_questions WHERE user_id = ? AND item_title != ''", (uid,))}
    info = _item_info(token, [q.get("item_id") for q in pending if q.get("item_id") not in known])
    ids = []
    for q in pending:
        ids.append(q["id"])
        title, link = info.get(q.get("item_id"), ("", ""))
        db.execute(
            "INSERT INTO ml_questions (id, user_id, item_id, item_title, item_link, text, date_created, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'UNANSWERED') ON CONFLICT(id) DO UPDATE SET text = excluded.text, "
            "item_title = CASE WHEN excluded.item_title != '' THEN excluded.item_title ELSE ml_questions.item_title END, "
            "item_link = CASE WHEN excluded.item_link != '' THEN excluded.item_link ELSE ml_questions.item_link END",
            (q["id"], uid, q.get("item_id"), title, link, q.get("text", ""), _iso(q.get("date_created"))))
    # completar títulos de publicaciones ya conocidas
    db.execute("UPDATE ml_questions SET item_title = (SELECT q2.item_title FROM ml_questions q2 WHERE q2.item_id = "
               "ml_questions.item_id AND q2.item_title != '' LIMIT 1) WHERE user_id = ? AND item_title = ''", (uid,))
    # las que ya no están pendientes se respondieron (o borraron) en Mercado Libre
    db.execute(f"UPDATE ml_questions SET status = 'CERRADA', answered_at = ? WHERE user_id = ? AND status = 'UNANSWERED' "
               f"AND id NOT IN ({','.join('?' * len(ids)) or 'SELECT NULL WHERE 0'})", (now_iso(), uid, *ids))
    db.execute("DELETE FROM ml_questions WHERE status != 'UNANSWERED' AND answered_at < ?",
               ((datetime.now() - timedelta(days=30)).isoformat(),))


def _sync_claims(db, uid, token):
    data = http("GET", "/post-purchase/v1/claims/search?" + urllib.parse.urlencode({"status": "opened", "limit": 50}), token)
    rows = data.get("data") or data.get("results") or []
    db.execute("DELETE FROM ml_claims WHERE user_id = ?", (uid,))
    for c in rows:
        me = next((p for p in c.get("players") or [] if p.get("user_id") == uid or p.get("role") == "respondent"), {})
        actions = me.get("available_actions") or []
        mandatory = sorted((a for a in actions if a.get("due_date")), key=lambda a: a["due_date"])
        first = mandatory[0] if mandatory else (actions[0] if actions else {})
        db.execute(
            "INSERT OR REPLACE INTO ml_claims (id, user_id, order_id, type, stage, status, reason_id, action, due_date, "
            "date_created, last_updated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (c["id"], uid, c.get("resource_id"), c.get("type", ""), c.get("stage", ""), c.get("status", ""),
             c.get("reason_id", ""), first.get("action", ""), _iso(first.get("due_date")),
             _iso(c.get("date_created")), _iso(c.get("last_updated"))))


def _sync_messages(db, uid, token):
    data = http("GET", "/messages/unread?role=seller&tag=post_sale", token)
    seen = []
    for r in data.get("results") or []:
        m = re.search(r"/packs/(\d+)", str(r.get("resource") or r.get("conversation_id") or r.get("path") or ""))
        if not m:
            continue
        pack = int(m.group(1))
        seen.append(pack)
        last, buyer = None, None
        try:
            conv = http("GET", f"/messages/packs/{pack}/sellers/{uid}?tag=post_sale&mark_as_read=false&limit=10", token)
            msgs = conv.get("messages") or []
            last = max(msgs, key=lambda x: (x.get("message_date") or {}).get("created", ""), default=None)
            buyer = next(((x.get("from") or {}).get("user_id") for x in msgs
                          if (x.get("from") or {}).get("user_id") != uid), None)
        except MLError:
            pass
        db.execute(
            "INSERT INTO ml_conversations (user_id, pack_id, unread, buyer_id, last_text, last_from_buyer, last_date, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(user_id, pack_id) DO UPDATE SET unread = excluded.unread, "
            "buyer_id = COALESCE(excluded.buyer_id, ml_conversations.buyer_id), last_text = excluded.last_text, "
            "last_from_buyer = excluded.last_from_buyer, last_date = excluded.last_date, updated_at = excluded.updated_at",
            (uid, pack, int(r.get("count") or 1), buyer, (last or {}).get("text", "")[:1000],
             0 if last and (last.get("from") or {}).get("user_id") == uid else 1,
             _iso((last or {}).get("message_date", {}).get("created")), now_iso()))
    db.execute(f"DELETE FROM ml_conversations WHERE user_id = ? AND pack_id NOT IN "
               f"({','.join('?' * len(seen)) or 'SELECT NULL WHERE 0'})", (uid, *seen))


def sync_account(user_id):
    """Trae todo de una cuenta. Nunca lanza: el error queda guardado en la cuenta."""
    lock = _account_lock(user_id)
    if not lock.acquire(blocking=False):
        return
    db = connect()
    try:
        ensure_schema(db)
        token = token_for(db, user_id)
        me = http("GET", "/users/me", token)
        rep = me.get("seller_reputation") or {}
        db.execute("UPDATE ml_accounts SET nickname = ?, reputation = ? WHERE user_id = ?",
                   (me.get("nickname", ""), json.dumps({"level_id": rep.get("level_id"),
                                                       "power_seller_status": rep.get("power_seller_status"),
                                                       "real_level": rep.get("real_level"),
                                                       "protection_end_date": rep.get("protection_end_date"),
                                                       "metrics": rep.get("metrics") or {},
                                                       "transactions": rep.get("transactions") or {}}), user_id))
        errors = []
        for step in (_sync_orders, _sync_questions, _sync_claims, _sync_messages):
            try:
                step(db, user_id, token)
                db.commit()
            except MLError as exc:
                db.rollback()
                errors.append(f"{step.__name__[6:]}: {exc}")
        db.execute("UPDATE ml_accounts SET status = ?, last_error = ?, last_sync = ?, updated_at = ? WHERE user_id = ?",
                   ("error" if errors else "ok", "; ".join(errors)[:500], now_iso(), now_iso(), user_id))
        db.commit()
    except MLError as exc:
        db.rollback()
        db.execute("UPDATE ml_accounts SET status = CASE WHEN status = 'reconectar' THEN status ELSE 'error' END, "
                   "last_error = ?, updated_at = ? WHERE user_id = ?", (str(exc)[:500], now_iso(), user_id))
        db.commit()
    except Exception as exc:  # que un error raro no frene a las otras cuentas
        db.rollback()
        db.execute("UPDATE ml_accounts SET status = 'error', last_error = ?, updated_at = ? WHERE user_id = ?",
                   (f"error interno: {exc}"[:500], now_iso(), user_id))
        db.commit()
    finally:
        db.close()
        lock.release()


def sync_all():
    if not configured() or not _sync_all_lock.acquire(blocking=False):
        return
    try:
        db = connect()
        try:
            ensure_schema(db)
            ids = [r[0] for r in db.execute("SELECT user_id FROM ml_accounts WHERE status != 'reconectar'")]
        finally:
            db.close()
        for uid in ids:
            sync_account(uid)
    finally:
        _sync_all_lock.release()


_last_notified = {}


def on_notification(payload):
    """Aviso de Mercado Libre (venta, pregunta, mensaje, reclamo): sincroniza esa cuenta enseguida.

    El aviso no trae datos confiables (no está firmado): solo se usa para saber a qué cuenta mirar.
    """
    if str(payload.get("application_id") or "") != os.environ.get("ML_CLIENT_ID", ""):
        return False
    try:
        uid = int(payload.get("user_id"))
    except (TypeError, ValueError):
        return False
    db = connect()
    try:
        ensure_schema(db)
        exists = db.execute("SELECT 1 FROM ml_accounts WHERE user_id = ? AND status != 'reconectar'", (uid,)).fetchone()
    finally:
        db.close()
    if not exists or time.monotonic() - _last_notified.get(uid, -1e9) < 30:
        return False
    _last_notified[uid] = time.monotonic()
    threading.Thread(target=sync_account, args=(uid,), daemon=True).start()
    return True


# ---------------------------------------------------------------------------
# Responder
# ---------------------------------------------------------------------------
def answer_question(db, question_id, text, actor):
    q = db.execute("SELECT * FROM ml_questions WHERE id = ?", (question_id,)).fetchone()
    if not q:
        raise MLError(404, "pregunta no encontrada")
    if q["status"] != "UNANSWERED":
        raise MLError(409, "esa pregunta ya se respondió")
    token = token_for(db, q["user_id"])
    http("POST", "/answers", token, body={"question_id": int(question_id), "text": text})
    db.execute("UPDATE ml_questions SET status = 'ANSWERED', answer = ?, answered_by = ?, answered_at = ? WHERE id = ?",
               (text, actor, now_iso(), question_id))
    db.commit()


def reply_message(db, user_id, pack_id, text):
    conv = db.execute("SELECT * FROM ml_conversations WHERE user_id = ? AND pack_id = ?", (user_id, pack_id)).fetchone()
    buyer = conv["buyer_id"] if conv else None
    if not buyer:
        row = db.execute("SELECT buyer_id FROM ml_orders WHERE user_id = ? AND (pack_id = ? OR id = ?) LIMIT 1",
                         (user_id, pack_id, pack_id)).fetchone()
        buyer = row["buyer_id"] if row else None
    if not buyer:
        raise MLError(404, "no se encontró el comprador de esa conversación")
    token = token_for(db, user_id)
    http("POST", f"/messages/packs/{pack_id}/sellers/{user_id}?tag=post_sale", token,
         body={"from": {"user_id": int(user_id)}, "to": {"user_id": int(buyer)}, "text": text})
    db.execute("UPDATE ml_conversations SET unread = 0, last_text = ?, last_from_buyer = 0, last_date = ?, updated_at = ? "
               "WHERE user_id = ? AND pack_id = ?", (text, now_iso(), now_iso(), user_id, pack_id))
    db.commit()


def conversation(db, user_id, pack_id):
    token = token_for(db, user_id)
    data = http("GET", f"/messages/packs/{pack_id}/sellers/{user_id}?tag=post_sale&mark_as_read=false&limit=30", token)
    msgs = sorted(data.get("messages") or [], key=lambda m: (m.get("message_date") or {}).get("created", ""))
    return [{"from_me": (m.get("from") or {}).get("user_id") == int(user_id), "text": m.get("text", ""),
             "date": (m.get("message_date") or {}).get("created", "")} for m in msgs]
