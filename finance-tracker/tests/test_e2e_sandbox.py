"""§12 end-to-end against Plaid Sandbox. Slow + needs real credentials."""
from __future__ import annotations

import os

import pytest


pytestmark = pytest.mark.slow


def _have_sandbox_creds():
    return all(os.getenv(v) for v in ("PLAID_CLIENT_ID", "PLAID_SECRET")) and os.getenv("PLAID_ENV") == "sandbox"


@pytest.mark.skipif(not _have_sandbox_creds(), reason="needs sandbox creds in env")
def test_12_1_fresh_install_happy_path(tmp_path, monkeypatch):
    """Manual: link ins_109508 with user_good/pass_good first via link.py.
    This test assumes a token already exists for institution='sandbox_chase'.
    """
    monkeypatch.setenv("FINANCE_DATA_DIR", str(tmp_path))
    from src.db import init_db, get_connection
    from src.fetch import fetch_all

    init_db()
    fetch_all()
    conn = get_connection()
    assert conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] > 0
    assert conn.execute("SELECT COUNT(*) FROM balances").fetchone()[0] > 0


@pytest.mark.skipif(not _have_sandbox_creds(), reason="needs sandbox creds in env")
def test_12_2_simulated_credit_card_payment(tmp_path, monkeypatch):
    """Manually inject a matched pair across two sandbox accounts; verify is_transfer flagging."""
    monkeypatch.setenv("FINANCE_DATA_DIR", str(tmp_path))
    from src.db import init_db, get_connection, upsert_transaction
    from src.analyze import detect_transfers
    from tests.fixtures.factories import txn

    init_db()
    conn = get_connection()
    upsert_transaction(conn, txn(amount=-1234.56, date="2026-04-10", account_id="sb_chk", transaction_id="cc_pmt_out"))
    upsert_transaction(conn, txn(amount=1234.56, date="2026-04-10", account_id="sb_cc", transaction_id="cc_pmt_in"))
    conn.commit()
    detect_transfers(conn)
    flagged = {r[0] for r in conn.execute("SELECT transaction_id FROM transactions WHERE is_transfer=1").fetchall()}
    assert flagged == {"cc_pmt_out", "cc_pmt_in"}


@pytest.mark.skipif(not _have_sandbox_creds(), reason="needs sandbox creds in env")
def test_12_3_manual_net_worth_verification(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCE_DATA_DIR", str(tmp_path))
    from src.db import init_db, get_connection
    from src.fetch import fetch_all
    from src.analyze import compute_weekly_snapshot, most_recent_sunday

    init_db()
    fetch_all()
    conn = get_connection()
    week = most_recent_sunday()
    snap = compute_weekly_snapshot(conn, week_ending=week)

    # Manual sum from current balances table
    rows = conn.execute("""
        SELECT account_type, SUM(balance_current)
        FROM balances
        WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM balances b2 WHERE b2.account_id = balances.account_id AND b2.snapshot_date <= ?)
        GROUP BY account_type
    """, (week,)).fetchall()
    by_type = dict(rows)
    expected = by_type.get("depository", 0) + by_type.get("investment", 0) - by_type.get("credit", 0)
    assert snap["net_worth"] == pytest.approx(expected, abs=0.01)
