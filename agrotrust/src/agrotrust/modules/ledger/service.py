"""Double-entry ledger (spec section 15).

Invariants enforced in code AND by DB CHECK/UNIQUE/trigger constraints:
* every entry balances (sum debits == sum credits, > 0);
* entries and lines are immutable (triggers); corrections are compensating entries;
* ``reference`` is unique -> posting the same business event twice is a no-op replay;
* an entry can be reversed at most once (unique reverses_entry_id);
* accounts that are not ``allow_negative`` can never be overdrawn (checked inside the
  same write-locked transaction as the posting, so concurrent postings serialise).
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from ...shared.context import Context
from ...shared.errors import Conflict, InsufficientFunds, NotFound, UnbalancedJournal, ValidationFailed
from ...shared.ids import new_id

# System accounts
BANK = "SYS:BANK"                  # ASSET: cash held at the payment provider / bank
ESCROW_HOLD = "SYS:ESCROW"         # LIABILITY: buyer money held pending release
FEE_REVENUE = "SYS:FEE_REVENUE"    # REVENUE: platform fees earned
LOAN_RECEIVABLE = "SYS:LOAN_RECEIVABLE"  # ASSET: principal owed by farmers
INTEREST_REVENUE = "SYS:INTEREST_REVENUE"
LOAN_FUNDING = "SYS:LOAN_FUNDING"  # EQUITY/capital that funds loans
INSURANCE_POOL = "SYS:INSURANCE_POOL"  # LIABILITY
PAYOUT_PENDING = "SYS:PAYOUT_PENDING"  # LIABILITY: withdrawals reserved, awaiting provider confirmation
_SYSTEM = [
    (BANK, "Bank / provider cash", "ASSET", True),
    (ESCROW_HOLD, "Escrow holding", "LIABILITY", False),
    (FEE_REVENUE, "Platform fee revenue", "REVENUE", False),
    (LOAN_RECEIVABLE, "Loan principal receivable", "ASSET", False),
    (INTEREST_REVENUE, "Interest revenue", "REVENUE", False),   # penalty/late-fee income is folded in here (see ADR)
    (LOAN_FUNDING, "Lending capital", "EQUITY", True),
    (INSURANCE_POOL, "Insurance pool", "LIABILITY", False),
    (PAYOUT_PENDING, "Payouts in flight", "LIABILITY", False),
]
_DEBIT_NORMAL = {"ASSET", "EXPENSE"}


@dataclass(frozen=True)
class Line:
    account: str      # account code
    side: str         # 'D' or 'C'
    amount_minor: int


def D(account: str, amount: int) -> Line:
    return Line(account, "D", amount)


def C(account: str, amount: int) -> Line:
    return Line(account, "C", amount)


def wallet_code(user_id: str) -> str:
    return f"WALLET:{user_id}"


class LedgerService:
    def __init__(self, ctx: Context):
        self.ctx = ctx
        self.db = ctx.db

    # ------------------------------------------------------------- accounts
    def ensure_system_accounts(self) -> None:
        with self.db.transaction():
            for code, name, typ, neg in _SYSTEM:
                self.db.execute(
                    "INSERT INTO ledger_accounts(id,code,name,type,allow_negative,created_at) VALUES (?,?,?,?,?,?)"
                    " ON CONFLICT(code) DO NOTHING", (new_id(), code, name, typ, 1 if neg else 0, self.ctx.now_iso()))

    def ensure_wallet(self, user_id: str) -> str:
        """Per-user wallet: a LIABILITY (we owe the user this money). Idempotent."""
        code = wallet_code(user_id)
        with self.db.transaction():
            self.db.execute(
                "INSERT INTO ledger_accounts(id,code,name,type,owner_user_id,allow_negative,created_at)"
                " VALUES (?,?,?,?,?,0,?) ON CONFLICT(code) DO NOTHING",
                (new_id(), code, f"Wallet {user_id}", "LIABILITY", user_id, self.ctx.now_iso()))
        return code

    def _account(self, code: str) -> dict:
        acc = self.db.one("SELECT * FROM ledger_accounts WHERE code=?", (code,))
        if not acc:
            raise NotFound(f"ledger account {code} not found")
        return acc

    def balance(self, code: str) -> int:
        """Natural-sign balance in minor units (assets: D-C; everything else: C-D)."""
        acc = self._account(code)
        return self._balance_of(acc)

    def _balance_of(self, acc: dict) -> int:
        row = self.db.one(
            "SELECT COALESCE(SUM(CASE WHEN side='D' THEN amount_minor ELSE 0 END),0) AS d,"
            " COALESCE(SUM(CASE WHEN side='C' THEN amount_minor ELSE 0 END),0) AS c"
            " FROM journal_lines WHERE account_id=?", (acc["id"],))
        return row["d"] - row["c"] if acc["type"] in _DEBIT_NORMAL else row["c"] - row["d"]

    def wallet_balance(self, user_id: str) -> int:
        code = wallet_code(user_id)
        if not self.db.one("SELECT 1 FROM ledger_accounts WHERE code=?", (code,)):
            return 0
        return self.balance(code)

    # -------------------------------------------------------------- posting
    def post(self, *, reference: str, entry_type: str, description: str, lines: list[Line],
             actor_id: str | None = None, meta: dict | None = None,
             reverses_entry_id: str | None = None) -> dict:
        """Post a balanced entry. Idempotent on ``reference``: a repeat returns the original
        entry (and raises if the repeat carries different lines - a caller bug)."""
        if not reference or len(reference) > 200:
            raise ValidationFailed("reference required (<=200 chars)")
        if len(lines) < 2:
            raise ValidationFailed("an entry needs at least two lines")
        for ln in lines:
            if ln.side not in ("D", "C") or not isinstance(ln.amount_minor, int) or isinstance(ln.amount_minor, bool) \
                    or ln.amount_minor <= 0:
                raise ValidationFailed("lines need side D/C and a positive integer amount")
        debit = sum(l.amount_minor for l in lines if l.side == "D")
        credit = sum(l.amount_minor for l in lines if l.side == "C")
        if debit != credit:
            raise UnbalancedJournal(f"debits {debit} != credits {credit}")
        with self.db.transaction():
            existing = self.db.one("SELECT * FROM journal_entries WHERE reference=?", (reference,))
            if existing:
                if existing["total_debit_minor"] != debit:
                    raise Conflict("reference reused with different amounts", details={"reference": reference})
                return existing
            accounts = {}
            for ln in lines:
                if ln.account not in accounts:
                    accounts[ln.account] = self._account(ln.account)
            entry_id = new_id()
            self.db.execute(
                "INSERT INTO journal_entries(id,reference,entry_type,description,total_debit_minor,total_credit_minor,"
                "reverses_entry_id,meta,created_by,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (entry_id, reference, entry_type, description, debit, credit, reverses_entry_id,
                 json.dumps(meta, sort_keys=True) if meta else None, actor_id, self.ctx.now_iso()))
            for ln in lines:
                self.db.execute("INSERT INTO journal_lines(entry_id,account_id,side,amount_minor) VALUES (?,?,?,?)",
                                (entry_id, accounts[ln.account]["id"], ln.side, ln.amount_minor))
            # overdraft guard (same write-locked txn => no race between check and post)
            for code, acc in accounts.items():
                if not acc["allow_negative"] and self._balance_of(acc) < 0:
                    raise InsufficientFunds(f"insufficient funds in {code}", details={"account": code})
            return self.db.one("SELECT * FROM journal_entries WHERE id=?", (entry_id,))

    def reverse(self, entry_id: str, *, reason: str, actor_id: str | None = None) -> dict:
        """Compensating entry with sides flipped. Never edits history."""
        if not reason:
            raise ValidationFailed("reason required")
        with self.db.transaction():
            entry = self.db.one("SELECT * FROM journal_entries WHERE id=?", (entry_id,))
            if not entry:
                raise NotFound("journal entry not found")
            if entry["reverses_entry_id"]:
                raise Conflict("cannot reverse a reversal")
            if self.db.one("SELECT 1 FROM journal_entries WHERE reverses_entry_id=?", (entry_id,)):
                raise Conflict("entry already reversed")
            rows = self.db.all(
                "SELECT a.code, l.side, l.amount_minor FROM journal_lines l JOIN ledger_accounts a ON a.id=l.account_id"
                " WHERE l.entry_id=?", (entry_id,))
            flipped = [Line(r["code"], "C" if r["side"] == "D" else "D", r["amount_minor"]) for r in rows]
            try:
                return self.post(reference=f"reversal:{entry_id}", entry_type="REVERSAL",
                                 description=f"Reversal of {entry['reference']}: {reason}", lines=flipped,
                                 actor_id=actor_id, meta={"reason": reason}, reverses_entry_id=entry_id)
            except Exception as e:  # unique reverses_entry_id race
                if "UNIQUE" in str(e).upper():
                    raise Conflict("entry already reversed") from e
                raise

    # ------------------------------------------------------------ integrity
    def trial_balance(self) -> dict:
        """Global invariant: total debits == total credits, and per-entry balance holds."""
        row = self.db.one(
            "SELECT COALESCE(SUM(CASE WHEN side='D' THEN amount_minor END),0) AS d,"
            " COALESCE(SUM(CASE WHEN side='C' THEN amount_minor END),0) AS c FROM journal_lines")
        bad = self.db.all(
            "SELECT e.id FROM journal_entries e JOIN journal_lines l ON l.entry_id=e.id GROUP BY e.id"
            " HAVING SUM(CASE WHEN l.side='D' THEN l.amount_minor ELSE -l.amount_minor END) != 0")
        return {"debits": row["d"], "credits": row["c"], "balanced": row["d"] == row["c"] and not bad,
                "unbalanced_entries": [b["id"] for b in bad]}
