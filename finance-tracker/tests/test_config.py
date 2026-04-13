"""§1 config.py — env loading + category taxonomy."""
from __future__ import annotations

import importlib
import sys

import pytest


def _reimport_config():
    sys.modules.pop("src.config", None)
    return importlib.import_module("src.config")


def test_1_1_loads_required_env_vars(env):
    config = _reimport_config()
    assert config.PLAID_CLIENT_ID == "test_client"
    assert config.PLAID_SECRET == "test_secret"
    assert config.PLAID_ENV == "sandbox"
    assert config.GSHEET_ID == "sheet_abc"
    assert config.FERNET_KEY  # truthy


def test_1_2_missing_env_fails_fast(monkeypatch, tmp_path):
    for var in ("PLAID_CLIENT_ID", "PLAID_SECRET", "PLAID_ENV", "GSHEET_ID", "FERNET_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("PLAID_CLIENT_ID", "x")
    monkeypatch.setenv("PLAID_SECRET", "x")
    monkeypatch.setenv("PLAID_ENV", "sandbox")
    monkeypatch.setenv("GSHEET_ID", "x")
    # FERNET_KEY intentionally missing
    with pytest.raises(Exception) as exc:
        _reimport_config()
    assert "FERNET_KEY" in str(exc.value)


# Plaid's 16 PFC primary categories (as of 2024 PFC taxonomy)
PFC_PRIMARIES = [
    "INCOME",
    "TRANSFER_IN",
    "TRANSFER_OUT",
    "LOAN_PAYMENTS",
    "BANK_FEES",
    "ENTERTAINMENT",
    "FOOD_AND_DRINK",
    "GENERAL_MERCHANDISE",
    "HOME_IMPROVEMENT",
    "MEDICAL",
    "PERSONAL_CARE",
    "GENERAL_SERVICES",
    "GOVERNMENT_AND_NON_PROFIT",
    "TRANSPORTATION",
    "TRAVEL",
    "RENT_AND_UTILITIES",
]


@pytest.mark.parametrize("primary", PFC_PRIMARIES)
def test_1_3_my_categories_covers_every_primary(env, primary):
    config = _reimport_config()
    # Expect a top-level helper that accepts a Plaid primary category and returns a bucket.
    bucket = config.remap_category(primary)
    assert bucket is not None and isinstance(bucket, str)
    assert bucket in config.MY_CATEGORIES


def test_1_3_unknown_primary_falls_through_to_other(env):
    config = _reimport_config()
    assert config.remap_category("WEIRD_NEW_CATEGORY_FROM_PLAID") == "Other"


@pytest.mark.parametrize(
    "env_val,expected_host",
    [
        ("sandbox", "https://sandbox.plaid.com"),
        ("development", "https://development.plaid.com"),
    ],
)
def test_1_4_env_to_host_mapping(monkeypatch, fernet_key, env_val, expected_host):
    monkeypatch.setenv("PLAID_CLIENT_ID", "x")
    monkeypatch.setenv("PLAID_SECRET", "x")
    monkeypatch.setenv("PLAID_ENV", env_val)
    monkeypatch.setenv("GSHEET_ID", "x")
    monkeypatch.setenv("FERNET_KEY", fernet_key)
    config = _reimport_config()
    assert config.plaid_host() == expected_host


def test_1_4_invalid_env_raises(monkeypatch, fernet_key):
    monkeypatch.setenv("PLAID_CLIENT_ID", "x")
    monkeypatch.setenv("PLAID_SECRET", "x")
    monkeypatch.setenv("PLAID_ENV", "prod-unofficial")
    monkeypatch.setenv("GSHEET_ID", "x")
    monkeypatch.setenv("FERNET_KEY", fernet_key)
    with pytest.raises(Exception):
        config = _reimport_config()
        config.plaid_host()
