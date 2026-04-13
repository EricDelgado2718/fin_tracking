"""§9 analyze.py — weekly snapshot math."""
from __future__ import annotations

import json

import pytest

from tests.fixtures.factories import txn, balance, fixture_week_412_balances


WEEK = "2026-04-12"  # Sunday


def _insert_balances(db, rows):
    from src.db import upsert_balance
    for r in rows:
        upsert_balance(db, r)
    db.commit()


def _insert_txns(db, rows):
    from src.db import upsert_transaction
    for r in rows:
        upsert_transaction(db, r)
    db.commit()


def test_9_1_net_worth_formula(db):
    from src.analyze import compute_weekly_snapshot
    _insert_balances(db, fixture_week_412_balances())
    snap = compute_weekly_snapshot(db, week_ending=WEEK)
    assert snap["total_cash"] == 23000.00
    assert snap["total_invested"] == 50000.00
    assert snap["total_credit_debt"] == 1000.00
    assert snap["net_worth"] == 72000.00


def test_9_2_window_inclusive_sunday_exclusive_next_monday(db):
    from src.analyze import compute_weekly_snapshot
    _insert_balances(db, fixture_week_412_balances())
    _insert_txns(db, [
        # Mon Apr 06 — included
        txn(amount=10.0, date="2026-04-06", account_id="chk", transaction_id="in_window"),
        # Mon Apr 13 — excluded
        txn(amount=20.0, date="2026-04-13", account_id="chk", transaction_id="out_of_window"),
    ])
    snap = compute_weekly_snapshot(db, week_ending=WEEK)
    assert snap["spending_this_week"] == 10.0


def test_9_3_income_excludes_transfers(db):
    from src.analyze import compute_weekly_snapshot
    _insert_balances(db, fixture_week_412_balances())
    _insert_txns(db, [
        txn(amount=-3000.00, date="2026-04-09", account_id="chk", transaction_id="paycheck"),
        txn(amount=-500.00, date="2026-04-09", account_id="hysa", is_transfer=1, transaction_id="xfer_in_hysa"),
    ])
    snap = compute_weekly_snapshot(db, week_ending=WEEK)
    assert snap["income_this_week"] == 3000.00


def test_9_4_spending_credit_plus_depository_excludes_transfers(db):
    from src.analyze import compute_weekly_snapshot
    _insert_balances(db, fixture_week_412_balances())
    _insert_txns(db, [
        txn(amount=50.0, date="2026-04-08", account_id="chk", pfc_primary="FOOD_AND_DRINK_GROCERIES",
            my_category="Groceries", transaction_id="g"),
        txn(amount=75.0, date="2026-04-08", account_id="cc1", pfc_primary="FOOD_AND_DRINK_RESTAURANTS",
            my_category="Eating out", transaction_id="d"),
        txn(amount=1200.0, date="2026-04-09", account_id="chk", is_transfer=1, transaction_id="cc_pmt_out"),
        txn(amount=-1200.0, date="2026-04-09", account_id="cc1", is_transfer=1, transaction_id="cc_pmt_in"),
    ])
    snap = compute_weekly_snapshot(db, week_ending=WEEK)
    assert snap["spending_this_week"] == 125.0


def test_9_5_net_income(db):
    from src.analyze import compute_weekly_snapshot
    _insert_balances(db, fixture_week_412_balances())
    _insert_txns(db, [
        txn(amount=-1000.0, date="2026-04-08", account_id="chk", transaction_id="pay"),
        txn(amount=300.0, date="2026-04-09", account_id="chk", transaction_id="spend"),
    ])
    snap = compute_weekly_snapshot(db, week_ending=WEEK)
    assert snap["net_income_this_week"] == 700.0


def test_9_6_spending_by_category(db):
    from src.analyze import compute_weekly_snapshot
    _insert_balances(db, fixture_week_412_balances())
    _insert_txns(db, [
        txn(amount=50.0, date="2026-04-08", account_id="chk", my_category="Groceries", transaction_id="g"),
        txn(amount=75.0, date="2026-04-09", account_id="cc1", my_category="Eating out", transaction_id="d"),
    ])
    snap = compute_weekly_snapshot(db, week_ending=WEEK)
    by_cat = json.loads(snap["spending_by_category_json"])
    assert by_cat == {"Groceries": 50.0, "Eating out": 75.0}


def test_9_7_default_week_ending(db, monkeypatch):
    from src.analyze import compute_weekly_snapshot, most_recent_sunday
    try:
        from freezegun import freeze_time
    except ImportError:
        pytest.skip("freezegun not installed")
    with freeze_time("2026-04-15"):  # Wednesday
        # Most recent past Sunday from a Wednesday is the previous Sunday (2026-04-12)
        assert most_recent_sunday() == "2026-04-12"
        _insert_balances(db, fixture_week_412_balances())
        snap = compute_weekly_snapshot(db)
        assert snap["week_ending"] == "2026-04-12"


def test_9_8_no_transactions_in_window(db):
    from src.analyze import compute_weekly_snapshot
    _insert_balances(db, fixture_week_412_balances())
    snap = compute_weekly_snapshot(db, week_ending=WEEK)
    assert snap["income_this_week"] == 0
    assert snap["spending_this_week"] == 0
    assert snap["net_income_this_week"] == 0
    assert json.loads(snap["spending_by_category_json"]) == {}


def test_9_9_uses_latest_balance_le_week_ending(db):
    from src.analyze import compute_weekly_snapshot
    from src.db import upsert_balance
    upsert_balance(db, balance(account_id="chk", balance_current=2500.0, snapshot_date="2026-04-10",
                               account_type="depository"))
    upsert_balance(db, balance(account_id="chk", balance_current=3000.0, snapshot_date="2026-04-12",
                               account_type="depository"))
    upsert_balance(db, balance(account_id="chk", balance_current=9999.0, snapshot_date="2026-04-14",
                               account_type="depository"))
    db.commit()
    snap = compute_weekly_snapshot(db, week_ending=WEEK)
    assert snap["total_cash"] == 3000.0
