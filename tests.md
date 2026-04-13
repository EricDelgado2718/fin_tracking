# Weekly Finance Tracker — Black-Box Test Cases

Test cases written against the spec + plan before implementation exists. Organized by module. Each case lists **Setup**, **Action**, **Expected**. "Sandbox" = Plaid Sandbox env with `ins_109508` + `user_good / pass_good`.

---

## 1. `config.py` — env + taxonomy

### 1.1 Loads required env vars
- **Setup:** `.env` with `PLAID_CLIENT_ID`, `PLAID_SECRET`, `PLAID_ENV=sandbox`, `GSHEET_ID`, `FERNET_KEY`.
- **Action:** import `config`.
- **Expected:** all five attributes accessible; no exception.

### 1.2 Missing env var fails fast
- **Setup:** `.env` missing `FERNET_KEY`.
- **Action:** import `config`.
- **Expected:** raises a clear error naming the missing var (not a silent `None`).

### 1.3 MY_CATEGORIES covers every Plaid PFC primary
- **Action:** for each of Plaid's 16 PFC primary categories (INCOME, TRANSFER_IN, TRANSFER_OUT, LOAN_PAYMENTS, BANK_FEES, ENTERTAINMENT, FOOD_AND_DRINK, GENERAL_MERCHANDISE, HOME_IMPROVEMENT, MEDICAL, PERSONAL_CARE, GENERAL_SERVICES, GOVERNMENT_AND_NON_PROFIT, TRANSPORTATION, TRAVEL, RENT_AND_UTILITIES), call `remap(primary)`.
- **Expected:** each returns a non-None bucket; unknown input returns `"Other"`.

### 1.4 PLAID_ENV maps to correct host
- **Expected:** `sandbox` → `https://sandbox.plaid.com`; `development` → `https://development.plaid.com`; invalid value raises.

---

## 2. `db.py`

### 2.1 `init_db()` is idempotent
- **Action:** call twice on fresh DB, then on existing DB.
- **Expected:** all four tables exist with schemas matching spec §3; second call does not error or drop data.

### 2.2 Transaction upsert by PK
- **Setup:** insert transaction `txn_1` with `pending=1, amount=10.00`.
- **Action:** upsert same `transaction_id` with `pending=0, amount=10.50`.
- **Expected:** single row; fields overwritten with new values.

### 2.3 Balance PK is (account_id, snapshot_date)
- **Action:** upsert two balance rows same account, different dates.
- **Expected:** both rows retained. Same account + same date → single row, latest wins.

### 2.4 Remove array handling
- **Setup:** `txn_1` exists.
- **Action:** apply removed-id list `["txn_1"]`.
- **Expected:** row deleted.

### 2.5 Cursor persistence is atomic with writes
- **Action:** simulate a crash mid-sync by raising inside the write transaction after writing one txn but before cursor update.
- **Expected:** neither the txn nor the new cursor is persisted (rollback). Next run reprocesses from old cursor.

### 2.6 Weekly window query
- **Setup:** 10 txns spanning 3 weeks.
- **Action:** query with `week_ending=YYYY-MM-DD` (a Sunday).
- **Expected:** returns only txns with `date` in [week_ending-6, week_ending] inclusive.

---

## 3. `tokens.py`

### 3.1 Round-trip encryption
- **Action:** `save_token("chase", "access-sandbox-xxx", "item_123")` then `load_tokens()`.
- **Expected:** dict contains chase entry with matching fields + `linked_at` ISO date.

### 3.2 File on disk is ciphertext
- **Action:** read `tokens.enc` raw bytes.
- **Expected:** does NOT contain the substring `"access-sandbox-xxx"` or `"item_123"`.

### 3.3 Wrong Fernet key fails cleanly
- **Setup:** tokens.enc created with key A.
- **Action:** set env FERNET_KEY to key B, call `load_tokens()`.
- **Expected:** raises typed decryption error with actionable message (not a raw `InvalidToken`).

### 3.4 Save second institution preserves first
- **Action:** save chase, then save capital_one.
- **Expected:** load returns both.

### 3.5 Missing file returns empty dict
- **Expected:** `load_tokens()` on nonexistent file → `{}`, no exception.

---

## 4. `plaid_client.py`

### 4.1 Link token create products
- **Action:** `create_link_token(institution="chase")`.
- **Expected:** request body `products=["transactions"]`. For `schwab`: still `["transactions"]` per plan (balance-only, no investments product).

