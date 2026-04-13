import json
import sqlite3
from datetime import UTC, date, datetime, timedelta

from . import config


SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id TEXT PRIMARY KEY,
    account_id TEXT,
    institution TEXT,
    date TEXT,
    amount REAL,
    merchant_name TEXT,
    name TEXT,
    plaid_category TEXT,
    my_category TEXT,
    pending INTEGER DEFAULT 0,
    is_transfer INTEGER DEFAULT 0,
    raw_json TEXT
);

CREATE TABLE IF NOT EXISTS balances (
    account_id TEXT,
    institution TEXT,
    account_name TEXT,
    account_type TEXT,
    account_subtype TEXT,
    balance_current REAL,
    balance_available REAL,
    snapshot_date TEXT,
    PRIMARY KEY (account_id, snapshot_date)
);

CREATE TABLE IF NOT EXISTS sync_cursors (
    item_id TEXT PRIMARY KEY,
    cursor TEXT,
    last_synced TEXT
);

CREATE TABLE IF NOT EXISTS weekly_snapshots (
    week_ending TEXT PRIMARY KEY,
    net_worth REAL,
    total_cash REAL,
    total_invested REAL,
    total_credit_debt REAL,
    income_this_week REAL,
    spending_this_week REAL,
    net_income_this_week REAL,
    spending_by_category_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_transactions_institution ON transactions(institution);
CREATE INDEX IF NOT EXISTS idx_balances_snapshot ON balances(snapshot_date);
"""


def get_connection(path=None):
    conn = sqlite3.connect(str(path or config.db_path()))
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path=None):
    conn = get_connection(path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


_TX_COLUMNS = (
    "transaction_id",
    "account_id",
    "institution",
    "date",
    "amount",
    "merchant_name",
    "name",
    "plaid_category",
    "my_category",
    "pending",
    "is_transfer",
    "raw_json",
)


def upsert_transaction(conn, row):
    values = {col: row.get(col) for col in _TX_COLUMNS}
    if values["pending"] is None:
        values["pending"] = 0
    if values["is_transfer"] is None:
        values["is_transfer"] = 0
    conn.execute(
        """
        INSERT INTO transactions (
            transaction_id, account_id, institution, date, amount,
            merchant_name, name, plaid_category, my_category, pending,
            is_transfer, raw_json
        ) VALUES (
            :transaction_id, :account_id, :institution, :date, :amount,
            :merchant_name, :name, :plaid_category, :my_category, :pending,
            :is_transfer, :raw_json
        )
        ON CONFLICT(transaction_id) DO UPDATE SET
            account_id=excluded.account_id,
            institution=excluded.institution,
            date=excluded.date,
            amount=excluded.amount,
            merchant_name=excluded.merchant_name,
            name=excluded.name,
            plaid_category=excluded.plaid_category,
            pending=excluded.pending,
            raw_json=excluded.raw_json
        """,
        values,
    )


_BAL_COLUMNS = (
    "account_id",
    "institution",
    "account_name",
    "account_type",
    "account_subtype",
    "balance_current",
    "balance_available",
    "snapshot_date",
)


def upsert_balance(conn, row):
    values = {col: row.get(col) for col in _BAL_COLUMNS}
    conn.execute(
        """
        INSERT INTO balances (
            account_id, institution, account_name, account_type, account_subtype,
            balance_current, balance_available, snapshot_date
        ) VALUES (
            :account_id, :institution, :account_name, :account_type, :account_subtype,
            :balance_current, :balance_available, :snapshot_date
        )
        ON CONFLICT(account_id, snapshot_date) DO UPDATE SET
            institution=excluded.institution,
            account_name=excluded.account_name,
            account_type=excluded.account_type,
            account_subtype=excluded.account_subtype,
            balance_current=excluded.balance_current,
            balance_available=excluded.balance_available
        """,
        values,
    )


def remove_transactions(conn, transaction_ids):
    ids = list(transaction_ids or [])
    if not ids:
        return
    conn.executemany(
        "DELETE FROM transactions WHERE transaction_id = ?",
        [(tid,) for tid in ids],
    )


def get_cursor(conn, item_id):
    row = conn.execute(
        "SELECT cursor FROM sync_cursors WHERE item_id = ?", (item_id,)
    ).fetchone()
    return row[0] if row else None


def _update_cursor(conn, item_id, cursor):
    conn.execute(
        """
        INSERT INTO sync_cursors (item_id, cursor, last_synced)
        VALUES (?, ?, ?)
        ON CONFLICT(item_id) DO UPDATE SET
            cursor=excluded.cursor,
            last_synced=excluded.last_synced
        """,
        (item_id, cursor, datetime.now(UTC).isoformat()),
    )


def apply_sync_page(
    conn,
    *,
    item_id,
    added=None,
    modified=None,
    removed=None,
    new_cursor=None,
    next_cursor=None,
    institution=None,
    _force_fail_after_write=False,
):
    new_cursor = new_cursor if new_cursor is not None else next_cursor
    added = added or []
    modified = modified or []
    removed = removed or []
    try:
        conn.execute("BEGIN")
        for tx in added:
            row = _plaid_tx_to_row(tx, institution)
            upsert_transaction(conn, row)
        for tx in modified:
            row = _plaid_tx_to_row(tx, institution)
            upsert_transaction(conn, row)
        removed_ids = [
            t["transaction_id"] if isinstance(t, dict) else t for t in removed
        ]
        remove_transactions(conn, removed_ids)
        if _force_fail_after_write:
            raise RuntimeError("forced failure after write for test")
        _update_cursor(conn, item_id, new_cursor)
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _plaid_tx_to_row(tx, institution):
    pfc = tx.get("personal_finance_category") or {}
    primary = pfc.get("primary") if isinstance(pfc, dict) else None
    my_cat = config.remap_category(primary)
    tx_date = tx.get("date")
    if hasattr(tx_date, "isoformat"):
        tx_date = tx_date.isoformat()
    return {
        "transaction_id": tx.get("transaction_id"),
        "account_id": tx.get("account_id"),
        "institution": institution,
        "date": tx_date,
        "amount": tx.get("amount"),
        "merchant_name": tx.get("merchant_name"),
        "name": tx.get("name"),
        "plaid_category": primary,
        "my_category": my_cat,
        "pending": 1 if tx.get("pending") else 0,
        "is_transfer": 0,
        "raw_json": json.dumps(tx, default=str),
    }


def transactions_in_week(conn, week_ending):
    if isinstance(week_ending, (datetime, date)):
        end = week_ending if isinstance(week_ending, date) and not isinstance(week_ending, datetime) else week_ending.date()
    else:
        end = date.fromisoformat(str(week_ending))
    start = end - timedelta(days=6)
    cur = conn.execute(
        """
        SELECT * FROM transactions
        WHERE date(date) BETWEEN date(?) AND date(?)
        ORDER BY date ASC, transaction_id ASC
        """,
        (start.isoformat(), end.isoformat()),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def save_weekly_snapshot(conn, snap):
    conn.execute(
        """
        INSERT INTO weekly_snapshots (
            week_ending, net_worth, total_cash, total_invested, total_credit_debt,
            income_this_week, spending_this_week, net_income_this_week, spending_by_category_json
        ) VALUES (
            :week_ending, :net_worth, :total_cash, :total_invested, :total_credit_debt,
            :income_this_week, :spending_this_week, :net_income_this_week, :spending_by_category_json
        )
        ON CONFLICT(week_ending) DO UPDATE SET
            net_worth=excluded.net_worth,
            total_cash=excluded.total_cash,
            total_invested=excluded.total_invested,
            total_credit_debt=excluded.total_credit_debt,
            income_this_week=excluded.income_this_week,
            spending_this_week=excluded.spending_this_week,
            net_income_this_week=excluded.net_income_this_week,
            spending_by_category_json=excluded.spending_by_category_json
        """,
        {
            "week_ending": snap["week_ending"],
            "net_worth": snap["net_worth"],
            "total_cash": snap["total_cash"],
            "total_invested": snap["total_invested"],
            "total_credit_debt": snap["total_credit_debt"],
            "income_this_week": snap["income_this_week"],
            "spending_this_week": snap["spending_this_week"],
            "net_income_this_week": snap["net_income_this_week"],
            "spending_by_category_json": json.dumps(snap.get("spending_by_category", {})),
        },
    )
    conn.commit()
