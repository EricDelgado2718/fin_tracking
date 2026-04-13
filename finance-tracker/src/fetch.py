from datetime import date

from . import db, plaid_client, tokens
from .plaid_client import PlaidReauthRequired


def sync_transactions(access_token, cursor=None, institution=None):
    return plaid_client.sync_transactions(
        access_token, cursor=cursor, institution=institution
    )


def accounts_balance_get(access_token, institution=None):
    resp = plaid_client.accounts_balance_get(access_token, institution=institution)
    return resp.get("accounts", []) if isinstance(resp, dict) else resp


def _snapshot_balances(conn, institution, balance_resp, snapshot_date):
    accounts = balance_resp if isinstance(balance_resp, list) else balance_resp.get("accounts", [])
    for acct in accounts:
        balances = acct.get("balances", {}) or {}
        db.upsert_balance(
            conn,
            {
                "account_id": acct.get("account_id"),
                "institution": institution,
                "account_name": acct.get("name"),
                "account_type": acct.get("type"),
                "account_subtype": acct.get("subtype"),
                "balance_current": balances.get("current"),
                "balance_available": balances.get("available"),
                "snapshot_date": snapshot_date,
            },
        )
    conn.commit()


def fetch_all(conn=None, snapshot_date=None):
    snapshot_date = snapshot_date or date.today().isoformat()
    close_conn = False
    if conn is None:
        db.init_db()
        conn = db.get_connection()
        close_conn = True
    results = {"synced": [], "reauth_required": [], "errors": []}
    try:
        tokens_map = tokens.load_tokens()
        for institution, record in tokens_map.items():
            access_token = record.get("access_token")
            item_id = record.get("item_id")
            try:
                cursor = db.get_cursor(conn, item_id)
                page = sync_transactions(
                    access_token, cursor=cursor, institution=institution
                )
                db.apply_sync_page(
                    conn,
                    item_id=item_id,
                    added=page["added"],
                    modified=page["modified"],
                    removed=page["removed"],
                    new_cursor=page["next_cursor"],
                    institution=institution,
                )
                bal = accounts_balance_get(access_token, institution=institution)
                _snapshot_balances(conn, institution, bal, snapshot_date)
                results["synced"].append(institution)
            except PlaidReauthRequired as e:
                print(f"[re-link required] institution={institution}: {e}")
                results["reauth_required"].append(institution)
                continue
            except Exception as e:
                print(f"[fetch error] institution={institution}: {e!r}")
                results["errors"].append((institution, repr(e)))
                continue
    finally:
        if close_conn:
            conn.close()
    return results