### 4.2 `transactions_sync` pagination
- **Setup:** mock Plaid returning `has_more=True` for 2 pages then False.
- **Action:** `sync_transactions(token, cursor=None)`.
- **Expected:** all pages concatenated; final cursor is from last page; three total HTTP calls.

### 4.3 ITEM_LOGIN_REQUIRED → typed exception
- **Setup:** mock Plaid 400 with `error_code=ITEM_LOGIN_REQUIRED`.
- **Action:** call any endpoint wrapper.
- **Expected:** raises `PlaidReauthRequired` carrying the institution slug.

### 4.4 Other Plaid errors propagate
- **Setup:** mock 500.
- **Expected:** raises (not swallowed); not `PlaidReauthRequired`.

---

## 5. `link.py` (Flask)

### 5.1 GET `/?institution=chase`
- **Expected:** 200, HTML contains `link-initialize.js` script tag and a link token value injected from Plaid.

### 5.2 Missing `institution` query param
- **Expected:** 400 with clear message.

### 5.3 POST `/exchange`
- **Setup:** Plaid mocked to return `access_token=ACCESS`, `item_id=ITEM`.
- **Action:** POST form `{public_token: PUB, institution: chase}`.
- **Expected:** 200; tokens.enc now contains chase entry; response body does not leak access_token.

### 5.4 Sequential linking
- **Action:** link chase, capital_one, discover, schwab, bask via the same running server.
- **Expected:** `load_tokens()` returns all 5.

---

## 6. `fetch.py`

### 6.1 Full sandbox sync happy path
- **Setup:** sandbox item linked.
- **Action:** `fetch_all()`.
- **Expected:** `transactions` populated (>0 rows); `balances` has today's snapshot for each account; `sync_cursors` has non-null cursor for the item.

### 6.2 Second run is incremental
- **Action:** run fetch twice back-to-back.
- **Expected:** second run's sync returns zero added/modified/removed; cursor advances or stays stable; no duplicate rows.

### 6.3 Re-auth isolates failure
- **Setup:** 3 linked institutions; mock one to raise `PlaidReauthRequired`.
- **Expected:** stderr/log contains `re-link capital_one` (or equivalent with the exact institution). Other two still write balances + txns. Process exits 0.

### 6.4 Balance snapshot date
- **Expected:** `balances.snapshot_date` == today's local date (YYYY-MM-DD), not the Plaid `as_of` timestamp.

### 6.5 Plaid sign convention preserved
- **Setup:** sandbox txn with amount `-500.00` (deposit).
- **Expected:** stored `amount = -500.00` exactly (no sign flip).

---

## 7. `analyze.py` — transfer detection (HIGHEST RISK)

### 7.1 Credit card payment detected
- **Setup:** depository txn `-1200.00` on 2026-04-10 account A; credit txn `+1200.00` on 2026-04-10 account B. Neither flagged.
- **Action:** `detect_transfers()`.
- **Expected:** both rows have `is_transfer=1`.

### 7.2 ±2 day window boundary
- **Setup:** pairs at offsets of 0, 1, 2, 3 days.
- **Expected:** offsets 0/1/2 flagged; offset 3 NOT flagged.

### 7.3 Exact amount match only
- **Setup:** `-100.00` on A and `+100.01` on B within window.
- **Expected:** neither flagged.

### 7.4 Opposite sign required
- **Setup:** `+100` on A and `+100` on B within window.
- **Expected:** neither flagged.

### 7.5 Same-account match ignored
- **Setup:** two opposite-sign, equal-amount txns on the same `account_id`.
- **Expected:** neither flagged (must be across different accounts).

### 7.6 No double-pairing
- **Setup:** `-100` on A, `+100` on B, `+100` on C — all same day.
- **Expected:** exactly one pair flagged; the third txn remains `is_transfer=0`. Decision must be deterministic (e.g., earliest by transaction_id).

### 7.7 Chase → Schwab investment transfer
- **Setup:** checking `-500`, investment account `-500` (Plaid sign for an inbound to investment may vary — verify against sandbox).
- **Expected:** both flagged per spec §4.

### 7.8 Idempotent
- **Action:** run twice.
- **Expected:** same set of flagged rows; does not un-flag or newly flag.

### 7.9 Already-flagged rows not reconsidered
- **Setup:** row manually set `is_transfer=1`.
- **Expected:** untouched regardless of partner presence.

