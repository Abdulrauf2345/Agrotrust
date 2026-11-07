# AgroTrust

An agricultural marketplace and fintech platform built for the Nigerian market, connecting
farmers, buyers, aggregators, logistics providers, lenders, insurers, cooperative admins, field
agents, and platform admins in one system: an escrow-backed marketplace, loan origination and
repayment, parametric weather insurance, farm-to-buyer traceability, logistics/shipment tracking,
and admin tooling.

This repository is a monorepo with two independent projects:

```
agrotrust/              Flask + SQLite backend (the API, business logic, ledger, tests)
agrotrust-frontend/     React 18 + TypeScript frontend (the web client)
```

Each has its own README with setup instructions:

- [`agrotrust/README.md`](./agrotrust/README.md) — backend setup, running the dev server, tests
- [`agrotrust-frontend/README.md`](./agrotrust-frontend/README.md) — frontend setup, running the dev server, tests

## Quick start

Run both servers side by side (two terminals):

```bash
# terminal 1: backend
cd agrotrust
python -m venv venv
venv\Scripts\activate      # Windows; use `source venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
$env:PYTHONPATH='src'; python scripts/run_dev_server.py   # PowerShell
# or: PYTHONPATH=src python scripts/run_dev_server.py     # macOS/Linux

# terminal 2: frontend
cd agrotrust-frontend
cp .env.example .env
npm install
npm run dev
```

Then open the URL `npm run dev` prints (typically `http://localhost:5173`).

## Status

Feature-complete demo across all 9 roles, with real tested business logic (a double-entry
ledger, role-scoped permissions, idempotent financial mutations, hash-chained custody records).
Not yet production-grade: the payment gateway is mocked, the database is SQLite rather than
Postgres, and there is no CI pipeline yet.
