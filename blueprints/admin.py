import re
import sqlite3

from flask import Blueprint, g, jsonify, render_template, request
from werkzeug.security import generate_password_hash

import auth
from db import DB_PATH, get_db, now_iso

bp = Blueprint("admin", __name__)

USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,30}$")

USERS_QUERY = "SELECT u.*, r.name AS role_name FROM users u LEFT JOIN roles r ON r.id = u.role_id "


def user_dict(row):
    return {
        "id": row["id"],
        "username": row["username"],
        "full_name": row["full_name"],
        "role_id": row["role_id"],
        "role_name": "Dueño" if row["is_owner"] else row["role_name"],
        "is_owner": bool(row["is_owner"]),
        "active": bool(row["active"]),
        "must_change_password": bool(row["must_change_password"]),
        "last_login": row["last_login"] or "",
    }


def role_dict(row, user_count=0):
    perms = [p for p in (row["permissions"] or "").split(",") if p]
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "permissions": perms,
        "is_system": bool(row["is_system"]),
        "user_count": user_count,
    }


# ---------------------------------------------------------------------------
# Paginas
# ---------------------------------------------------------------------------
@bp.route("/usuarios")
def users_page():
    return render_template("usuarios.html", active="usuarios")


@bp.route("/actividad")
def audit_page():
    return render_template("actividad.html", active="actividad")


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------
@bp.route("/api/users", methods=["GET"])
def list_users():
    db = get_db()
    rows = db.execute(USERS_QUERY + "ORDER BY u.is_owner DESC, u.id").fetchall()
    return jsonify([user_dict(r) for r in rows])


@bp.route("/api/users", methods=["POST"])
def create_user():
    data = request.get_json(force=True) or {}
    username = str(data.get("username", "")).strip().lower()
    full_name = str(data.get("full_name", "")).strip()
    if not USERNAME_RE.match(username):
        return jsonify({"error": "Usuario invalido: 3 a 30 caracteres, solo letras minusculas, numeros, punto, guion"}), 400
    if not full_name:
        return jsonify({"error": "El nombre es obligatorio"}), 400

    db = get_db()
    role = db.execute("SELECT id FROM roles WHERE id = ?", (data.get("role_id"),)).fetchone()
    if not role:
        return jsonify({"error": "Elegi un rol"}), 400
    if db.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
        return jsonify({"error": f"Ya existe el usuario {username}"}), 409

    password = str(data.get("password", "")).strip()
    if password:
        problem = auth.validate_new_password(password)
        if problem:
            return jsonify({"error": problem}), 400
    else:
        password = auth.generate_temp_password()

    cur = db.execute(
        "INSERT INTO users (username, full_name, password_hash, role_id, is_owner, active, must_change_password, created_at) "
        "VALUES (?, ?, ?, ?, 0, 1, 1, ?)",
        (username, full_name, generate_password_hash(password), role["id"], now_iso()),
    )
    db.commit()
    auth.audit("usuario_creado", "user", cur.lastrowid, username)
    row = db.execute(USERS_QUERY + "WHERE u.id = ?", (cur.lastrowid,)).fetchone()
    return jsonify({"user": user_dict(row), "temp_password": password}), 201


@bp.route("/api/users/<int:user_id>", methods=["PUT"])
def update_user(user_id):
    db = get_db()
    row = db.execute(USERS_QUERY + "WHERE u.id = ?", (user_id,)).fetchone()
    if not row:
        return jsonify({"error": "usuario no encontrado"}), 404
    data = request.get_json(force=True) or {}

    full_name = str(data.get("full_name", row["full_name"])).strip() or row["full_name"]
    if row["is_owner"]:
        db.execute("UPDATE users SET full_name = ? WHERE id = ?", (full_name, user_id))
        db.commit()
        return jsonify(user_dict(db.execute(USERS_QUERY + "WHERE u.id = ?", (user_id,)).fetchone()))

    role_id = data.get("role_id", row["role_id"])
    if not db.execute("SELECT 1 FROM roles WHERE id = ?", (role_id,)).fetchone():
        return jsonify({"error": "rol invalido"}), 400
    active = 1 if data.get("active", bool(row["active"])) else 0

    # Si se desactiva o cambia de rol, se cierra su sesion para que el cambio rija ya
    token_bump = 1 if (active == 0 and row["active"]) or role_id != row["role_id"] else 0
    db.execute(
        "UPDATE users SET full_name = ?, role_id = ?, active = ?, token_version = token_version + ? WHERE id = ?",
        (full_name, role_id, active, token_bump, user_id),
    )
    db.commit()
    detail = f"{row['username']}: rol {row['role_id']}->{role_id}, activo {row['active']}->{active}"
    auth.audit("usuario_editado", "user", user_id, detail)
    return jsonify(user_dict(db.execute(USERS_QUERY + "WHERE u.id = ?", (user_id,)).fetchone()))


