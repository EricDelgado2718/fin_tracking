"""§11 main.py — CLI + orchestration."""
from __future__ import annotations

import subprocess
import sys
from unittest.mock import patch, MagicMock, call

import pytest


def test_11_1_cli_args(env):
    import main
    parser = main.build_parser()
    ns = parser.parse_args([])
    assert ns.include_transactions is False
    ns = parser.parse_args(["--include-transactions", "--week-ending", "2026-04-12"])
    assert ns.include_transactions is True
    assert ns.week_ending == "2026-04-12"
    with pytest.raises(SystemExit):
        parser.parse_args(["--week-ending", "not-a-date"])


def test_11_2_pipeline_order(env, frozen_today):
    import main
    calls = []
    def rec(name):
        def _f(*a, **kw):
            calls.append(name)
            return MagicMock()
        return _f

    with patch.object(main, "init_db", side_effect=rec("init_db")), \
         patch.object(main, "fetch_all", side_effect=rec("fetch_all")), \
         patch.object(main, "detect_transfers", side_effect=rec("detect_transfers")), \
         patch.object(main, "compute_weekly_snapshot", side_effect=lambda *a, **kw: (calls.append("compute_weekly_snapshot"), {"week_ending": "2026-04-12"})[1]), \
         patch.object(main, "save_snapshot", side_effect=rec("save_snapshot")), \
         patch.object(main, "append_to_gsheet", side_effect=rec("append_to_gsheet")), \
         patch.object(main, "print_summary_to_stdout", side_effect=rec("print_summary_to_stdout")):
        main.run(include_transactions=False, week_ending=None)

    assert calls == [
        "init_db", "fetch_all", "detect_transfers",
        "compute_weekly_snapshot", "save_snapshot",
        "append_to_gsheet", "print_summary_to_stdout",
    ]


def test_11_3_partial_failure_still_writes_snapshot(env, frozen_today, capsys):
    import main
    from src.plaid_client import PlaidReauthRequired

    def fetch_with_partial_fail():
        # Simulate fetch_all having logged the reauth itself (the real fetch_all swallows + logs)
        print("re-link capital_one")

    snapshot = {"week_ending": "2026-04-12", "net_worth": 1.0,
                "income_this_week": 0, "spending_this_week": 0,
                "net_income_this_week": 0,
                "spending_by_category_json": "{}"}

    with patch.object(main, "init_db"), \
         patch.object(main, "fetch_all", side_effect=fetch_with_partial_fail), \
         patch.object(main, "detect_transfers"), \
         patch.object(main, "compute_weekly_snapshot", return_value=snapshot), \
         patch.object(main, "save_snapshot") as save, \
         patch.object(main, "append_to_gsheet") as gsheet, \
         patch.object(main, "print_summary_to_stdout") as stdout:
        rc = main.run(include_transactions=False, week_ending=None)

    assert rc == 0
    save.assert_called_once()
    gsheet.assert_called_once()
    out = capsys.readouterr().out
    assert "capital_one" in out


def test_11_4_stdout_summary_content(env, capsys):
    import main
    snap = {
        "week_ending": "2026-04-12", "net_worth": 72000.0,
        "income_this_week": 3000.0, "spending_this_week": 600.0,
        "net_income_this_week": 2400.0,
        "spending_by_category_json": '{"Eating out": 300.0, "Groceries": 200.0}',
    }
    main.print_summary_to_stdout(snap)
    out = capsys.readouterr().out
    assert "2026-04-12" in out
    assert "72000" in out.replace(",", "")
    assert "Eating out" in out


def test_11_5_exit_code_on_sheet_failure(env, frozen_today):
    import main
    snap = {"week_ending": "2026-04-12", "net_worth": 1.0,
            "income_this_week": 0, "spending_this_week": 0,
            "net_income_this_week": 0, "spending_by_category_json": "{}"}
    with patch.object(main, "init_db"), \
         patch.object(main, "fetch_all"), \
         patch.object(main, "detect_transfers"), \
         patch.object(main, "compute_weekly_snapshot", return_value=snap), \
         patch.object(main, "save_snapshot"), \
         patch.object(main, "append_to_gsheet", side_effect=RuntimeError("sheet write failed")), \
         patch.object(main, "print_summary_to_stdout"):
        rc = main.run(include_transactions=False, week_ending=None)
    assert rc != 0
