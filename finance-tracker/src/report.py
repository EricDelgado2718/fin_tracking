import json

import gspread
from google.oauth2.service_account import Credentials

from . import config


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SUMMARY_TAB = "Weekly Summary"
CATEGORY_TAB = "Category Detail"
TRANSACTIONS_TAB = "All Transactions"


def _gspread_client():
    creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    return gspread.authorize(creds)


def _open_sheet(client=None):
    client = client or _gspread_client()
    return client.open_by_key(config.GSHEET_ID)


def _get_or_create_ws(sheet, title, headers):
    try:
        ws = sheet.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        ws = sheet.add_worksheet(title=title, rows=1000, cols=max(10, len(headers)))
        ws.append_row(headers)
        return ws
    # Ensure header row exists
    existing = ws.row_values(1)
    if not existing:
        ws.append_row(headers)
    return ws


def _top_category(spending_by_category):
    if not spending_by_category:
        return ("", 0.0)
    top = max(spending_by_category.items(), key=lambda kv: kv[1])
    return (top[0], round(top[1], 2))


def _spending_dict(snap):
    raw = snap.get("spending_by_category")
    if raw:
        return raw
    raw_json = snap.get("spending_by_category_json")
    if raw_json:
        try:
            return json.loads(raw_json)
        except (TypeError, ValueError):
            return {}
    return {}


def append_weekly_summary(snap, client=None):
    sheet = _open_sheet(client)
    headers = [
        "Week Ending", "Net Worth", "Cash", "Invested", "Credit Debt",
        "Income", "Spending", "Net Income", "Savings Rate",
        "Top Category", "Top Category $",
    ]
    ws = _get_or_create_ws(sheet, SUMMARY_TAB, headers)
    week_ending = snap["week_ending"]
    try:
        existing_weeks = ws.col_values(1)
    except Exception:
        existing_weeks = []
    if week_ending in existing_weeks:
        return None
    income = snap.get("income_this_week", 0.0) or 0.0
    net = snap.get("net_income_this_week", 0.0) or 0.0
    savings_rate = round((net / income), 4) if income else "N/A"
    top_cat, top_amt = _top_category(_spending_dict(snap))
    row = [
        snap["week_ending"],
        snap.get("net_worth", 0.0),
        snap.get("total_cash", 0.0),
        snap.get("total_invested", 0.0),
        snap.get("total_credit_debt", 0.0),
        income,
        snap.get("spending_this_week", 0.0),
        net,
        savings_rate,
        top_cat,
        top_amt,
    ]
    ws.append_row(row, value_input_option="USER_ENTERED")
    return row


def append_category_detail(snap, txn_counts=None, client=None):
    sheet = _open_sheet(client)
    headers = ["Week Ending", "Category", "Amount", "% of Spending", "Transaction Count"]
    ws = _get_or_create_ws(sheet, CATEGORY_TAB, headers)
    spending = _spending_dict(snap)
    total = snap.get("spending_this_week", 0.0) or sum(spending.values())
    counts = txn_counts or snap.get("category_counts", {}) or {}
    rows = []
    for category, amount in sorted(spending.items(), key=lambda kv: -kv[1]):
        pct = round((amount / total), 4) if total else 0.0
        rows.append([
            snap["week_ending"],
            category,
            round(amount, 2),
            pct,
            int(counts.get(category, 0)),
        ])
    if rows:
        ws.append_rows(rows, value_input_option="USER_ENTERED")
    return rows


def write_all_transactions(rows, include=False, client=None):
    if not include:
        return 0
    sheet = _open_sheet(client)
    headers = [
        "transaction_id", "account_id", "institution", "date", "amount",
        "merchant_name", "name", "plaid_category", "my_category",
        "pending", "is_transfer",
    ]
    ws = _get_or_create_ws(sheet, TRANSACTIONS_TAB, headers)
    ws.clear()
    ws.append_row(headers)
    body = [[r.get(h) for h in headers] for r in rows]
    if body:
        ws.append_rows(body, value_input_option="USER_ENTERED")
    return len(body)