@bp.route("/api/users/<int:user_id>/reset-password", methods=["POST"])
def reset_password(user_id):
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        return jsonify({"error": "usuario no encontrado"}), 404
    temp = auth.generate_temp_password()
    db.execute(
        "UPDATE users SET password_hash = ?, must_change_password = ?, token_version = token_version + 1 WHERE id = ?",
        (generate_password_hash(temp), 0 if row["is_owner"] else 1, user_id),
    )
    db.commit()
    auth.audit("clave_reseteada", "user", user_id, row["username"])
    return jsonify({"temp_password": temp, "same_user": row["id"] == g.user["id"]})


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------
@bp.route("/api/permissions", methods=["GET"])
def permissions_catalog():
    return jsonify([{"group": grp, "key": key, "label": label} for grp, key, label in auth.PERMISSIONS])


@bp.route("/api/roles", methods=["GET"])
def list_roles():
    db = get_db()
    rows = db.execute(
        "SELECT r.*, (SELECT COUNT(*) FROM users u WHERE u.role_id = r.id) AS user_count FROM roles r ORDER BY r.id"
    ).fetchall()
    return jsonify([role_dict(r, r["user_count"]) for r in rows])


def _clean_permissions(raw):
    perms = [p for p in (raw or []) if p in auth.PERMISSION_KEYS]
    return ",".join(sorted(set(perms), key=auth.PERMISSION_KEYS.index))


