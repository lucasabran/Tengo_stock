"""Usuarios, roles, permisos, sesion y registro de actividad."""
import os
import secrets
import sqlite3
import time
from urllib.parse import urlparse

from flask import abort, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from db import DB_PATH, get_db, now_iso

# ---------------------------------------------------------------------------
# Catalogo de permisos (grupo, clave, descripcion)
# ---------------------------------------------------------------------------
PERMISSIONS = [
    ("Dashboard", "dashboard.view", "Ver el dashboard (ventas, ganancias, totales)"),
    ("Stock", "stock.view", "Ver productos y stock"),
    ("Stock", "stock.edit", "Crear/editar productos y cargar stock"),
    ("Stock", "stock.delete", "Eliminar productos"),
    ("Stock", "stock.import", "Importar y exportar productos (CSV/Excel)"),
    ("Stock", "movements.view", "Ver historial de movimientos de stock"),
    ("Ventas", "sales.view", "Ver ventas y comprobantes"),
    ("Ventas", "sales.create", "Registrar ventas"),
    ("Ventas", "sales.export", "Exportar ventas a CSV"),
    ("Ventas", "sales.import", "Cargar ventas masivamente desde Excel"),
    ("Ventas", "sales.delete", "Eliminar ventas (devuelve el stock)"),
    ("Devoluciones", "returns.view", "Ver devoluciones"),
    ("Devoluciones", "returns.create", "Registrar devoluciones"),
    ("Devoluciones", "returns.delete", "Eliminar devoluciones"),
    ("Clientes", "customers.view", "Ver clientes"),
    ("Clientes", "customers.manage", "Editar y eliminar clientes"),
    ("Cuentas corrientes", "accounts.view", "Ver cuentas corrientes (informacion sensible)"),
    ("Cuentas corrientes", "accounts.manage", "Registrar movimientos de cuenta corriente"),
    ("Gastos", "expenses.view", "Ver gastos (informacion sensible)"),
    ("Gastos", "expenses.manage", "Crear y editar gastos"),
    ("Gastos", "expenses.import", "Cargar gastos masivamente desde Excel"),
    ("Gastos", "expenses.delete", "Eliminar gastos"),
    ("Configuracion", "channels.manage", "Editar y desactivar canales de venta"),
    ("Configuracion", "audit.view", "Ver el registro de actividad"),
]
PERMISSION_KEYS = [p[1] for p in PERMISSIONS]

ADMIN_ROLE = "Administrador"
OPERATOR_ROLE = "Operador"
OPERATOR_PERMS = ["stock.view", "stock.edit", "movements.view", "sales.view", "sales.create"]