---

## 8. `analyze.py` — category remap

### 8.1 Known primary maps
- **Input:** `FOOD_AND_DRINK_GROCERIES` → `Groceries`; `TRANSPORTATION_GAS` → `Transport`.

### 8.2 Wildcard families map
- **Input:** `GENERAL_MERCHANDISE_ELECTRONICS` → `Shopping`; `MEDICAL_DENTAL_CARE` → `Healthcare`; `TRAVEL_FLIGHTS` → `Travel`.

### 8.3 Unknown falls through
- **Input:** `WEIRD_NEW_CATEGORY_FROM_PLAID`.
- **Expected:** `Other`, no raise.

### 8.4 Null primary
- **Input:** `None`.
- **Expected:** `Other`.

---

## 9. `analyze.py` — weekly snapshot math

Fixture (use consistent across tests below): week_ending = 2026-04-12 (Sunday). Accounts: checking (depository), HYSA (depository), CC1 (credit), CC2 (credit), brokerage (investment). Balances on 2026-04-12: checking=$3,000, HYSA=$20,000, brokerage=$50,000, CC1=$800 (debt), CC2=$200 (debt).

### 9.1 Net worth formula
- **Expected:** `total_cash=23000, total_invested=50000, total_credit_debt=1000, net_worth=72000`.

### 9.2 Window is 7 days ending Sunday inclusive
- **Setup:** txn on 2026-04-06 (Mon) and 2026-04-13 (Mon after).
- **Expected:** Apr 06 included, Apr 13 excluded (window = Apr 06..Apr 12).

### 9.3 Income excludes transfers
- **Setup:** paycheck `-3000` on checking (non-transfer); transfer-in `-500` on HYSA (flagged).
- **Expected:** `income_this_week=3000` (abs of negative on depository, transfers excluded).

### 9.4 Spending includes credit + depository, excludes transfers
- **Setup:** +50 groceries on checking, +75 dinner on CC1, +1200 CC payment on checking (is_transfer=1), +1200 CC payment receipt on CC1 (is_transfer=1).
- **Expected:** `spending_this_week=125`.

### 9.5 Net income
- **Expected:** `net_income_this_week = income - spending`.

### 9.6 Spending by category sums & is JSON-serialized
- **Setup:** Groceries 50, Eating out 75.
- **Expected:** `spending_by_category_json` decodes to `{"Groceries": 50.0, "Eating out": 75.0}`. Zero-spend categories omitted.

### 9.7 Default week_ending
- **Action:** call with no arg on a Wednesday.
- **Expected:** resolves to the most recent past Sunday.

### 9.8 No transactions in window
- **Expected:** income=0, spending=0, net=0, `spending_by_category_json="{}"`. Does not raise.

### 9.9 Uses latest balance per account ≤ week_ending
- **Setup:** checking balance 2026-04-10=2500, 2026-04-12=3000, 2026-04-14=9999.
- **Expected:** net worth uses 3000, not 9999.

---

## 10. `report.py` (Google Sheets)

### 10.1 Weekly Summary append schema
- **Expected:** 11 columns in this order: Week Ending, Net Worth, Cash, Invested, Credit Debt, Income, Spending, Net Income, Savings Rate, Top Category, Top Category $.

### 10.2 Savings rate calc
- **Expected:** `net_income / income` formatted as percent; if income=0 → blank or `"N/A"` (never divide-by-zero error).

### 10.3 Top category resolution
- **Setup:** Groceries $200, Eating out $300, Shopping $100.
- **Expected:** Top Category="Eating out", Top Category $=300. Ties broken alphabetically (documented).

### 10.4 Category Detail batch append
- **Setup:** 4 categories with spend in week.
- **Expected:** exactly 4 rows appended in one batch call; columns: Week Ending, Category, Amount, % of Spending, Transaction Count.

### 10.5 Idempotency on re-run same week
- **Action:** run pipeline twice for same week_ending.
- **Expected:** either (a) second run is a no-op for the sheet, or (b) documented overwrite. Must NOT silently append duplicate rows. [Pick one; test the chosen contract.]

### 10.6 `--include-transactions` flag
- **Off (default):** "All Transactions" tab not written.
- **On:** tab written with columns mirroring the `transactions` table; only rows in the week window appended.

### 10.7 Sheet auth failure surfaces
- **Setup:** service account lacks edit access.
- **Expected:** clear error identifying the sheet ID; pipeline exits nonzero; SQLite snapshot already saved (so a retry only needs to re-publish).

