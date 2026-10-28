import os
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(os.environ.get("STOCK_DB_PATH", Path(__file__).parent / "stock.db"))


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def get_db():
    from flask import g

    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(exception=None):
    from flask import g

    db = g.pop("db", None)
    if db is not None:
        db.close()


def _backup_before_migration():
    """Si la base existente es de una version anterior (con datos y sin oficinas), guarda una copia
    completa en backups/ ANTES de tocar nada. Queda en el mismo disco persistente que la base."""
    import shutil

    path = Path(DB_PATH)
    if not path.exists() or path.stat().st_size == 0:
        return
    probe = sqlite3.connect(path)
    try:
        tables = {r[0] for r in probe.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if "products" not in tables or "offices" in tables:
            return
    finally:
        probe.close()
    backup_dir = path.parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    target = backup_dir / f"antes-de-migrar-oficinas-{datetime.now():%Y%m%d-%H%M%S}.db"
    shutil.copy2(path, target)
    print(f"Copia de seguridad previa a la migracion: {target}")


def init_db():
    _backup_before_migration()
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA foreign_keys = ON")

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            sku TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            price REAL NOT NULL DEFAULT 0,
            quantity INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )
        """
    )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            type TEXT NOT NULL DEFAULT 'other',
            external_account_id TEXT DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
        """
    )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT DEFAULT '',
            email TEXT DEFAULT '',
            doc_number TEXT DEFAULT '',
            note TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id INTEGER NOT NULL REFERENCES channels(id),
            customer_id INTEGER REFERENCES customers(id),
            status TEXT NOT NULL DEFAULT 'completed',
            subtotal REAL NOT NULL DEFAULT 0,
            discount REAL NOT NULL DEFAULT 0,
            total REAL NOT NULL DEFAULT 0,
            payment_method TEXT DEFAULT '',
            note TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS sale_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER NOT NULL REFERENCES sales(id),
            sku TEXT NOT NULL REFERENCES products(sku),
            product_name TEXT NOT NULL,
            unit_price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            line_total REAL NOT NULL
        )
        """
    )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS returns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER NOT NULL REFERENCES sales(id),
            reason TEXT NOT NULL DEFAULT '',
            note TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS return_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            return_id INTEGER NOT NULL REFERENCES returns(id),
            sale_item_id INTEGER NOT NULL REFERENCES sale_items(id),
            quantity INTEGER NOT NULL
        )
        """
    )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            expense_date TEXT NOT NULL,
            vendor TEXT DEFAULT '',
            note TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS stock_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT NOT NULL REFERENCES products(sku),
            change_qty INTEGER NOT NULL,
            reason TEXT NOT NULL,
            reference_type TEXT DEFAULT '',
            reference_id INTEGER,
            created_at TEXT NOT NULL
        )
        """
    )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS account_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL REFERENCES customers(id),
            amount REAL NOT NULL,
            payment_method TEXT DEFAULT '',
            note TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )

    _ensure_column(db, "products", "category", "category TEXT DEFAULT ''")
    _ensure_column(db, "products", "currency", "currency TEXT DEFAULT 'ARS'")
    _ensure_column(db, "stock_movements", "note", "note TEXT DEFAULT ''")
    _ensure_column(db, "sales", "currency", "currency TEXT DEFAULT 'ARS'")
    _ensure_column(db, "account_payments", "currency", "currency TEXT DEFAULT 'ARS'")
    _ensure_column(db, "account_payments", "type", "type TEXT DEFAULT 'payment'")

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT DEFAULT '',
            permissions TEXT NOT NULL DEFAULT '',
            is_system INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """
    )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            full_name TEXT NOT NULL DEFAULT '',
            password_hash TEXT NOT NULL,
            role_id INTEGER REFERENCES roles(id),
            is_owner INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            must_change_password INTEGER NOT NULL DEFAULT 0,
            token_version INTEGER NOT NULL DEFAULT 1,
            last_login TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT NOT NULL DEFAULT '',
            action TEXT NOT NULL,
            entity TEXT DEFAULT '',
            entity_id TEXT DEFAULT '',
            detail TEXT DEFAULT '',
            ip TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at)")

    _ensure_column(db, "products", "photo", "photo TEXT DEFAULT ''")
    _ensure_column(db, "products", "min_stock", "min_stock INTEGER NOT NULL DEFAULT 0")
    _ensure_column(db, "sales", "stock_deducted", "stock_deducted INTEGER NOT NULL DEFAULT 1")
    for table in ("sales", "returns", "expenses", "stock_movements", "account_payments"):
        _ensure_column(db, table, "created_by", "created_by TEXT DEFAULT ''")


    db.execute(
        """
        CREATE TABLE IF NOT EXISTS offices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS stock_levels (
            sku TEXT NOT NULL REFERENCES products(sku),
            office_id INTEGER NOT NULL REFERENCES offices(id),
            quantity INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (sku, office_id)
        )
        """
    )

    _ensure_column(db, "products", "condition", "condition TEXT NOT NULL DEFAULT 'Nuevo'")
    _ensure_column(db, "products", "price_wholesale", "price_wholesale REAL NOT NULL DEFAULT 0")
    _ensure_column(db, "stock_movements", "office_id", "office_id INTEGER")
    _ensure_column(db, "sales", "office_id", "office_id INTEGER")
    _ensure_column(db, "sales", "sale_type", "sale_type TEXT NOT NULL DEFAULT 'minorista'")
    _ensure_column(db, "customers", "address", "address TEXT DEFAULT ''")
    _ensure_column(db, "customers", "city", "city TEXT DEFAULT ''")
    _ensure_column(db, "customers", "province", "province TEXT DEFAULT ''")
    _ensure_column(db, "customers", "office_id", "office_id INTEGER")
    _ensure_column(db, "customers", "customer_type", "customer_type TEXT NOT NULL DEFAULT 'minorista'")
    _ensure_column(db, "users", "office_id", "office_id INTEGER")

    # Primera oficina y reparto inicial del stock existente (solo la primera vez)
    if db.execute("SELECT COUNT(*) FROM offices").fetchone()[0] == 0:
        db.execute("INSERT INTO offices (name, active, created_at) VALUES ('Villanova', 1, ?)", (now_iso(),))
    default_office = db.execute("SELECT MIN(id) FROM offices").fetchone()[0]
    db.execute(
        "INSERT INTO stock_levels (sku, office_id, quantity) "
        "SELECT sku, ?, quantity FROM products "
        "WHERE quantity != 0 AND sku NOT IN (SELECT sku FROM stock_levels)",
        (default_office,),
    )
    db.execute("UPDATE stock_movements SET office_id = ? WHERE office_id IS NULL", (default_office,))
    db.execute("UPDATE sales SET office_id = ? WHERE office_id IS NULL", (default_office,))

    db.execute(
        "INSERT OR IGNORE INTO channels (name, type, active, created_at) VALUES (?, ?, 1, ?)",
        ("Mostrador", "mostrador", now_iso()),
    )

    db.commit()
    db.close()


def _ensure_column(db, table, column, ddl):
    existing = {row[1] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