# Cada endpoint exige AL MENOS UNO de estos permisos. Lo que no figura aca se
# deniega (salvo las rutas publicas de abajo).
ENDPOINT_PERMS = {
    "dashboard.dashboard_page": ("dashboard.view",),
    "dashboard.summary": ("dashboard.view",),
    "products.stock_page": ("stock.view",),
    "products.list_products": ("stock.view", "sales.create"),
    "products.list_categories": ("stock.view", "sales.create"),
    "products.get_product": ("stock.view", "sales.create"),
    "products.create_product": ("stock.edit",),
    "products.update_product": ("stock.edit",),
    "products.add_stock": ("stock.edit",),
    "products.upload_photo": ("stock.edit",),
    "products.delete_photo": ("stock.edit",),
    "products.product_photo": ("stock.view", "sales.create", "sales.view"),
    "products.download_template": ("stock.import",),
    "products.export_products": ("stock.import",),
    "products.import_products": ("stock.import",),
    "bulk.stock_entries_template": ("stock.import",),
    "bulk.import_stock_entries": ("stock.import",),
    "bulk.sales_template": ("sales.import",),
    "bulk.import_sales": ("sales.import",),
    "bulk.expenses_template": ("expenses.import",),
    "bulk.import_expenses": ("expenses.import",),
    "sales.delete_sale": ("sales.delete",),
    "returns.delete_return": ("returns.delete",),
    "products.delete_product": ("stock.delete",),
    "movements.movimientos_page": ("movements.view",),
    "movements.list_movements": ("movements.view",),
    "sales.ventas_page": ("sales.view",),
    "sales.venta_nueva_page": ("sales.create",),
    "sales.venta_detalle_page": ("sales.view",),
    "sales.comprobante": ("sales.view",),
    "sales.list_sales": ("sales.view", "returns.create"),
    "sales.get_sale": ("sales.view", "returns.create"),
    "sales.export_sales": ("sales.export",),
    "sales.create_sale": ("sales.create",),
    "returns.devoluciones_page": ("returns.view",),
    "returns.devolucion_nueva_page": ("returns.create",),
    "returns.list_returns": ("returns.view",),
    "returns.get_return": ("returns.view",),
    "returns.create_return": ("returns.create",),
    "customers.clientes_page": ("customers.view",),
    "customers.list_customers": ("customers.view", "sales.create", "accounts.view", "returns.create"),
    "customers.create_customer": ("customers.manage", "sales.create"),
    "customers.update_customer": ("customers.manage",),
    "customers.delete_customer": ("customers.manage",),
    "channels.list_channels": ("sales.view", "sales.create", "channels.manage"),
    "channels.create_channel": ("channels.manage", "sales.create"),
    "channels.update_channel": ("channels.manage",),
    "accounts.accounts_page": ("accounts.view",),
    "accounts.account_detail_page": ("accounts.view",),
    "accounts.list_accounts": ("accounts.view",),
    "accounts.get_account": ("accounts.view",),
    "accounts.create_movement": ("accounts.manage",),
    "expenses.gastos_page": ("expenses.view",),
    "expenses.list_expenses": ("expenses.view",),
    "expenses.export_expenses": ("expenses.view",),
    "expenses.create_expense": ("expenses.manage",),
    "expenses.update_expense": ("expenses.manage",),
    "expenses.delete_expense": ("expenses.delete",),
    "admin.audit_page": ("audit.view",),
    "admin.list_audit": ("audit.view",),
}

# Solo lo ve/usa el dueño (usuario con is_owner = 1)
OWNER_ONLY_ENDPOINTS = {
    "admin.users_page", "admin.list_users", "admin.create_user", "admin.update_user", "admin.reset_password",
    "admin.list_roles", "admin.create_role", "admin.update_role", "admin.delete_role", "admin.permissions_catalog",
    "admin.download_backup", "admin.wipe_data",
}
# Cualquier usuario con sesion iniciada
LOGGED_IN_ENDPOINTS = {"auth.account_page", "auth.change_password", "auth.logout", "auth.me"}
PUBLIC_ENDPOINTS = {"auth.login", "auth.login_page", "static", "healthcheck"}

# Orden y destino de la barra de navegacion: (clave, texto, url, permisos que la habilitan)
NAV_ITEMS = [
    ("dashboard", "Dashboard", "/", ("dashboard.view",)),
    ("stock", "Stock", "/stock", ("stock.view",)),
    ("movimientos", "Movimientos", "/movimientos", ("movements.view",)),
    ("ventas", "Ventas", "/ventas", ("sales.view", "sales.create")),
    ("devoluciones", "Devoluciones", "/devoluciones", ("returns.view",)),
    ("gastos", "Gastos", "/gastos", ("expenses.view",)),
    ("clientes", "Clientes", "/clientes", ("customers.view",)),
    ("cuentas", "Cuentas corrientes", "/cuentas", ("accounts.view",)),
    ("actividad", "Actividad", "/actividad", ("audit.view",)),
]


# ---------------------------------------------------------------------------
# Usuario actual y permisos
# ---------------------------------------------------------------------------
def _load_user(user_id):
    db = get_db()
    return db.execute(
        "SELECT u.*, r.name AS role_name, r.permissions AS role_permissions "
        "FROM users u LEFT JOIN roles r ON r.id = u.role_id WHERE u.id = ?",
        (user_id,),
    ).fetchone()


def current_permissions(user):
    if user is None:
        return set()
    if user["is_owner"]:
        return set(PERMISSION_KEYS)
    return {p for p in (user["role_permissions"] or "").split(",") if p in PERMISSION_KEYS}


def has_any(perms):
    return bool(g.get("permissions", set()) & set(perms))


def first_allowed_url():
    for _key, _label, url, perms in NAV_ITEMS:
        if has_any(perms):
            return url
    return None