---

## 11. `main.py` — orchestrator

### 11.1 CLI args
- **Expected:** `--include-transactions` (bool flag, default False); `--week-ending YYYY-MM-DD` (default: most recent Sunday); invalid date → nonzero exit with clear error.

### 11.2 Pipeline order
- **Expected call order:** `init_db → (per-institution fetch) → detect_transfers → compute_weekly_snapshot → save_snapshot → append_to_gsheet → print_summary_to_stdout`.

### 11.3 Partial failure behavior
- **Setup:** 5 institutions, 1 raises PlaidReauthRequired.
- **Expected:** snapshot still computed and written. Stdout summary flags the reauth institution by name.

### 11.4 Stdout summary content
- **Expected:** single block containing week_ending, net_worth, income, spending, top category. Machine-parseable enough for a cron log.

### 11.5 Exit codes
- **All green:** 0. **Sheet write fails:** nonzero. **DB write fails:** nonzero. **Single reauth:** 0 (logged, not fatal).

---

## 12. End-to-end (sandbox)

### 12.1 Fresh install happy path
- **Steps:** link ins_109508 with user_good/pass_good via link.py → run main.py → inspect SQLite + Sheet.
- **Expected:** transactions+balances populated; one Weekly Summary row; Category Detail rows sum to spending_this_week.

### 12.2 Simulated credit card payment
- **Setup:** manually insert matched pair across two sandbox accounts.
- **Expected:** both flagged is_transfer=1 after main.py; weekly spending unchanged vs. a run without the pair.

### 12.3 Manual net-worth verification
- **Action:** hand-sum balances; compare to `weekly_snapshots.net_worth`.
- **Expected:** equal to the cent.

### 12.4 Re-auth path
- **Setup:** corrupt a token in tokens.enc (or use sandbox `/sandbox/item/reset_login`).
- **Expected:** main.py prints `re-link <institution>`; other institutions still process; subsequent re-link + rerun clears the state.

---

## 13. Bask fallback (only if Plaid unsupported)

### 13.1 CSV import
- **Setup:** drop `bask_2026-04-12.csv` in `data/bask_inbox/` with a deposit and balance row.
- **Action:** run import.
- **Expected:** rows land in `transactions` and `balances` with `institution='bask'`; same downstream math works; processed file moved or marked so rerun doesn't duplicate.

### 13.2 Malformed CSV
- **Expected:** file rejected with clear error; no partial writes; other institutions unaffected.

---

## 14. Security / hygiene

### 14.1 `.gitignore` coverage
- **Expected:** `.env`, `*.db`, `tokens.enc`, `credentials.json`, `__pycache__`, `.venv` all ignored. `git check-ignore` passes for each.

### 14.2 No secrets in logs
- **Action:** grep run.log after a sandbox run.
- **Expected:** no `access-`, no `client_id`, no `secret`, no `FERNET_KEY` value.

### 14.3 tokens.enc opaque
- **Covered by 3.2.**

### 14.4 Plaid sign-convention regression guard
- **Setup:** snapshot test with fixture: deposits negative, purchases positive; verify income and spending produce expected signs in sheet (income positive, spending positive, credit debt positive).

---

## Suggested layout when implemented

```
tests/
├── conftest.py              # sqlite tmpfile fixture, Fernet key, frozen "today"
├── fixtures/
│   ├── plaid_sync_page1.json
│   ├── plaid_sync_page2.json
│   ├── balances.json
│   └── transfers_scenarios.py
├── test_config.py           # §1
├── test_db.py               # §2
├── test_tokens.py           # §3
├── test_plaid_client.py     # §4 (responses/respx mocking)
├── test_link.py             # §5 (Flask test client)
├── test_fetch.py            # §6
├── test_analyze_transfers.py # §7 (the risky one — most cases)
├── test_analyze_categories.py # §8
├── test_analyze_snapshot.py  # §9
├── test_report.py           # §10 (gspread mocked)
├── test_main.py             # §11
├── test_e2e_sandbox.py      # §12 (marked @slow, real sandbox)
├── test_bask.py             # §13
└── test_security.py         # §14
```

Recommend freezing "today" with `freezegun` for all snapshot/window tests; mocking Plaid with `responses` or `respx`; mocking gspread with a fake worksheet that records `append_row` / `append_rows` calls.
