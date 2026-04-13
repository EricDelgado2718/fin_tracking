"""Shared fixtures. Assumes source modules live under `src/`."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture
def fernet_key() -> str:
    return Fernet.generate_key().decode()


@pytest.fixture
def env(monkeypatch, tmp_path, fernet_key):
    """Populate required env vars + isolate data dir."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("PLAID_CLIENT_ID", "test_client")
    monkeypatch.setenv("PLAID_SECRET", "test_secret")
    monkeypatch.setenv("PLAID_ENV", "sandbox")
    monkeypatch.setenv("GSHEET_ID", "sheet_abc")
    monkeypatch.setenv("FERNET_KEY", fernet_key)
    monkeypatch.setenv("FINANCE_DATA_DIR", str(data_dir))
    # Force re-import so config picks up the patched env.
    for mod in list(sys.modules):
        if mod.startswith("src."):
            del sys.modules[mod]
    return {"data_dir": data_dir, "fernet_key": fernet_key}


@pytest.fixture
def db(env):
    from src.db import init_db, get_connection
    init_db()
    conn = get_connection()
    yield conn
    conn.close()


@pytest.fixture
def frozen_today(monkeypatch):
    """Use freezegun if available; otherwise rely on caller passing date explicitly."""
    try:
        from freezegun import freeze_time
    except ImportError:
        pytest.skip("freezegun not installed")
    with freeze_time("2026-04-13"):  # Monday after Sunday 2026-04-12
        yield "2026-04-13"
