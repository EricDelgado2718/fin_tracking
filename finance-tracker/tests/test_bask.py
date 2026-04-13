"""§13 Bask CSV fallback. Only runs if `src.bask_csv_import` exists."""
from __future__ import annotations

import importlib.util
import textwrap

import pytest


pytestmark = pytest.mark.bask_csv


def _bask_available():
    return importlib.util.find_spec("src.bask_csv_import") is not None


@pytest.mark.skipif(not _bask_available(), reason="bask CSV importer not implemented (Plaid supports Bask)")
def test_13_1_csv_import(env, tmp_path):
    from src.db import init_db, get_connection
    from src import bask_csv_import

    init_db()
    inbox = env["data_dir"] / "bask_inbox"
    inbox.mkdir()
    csv_path = inbox / "bask_2026-04-12.csv"
    csv_path.write_text(textwrap.dedent("""\
        date,description,amount,balance_after
        2026-04-09,DEPOSIT FROM CHASE,-2000.00,22000.00
        2026-04-10,INTEREST,-5.00,22005.00
    """))

    bask_csv_import.import_inbox()

    conn = get_connection()
    txns = conn.execute("SELECT amount FROM transactions WHERE institution='bask'").fetchall()
    assert len(txns) == 2
    bal = conn.execute("SELECT balance_current FROM balances WHERE institution='bask'").fetchone()
    assert bal[0] == 22005.00

    # Idempotency: second run does not duplicate
    bask_csv_import.import_inbox()
    again = conn.execute("SELECT COUNT(*) FROM transactions WHERE institution='bask'").fetchone()[0]
    assert again == 2


@pytest.mark.skipif(not _bask_available(), reason="bask CSV importer not implemented")
def test_13_2_malformed_csv_rejected(env):
    from src.db import init_db, get_connection
    from src import bask_csv_import

    init_db()
    inbox = env["data_dir"] / "bask_inbox"
    inbox.mkdir()
    (inbox / "bad.csv").write_text("this,is,not,bask,format\n1,2,3,4,5\n")
    with pytest.raises(Exception):
        bask_csv_import.import_inbox()
    conn = get_connection()
    assert conn.execute("SELECT COUNT(*) FROM transactions WHERE institution='bask'").fetchone()[0] == 0