def audit(action, entity="", entity_id="", detail="", username=None):
    """Registra una accion. Usa su propia conexion para no mezclarse con la transaccion en curso."""
    user = g.get("user")
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.execute(
            "INSERT INTO audit_log (user_id, username, action, entity, entity_id, detail, ip, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user["id"] if user else None,
                username if username is not None else (user["username"] if user else ""),
                action, str(entity), str(entity_id), str(detail)[:500], _client_ip(), now_iso(),
            ),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error:
        pass


def actor():
    user = g.get("user")
    return user["username"] if user else ""


def _client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "")
    return (forwarded.split(",")[0].strip() if forwarded else request.remote_addr) or ""


# ---------------------------------------------------------------------------
# Intentos de login (en memoria: gunicorn corre con un solo worker)
# ---------------------------------------------------------------------------
MAX_FAILS = 5
LOCK_SECONDS = 300
_fails = {}


def _fail_key(username):
    return f"{_client_ip()}|{username.lower()}"


def is_locked(username):
    entries = [t for t in _fails.get(_fail_key(username), []) if time.time() - t < LOCK_SECONDS]
    _fails[_fail_key(username)] = entries
    return len(entries) >= MAX_FAILS


def register_fail(username):
    _fails.setdefault(_fail_key(username), []).append(time.time())


def clear_fails(username):
    _fails.pop(_fail_key(username), None)


# ---------------------------------------------------------------------------
# Claves
# ---------------------------------------------------------------------------
def generate_temp_password():
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(10))


def validate_new_password(password):
    if len(password or "") < 8:
        return "La clave debe tener al menos 8 caracteres"
    return None


_DUMMY_HASH = generate_password_hash("no-existe")


# ---------------------------------------------------------------------------
# Inicializacion: clave de sesion, roles y usuarios iniciales
# ---------------------------------------------------------------------------
def load_secret_key():
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT value FROM settings WHERE key = 'secret_key'").fetchone()
    if row:
        key = row[0]
    else:
        key = secrets.token_hex(32)
        conn.execute("INSERT INTO settings (key, value) VALUES ('secret_key', ?)", (key,))
        conn.commit()
    conn.close()
    return key


def seed_auth():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    now = now_iso()

    conn.execute(
        "INSERT OR IGNORE INTO roles (name, description, permissions, is_system, created_at) VALUES (?, ?, ?, 1, ?)",
        (ADMIN_ROLE, "Acceso a todo el sistema (menos administrar usuarios)", ",".join(PERMISSION_KEYS), now),
    )
    conn.execute(
        "INSERT OR IGNORE INTO roles (name, description, permissions, is_system, created_at) VALUES (?, ?, ?, 0, ?)",
        (OPERATOR_ROLE, "Solo carga ventas y stock. No ve gastos ni cuentas corrientes.", ",".join(OPERATOR_PERMS), now),
    )
    admin_role = conn.execute("SELECT id FROM roles WHERE name = ?", (ADMIN_ROLE,)).fetchone()["id"]
    operator_role = conn.execute("SELECT id FROM roles WHERE name = ?", (OPERATOR_ROLE,)).fetchone()["id"]
    # El rol Administrador siempre incluye los permisos nuevos que se agreguen al sistema
    conn.execute("UPDATE roles SET permissions = ? WHERE id = ?", (",".join(PERMISSION_KEYS), admin_role))

    owner_user = os.environ.get("STOCK_USER", "admin")
    owner_pass = os.environ.get("STOCK_PASSWORD", "admin1234")
    has_users = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"] > 0

    created = []
    if not has_users:
        conn.execute(
            "INSERT INTO users (username, full_name, password_hash, role_id, is_owner, active, must_change_password, created_at) "
            "VALUES (?, ?, ?, ?, 1, 1, 0, ?)",
            (owner_user, "Lucas Abran", generate_password_hash(owner_pass), admin_role, now),
        )
        initial = [
            ("denis", "Denis Olivera", admin_role),
            ("nahuel", "Nahuel Olivera", admin_role),
            ("user1", "Usuario 1", operator_role),
            ("user2", "Usuario 2", operator_role),
            ("user3", "Usuario 3", operator_role),
        ]
        for username, full_name, role_id in initial:
            temp = generate_temp_password()
            conn.execute(
                "INSERT INTO users (username, full_name, password_hash, role_id, is_owner, active, must_change_password, created_at) "
                "VALUES (?, ?, ?, ?, 0, 1, 1, ?)",
                (username, full_name, generate_password_hash(temp), role_id, now),
            )
            created.append((username, temp))
    elif os.environ.get("STOCK_FORCE_OWNER_RESET") == "1":
        # Rescate: si el dueño pierde su clave, define STOCK_FORCE_OWNER_RESET=1 y STOCK_PASSWORD en Render
        conn.execute(
            "UPDATE users SET password_hash = ?, active = 1, token_version = token_version + 1 WHERE is_owner = 1",
            (generate_password_hash(owner_pass),),
        )

    conn.commit()
    conn.close()

    if created:
        print("=" * 60)
        print("USUARIOS CREADOS (claves temporales, se piden cambiar al primer ingreso).")
        print("Tambien se pueden regenerar desde /usuarios con el usuario dueño.")
        for username, temp in created:
            print(f"  {username}: {temp}")
        print("=" * 60)


