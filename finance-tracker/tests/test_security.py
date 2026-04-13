"""§14 security & hygiene."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


REQUIRED_IGNORES = [".env", "tokens.enc", "credentials.json", "__pycache__", ".venv"]


def test_14_1_gitignore_coverage():
    gi = REPO_ROOT / ".gitignore"
    assert gi.exists(), ".gitignore missing"
    text = gi.read_text()
    for pat in REQUIRED_IGNORES:
        assert pat in text, f"{pat} not in .gitignore"
    # *.db pattern (matches finance.db etc.)
    assert "*.db" in text or "data/finance.db" in text


def test_14_1_git_check_ignore_for_sensitive_paths(tmp_path):
    """git check-ignore returns 0 if path is ignored."""
    candidates = [".env", "data/finance.db", "data/tokens.enc", "credentials.json"]
    for c in candidates:
        rc = subprocess.run(
            ["git", "check-ignore", "-q", c],
            cwd=REPO_ROOT,
            capture_output=True,
        ).returncode
        assert rc == 0, f"{c} is not gitignored"


def test_14_2_no_secrets_in_log(env, tmp_path, monkeypatch):
    """After a run, run.log must not contain secrets verbatim."""
    log_path = tmp_path / "run.log"
    monkeypatch.setattr("sys.stdout", log_path.open("w"))
    # Intentionally cause a print of snapshot/summary; ensure no secrets leak
    import main
    snap = {"week_ending": "2026-04-12", "net_worth": 1.0, "income_this_week": 0,
            "spending_this_week": 0, "net_income_this_week": 0,
            "spending_by_category_json": "{}"}
    main.print_summary_to_stdout(snap)
    monkeypatch.undo()

    log = log_path.read_text()
    assert "test_secret" not in log
    assert env["fernet_key"] not in log
    assert "access-" not in log


def test_14_4_sign_convention_smoke(env, db):
    """Spec gotcha: deposits negative, purchases positive, credit debt positive."""
    from src.analyze import compute_weekly_snapshot
    from src.db import upsert_balance, upsert_transaction
    from tests.fixtures.factories import balance, txn
    upsert_balance(db, balance(account_id="chk", balance_current=100.0, snapshot_date="2026-04-12",
                               account_type="depository"))
    upsert_balance(db, balance(account_id="cc", balance_current=50.0, snapshot_date="2026-04-12",
                               account_type="credit"))
    upsert_transaction(db, txn(amount=-200.0, date="2026-04-09", account_id="chk", transaction_id="dep"))
    upsert_transaction(db, txn(amount=30.0, date="2026-04-10", account_id="chk", transaction_id="buy"))
    db.commit()
    snap = compute_weekly_snapshot(db, week_ending="2026-04-12")
    assert snap["income_this_week"] == 200.0  # positive in sheet despite Plaid's negative sign
    assert snap["spending_this_week"] == 30.0
    assert snap["total_credit_debt"] == 50.0
    assert snap["net_worth"] == 50.0  # 100 - 50
