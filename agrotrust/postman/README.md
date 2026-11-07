# AgroTrust — Postman Collection

This collection (`AgroTrust.postman_collection.json`) covers the full HTTP surface of the
AgroTrust API — about 99 requests across every module. Folders are numbered in the order
they're meant to be run, and each request that creates something automatically saves its ID
into a collection variable (e.g. `{{farm_id}}`, `{{order_id}}`) that later requests reuse — so
running a folder top-to-bottom tells a coherent story instead of needing you to copy-paste IDs
by hand.

## 1. Import it

Postman → **Import** → select `AgroTrust.postman_collection.json`.

## 2. Start the server

Use the provided script instead of starting Flask directly — it pins the database to a fixed
file (`.dev_data/agrotrust_dev.db`) instead of a random temp file, which matters for step 3
below, and it comes with a few reference crops (MAIZE, RICE, CASSAVA) already seeded:

```bash
PYTHONPATH=src python3 scripts/run_dev_server.py
```

The collection's `base_url` variable defaults to `http://localhost:8000` — matches this
automatically, nothing to configure. Use `crop-maize` as the `crop_id` value in the
"Create listing" and "Create lot" requests (replace the `<paste-crop-id-see-readme>`
placeholders) — or query `GET /api/v1/listings` with no filters, or just pick any crop code you
prefer (`RICE` → `crop-rice`, `CASSAVA` → `crop-cassava`).

By default the database **persists** across restarts (so your Postman-created farms/orders
survive you stopping and restarting the server) — pass `--fresh` to wipe it:

```bash
PYTHONPATH=src python3 scripts/run_dev_server.py --fresh
```

## 3. One manual setup step: granting non-self-registerable roles

`PLATFORM_ADMIN`, `LENDER`, and `FIELD_AGENT` can't be obtained through
`/api/v1/auth/register` — that's intentional (see `security/permissions.py`'s
`SELF_REGISTERABLE` set): nobody should be able to self-promote to admin or lender through a
public signup form. The collection registers these three as plain `BUYER`s first (run the
"Register ... (manual role grant required)" requests in the Auth folder); you then grant the
real role with the provided script, pointed at the **same** `--db` path the server is running
with:

```bash
python3 scripts/grant_role.py --db .dev_data/agrotrust_dev.db --phone +2348011110099 --role PLATFORM_ADMIN
python3 scripts/grant_role.py --db .dev_data/agrotrust_dev.db --phone +2348011110005 --role LENDER
python3 scripts/grant_role.py --db .dev_data/agrotrust_dev.db --phone +2348011110006 --role FIELD_AGENT
```

Then run the matching "Login ... (run AFTER granting ...)" requests in Postman — their tokens
will now carry the real role.

**Finding a user's ID for admin actions:** a couple of requests (assign farm agent, admin user
detail) need a raw user ID, not a phone number. Run "My profile" with that user's token and copy
`id` from the response, or `grant_role.py` prints it out when it runs.

## 4. Recommended run order

Run folders **00 through 14 in order**. Within "01 - Auth", run every "Register" and "Login"
request first (including the admin/lender/agent ones, after doing step (b) above) before moving
to later folders — later folders' requests reference `{{farmer_access_token}}`,
`{{lender_access_token}}`, etc., which only exist once the matching login request has run.

You can also use Postman's **Collection Runner** to fire an entire folder in sequence
automatically, which is the fastest way to replay the whole walkthrough after a server restart.

## 5. What you can fully test vs. what needs the automated test suite instead

**Fully testable via this collection, end to end, against a live server:** auth, marketplace,
orders, escrow release, farms + verification lifecycle, traceability/lots, inventory, logistics,
lending (including disbursement and repayment), offline sync, notifications, admin, analytics,
and — thanks to the three `[DEV]` endpoints in the Payments folder — the **full payment webhook
flow**, signature and all (those `[DEV]` endpoints exist only because a real payment gateway's
hosted checkout page would normally call our webhook after an actual payment; the mocked
provider has no such page, so these three endpoints stand in for it, the same way Paystack/
Flutterwave's own sandboxes have a "simulate success" test action).

**Not practically testable through Postman, by design:** the insurance payout's weather-trigger
evaluation depends on real wall-clock time passing a policy's `window_end` — there's no HTTP
endpoint to fast-forward the server's clock (unlike the test suite, which uses a `FrozenClock`
it can advance instantly). If you want to see an insurance payout actually fire via Postman,
create the policy with a `window_end` already in the past (the collection's example does this —
`2020-01-31`) and separately call `InsuranceService.ingest_observation()` / `evaluate()` from a
Python shell against the same database, since there's no public endpoint for weather-data
ingestion either (a real deployment would have a scheduled job pulling from a weather API, not
a user-facing endpoint). For a fully automated, no-manual-steps proof that insurance payouts
work correctly, see `tests/integration/test_insurance.py` instead — that's the better tool for
that specific question.

## 6. The `[DEV]` endpoints are not production code paths

Everything under `/api/v1/_dev/` in `api/app.py` is wrapped in
`if c.settings.env in ("development", "testing")` — it structurally cannot exist if
`AGROTRUST_ENV` is set to `staging` or `production`. They exist purely so this Postman
collection (an external HTTP client with no Python access) can drive flows that would otherwise
require calling mock-provider methods directly from Python, the way the automated test suite
does.
