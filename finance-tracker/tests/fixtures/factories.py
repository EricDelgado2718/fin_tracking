"""Factory helpers for building transaction/balance rows in tests."""
from __future__ import annotations

import itertools
import json
from typing import Any

_counter = itertools.count(1)


def txn(
    *,
    amount: float,
    date: str,
    account_id: str = "acct_checking",
    institution: str = "chase",
    pfc_primary: str = "GENERAL_MERCHANDISE_OTHER",
    my_category: str = "Shopping",
    pending: int = 0,
    is_transfer: int = 0,
    transaction_id: str | None = None,
    merchant_name: str = "Test Merchant",
    name: str = "TEST TXN",
) -> dict[str, Any]:
    tid = transaction_id or f"txn_{next(_counter)}"
    return {
        "transaction_id": tid,
        "account_id": account_id,
        "institution": institution,
        "date": date,
        "amount": amount,
        "merchant_name": merchant_name,
        "name": name,
        "plaid_category": pfc_primary,
        "my_category": my_category,
        "pending": pending,
        "is_transfer": is_transfer,
        "raw_json": json.dumps({"transaction_id": tid, "amount": amount}),
    }


def balance(
    *,
    account_id: str,
    balance_current: float,
    snapshot_date: str,
    account_type: str = "depository",
    account_subtype: str = "checking",
    account_name: str = "Test Account",
    institution: str = "chase",
    balance_available: float | None = None,
) -> dict[str, Any]:
    return {
        "account_id": account_id,
        "institution": institution,
        "account_name": account_name,
        "account_type": account_type,
        "account_subtype": account_subtype,
        "balance_current": balance_current,
        "balance_available": balance_current if balance_available is None else balance_available,
        "snapshot_date": snapshot_date,
    }


# Canonical fixture for §9 snapshot math
def fixture_week_412_balances() -> list[dict[str, Any]]:
    """Week ending 2026-04-12 balances from tests.md §9."""
    d = "2026-04-12"
    return [
        balance(account_id="chk", balance_current=3000.00, snapshot_date=d,
                account_type="depository", account_subtype="checking"),
        balance(account_id="hysa", balance_current=20000.00, snapshot_date=d,
                account_type="depository", account_subtype="savings", institution="bask"),
        balance(account_id="brk", balance_current=50000.00, snapshot_date=d,
                account_type="investment", account_subtype="brokerage", institution="schwab"),
        balance(account_id="cc1", balance_current=800.00, snapshot_date=d,
                account_type="credit", account_subtype="credit card", institution="chase"),
        balance(account_id="cc2", balance_current=200.00, snapshot_date=d,
                account_type="credit", account_subtype="credit card", institution="capital_one"),
    ]
