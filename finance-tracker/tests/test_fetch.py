"""§6 fetch.py — per-institution sync + balance snapshot + reauth isolation."""
from __future__ import annotations

from unittest.mock import patch

import pytest


def _plaid_txn(tid, amount, date, account_id="acct_checking"):
    return {
        "transaction_id": tid,
        "account_id": account_id,
        "date": date,
        "amount": amount,
        "merchant_name": "Merchant",
        "name": "NAME",
        "personal_finance_category": {"primary": "GENERAL_MERCHANDISE_OTHER"},
        "pending": False,
    }


def _plaid_balance(account_id, account_type, current, subtype="checking"):
    return {
        "account_id": account_id,
        "name": "Account",
        "type": account_type,
        "subtype": subtype,
        "balances": {"current": current, "available": current},
    }


@pytest.fixture
def linked(env):
    from src.tokens import save_token
    save_token("chase", access_token="acc-chase", item_id="item-chase")
    save_token("capital_one", access_token="acc-co", item_id="item-co")
    save_token("discover", access_token="acc-disc", item_id="item-disc")


def test_6_1_full_sync_happy_path(env, linked, frozen_today):
    from src import fetch
    from src.db import init_db, get_connection
    init_db()

    def fake_sync(access_token, cursor, institution=None):
        return {
            "added": [_plaid_txn("t1", 12.50, "2026-04-10"), _plaid_txn("t2", -500.00, "2026-04-09")],
            "modified": [],
            "removed": [],
            "next_cursor": "cursor_v1",
        }

    def fake_balances(access_token, institution=None):
        return [_plaid_balance("acct_checking", "depository", 1500.00)]

    with patch("src.fetch.sync_transactions", side_effect=fake_sync), \
         patch("src.fetch.accounts_balance_get", side_effect=fake_balances):
        fetch.fetch_all()

    conn = get_connection()
    assert conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] >= 2
    assert conn.execute("SELECT COUNT(*) FROM balances WHERE snapshot_date='2026-04-13'").fetchone()[0] >= 1
    cur = conn.execute("SELECT cursor FROM sync_cursors").fetchall()
    assert any(r[0] == "cursor_v1" for r in cur)


def test_6_2_second_run_incremental(env, linked, frozen_today):
    from src import fetch
    from src.db import init_db, get_connection
    init_db()

    call_count = {"n": 0}
    def fake_sync(access_token, cursor, institution=None):
        call_count["n"] += 1
        if cursor is None:
            return {"added": [_plaid_txn("t1", 10.0, "2026-04-10")], "modified": [], "removed": [], "next_cursor": "c1"}
        return {"added": [], "modified": [], "removed": [], "next_cursor": cursor}

    with patch("src.fetch.sync_transactions", side_effect=fake_sync), \
         patch("src.fetch.accounts_balance_get", return_value=[_plaid_balance("a", "depository", 100.0)]):
        fetch.fetch_all()
        fetch.fetch_all()

    conn = get_connection()
    assert conn.execute("SELECT COUNT(*) FROM transactions WHERE transaction_id='t1'").fetchone()[0] == 1


def test_6_3_reauth_isolates(env, linked, capsys):
    from src import fetch
    from src.plaid_client import PlaidReauthRequired
    from src.db import init_db, get_connection
    init_db()

    def fake_sync(access_token, cursor, institution=None):
        if institution == "capital_one":
            raise PlaidReauthRequired(institution="capital_one")
        return {"added": [_plaid_txn(f"t-{institution}", 1.0, "2026-04-10")], "modified": [], "removed": [], "next_cursor": "c"}

    with patch("src.fetch.sync_transactions", side_effect=fake_sync), \
         patch("src.fetch.accounts_balance_get", return_value=[_plaid_balance("a", "depository", 100.0)]):
        fetch.fetch_all()  # must NOT raise

    out = capsys.readouterr()
    assert "capital_one" in (out.out + out.err)
    assert "re-link" in (out.out + out.err).lower()
    conn = get_connection()
    # Other institutions still wrote
    rows = conn.execute("SELECT transaction_id FROM transactions").fetchall()
    ids = {r[0] for r in rows}
    assert "t-chase" in ids
    assert "t-discover" in ids


def test_6_4_balance_snapshot_date_is_today(env, linked, frozen_today):
    from src import fetch
    from src.db import init_db, get_connection
    init_db()
    with patch("src.fetch.sync_transactions", return_value={"added": [], "modified": [], "removed": [], "next_cursor": "c"}), \
         patch("src.fetch.accounts_balance_get", return_value=[_plaid_balance("a", "depository", 100.0)]):
        fetch.fetch_all()
    conn = get_connection()
    dates = {r[0] for r in conn.execute("SELECT DISTINCT snapshot_date FROM balances").fetchall()}
    assert dates == {"2026-04-13"}


def test_6_5_sign_convention_preserved(env, linked, frozen_today):
    from src import fetch
    from src.db import init_db, get_connection
    init_db()
    with patch("src.fetch.sync_transactions", return_value={
        "added": [_plaid_txn("deposit", -500.00, "2026-04-09")],
        "modified": [], "removed": [], "next_cursor": "c",
    }), patch("src.fetch.accounts_balance_get", return_value=[]):
        fetch.fetch_all()
    conn = get_connection()
    amt = conn.execute("SELECT amount FROM transactions WHERE transaction_id='deposit'").fetchone()[0]
    assert amt == -500.00
