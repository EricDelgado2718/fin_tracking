import json
from collections import defaultdict
from datetime import date, timedelta

from . import db


def most_recent_sunday(today=None):
    today = today or date.today()
    if isinstance(today, str):
        today = date.fromisoformat(today)
    # Python weekday: Mon=0 ... Sun=6; offset to last Sunday (0 if today is Sunday)
    offset = (today.weekday() + 1) % 7
    return (today - timedelta(days=offset)).isoformat()


def detect_transfers(conn, window_days=2):
    cur = conn.execute(
        "SELECT transaction_id, account_id, date, amount FROM transactions WHERE amount IS NOT NULL"
    )
    rows = [
        {
            "transaction_id": r[0],
            "account_id": r[1],
            "date": date.fromisoformat(r[2]) if r[2] else None,
            "amount": r[3],
        }
        for r in cur.fetchall()
        if r[2]
    ]
    matched = set()
    updates = []
    # Group by absolute amount for efficient pairing
    by_abs = defaultdict(list)
    for r in rows:
        by_abs[round(abs(r["amount"]), 2)].append(r)

    for amount_key, bucket in by_abs.items():
        if amount_key == 0:
            continue
        for i, a in enumerate(bucket):
            if a["transaction_id"] in matched:
                continue
            for b in bucket[i + 1 :]:
                if b["transaction_id"] in matched:
                    continue
                if a["account_id"] == b["account_id"]:
                    continue
                if (a["amount"] > 0) == (b["amount"] > 0):
                    continue
                if abs((a["date"] - b["date"]).days) > window_days:
                    continue
                matched.add(a["transaction_id"])
                matched.add(b["transaction_id"])
                updates.append(a["transaction_id"])
                updates.append(b["transaction_id"])
                break

    if updates:
        conn.executemany(
            "UPDATE transactions SET is_transfer = 1 WHERE transaction_id = ?",
            [(tid,) for tid in updates],
        )
        conn.commit()
    return len(updates)


def _latest_balances(conn, as_of):
    cur = conn.execute(
        """
        SELECT b.account_id, b.account_type, b.balance_current
        FROM balances b
        JOIN (
            SELECT account_id, MAX(snapshot_date) AS latest
            FROM balances
            WHERE snapshot_date <= ?
            GROUP BY account_id
        ) m ON m.account_id = b.account_id AND m.latest = b.snapshot_date
        """,
        (as_of.isoformat() if isinstance(as_of, date) else as_of,),
    )
    return cur.fetchall()


def _account_types(conn):
    cur = conn.execute(
        """
        SELECT account_id, account_type
        FROM balances
        GROUP BY account_id
        """
    )
    return {row[0]: row[1] for row in cur.fetchall()}


def compute_weekly_snapshot(conn, week_ending=None):
    if week_ending is None:
        week_ending = most_recent_sunday()
    if isinstance(week_ending, str):
        week_ending = date.fromisoformat(week_ending)
    elif isinstance(week_ending, date):
        pass

    # Net worth from latest balances <= week_ending
    balances = _latest_balances(conn, week_ending)
    total_cash = 0.0
    total_invested = 0.0
    total_credit = 0.0
    for _account_id, account_type, current in balances:
        amt = current or 0.0
        if account_type == "depository":
            total_cash += amt
        elif account_type == "investment":
            total_invested += amt
        elif account_type == "credit":
            total_credit += amt
    net_worth = total_cash + total_invested - total_credit

    # Weekly window
    txns = db.transactions_in_week(conn, week_ending)
    acct_types = _account_types(conn)

    income = 0.0
    spending = 0.0
    spending_by_category = defaultdict(float)
    category_counts = defaultdict(int)

    for tx in txns:
        if tx.get("is_transfer"):
            continue
        amount = tx.get("amount") or 0.0
        acct_type = acct_types.get(tx.get("account_id"))
        if amount < 0 and acct_type == "depository":
            income += -amount
        if amount > 0 and acct_type in ("depository", "credit"):
            spending += amount
            bucket = tx.get("my_category") or "Other"
            spending_by_category[bucket] += amount
            category_counts[bucket] += 1

    net_income = income - spending
    return {
        "week_ending": week_ending.isoformat(),
        "net_worth": round(net_worth, 2),
        "total_cash": round(total_cash, 2),
        "total_invested": round(total_invested, 2),
        "total_credit_debt": round(total_credit, 2),
        "income_this_week": round(income, 2),
        "spending_this_week": round(spending, 2),
        "net_income_this_week": round(net_income, 2),
        "spending_by_category": {k: round(v, 2) for k, v in spending_by_category.items()},
        "spending_by_category_json": json.dumps({k: round(v, 2) for k, v in spending_by_category.items()}),
        "category_counts": dict(category_counts),
    }


def save_snapshot(conn, snapshot):
    db.save_weekly_snapshot(conn, {
        **snapshot,
        "spending_by_category_json": json.dumps(snapshot.get("spending_by_category", {})),
    })