@bp.route("/api/roles", methods=["POST"])
def create_role():
    data = request.get_json(force=True) or {}
    name = str(data.get("name", "")).strip()
    if not name:
        return jsonify({"error": "El nombre del rol es obligatorio"}), 400
    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO roles (name, description, permissions, is_system, created_at) VALUES (?, ?, ?, 0, ?)",
            (name, str(data.get("description", "")).strip(), _clean_permissions(data.get("permissions")), now_iso()),
        )
    except sqlite3.IntegrityError:
        return jsonify({"error": f"Ya existe un rol llamado {name}"}), 409
    db.commit()
    auth.audit("rol_creado", "role", cur.lastrowid, name)
    row = db.execute("SELECT * FROM roles WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(role_dict(row)), 201


@bp.route("/api/roles/<int:role_id>", methods=["PUT"])
def update_role(role_id):
    db = get_db()
    row = db.execute("SELECT * FROM roles WHERE id = ?", (role_id,)).fetchone()
    if not row:
        return jsonify({"error": "rol no encontrado"}), 404
    data = request.get_json(force=True) or {}
    description = str(data.get("description", row["description"])).strip()
    if row["is_system"]:
        name, perms = row["name"], row["permissions"]
    else:
        name = str(data.get("name", row["name"])).strip() or row["name"]
        perms = _clean_permissions(data.get("permissions"))
    try:
        db.execute(
            "UPDATE roles SET name = ?, description = ?, permissions = ? WHERE id = ?",
            (name, description, perms, role_id),
        )
    except sqlite3.IntegrityError:
        return jsonify({"error": f"Ya existe un rol llamado {name}"}), 409
    # Los permisos cambiaron: se cierran las sesiones de ese rol para que rija ya
    db.execute("UPDATE users SET token_version = token_version + 1 WHERE role_id = ? AND is_owner = 0", (role_id,))
    db.commit()
    auth.audit("rol_editado", "role", role_id, f"{name}: {perms}")
    row = db.execute("SELECT * FROM roles WHERE id = ?", (role_id,)).fetchone()
    return jsonify(role_dict(row))


@bp.route("/api/roles/<int:role_id>", methods=["DELETE"])
def delete_role(role_id):
    db = get_db()
    row = db.execute("SELECT * FROM roles WHERE id = ?", (role_id,)).fetchone()
    if not row:
        return jsonify({"error": "rol no encontrado"}), 404
    if row["is_system"]:
        return jsonify({"error": "El rol Administrador no se puede eliminar"}), 409
    if db.execute("SELECT 1 FROM users WHERE role_id = ?", (role_id,)).fetchone():
        return jsonify({"error": "Hay usuarios con este rol. Cambialos de rol primero."}), 409
    db.execute("DELETE FROM roles WHERE id = ?", (role_id,))
    db.commit()
    auth.audit("rol_eliminado", "role", role_id, row["name"])
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Registro de actividad
# ---------------------------------------------------------------------------
@bp.route("/api/audit", methods=["GET"])
def list_audit():
    clauses, params = [], []
    username = request.args.get("user", "").strip()
    action = request.args.get("action", "").strip()
    q = request.args.get("q", "").strip()
    if username:
        clauses.append("username = ?")
        params.append(username)
    if action:
        clauses.append("action = ?")
        params.append(action)
    if q:
        clauses.append("(detail LIKE ? OR entity_id LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    try:
        limit = min(max(int(request.args.get("limit", 200)), 1), 500)
    except ValueError:
        limit = 200
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    db = get_db()
    rows = db.execute(f"SELECT * FROM audit_log {where} ORDER BY id DESC LIMIT ?", (*params, limit)).fetchall()
    actions = [r[0] for r in db.execute("SELECT DISTINCT action FROM audit_log ORDER BY action").fetchall()]
    users = [r[0] for r in db.execute("SELECT username FROM users ORDER BY username").fetchall()]
    return jsonify(
        {
            "items": [
                {
                    "id": r["id"], "username": r["username"], "action": r["action"], "entity": r["entity"],
                    "entity_id": r["entity_id"], "detail": r["detail"], "ip": r["ip"], "created_at": r["created_at"],
                }
                for r in rows
            ],
            "actions": actions,
            "users": users,
        }
    )


# ---------------------------------------------------------------------------
# Herramientas del dueño: backup y limpieza de datos
# ---------------------------------------------------------------------------
def _make_backup(dest_path):
    import sqlite3 as _sqlite

    src = _sqlite.connect(DB_PATH)
    dst = _sqlite.connect(dest_path)
    with dst:
        src.backup(dst)
    dst.close()
    src.close()


@bp.route("/api/admin/backup", methods=["GET"])
def download_backup():
    import os
    import tempfile
    from datetime import datetime

    from flask import send_file

    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    _make_backup(tmp)
    auth.audit("backup_descargado", "", "", "")
    name = f"tengo-stock-backup-{datetime.now().strftime('%Y%m%d-%H%M')}.db"

    resp = send_file(tmp, as_attachment=True, download_name=name, mimetype="application/octet-stream")
    resp.call_on_close(lambda: os.path.exists(tmp) and os.remove(tmp))
    return resp


WIPE_TARGETS = {
    "sales": "Ventas y devoluciones",
    "expenses": "Gastos",
    "products": "Productos y movimientos de stock",
    "customers": "Clientes y cuentas corrientes",
    "audit": "Registro de actividad",
}


@bp.route("/api/admin/wipe", methods=["POST"])
def wipe_data():
    import os
    import shutil
    from datetime import datetime

    from blueprints.products import UPLOAD_DIR

    data = request.get_json(force=True) or {}
    if str(data.get("confirm", "")).strip().upper() != "BORRAR":
        return jsonify({"error": "Escribi BORRAR para confirmar"}), 400
    targets = {t for t in (data.get("targets") or []) if t in WIPE_TARGETS}
    if not targets:
        return jsonify({"error": "Elegi que datos borrar"}), 400

    db = get_db()
    has_sales = db.execute("SELECT 1 FROM sales LIMIT 1").fetchone() is not None
    if "products" in targets and has_sales and "sales" not in targets:
        return jsonify({"error": "Para borrar productos hay que borrar tambien las ventas"}), 400
    if "customers" in targets and has_sales and "sales" not in targets:
        return jsonify({"error": "Para borrar clientes hay que borrar tambien las ventas"}), 400

    # copia de seguridad automatica antes de borrar
    backup_dir = os.path.join(os.path.dirname(str(DB_PATH)), "backups")
    os.makedirs(backup_dir, exist_ok=True)
    backup_name = f"antes-de-borrar-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
    _make_backup(os.path.join(backup_dir, backup_name))

    counts = {}

    def wipe(table, label):
        counts[label] = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        db.execute(f"DELETE FROM {table}")

    try:
        if "sales" in targets:
            wipe("return_items", "items de devoluciones")
            wipe("returns", "devoluciones")
            wipe("sale_items", "items de ventas")
            wipe("sales", "ventas")
            db.execute("DELETE FROM stock_movements WHERE reference_type IN ('sale', 'return')")
        if "expenses" in targets:
            wipe("expenses", "gastos")
        if "customers" in targets:
            wipe("account_payments", "movimientos de cuenta corriente")
            wipe("customers", "clientes")
        if "products" in targets:
            wipe("stock_movements", "movimientos de stock")
            wipe("products", "productos")
        if "audit" in targets:
            wipe("audit_log", "registros de actividad")
        db.commit()
    except Exception as exc:
        db.rollback()
        return jsonify({"error": f"No se pudo borrar: {exc}"}), 500

    if "products" in targets:
        shutil.rmtree(UPLOAD_DIR, ignore_errors=True)

    auth.audit("datos_borrados", "", "", ", ".join(f"{k}: {v}" for k, v in counts.items()) + f" | backup {backup_name}")
    return jsonify({"ok": True, "deleted": counts, "backup": backup_name})