# ---------------------------------------------------------------------------
# Guardia de acceso
# ---------------------------------------------------------------------------
def _wants_json():
    return request.path.startswith("/api/") or request.is_json


def _deny(status, message):
    if _wants_json():
        return jsonify({"error": message}), status
    return render_template("error.html", status=status, message=message, home_url=first_allowed_url() or "/logout"), status


def _same_origin_ok():
    origin = request.headers.get("Origin")
    if not origin:
        return True
    return urlparse(origin).netloc == request.host


def install(app):
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=bool(os.environ.get("RENDER")),
        PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 14,
        MAX_CONTENT_LENGTH=8 * 1024 * 1024,
    )

    @app.before_request
    def guard():
        endpoint = request.endpoint
        if endpoint is None or endpoint in PUBLIC_ENDPOINTS:
            return None

        if request.method not in ("GET", "HEAD", "OPTIONS") and not _same_origin_ok():
            return _deny(403, "Origen no permitido")

        g.user = None
        g.permissions = set()
        user_id = session.get("uid")
        if user_id:
            user = _load_user(user_id)
            if user and user["active"] and user["token_version"] == session.get("tv"):
                g.user = user
                g.permissions = current_permissions(user)
        if g.user is None:
            session.clear()
            if _wants_json():
                return jsonify({"error": "Sesion vencida. Volve a ingresar."}), 401
            return redirect(url_for("auth.login_page", next=request.full_path.rstrip("?")))

        if g.user["must_change_password"] and endpoint not in ("auth.account_page", "auth.change_password", "auth.logout"):
            if _wants_json():
                return jsonify({"error": "Tenes que cambiar tu clave antes de seguir"}), 403
            return redirect(url_for("auth.account_page", forced=1))

        if endpoint in LOGGED_IN_ENDPOINTS:
            return None
        if endpoint in OWNER_ONLY_ENDPOINTS:
            return None if g.user["is_owner"] else _deny(403, "Solo el usuario dueño puede entrar aca")

        needed = ENDPOINT_PERMS.get(endpoint)
        if needed is None:
            return _deny(403, "Acceso no permitido")
        if not has_any(needed):
            # El inicio ("/") lleva a la primera seccion habilitada en lugar de mostrar un error
            if endpoint == "dashboard.dashboard_page":
                home = first_allowed_url()
                if home and home != "/":
                    return redirect(home)
            return _deny(403, "No tenes permiso para ver esto")
        return None

    @app.context_processor
    def inject_auth():
        user = g.get("user")
        perms = g.get("permissions", set())
        nav = [
            {"key": key, "label": label, "url": url}
            for key, label, url, needed in NAV_ITEMS
            if perms & set(needed)
        ]
        if user and user["is_owner"]:
            nav.append({"key": "usuarios", "label": "Usuarios y roles", "url": "/usuarios"})
        return {"current_user": user, "nav_items": nav, "user_perms": sorted(perms)}

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if request.endpoint not in ("static", "products.product_photo"):
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp


def start_session(user):
    session.clear()
    session.permanent = True
    session["uid"] = user["id"]
    session["tv"] = user["token_version"]
