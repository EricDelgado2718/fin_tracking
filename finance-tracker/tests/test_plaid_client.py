"""§4 plaid_client.py — link, sync pagination, typed errors."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


@pytest.mark.parametrize("institution", ["chase", "capital_one", "discover", "schwab", "bask"])
def test_4_1_link_token_products_transactions_only(env, institution):
    from src import plaid_client
    with patch.object(plaid_client, "_raw_link_token_create") as mock_create:
        mock_create.return_value = {"link_token": "link-xxx"}
        plaid_client.create_link_token(institution=institution, user_id="u1")
        req = mock_create.call_args.kwargs.get("request") or mock_create.call_args.args[0]
        products = req["products"] if isinstance(req, dict) else getattr(req, "products", None)
        assert list(products) == ["transactions"]


def test_4_2_transactions_sync_pagination(env):
    from src import plaid_client
    pages = [
        {"added": [{"transaction_id": "t1"}], "modified": [], "removed": [], "next_cursor": "c1", "has_more": True},
        {"added": [{"transaction_id": "t2"}], "modified": [], "removed": [], "next_cursor": "c2", "has_more": True},
        {"added": [{"transaction_id": "t3"}], "modified": [], "removed": [], "next_cursor": "c_final", "has_more": False},
    ]
    with patch.object(plaid_client, "_raw_transactions_sync", side_effect=pages) as mock_sync:
        result = plaid_client.sync_transactions(access_token="access-x", cursor=None)
        assert mock_sync.call_count == 3
        added_ids = [t["transaction_id"] for t in result["added"]]
        assert added_ids == ["t1", "t2", "t3"]
        assert result["next_cursor"] == "c_final"


def test_4_3_item_login_required_raises_typed(env):
    from src import plaid_client
    from src.plaid_client import PlaidReauthRequired

    err = Exception("plaid api error")
    err.body = {"error_code": "ITEM_LOGIN_REQUIRED"}

    with patch.object(plaid_client, "_raw_transactions_sync", side_effect=_fake_plaid_error("ITEM_LOGIN_REQUIRED")):
        with pytest.raises(PlaidReauthRequired) as exc:
            plaid_client.sync_transactions(access_token="access-x", cursor=None, institution="capital_one")
        assert exc.value.institution == "capital_one"


def test_4_4_other_plaid_errors_propagate(env):
    from src import plaid_client
    from src.plaid_client import PlaidReauthRequired
    with patch.object(plaid_client, "_raw_transactions_sync", side_effect=_fake_plaid_error("INTERNAL_SERVER_ERROR")):
        with pytest.raises(Exception) as exc:
            plaid_client.sync_transactions(access_token="access-x", cursor=None, institution="chase")
        assert not isinstance(exc.value, PlaidReauthRequired)


def _fake_plaid_error(code):
    e = RuntimeError(code)
    e.body = {"error_code": code}
    e.code = code
    return e
