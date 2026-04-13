"""§7 analyze.py — transfer detection (the highest-risk module)."""
from __future__ import annotations

import pytest

from tests.fixtures.factories import txn


def _insert(conn, rows):
    from src.db import upsert_transaction
    for r in rows:
        upsert_transaction(conn, r)
    conn.commit()


def _flagged(conn):
    rows = conn.execute("SELECT transaction_id, is_transfer FROM transactions").fetchall()
    return {r[0] for r in rows if r[1] == 1}


def test_7_1_credit_card_payment_detected(db):
    from src.analyze import detect_transfers
    _insert(db, [
        txn(amount=-1200.00, date="2026-04-10", account_id="chk", institution="chase", transaction_id="p_out"),
        txn(amount=1200.00, date="2026-04-10", account_id="cc1", institution="chase", transaction_id="p_in"),
    ])
    detect_transfers(db)
    assert _flagged(db) == {"p_out", "p_in"}


@pytest.mark.parametrize(
    "offset_days,expected_flagged",
    [(0, True), (1, True), (2, True), (3, False)],
)
def test_7_2_window_boundary(db, offset_days, expected_flagged):
    from src.analyze import detect_transfers
    from datetime import date, timedelta
    d0 = date(2026, 4, 10)
    d1 = (d0 + timedelta(days=offset_days)).isoformat()
    _insert(db, [
        txn(amount=-100.00, date=d0.isoformat(), account_id="A", transaction_id="a"),
        txn(amount=100.00, date=d1, account_id="B", transaction_id="b"),
    ])
    detect_transfers(db)
    assert (_flagged(db) == {"a", "b"}) is expected_flagged


def test_7_3_exact_amount_match_only(db):
    from src.analyze import detect_transfers
    _insert(db, [
        txn(amount=-100.00, date="2026-04-10", account_id="A", transaction_id="a"),
        txn(amount=100.01, date="2026-04-10", account_id="B", transaction_id="b"),
    ])
    detect_transfers(db)
    assert _flagged(db) == set()


def test_7_4_opposite_sign_required(db):
    from src.analyze import detect_transfers
    _insert(db, [
        txn(amount=100.00, date="2026-04-10", account_id="A", transaction_id="a"),
        txn(amount=100.00, date="2026-04-10", account_id="B", transaction_id="b"),
    ])
    detect_transfers(db)
    assert _flagged(db) == set()


def test_7_5_same_account_ignored(db):
    from src.analyze import detect_transfers
    _insert(db, [
        txn(amount=-100.00, date="2026-04-10", account_id="A", transaction_id="a"),
        txn(amount=100.00, date="2026-04-10", account_id="A", transaction_id="b"),
    ])
    detect_transfers(db)
    assert _flagged(db) == set()


def test_7_6_no_double_pairing(db):
    from src.analyze import detect_transfers
    _insert(db, [
        txn(amount=-100.00, date="2026-04-10", account_id="A", transaction_id="a"),
        txn(amount=100.00, date="2026-04-10", account_id="B", transaction_id="b"),
        txn(amount=100.00, date="2026-04-10", account_id="C", transaction_id="c"),
    ])
    detect_transfers(db)
    flagged = _flagged(db)
    assert len(flagged) == 2
    assert "a" in flagged
    # Deterministic: pair with the earlier transaction_id
    assert "b" in flagged and "c" not in flagged


def test_7_7_checking_to_investment(db):
    from src.analyze import detect_transfers
    _insert(db, [
        txn(amount=500.00, date="2026-04-10", account_id="chk", institution="chase", transaction_id="out"),
        txn(amount=-500.00, date="2026-04-10", account_id="brk", institution="schwab", transaction_id="in"),
    ])
    detect_transfers(db)
    assert _flagged(db) == {"out", "in"}


def test_7_8_idempotent(db):
    from src.analyze import detect_transfers
    _insert(db, [
        txn(amount=-50.00, date="2026-04-10", account_id="A", transaction_id="a"),
        txn(amount=50.00, date="2026-04-10", account_id="B", transaction_id="b"),
    ])
    detect_transfers(db)
    first = _flagged(db)
    detect_transfers(db)
    assert _flagged(db) == first


def test_7_9_already_flagged_rows_not_reconsidered(db):
    from src.analyze import detect_transfers
    # Lone flagged row with no partner
    _insert(db, [txn(amount=50.00, date="2026-04-10", account_id="A", transaction_id="lone", is_transfer=1)])
    detect_transfers(db)
    # Should remain flagged (not un-flagged)
    got = db.execute("SELECT is_transfer FROM transactions WHERE transaction_id='lone'").fetchone()[0]
    assert got == 1
