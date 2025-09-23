"""Database schema migrations for legacy SQLite files."""
from __future__ import annotations

import logging

from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)


def _column_exists(conn, table: str, column: str) -> bool:
    rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def _index_exists(conn, table: str, index_name: str) -> bool:
    rows = conn.exec_driver_sql(f"PRAGMA index_list({table})").fetchall()
    return any(row[1] == index_name for row in rows)


def _table_exists(conn, table: str) -> bool:
    row = conn.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _ensure_column(conn, table: str, column: str, ddl: str) -> bool:
    if _column_exists(conn, table, column):
        return False
    log.debug("Adding column %s.%s", table, column)
    conn.exec_driver_sql(ddl)
    return True


def _ensure_index(conn, table: str, ddl: str, index_name: str) -> None:
    if _index_exists(conn, table, index_name):
        return
    log.debug("Creating index %s on %s", index_name, table)
    conn.exec_driver_sql(ddl)


def _ensure_table(conn, ddl: str) -> None:
    conn.exec_driver_sql(ddl)


def run_migrations(engine: Engine) -> None:
    """Upgrade legacy installations to the latest schema."""
    with engine.begin() as conn:
        # Items table upgrades
        added_owner = _ensure_column(
            conn,
            "items",
            "owner_key",
            "ALTER TABLE items ADD COLUMN owner_key VARCHAR NOT NULL DEFAULT ''",
        )
        added_normalized = _ensure_column(
            conn,
            "items",
            "normalized_name",
            "ALTER TABLE items ADD COLUMN normalized_name VARCHAR NOT NULL DEFAULT ''",
        )
        if added_owner:
            conn.exec_driver_sql("UPDATE items SET owner_key = COALESCE(owner_key, '')")
        if added_normalized:
            conn.exec_driver_sql(
                "UPDATE items SET normalized_name = lower(trim(name)) "
                "WHERE normalized_name IS NULL OR normalized_name = ''"
            )
        conn.exec_driver_sql(
            "UPDATE items SET normalized_name = lower(trim(name)) "
            "WHERE normalized_name IS NULL OR normalized_name = ''"
        )

        # Transactions table upgrades
        added_tx_owner = _ensure_column(
            conn,
            "transactions",
            "owner_key",
            "ALTER TABLE transactions ADD COLUMN owner_key VARCHAR NOT NULL DEFAULT ''",
        )
        added_unit = _ensure_column(
            conn,
            "transactions",
            "unit",
            "ALTER TABLE transactions ADD COLUMN unit VARCHAR NOT NULL DEFAULT ''",
        )
        added_ts = _ensure_column(
            conn,
            "transactions",
            "ts",
            "ALTER TABLE transactions ADD COLUMN ts DATETIME",
        )
        _ensure_column(
            conn,
            "transactions",
            "location",
            "ALTER TABLE transactions ADD COLUMN location VARCHAR NOT NULL DEFAULT ''",
        )
        _ensure_column(
            conn,
            "transactions",
            "location_normalized",
            "ALTER TABLE transactions ADD COLUMN location_normalized VARCHAR NOT NULL DEFAULT ''",
        )
        _ensure_column(
            conn,
            "transactions",
            "entered_by",
            "ALTER TABLE transactions ADD COLUMN entered_by VARCHAR NOT NULL DEFAULT ''",
        )
        _ensure_column(
            conn,
            "transactions",
            "source",
            "ALTER TABLE transactions ADD COLUMN source VARCHAR NOT NULL DEFAULT ''",
        )
        _ensure_column(
            conn,
            "transactions",
            "raw_payload",
            "ALTER TABLE transactions ADD COLUMN raw_payload TEXT NOT NULL DEFAULT ''",
        )

        if added_unit:
            conn.exec_driver_sql(
                "UPDATE transactions SET unit = COALESCE((SELECT unit FROM items WHERE items.id = transactions.item_id), '') "
                "WHERE unit IS NULL OR unit = ''"
            )
        if added_tx_owner:
            conn.exec_driver_sql(
                "UPDATE transactions SET owner_key = COALESCE((SELECT owner_key FROM items WHERE items.id = transactions.item_id), owner_key, '')"
            )
        if added_ts:
            conn.exec_driver_sql(
                "UPDATE transactions SET ts = COALESCE(ts, CURRENT_TIMESTAMP)"
            )

        # Stock snapshots table
        if not _table_exists(conn, "stock_snapshots"):
            _ensure_table(
                conn,
                """
                CREATE TABLE IF NOT EXISTS stock_snapshots (
                    id INTEGER PRIMARY KEY,
                    owner_key VARCHAR NOT NULL,
                    label VARCHAR,
                    actor VARCHAR,
                    data TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

        # Audit logs table
        if not _table_exists(conn, "audit_logs"):
            _ensure_table(
                conn,
                """
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY,
                    owner_key VARCHAR NOT NULL,
                    actor VARCHAR,
                    action VARCHAR NOT NULL,
                    entity VARCHAR,
                    reference_id INTEGER,
                    payload TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

        # Indexes
        _ensure_index(
            conn,
            "transactions",
            "CREATE INDEX IF NOT EXISTS ix_txn_owner_item_ts ON transactions (owner_key, item_id, ts)",
            "ix_txn_owner_item_ts",
        )
        _ensure_index(
            conn,
            "transactions",
            "CREATE INDEX IF NOT EXISTS ix_txn_owner_location ON transactions (owner_key, location_normalized)",
            "ix_txn_owner_location",
        )
        _ensure_index(
            conn,
            "stock_snapshots",
            "CREATE INDEX IF NOT EXISTS ix_snapshots_owner_created ON stock_snapshots (owner_key, created_at)",
            "ix_snapshots_owner_created",
        )
        _ensure_index(
            conn,
            "audit_logs",
            "CREATE INDEX IF NOT EXISTS ix_audit_owner_created ON audit_logs (owner_key, created_at)",
            "ix_audit_owner_created",
        )
