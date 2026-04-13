"""§3 tokens.py — Fernet-encrypted token store."""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet


def test_3_1_round_trip(env):
    from src.tokens import save_token, load_tokens
    save_token("chase", access_token="access-sandbox-xxx", item_id="item_123")
    tokens = load_tokens()
    assert "chase" in tokens
    assert tokens["chase"]["access_token"] == "access-sandbox-xxx"
    assert tokens["chase"]["item_id"] == "item_123"
    assert "linked_at" in tokens["chase"]


def test_3_2_file_on_disk_is_ciphertext(env):
    from src.tokens import save_token
    save_token("chase", access_token="access-sandbox-xxx", item_id="item_123")
    path = env["data_dir"] / "tokens.enc"
    assert path.exists()
    raw = path.read_bytes()
    assert b"access-sandbox-xxx" not in raw
    assert b"item_123" not in raw


def test_3_3_wrong_key_fails_cleanly(monkeypatch, env):
    from src.tokens import save_token
    save_token("chase", access_token="a", item_id="b")
    # Swap key; re-import so module rereads FERNET_KEY
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())
    import importlib, sys
    sys.modules.pop("src.tokens", None)
    sys.modules.pop("src.config", None)
    from src import tokens as tokens_mod
    importlib.reload(tokens_mod)
    with pytest.raises(Exception) as exc:
        tokens_mod.load_tokens()
    msg = str(exc.value).lower()
    assert "decrypt" in msg or "fernet" in msg or "key" in msg


def test_3_4_save_second_preserves_first(env):
    from src.tokens import save_token, load_tokens
    save_token("chase", access_token="a1", item_id="i1")
    save_token("capital_one", access_token="a2", item_id="i2")
    tokens = load_tokens()
    assert set(tokens.keys()) == {"chase", "capital_one"}


def test_3_5_missing_file_returns_empty(env):
    from src.tokens import load_tokens
    assert load_tokens() == {}
