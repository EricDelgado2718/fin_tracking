"""§10 report.py — Google Sheets writes (gspread mocked)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


SUMMARY_HEADERS = [
    "Week Ending", "Net Worth", "Cash", "Invested", "Credit Debt",
    "Income", "Spending", "Net Income", "Savings Rate", "Top Category", "Top Category $",
]


def _snapshot(**overrides):
    base = {
        "week_ending": "2026-04-12",
        "net_worth": 72000.00,
        "total_cash": 23000.00,
        "total_invested": 50000.00,
        "total_credit_debt": 1000.00,
        "income_this_week": 3000.00,
        "spending_this_week": 600.00,
        "net_income_this_week": 2400.00,
        "spending_by_category_json": json.dumps({"Groceries": 200.0, "Eating out": 300.0, "Shopping": 100.0}),
    }
    base.update(overrides)
    return base


@pytest.fixture
def fake_gspread():
    """Patch gspread client and return the fake worksheet objects."""
    summary_ws = MagicMock(name="summary_ws")
    detail_ws = MagicMock(name="detail_ws")
    txns_ws = MagicMock(name="txns_ws")
    sheet = MagicMock(name="spreadsheet")

    def worksheet(name):
        return {"Weekly Summary": summary_ws, "Category Detail": detail_ws, "All Transactions": txns_ws}[name]
    sheet.worksheet.side_effect = worksheet

    client = MagicMock()
    client.open_by_key.return_value = sheet
    with patch("src.report._gspread_client", return_value=client):
        yield {"summary": summary_ws, "detail": detail_ws, "txns": txns_ws, "sheet": sheet}


def test_10_1_weekly_summary_schema(env, fake_gspread):
    from src.report import append_weekly_summary
    append_weekly_summary(_snapshot())
    args, _ = fake_gspread["summary"].append_row.call_args
    row = args[0]
    assert len(row) == 11
    assert row[0] == "2026-04-12"
    assert row[1] == 72000.00


def test_10_2_savings_rate(env, fake_gspread):
    from src.report import append_weekly_summary
    append_weekly_summary(_snapshot(income_this_week=3000.0, net_income_this_week=2400.0))
    row = fake_gspread["summary"].append_row.call_args.args[0]
    sr = row[8]
    assert ("80" in str(sr)) or sr == pytest.approx(0.80, rel=1e-3)


def test_10_2_savings_rate_zero_income_no_div(env, fake_gspread):
    from src.report import append_weekly_summary
    append_weekly_summary(_snapshot(income_this_week=0, net_income_this_week=-500))
    row = fake_gspread["summary"].append_row.call_args.args[0]
    sr = str(row[8])
    assert sr in ("", "N/A") or "n/a" in sr.lower()


def test_10_3_top_category(env, fake_gspread):
    from src.report import append_weekly_summary
    append_weekly_summary(_snapshot())
    row = fake_gspread["summary"].append_row.call_args.args[0]
    assert row[9] == "Eating out"
    assert row[10] == 300.0


def test_10_4_category_detail_batch(env, fake_gspread):
    from src.report import append_category_detail
    snap = _snapshot(spending_by_category_json=json.dumps({
        "Groceries": 200.0, "Eating out": 300.0, "Shopping": 100.0, "Transport": 50.0,
    }))
    # Optionally tracker for transaction counts
    append_category_detail(snap, txn_counts={"Groceries": 4, "Eating out": 6, "Shopping": 2, "Transport": 1})
    fake_gspread["detail"].append_rows.assert_called_once()
    rows = fake_gspread["detail"].append_rows.call_args.args[0]
    assert len(rows) == 4
    assert all(len(r) == 5 for r in rows)
    # First column always week_ending
    assert all(r[0] == "2026-04-12" for r in rows)


def test_10_5_idempotent_on_rerun(env, fake_gspread):
    """Pick a contract — here: second run for the same week is a no-op for the sheet."""
    from src.report import append_weekly_summary
    fake_gspread["summary"].col_values.return_value = ["Week Ending", "2026-04-12"]
    append_weekly_summary(_snapshot())
    fake_gspread["summary"].append_row.assert_not_called()


def test_10_6_include_transactions_flag(env, fake_gspread):
    from src.report import write_all_transactions
    transactions = [
        {"transaction_id": "t1", "date": "2026-04-10", "amount": 12.0,
         "merchant_name": "M", "name": "N", "my_category": "Shopping",
         "account_id": "a", "institution": "chase", "is_transfer": 0, "pending": 0},
    ]
    write_all_transactions(transactions, include=True)
    fake_gspread["txns"].append_rows.assert_called_once()


def test_10_6_include_transactions_off_skips(env, fake_gspread):
    from src.report import write_all_transactions
    write_all_transactions([{"transaction_id": "t1"}], include=False)
    fake_gspread["txns"].append_rows.assert_not_called()


def test_10_7_auth_failure_surfaces(env):
    from src import report
    with patch("src.report._gspread_client", side_effect=PermissionError("no edit access on sheet sheet_abc")):
        with pytest.raises(Exception) as exc:
            report.append_weekly_summary(_snapshot())
        assert "sheet_abc" in str(exc.value)
