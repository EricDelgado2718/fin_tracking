import json
from urllib import request as urllib_request
from urllib.error import HTTPError

from . import config


class PlaidReauthRequired(Exception):
    def __init__(self, institution=None, message=None):
        self.institution = institution
        self.message = message or "ITEM_LOGIN_REQUIRED"
        super().__init__(f"{institution}: {self.message}" if institution else self.message)


class PlaidAPIError(Exception):
    def __init__(self, error_code=None, error_type=None, message=None, status=None):
        self.error_code = error_code
        self.error_type = error_type
        self.status = status
        super().__init__(message or error_code or "Plaid API error")


def _post(endpoint, payload):
    url = f"{config.plaid_host()}{endpoint}"
    body = json.dumps({
        "client_id": config.PLAID_CLIENT_ID,
        "secret": config.PLAID_SECRET,
        **payload,
    }).encode("utf-8")
    req = urllib_request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib_request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw)
        except ValueError:
            data = {"error_message": raw}
        err = PlaidAPIError(
            error_code=data.get("error_code"),
            error_type=data.get("error_type"),
            message=data.get("error_message"),
            status=e.code,
        )
        raise err from None


def _raw_link_token_create(payload):
    return _post("/link/token/create", payload)


def _raw_item_public_token_exchange(public_token):
    return _post("/item/public_token/exchange", {"public_token": public_token})


def _raw_transactions_sync(access_token, cursor=None):
    payload = {"access_token": access_token}
    if cursor:
        payload["cursor"] = cursor
    return _post("/transactions/sync", payload)


def _raw_accounts_balance_get(access_token):
    from datetime import UTC, datetime, timedelta
    min_updated = (datetime.now(UTC) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return _post(
        "/accounts/balance/get",
        {
            "access_token": access_token,
            "options": {"min_last_updated_datetime": min_updated},
        },
    )


def create_link_token(user_id="finance-tracker-user", products=None, institution=None):
    products = products or ["transactions"]
    payload = {
        "user": {"client_user_id": user_id},
        "client_name": "Weekly Finance Tracker",
        "products": products,
        "country_codes": ["US"],
        "language": "en",
    }
    return _raw_link_token_create(payload)


def exchange_public_token(public_token):
    return _raw_item_public_token_exchange(public_token)


def _error_code_of(exc):
    body = getattr(exc, "body", None)
    if isinstance(body, dict) and body.get("error_code"):
        return body["error_code"]
    if isinstance(exc, PlaidAPIError):
        return exc.error_code
    return None


def _reraise_if_reauth(exc, institution):
    if _error_code_of(exc) == "ITEM_LOGIN_REQUIRED":
        raise PlaidReauthRequired(institution=institution, message=str(exc)) from exc


def _maybe_reauth(resp, institution=None):
    if not isinstance(resp, dict):
        return
    if resp.get("error_code") == "ITEM_LOGIN_REQUIRED":
        raise PlaidReauthRequired(institution=institution, message=resp.get("error_message"))


def sync_transactions(access_token, cursor=None, institution=None):
    added, modified, removed = [], [], []
    next_cursor = cursor
    while True:
        try:
            resp = _raw_transactions_sync(access_token, cursor=next_cursor)
        except Exception as e:
            _reraise_if_reauth(e, institution)
            raise
        _maybe_reauth(resp, institution=institution)
        added.extend(resp.get("added", []))
        modified.extend(resp.get("modified", []))
        removed.extend(resp.get("removed", []))
        next_cursor = resp.get("next_cursor")
        if not resp.get("has_more"):
            break
    return {
        "added": added,
        "modified": modified,
        "removed": removed,
        "next_cursor": next_cursor,
        "has_more": False,
    }


def accounts_balance_get(access_token, institution=None):
    try:
        resp = _raw_accounts_balance_get(access_token)
    except Exception as e:
        _reraise_if_reauth(e, institution)
        raise
    _maybe_reauth(resp, institution=institution)
    return {
        "accounts": resp.get("accounts", []),
        "item": resp.get("item", {}),
    }
