"""Tareas automaticas en segundo plano (un hilo dentro del servidor):

- Sincronizar las ventas de Tienda Nube cada 10 minutos (si esta activada).
- Copia de seguridad diaria de la base (se guardan las ultimas 14) en el disco persistente.
- Mercado Libre multicuenta: ventas, preguntas, reclamos y mensajes cada 5 minutos (ml_multi.py).
- Resumen diario por mail a las 8:00 (hora de Argentina), si esta configurado.

Se puede apagar con la variable STOCK_DISABLE_JOBS=1 (la usan las pruebas).
"""
import os
import smtplib
import sqlite3
import threading
import time
from datetime import date, datetime, time as dtime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

import ml_multi
import profitability
import tn_sync
from db import DB_PATH, now_iso

ART = timezone(timedelta(hours=-3))
KEEP_DAILY_BACKUPS = 14
SUMMARY_HOUR = 8
TICK_SECONDS = 60

_started = False
_last_tn_run = 0.0
_last_ml_run = 0.0
_last_summary_try = 0.0


# ---------------------------------------------------------------------------
# Copias de seguridad
# ---------------------------------------------------------------------------
def backup_dir():
    path = Path(DB_PATH).parent / "backups"
    path.mkdir(exist_ok=True)
    return path


def make_backup(dest):
    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(dest)
    try:
        with dst:
            src.backup(dst)
    finally:
        dst.close()
        src.close()


def verify_backup(path):
    conn = sqlite3.connect(path)
    try:
        return conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        conn.close()


def daily_backup(today=None):
    """Una copia por dia (diario-AAAAMMDD.db). Devuelve el nombre si la hizo, None si ya existia."""
    today = today or datetime.now(ART).date()
    folder = backup_dir()
    target = folder / f"diario-{today:%Y%m%d}.db"
    if target.exists():
        return None
    tmp = folder / f".tmp-{target.name}"
    tmp.unlink(missing_ok=True)
    make_backup(tmp)
    if not verify_backup(tmp):
        tmp.unlink(missing_ok=True)
        raise RuntimeError("la copia de seguridad no paso la verificacion de integridad")
    tmp.replace(target)
    for old in sorted(folder.glob("diario-*.db"))[:-KEEP_DAILY_BACKUPS]:
        old.unlink(missing_ok=True)
    return target.name


