import argparse
import json
import sys
from datetime import date

from dotenv import load_dotenv

load_dotenv()

from src import analyze, db, fetch, report  # noqa: E402 — load_dotenv must run first


init_db = db.init_db
fetch_all = fetch.fetch_all
detect_transfers = analyze.detect_transfers
compute_weekly_snapshot = analyze.compute_weekly_snapshot
save_snapshot = analyze.save_snapshot


def append_to_gsheet(snap, include_transactions=False, all_transactions_rows=None):
    report.append_weekly_summary(snap)
    report.append_category_detail(snap, txn_counts=snap.get("category_counts"))
    if include_transactions:
        report.write_all_transactions(all_transactions_rows or [], include=True)


def _iso_date(value):
    try:
        date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid ISO date: {value!r}")
    return value


def build_parser():
    parser = argparse.ArgumentParser(
        prog="finance-tracker",
        description="Weekly personal finance tracker: Plaid -> SQLite -> Google Sheets.",
    )
    parser.add_argument(
        "--include-transactions",
        action="store_true",
        help="Also write the 'All Transactions' tab to the sheet",
    )
    parser.add_argument(
        "--week-ending",
        default=None,
        type=_iso_date,
        help="ISO date (YYYY-MM-DD) for the week ending; defaults to most recent Sunday",
    )
    return parser


def _spending_from(snap):
    if snap.get("spending_by_category"):
        return snap["spending_by_category"]
    raw = snap.get("spending_by_category_json")
    if raw:
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return {}
    return {}


def print_summary_to_stdout(snap):
    lines = [
        f"Week ending:       {snap.get('week_ending')}",
        f"Net worth:         ${snap.get('net_worth', 0):,.2f}",
        f"  Cash:            ${snap.get('total_cash', 0):,.2f}",
        f"  Invested:        ${snap.get('total_invested', 0):,.2f}",
        f"  Credit debt:     ${snap.get('total_credit_debt', 0):,.2f}",
        f"Income this week:  ${snap.get('income_this_week', 0):,.2f}",
        f"Spending this wk:  ${snap.get('spending_this_week', 0):,.2f}",
        f"Net income:        ${snap.get('net_income_this_week', 0):,.2f}",
    ]
    spending = _spending_from(snap)
    if spending:
        lines.append("Spending by category:")
        for cat, amt in sorted(spending.items(), key=lambda kv: -kv[1]):
            lines.append(f"  {cat:<16} ${amt:,.2f}")
    print("\n".join(lines))


def _all_transaction_rows():
    conn = db.get_connection()
    try:
        cur = conn.execute("SELECT * FROM transactions ORDER BY date ASC")
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def run(include_transactions=False, week_ending=None):
    try:
        init_db()
        conn = db.get_connection()
        try:
            fetch_all()
            detect_transfers(conn)
            snap = compute_weekly_snapshot(conn, week_ending=week_ending)
            save_snapshot(conn, snap)
        finally:
            conn.close()

        try:
            append_to_gsheet(
                snap,
                include_transactions=include_transactions,
                all_transactions_rows=_all_transaction_rows() if include_transactions else None,
            )
        except Exception as e:
            print(f"[sheet error] {e!r}", file=sys.stderr)
            print_summary_to_stdout(snap)
            return 2

        print_summary_to_stdout(snap)
        return 0
    except Exception as e:
        print(f"[fatal] {e!r}", file=sys.stderr)
        return 1


def main(argv=None):
    args = build_parser().parse_args(argv)
    return run(
        include_transactions=args.include_transactions,
        week_ending=args.week_ending,
    )


if __name__ == "__main__":
    sys.exit(main())
