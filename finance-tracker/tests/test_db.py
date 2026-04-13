"""§2 db.py — schema, upserts, atomicity, windowed queries."""
from __future__ import annotations

import pytest

from tests.fixtures.factories import txn, balance


REQUIRED_TABLES = {"transactions", "balances", "sync_cursors", "weekly_snapshots"}


def _tables(conn):
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r[0] for r in rows}


def test_2_1_init_db_is_idempotent(env):
    from src.db import init_db, get_connection, upsert_transaction
    init_db()
    conn = get_connection()
    upsert_transaction(conn, txn(amount=10.0, date="2026-04-10"))
    conn.commit()
    init_db()  # second call
    conn2 = get_connection()
    assert REQUIRED_TABLES.issubset(_tables(conn2))
    assert conn2.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 1


def test_2_2_transaction_upsert_by_pk(db):
    from src.db import upsert_transaction
    row = txn(amount=10.00, date="2026-04-10", transaction_id="txn_1", pending=1)
    upsert_transaction(db, row)
    row2 = {**row, "amount": 10.50, "pending": 0}
    upsert_transaction(db, row2)
    db.commit()
    rows = db.execute("SELECT amount, pending FROM transactions WHERE transaction_id='txn_1'").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 10.50
    assert rows[0][1] == 0


def test_2_3_balance_pk_account_and_date(db):
    from src.db import upsert_balance
    upsert_balance(db, balance(account_id="a", balance_current=100.0, snapshot_date="2026-04-10"))
    upsert_balance(db, balance(account_id="a", balance_current=150.0, snapshot_date="2026-04-11"))
    upsert_balance(db, balance(account_id="a", balance_current=999.0, snapshot_date="2026-04-10"))  # update
    db.commit()
    rows = db.execute("SELECT snapshot_date, balance_current FROM balances WHERE account_id='a' ORDER BY snapshot_date").fetchall()
    assert len(rows) == 2
    assert rows[0] == ("2026-04-10", 999.0)
    assert rows[1] == ("2026-04-11", 150.0)


def test_2_4_remove_array_deletes(db):
    from src.db import upsert_transaction, remove_transactions
    upsert_transaction(db, txn(amount=5.0, date="2026-04-10", transaction_id="txn_1"))
    db.commit()
    remove_transactions(db, ["txn_1"])
    db.commit()
    assert db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 0


def test_2_5_cursor_write_atomic_with_txns(db):
    from src.db import apply_sync_page
    # Expected API: apply_sync_page writes added/modified/removed AND advances cursor in a single transaction.
    added = [txn(amount=1.0, date="2026-04-10", transaction_id="new_1")]
    with pytest.raises(RuntimeError):
        apply_sync_page(
            db,
            item_id="item_xyz",
            added=added,
            modified=[],
            removed=[],
            new_cursor="CURSOR_V2",
            _force_fail_after_write=True,  # test hook expected on this function
        )
    # Rollback: no row and no cursor row
    assert db.execute("SELECT COUNT(*) FROM transactions WHERE transaction_id='new_1'").fetchone()[0] == 0
    row = db.execute("SELECT cursor FROM sync_cursors WHERE item_id='item_xyz'").fetchone()
    assert row is None or row[0] != "CURSOR_V2"


def test_2_6_weekly_window_query_inclusive_bounds(db):
    from src.db import upsert_transaction, transactions_in_week
    dates = ["2026-04-05", "2026-04-06", "2026-04-12", "2026-04-13"]
    for d in dates:
        upsert_transaction(db, txn(amount=1.0, date=d, transaction_id=f"t_{d}"))
    db.commit()
    rows = transactions_in_week(db, week_ending="2026-04-12")
    got_dates = sorted(r["date"] for r in rows)
    assert got_dates == ["2026-04-06", "2026-04-12"]
