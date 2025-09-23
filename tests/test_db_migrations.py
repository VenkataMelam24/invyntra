from sqlalchemy import create_engine

from app.db_migrations import run_migrations


def _get_columns(conn, table):
    return {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()}


def _table_exists(conn, table):
    return conn.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def test_run_migrations_adds_inventory_columns():
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE items (
                id INTEGER PRIMARY KEY,
                name VARCHAR NOT NULL,
                unit VARCHAR NOT NULL
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE transactions (
                id INTEGER PRIMARY KEY,
                item_id INTEGER NOT NULL,
                kind VARCHAR NOT NULL,
                qty FLOAT NOT NULL
            )
            """
        )
        conn.exec_driver_sql("INSERT INTO items (id, name, unit) VALUES (1, 'Rice', 'kg')")
        conn.exec_driver_sql("INSERT INTO transactions (item_id, kind, qty) VALUES (1, 'IN', 5)")

    run_migrations(engine)

    with engine.begin() as conn:
        item_cols = _get_columns(conn, "items")
        txn_cols = _get_columns(conn, "transactions")
        assert {"owner_key", "normalized_name"}.issubset(item_cols)
        assert {"owner_key", "unit", "location", "location_normalized", "entered_by", "source", "raw_payload", "ts"}.issubset(txn_cols)
        unit_value = conn.exec_driver_sql("SELECT unit FROM transactions WHERE id = 1").scalar_one()
        assert unit_value == "kg"
        assert _table_exists(conn, "stock_snapshots")
        assert _table_exists(conn, "audit_logs")
