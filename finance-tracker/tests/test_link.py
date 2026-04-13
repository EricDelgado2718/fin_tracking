"""§5 link.py — Flask link flow."""
from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture
def client(env):
    from src.link import app
    app.config["TESTING"] = True
    return app.test_client()


def test_5_1_get_renders_link_html(env, client):
    with patch("src.link.create_link_token", return_value="link-abc"):
        resp = client.get("/?institution=chase")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "link-initialize.js" in body
    assert "link-abc" in body


def test_5_2_missing_institution_400(client):
    resp = client.get("/")
    assert resp.status_code == 400
    assert b"institution" in resp.data.lower() if isinstance(resp.data, bytes) else True


def test_5_3_exchange_stores_token(env, client):
    with patch("src.link.exchange_public_token", return_value=("ACCESS", "ITEM")) as mock_x, \
         patch("src.link.save_token") as mock_save:
        resp = client.post("/exchange", data={"public_token": "PUB", "institution": "chase"})
    assert resp.status_code == 200
    mock_save.assert_called_once()
    kwargs = mock_save.call_args.kwargs or {}
    args = mock_save.call_args.args
    # Token saved with the right institution
    assert "chase" in (list(args) + list(kwargs.values()))
    # Response does not leak access token
    assert b"ACCESS" not in resp.data


def test_5_4_sequential_linking(env, client):
    saved = {}
    def fake_save(institution, access_token, item_id):
        saved[institution] = {"access_token": access_token, "item_id": item_id}
    with patch("src.link.exchange_public_token", side_effect=lambda p: (f"acc-{p}", f"item-{p}")), \
         patch("src.link.save_token", side_effect=fake_save):
        for inst in ["chase", "capital_one", "discover", "schwab", "bask"]:
            resp = client.post("/exchange", data={"public_token": f"pub-{inst}", "institution": inst})
            assert resp.status_code == 200
    assert set(saved.keys()) == {"chase", "capital_one", "discover", "schwab", "bask"}