def list_backups():
    items = []
    for f in sorted(backup_dir().glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True):
        if f.name.startswith("."):
            continue
        st = f.stat()
        items.append({"name": f.name, "size": st.st_size, "modified": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")})
    return items


# ---------------------------------------------------------------------------
# Resumen diario
# ---------------------------------------------------------------------------
def day_bounds(day):
    """Inicio y fin del dia argentino, expresados en la hora del servidor (como se guardan las ventas)."""
    start = datetime.combine(day, dtime(0, 0), ART)
    end = start + timedelta(days=1)
    naive = lambda d: d.astimezone().replace(tzinfo=None).isoformat(timespec="seconds")
    return naive(start), naive(end)


def build_summary(db, day=None, sales=True, costs=True):
    day = day or (datetime.now(ART).date() - timedelta(days=1))
    start, end = day_bounds(day)
    out = {"date": day.isoformat(), "sales": None, "stock": {}, "tienda_nube": None}

    if sales:
        totals = db.execute(
            "SELECT COALESCE(currency, 'ARS') AS cur, COUNT(*) AS n, COALESCE(SUM(total), 0) AS total FROM sales "
            "WHERE created_at >= ? AND created_at < ? GROUP BY COALESCE(currency, 'ARS')", (start, end)).fetchall()
        channels = db.execute(
            "SELECT c.name, COUNT(*) AS n, COALESCE(SUM(s.total), 0) AS total FROM sales s JOIN channels c ON c.id = s.channel_id "
            "WHERE s.created_at >= ? AND s.created_at < ? AND COALESCE(s.currency, 'ARS') = 'ARS' GROUP BY c.id ORDER BY total DESC",
            (start, end)).fetchall()
        top = db.execute(
            "SELECT si.sku, si.product_name, SUM(si.quantity) AS qty FROM sale_items si JOIN sales s ON s.id = si.sale_id "
            "WHERE s.created_at >= ? AND s.created_at < ? GROUP BY si.sku ORDER BY qty DESC LIMIT 5", (start, end)).fetchall()
        out["sales"] = {
            "totals": [{"currency": r["cur"], "count": r["n"], "total": r["total"]} for r in totals],
            "by_channel": [{"channel": r["name"], "count": r["n"], "total": r["total"]} for r in channels],
            "top": [{"sku": r["sku"], "name": r["product_name"], "quantity": r["qty"]} for r in top],
        }

    zero = db.execute("SELECT sku, name, quantity, min_stock FROM products WHERE min_stock > 0 AND quantity <= 0 ORDER BY name LIMIT 15").fetchall()
    low = db.execute(
        "SELECT sku, name, quantity, min_stock FROM products WHERE min_stock > 0 AND quantity > 0 AND quantity <= min_stock "
        "ORDER BY quantity LIMIT 15").fetchall()
    out["stock"] = {
        "zero": [dict(r) for r in zero],
        "low": [dict(r) for r in low],
        "negative": db.execute("SELECT COUNT(*) FROM stock_levels WHERE quantity < 0").fetchone()[0],
    }
    if costs:
        cfg = profitability.load_config(db)
        losing = []
        for p in db.execute("SELECT sku, name, price, cost_price, currency FROM products WHERE cost_price > 0 AND price > 0").fetchall():
            analysis = profitability.analyze(p["cost_price"], p["price"], cfg, p["currency"])
            if analysis and analysis["is_negative"]:
                losing.append({"sku": p["sku"], "name": p["name"]})
        out["stock"]["losing_money"] = {"count": len(losing), "items": losing[:10]}

    try:
        tn = tn_sync.status_summary(db)
        imported_yesterday = db.execute(
            "SELECT COUNT(*) FROM sales WHERE created_by = 'tienda-nube' AND created_at >= ? AND created_at < ?", (start, end)).fetchone()[0]
        out["tienda_nube"] = {"enabled": tn["enabled"], "review": tn["review"], "flagged": tn["flagged"],
                              "last_error": tn["last_error"], "imported_yesterday": imported_yesterday}
    except sqlite3.Error:
        pass
    return out


def _money(value, currency="ARS"):
    text = f"{value:,.0f}".replace(",", ".")
    return f"US$ {text}" if currency == "USD" else f"$ {text}"


def format_text(s):
    day = date.fromisoformat(s["date"])
    lines = [f"Resumen de Tengo Stock - {day:%d/%m/%Y}", ""]
    if s["sales"] is not None:
        sales = s["sales"]
        if sales["totals"]:
            lines.append("VENTAS DEL DIA")
            for t in sales["totals"]:
                lines.append(f"  {t['count']} venta(s) por {_money(t['total'], t['currency'])}")
            for c in sales["by_channel"]:
                lines.append(f"    - {c['channel']}: {c['count']} ({_money(c['total'])})")
            if sales["top"]:
                lines.append("  Mas vendidos: " + ", ".join(f"{t['name']} x{t['quantity']}" for t in sales["top"]))
        else:
            lines.append("VENTAS DEL DIA: no hubo ventas registradas.")
        lines.append("")
    st = s["stock"]
    lines.append("STOCK")
    lines.append(f"  Sin stock (con minimo definido): {len(st['zero'])}" + (": " + ", ".join(i["name"] for i in st["zero"][:5]) if st["zero"] else ""))
    lines.append(f"  Por debajo del minimo: {len(st['low'])}" + (": " + ", ".join(f"{i['name']} ({i['quantity']})" for i in st["low"][:5]) if st["low"] else ""))
    if st["negative"]:
        lines.append(f"  ATENCION: {st['negative']} producto(s) con stock negativo en alguna oficina.")
    if "losing_money" in st and st["losing_money"]["count"]:
        lines.append(f"  Productos que pierden plata con las reglas de margen: {st['losing_money']['count']}")
    tn = s.get("tienda_nube")
    if tn and (tn["enabled"] or tn["review"] or tn["flagged"]):
        lines.append("")
        lines.append("TIENDA NUBE")
        lines.append(f"  Ventas importadas ayer: {tn['imported_yesterday']}")
        if tn["review"]:
            lines.append(f"  Pedidos para revisar a mano: {tn['review']}")
        if tn["flagged"]:
            lines.append(f"  Pedidos ya cargados que se cancelaron o reembolsaron: {tn['flagged']}")
        if tn["last_error"]:
            lines.append(f"  Ultimo error de sincronizacion: {tn['last_error']}")
    lines.append("")
    lines.append("Detalle completo en la pestaña Alertas del sistema.")
    return "\n".join(lines)


def smtp_configured():
    return bool(os.environ.get("SMTP_HOST") and os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASSWORD"))


def send_email(recipients, subject, body):
    msg = EmailMessage()
    sender = os.environ.get("SMTP_FROM") or os.environ["SMTP_USER"]
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content(body)
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    if port == 465:
        server = smtplib.SMTP_SSL(host, port, timeout=30)
    else:
        server = smtplib.SMTP(host, port, timeout=30)
        server.starttls()
    try:
        server.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        server.send_message(msg)
    finally:
        server.quit()


def parse_recipients(text):
    return [x.strip() for x in str(text or "").replace(";", ",").split(",") if "@" in x.strip()]


def send_summary(db, day=None):
    """Arma y envia el resumen a los destinatarios guardados. Devuelve (ok, mensaje)."""
    recipients = parse_recipients(tn_sync.get_setting(db, "summary_to"))
    if not recipients:
        return False, "No hay destinatarios cargados"
    if not smtp_configured():
        return False, "Falta configurar el correo saliente en el servidor (SMTP_HOST, SMTP_USER, SMTP_PASSWORD)"
    summary = build_summary(db, day)
    send_email(recipients, f"Tengo Stock - resumen del {date.fromisoformat(summary['date']):%d/%m}", format_text(summary))
    return True, f"Enviado a {', '.join(recipients)}"


def _maybe_send_summary(db):
    global _last_summary_try
    if tn_sync.get_setting(db, "summary_enabled") != "1":
        return
    now = datetime.now(ART)
    today = now.date().isoformat()
    if now.hour < SUMMARY_HOUR or tn_sync.get_setting(db, "summary_last_date") == today:
        return
    if time.monotonic() - _last_summary_try < 1800:  # si falla, reintenta cada 30 minutos
        return
    _last_summary_try = time.monotonic()
    # reclamar el dia antes de enviar: si hay dos procesos, solo uno manda
    cur = db.execute(
        "INSERT INTO settings (key, value) VALUES ('summary_last_date', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value WHERE settings.value != excluded.value", (today,))
    db.commit()
    if cur.rowcount == 0:
        return
    try:
        ok, message = send_summary(db)
    except Exception as exc:  # SMTP caido, clave mala, etc.
        ok, message = False, str(exc)
    tn_sync.set_setting(db, "summary_last_result", f"{now_iso()}: {message}"[:300])
    if not ok:  # liberar el dia para reintentar
        tn_sync.set_setting(db, "summary_last_date", "")
    db.commit()


# ---------------------------------------------------------------------------
# Hilo principal
# ---------------------------------------------------------------------------
def tick():
    global _last_tn_run, _last_ml_run
    db = tn_sync.connect()
    try:
        tn_sync.ensure_schema(db)
        if tn_sync.get_setting(db, "tn_enabled") == "1" and tn_sync.configured():
            if time.monotonic() - _last_tn_run >= tn_sync.SYNC_EVERY_SECONDS:
                _last_tn_run = time.monotonic()
                tn_sync.run_sync()
        if ml_multi.configured() and time.monotonic() - _last_ml_run >= ml_multi.SYNC_EVERY_SECONDS:
            _last_ml_run = time.monotonic()
            try:
                ml_multi.sync_all()
            except Exception as exc:
                print(f"[jobs] mercado libre: {exc}")
        try:
            daily_backup()
        except Exception as exc:
            tn_sync.set_setting(db, "backup_last_error", f"{now_iso()}: {exc}"[:300])
            db.commit()
        _maybe_send_summary(db)
    finally:
        db.close()


def _loop():
    time.sleep(20)  # dejar que el servidor termine de arrancar
    while True:
        try:
            tick()
        except Exception as exc:  # el hilo nunca debe morir
            print(f"[jobs] error: {exc}")
        time.sleep(TICK_SECONDS)


def start():
    global _started
    if _started or os.environ.get("STOCK_DISABLE_JOBS") == "1":
        return
    _started = True
    threading.Thread(target=_loop, name="tengo-stock-jobs", daemon=True).start()
