"""§8 analyze.py — category remap."""
from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    "pfc,expected",
    [
        ("FOOD_AND_DRINK_GROCERIES", "Groceries"),
        ("TRANSPORTATION_GAS", "Transport"),
        ("FOOD_AND_DRINK_RESTAURANTS", "Eating out"),
        ("FOOD_AND_DRINK_COFFEE", "Eating out"),
    ],
)
def test_8_1_known_primary(env, pfc, expected):
    from src.config import remap_category
    assert remap_category(pfc) == expected


@pytest.mark.parametrize(
    "pfc,expected",
    [
        ("GENERAL_MERCHANDISE_ELECTRONICS", "Shopping"),
        ("MEDICAL_DENTAL_CARE", "Healthcare"),
        ("TRAVEL_FLIGHTS", "Travel"),
    ],
)
def test_8_2_wildcard_families(env, pfc, expected):
    from src.config import remap_category
    assert remap_category(pfc) == expected


def test_8_3_unknown_falls_through(env):
    from src.config import remap_category
    assert remap_category("WEIRD_NEW_CATEGORY_FROM_PLAID") == "Other"


def test_8_4_null_primary(env):
    from src.config import remap_category
    assert remap_category(None) == "Other"
