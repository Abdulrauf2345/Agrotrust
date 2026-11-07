"""Identity, authentication, sessions, roles, OTP and KYC."""
from __future__ import annotations

import hashlib
import re
import secrets
from datetime import timedelta

from ...integrations.identity_verification import IdentityVerificationProvider
from ...security.passwords import hash_password, validate_password_strength, verify_password
from ...security.permissions import ROLE_PERMISSIONS, SELF_REGISTERABLE, Principal, Role
from ...security.tokens import TokenService, hash_token, new_refresh_token
from ...shared.clock import from_iso, to_iso
from ...shared.context import Context
from ...shared.errors import (AuthenticationFailed, Conflict, NotFound, PermissionDenied, ValidationFailed)
from ...shared.ids import new_id
from ..notifications.service import NotificationService

_PHONE_RE = re.compile(r"^\+[1-9]\d{9,14}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DUMMY_HASH = hash_password("dummy-password-for-timing-1")
_KYC_FORMATS = {"NIN": r"^\d{11}$", "BVN": r"^\d{11}$", "VOTERS_CARD": r"^[A-Z0-9]{9,19}$",
                "DRIVERS_LICENSE": r"^[A-Z0-9]{10,16}$", "PASSPORT": r"^[A-Z][0-9]{8}$"}


def normalize_phone(raw: str) -> str:
    if not isinstance(raw, str):
        raise ValidationFailed("phone must be a string")
    s = re.sub(r"[\s\-()]", "", raw)
    if s.startswith("+"):
        pass
    elif s.startswith("234"):
        s = "+" + s
    elif s.startswith("0") and len(s) == 11:
        s = "+234" + s[1:]
    if not _PHONE_RE.match(s):
        raise ValidationFailed("invalid phone number")
    return s


class IdentityService:
    def __init__(self, ctx: Context, tokens: TokenService, notifications: NotificationService,
                 kyc_provider: IdentityVerificationProvider):
        self.ctx, self.tokens, self.notifications, self.kyc = ctx, tokens, notifications, kyc_provider

    @property
    def db(self):
        return self.ctx.db

    # ---------------------------------------------------------------- bootstrap
    def seed_roles(self) -> None:
        """Idempotently load default roles/permissions (extensible at runtime via admin API)."""
        with self.db.transaction():
            for role, perms in ROLE_PERMISSIONS.items():
                self.db.execute("INSERT INTO roles(name, description, self_register) VALUES (?,?,?) ON CONFLICT DO NOTHING",
                                (role, role.replace("_", " ").title(), 1 if role in SELF_REGISTERABLE else 0))
                for p in perms:
                    self.db.execute("INSERT INTO role_permissions(role, permission) VALUES (?,?) ON CONFLICT DO NOTHING", (role, p))

    def bootstrap_admin(self, phone: str, password: str, full_name: str = "Platform Admin") -> str:
        """Out-of-band creation of the first PLATFORM_ADMIN (CLI/seed only, never exposed over HTTP)."""
        return self._create_user(normalize_phone(phone), password, [Role.PLATFORM_ADMIN], None, full_name, actor=None)

    # ------------------------------------------------------------- registration
    def register(self, *, phone: str, password: str, role: str = Role.FARMER, email: str | None = None,
                 full_name: str | None = None) -> dict:
        row = self.db.one("SELECT self_register FROM roles WHERE name=?", (role,))
        if not row or not row["self_register"]:
            raise PermissionDenied("this role cannot be self-registered")   # blocks privilege escalation
        user_id = self._create_user(normalize_phone(phone), password, [role], email, full_name, actor=None)
        return {"id": user_id, "phone": normalize_phone(phone), "roles": [role], "status": "ACTIVE"}

    def _create_user(self, phone, password, roles, email, full_name, actor) -> str:
        validate_password_strength(password)
        if email is not None:
            email = email.strip().lower()
            if not _EMAIL_RE.match(email):
                raise ValidationFailed("invalid email")
        pw_hash = hash_password(password)   # slow: outside the transaction
        user_id, now = new_id(), self.ctx.now_iso()
        with self.db.transaction():
            if self.db.one("SELECT 1 AS x FROM users WHERE phone=?", (phone,)) or \
               (email and self.db.one("SELECT 1 AS x FROM users WHERE email=?", (email,))):
                raise Conflict("an account with this phone or email already exists")
            self.db.execute("INSERT INTO users(id, phone, email, password_hash, full_name, status, created_at, updated_at)"
                            " VALUES (?,?,?,?,?,'ACTIVE',?,?)", (user_id, phone, email, pw_hash, full_name, now, now))
            for r in roles:
                self.db.execute("INSERT INTO user_roles(user_id, role, granted_by, granted_at) VALUES (?,?,?,?)",
                                (user_id, r, actor, now))
            self.ctx.audit.record(actor_id=actor or user_id, action="USER_REGISTERED", resource_type="user",
                                  resource_id=user_id, new={"roles": roles})
        return user_id

    # -------------------------------------------------------------------- login
    def login(self, phone: str, password: str) -> dict:
        try:
            phone = normalize_phone(phone)
        except ValidationFailed:
            verify_password(password, _DUMMY_HASH)
            raise AuthenticationFailed("invalid credentials")
        user = self.db.one("SELECT * FROM users WHERE phone=?", (phone,))
        now = self.ctx.clock.now()
        if user is None:
            verify_password(password, _DUMMY_HASH)   # equalise timing: no user enumeration
            raise AuthenticationFailed("invalid credentials")
        locked = user["locked_until"] and from_iso(user["locked_until"]) > now
        ok = verify_password(password, user["password_hash"]) and not locked and user["status"] == "ACTIVE"
        with self.db.transaction():
            if ok:
                self.db.execute("UPDATE users SET failed_logins=0, locked_until=NULL WHERE id=?", (user["id"],))
                tokens = self._issue_session(user["id"], family_id=new_id())
                self.ctx.audit.record(actor_id=user["id"], action="LOGIN", resource_type="user", resource_id=user["id"])
                return tokens
            if not locked and user["status"] == "ACTIVE":
                fails = user["failed_logins"] + 1
                lock = to_iso(now + timedelta(seconds=self.ctx.settings.lockout_s)) if fails >= self.ctx.settings.max_failed_logins else None
                self.db.execute("UPDATE users SET failed_logins=?, locked_until=? WHERE id=?", (fails, lock, user["id"]))
                self.ctx.audit.record(actor_id=user["id"], action="LOGIN_FAILED", resource_type="user", resource_id=user["id"],
                                      new={"failed_logins": fails, "locked": bool(lock)})
        raise AuthenticationFailed("invalid credentials")   # identical message for every failure cause

    def _issue_session(self, user_id: str, family_id: str) -> dict:
        access, ttl = self.tokens.create_access_token(user_id)
        refresh = new_refresh_token()
        now = self.ctx.clock.now()
        self.db.execute(
            "INSERT INTO refresh_tokens(id, user_id, family_id, token_hash, created_at, expires_at) VALUES (?,?,?,?,?,?)",
            (new_id(), user_id, family_id, hash_token(refresh), to_iso(now),
             to_iso(now + timedelta(seconds=self.ctx.settings.refresh_token_ttl_s))))
        return {"access_token": access, "refresh_token": refresh, "token_type": "Bearer", "expires_in": ttl}

    # ---------------------------------------------------- refresh-token rotation
    def refresh(self, refresh_token: str) -> dict:
        h = hash_token(refresh_token or "")
        reuse_detected = False
        result = None
        with self.db.transaction():
            row = self.db.one("SELECT * FROM refresh_tokens WHERE token_hash=?", (h,))
            if row is None:
                raise AuthenticationFailed("invalid refresh token")
            now = self.ctx.clock.now()
            won = self.db.execute(   # atomic single-use: exactly one concurrent caller wins
                "UPDATE refresh_tokens SET used_at=? WHERE id=? AND used_at IS NULL AND revoked_at IS NULL",
                (to_iso(now), row["id"])).rowcount == 1
            if not won:
                reuse_detected = True
                self.db.execute("UPDATE refresh_tokens SET revoked_at=? WHERE family_id=? AND revoked_at IS NULL",
                                (to_iso(now), row["family_id"]))
                self.ctx.audit.record(actor_id=row["user_id"], action="REFRESH_TOKEN_REUSE_DETECTED",
                                      resource_type="user", resource_id=row["user_id"], context={"family": row["family_id"]})
            elif from_iso(row["expires_at"]) <= now:
                raise AuthenticationFailed("refresh token expired")
            else:
                user = self.db.one("SELECT status FROM users WHERE id=?", (row["user_id"],))
                if user["status"] != "ACTIVE":
                    raise AuthenticationFailed("account is not active")
                result = self._issue_session(row["user_id"], row["family_id"])
        if reuse_detected:   # committed revocation first, then fail
            raise AuthenticationFailed("refresh token reuse detected; session revoked")
        return result

    def logout(self, refresh_token: str) -> None:
        with self.db.transaction():
            row = self.db.one("SELECT family_id FROM refresh_tokens WHERE token_hash=?", (hash_token(refresh_token or ""),))
            if row:
                self.db.execute("UPDATE refresh_tokens SET revoked_at=? WHERE family_id=? AND revoked_at IS NULL",
                                (self.ctx.now_iso(), row["family_id"]))

    def revoke_all_sessions(self, user_id: str) -> None:
        self.db.execute("UPDATE refresh_tokens SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", (self.ctx.now_iso(), user_id))

    # ------------------------------------------------------------ authentication
    def authenticate(self, access_token: str) -> Principal:
        claims = self.tokens.decode_access_token(access_token)
        return self.load_principal(claims["sub"])

    def load_principal(self, user_id: str) -> Principal:
        user = self.db.one("SELECT id, status FROM users WHERE id=?", (user_id,))
        if not user or user["status"] != "ACTIVE":
            raise AuthenticationFailed("account is not active")
        roles = [r["role"] for r in self.db.all("SELECT role FROM user_roles WHERE user_id=?", (user_id,))]
        perms = {r["permission"] for r in self.db.all(
            "SELECT DISTINCT permission FROM role_permissions WHERE role IN (SELECT role FROM user_roles WHERE user_id=?)", (user_id,))}
        orgs = {r["org_id"]: r["org_role"] for r in self.db.all("SELECT org_id, org_role FROM org_members WHERE user_id=?", (user_id,))}
        return Principal(user_id, frozenset(roles), frozenset(perms), orgs)

    # ------------------------------------------------------------- profile / pw
    def get_profile(self, principal: Principal, user_id: str | None = None) -> dict:
        target = user_id or principal.user_id
        if target != principal.user_id:
            principal.require("user:manage")
        u = self.db.one("SELECT id, phone, email, full_name, status, phone_verified, created_at FROM users WHERE id=?", (target,))
        if not u:
            raise NotFound("user not found")
        u["roles"] = [r["role"] for r in self.db.all("SELECT role FROM user_roles WHERE user_id=?", (target,))]
        return u   # never includes password_hash

    def change_password(self, principal: Principal, old_password: str, new_password: str) -> None:
        user = self.db.one("SELECT password_hash FROM users WHERE id=?", (principal.user_id,))
        if not verify_password(old_password, user["password_hash"]):
            raise AuthenticationFailed("invalid credentials")
        validate_password_strength(new_password)
        new_hash = hash_password(new_password)
        with self.db.transaction():
            self.db.execute("UPDATE users SET password_hash=?, updated_at=? WHERE id=?", (new_hash, self.ctx.now_iso(), principal.user_id))
            self.revoke_all_sessions(principal.user_id)
            self.ctx.audit.record(actor_id=principal.user_id, action="PASSWORD_CHANGED", resource_type="user", resource_id=principal.user_id)

    # ---------------------------------------------------------------------- OTP
    def request_otp(self, phone: str, purpose: str = "PHONE_VERIFY") -> None:
        """Always returns silently (no account enumeration)."""
        phone = normalize_phone(phone)
        user = self.db.one("SELECT id FROM users WHERE phone=? AND status='ACTIVE'", (phone,))
        if not user:
            return
        code = f"{secrets.randbelow(10**6):06d}"
        now = self.ctx.clock.now()
        with self.db.transaction():
            self.db.execute("UPDATE otp_codes SET consumed_at=? WHERE phone=? AND purpose=? AND consumed_at IS NULL",
                            (to_iso(now), phone, purpose))
            self.db.execute("INSERT INTO otp_codes(id, phone, purpose, code_hash, created_at, expires_at) VALUES (?,?,?,?,?,?)",
                            (new_id(), phone, purpose, self._otp_hash(phone, purpose, code), to_iso(now),
                             to_iso(now + timedelta(seconds=self.ctx.settings.otp_ttl_s))))
            self.notifications.enqueue(user["id"], "otp", {"code": code, "minutes": self.ctx.settings.otp_ttl_s // 60},
                                       channels=["SMS"])

    def verify_otp(self, phone: str, code: str, purpose: str = "PHONE_VERIFY") -> bool:
        phone = normalize_phone(phone)
        ok = False
        with self.db.transaction():
            row = self.db.one("SELECT * FROM otp_codes WHERE phone=? AND purpose=? AND consumed_at IS NULL ORDER BY created_at DESC LIMIT 1",
                              (phone, purpose))
            now = self.ctx.clock.now()
            if row and from_iso(row["expires_at"]) > now and row["attempts"] < self.ctx.settings.otp_max_attempts:
                if secrets.compare_digest(row["code_hash"], self._otp_hash(phone, purpose, code or "")):
                    self.db.execute("UPDATE otp_codes SET consumed_at=? WHERE id=?", (to_iso(now), row["id"]))
                    if purpose == "PHONE_VERIFY":
                        self.db.execute("UPDATE users SET phone_verified=1, updated_at=? WHERE phone=?", (to_iso(now), phone))
                    ok = True
                else:
                    self.db.execute("UPDATE otp_codes SET attempts = attempts + 1 WHERE id=?", (row["id"],))
        if not ok:
            raise AuthenticationFailed("invalid or expired code")
        return True

    def _otp_hash(self, phone: str, purpose: str, code: str) -> str:
        return hashlib.sha256(f"{self.ctx.settings.jwt_secret}:{phone}:{purpose}:{code}".encode()).hexdigest()

    def require_phone_verified(self, user_id: str) -> None:
        if not self.db.scalar("SELECT phone_verified FROM users WHERE id=?", (user_id,)):
            raise PermissionDenied("verify your phone number first")

    # -------------------------------------------------------------------- roles
    def assign_role(self, actor: Principal, user_id: str, role: str) -> None:
        actor.require("role:manage")
        with self.db.transaction():
            if not self.db.one("SELECT 1 AS x FROM roles WHERE name=?", (role,)):
                raise NotFound("unknown role")
            if not self.db.one("SELECT 1 AS x FROM users WHERE id=?", (user_id,)):
                raise NotFound("user not found")
            res = self.db.execute("INSERT INTO user_roles(user_id, role, granted_by, granted_at) VALUES (?,?,?,?) ON CONFLICT DO NOTHING",
                                  (user_id, role, actor.user_id, self.ctx.now_iso()))
            if res.rowcount:
                self.ctx.audit.record(actor_id=actor.user_id, action="ROLE_ASSIGNED", resource_type="user", resource_id=user_id, new={"role": role})

    def revoke_role(self, actor: Principal, user_id: str, role: str) -> None:
        actor.require("role:manage")
        with self.db.transaction():
            if role == Role.PLATFORM_ADMIN:
                admins = self.db.scalar("SELECT COUNT(*) FROM user_roles WHERE role='PLATFORM_ADMIN'")
                if admins <= 1:
                    raise Conflict("cannot remove the last platform admin")
            res = self.db.execute("DELETE FROM user_roles WHERE user_id=? AND role=?", (user_id, role))
            if res.rowcount:
                self.ctx.audit.record(actor_id=actor.user_id, action="ROLE_REVOKED", resource_type="user", resource_id=user_id, old={"role": role})

    def create_role(self, actor: Principal, name: str, permissions: list[str], description: str = "") -> None:
        actor.require("role:manage")
        if not re.match(r"^[A-Z][A-Z0-9_]{2,40}$", name):
            raise ValidationFailed("role names are UPPER_SNAKE_CASE")
        with self.db.transaction():
            if self.db.one("SELECT 1 AS x FROM roles WHERE name=?", (name,)):
                raise Conflict("role exists")
            self.db.execute("INSERT INTO roles(name, description, self_register) VALUES (?,?,0)", (name, description))
            for p in sorted(set(permissions)):
                self.db.execute("INSERT INTO role_permissions(role, permission) VALUES (?,?)", (name, p))
            self.ctx.audit.record(actor_id=actor.user_id, action="ROLE_CREATED", resource_type="role", resource_id=name, new={"permissions": sorted(set(permissions))})

    # ---------------------------------------------------------------------- KYC
    def submit_kyc(self, principal: Principal, id_type: str, id_number: str, full_name: str | None = None) -> dict:
        principal.require("kyc:submit")
        id_type = (id_type or "").upper()
        pattern = _KYC_FORMATS.get(id_type)
        id_number = (id_number or "").strip().upper()
        if not pattern or not re.match(pattern, id_number):
            raise ValidationFailed("unsupported ID type or invalid ID number format")
        result = self.kyc.verify(id_type, id_number, full_name)     # external call: outside any transaction
        now = self.ctx.now_iso()
        status = "VERIFIED" if result.verified else "FAILED"
        with self.db.transaction():
            kid = new_id()
            self.db.execute(
                "INSERT INTO kyc_records(id, user_id, id_type, id_last4, provider, provider_reference, status, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (kid, principal.user_id, id_type, id_number[-4:], self.kyc.name, result.reference, status, now, now))
            self.ctx.audit.record(actor_id=principal.user_id, action="KYC_SUBMITTED", resource_type="kyc", resource_id=kid,
                                  new={"id_type": id_type, "status": status})    # never the number itself
        return {"id": kid, "status": status, "id_type": id_type}

    def kyc_status(self, principal: Principal, user_id: str | None = None) -> dict:
        target = user_id or principal.user_id
        if target != principal.user_id:
            principal.require("kyc:read")
            with self.db.transaction():   # reads of another person's KYC are themselves audited
                self.ctx.audit.record(actor_id=principal.user_id, action="KYC_VIEWED", resource_type="user", resource_id=target)
        row = self.db.one("SELECT id_type, id_last4, status, created_at FROM kyc_records WHERE user_id=? ORDER BY created_at DESC LIMIT 1", (target,))
        return row or {"status": "NONE"}

    def is_kyc_verified(self, user_id: str) -> bool:
        return bool(self.db.scalar("SELECT 1 FROM kyc_records WHERE user_id=? AND status='VERIFIED' LIMIT 1", (user_id,)))

    def require_kyc_verified(self, user_id: str) -> None:
        if not self.is_kyc_verified(user_id):
            raise PermissionDenied("identity verification (KYC) is required for this action", details={"kyc": "REQUIRED"})

    # ------------------------------------------------------- suspend / erase (NDPA)
    def set_status(self, actor: Principal, user_id: str, status: str, reason: str) -> None:
        actor.require("user:manage")
        if status not in ("ACTIVE", "SUSPENDED"):
            raise ValidationFailed("status must be ACTIVE or SUSPENDED")
        with self.db.transaction():
            u = self.db.one("SELECT status FROM users WHERE id=?", (user_id,))
            if not u:
                raise NotFound("user not found")
            if u["status"] == "DELETED":
                raise Conflict("user is erased")
            self.db.execute("UPDATE users SET status=?, updated_at=? WHERE id=?", (status, self.ctx.now_iso(), user_id))
            if status == "SUSPENDED":
                self.revoke_all_sessions(user_id)
            self.ctx.audit.record(actor_id=actor.user_id, action="USER_STATUS_CHANGED", resource_type="user", resource_id=user_id,
                                  old={"status": u["status"]}, new={"status": status}, context={"reason": reason})

    def erase_user(self, actor: Principal, user_id: str, reason: str) -> None:
        """NDPA erasure/anonymisation request. Financial records are retained (legal obligation)
        but detached from personal data. Refused while obligations are open."""
        if actor.user_id != user_id:
            actor.require("user:manage")
        with self.db.transaction():
            if not self.db.one("SELECT 1 AS x FROM users WHERE id=? AND status<>'DELETED'", (user_id,)):
                raise NotFound("user not found")
            open_orders = self.db.scalar("SELECT COUNT(*) FROM orders WHERE (buyer_id=? OR seller_id=?) AND state NOT IN ('COMPLETED','CANCELLED')", (user_id, user_id))
            open_loans = self.db.scalar("SELECT COUNT(*) FROM loans WHERE borrower_id=? AND state<>'COMPLETED'", (user_id,))
            wallet = self.db.scalar(
                "SELECT COALESCE(SUM(CASE l.side WHEN 'C' THEN l.amount_minor ELSE -l.amount_minor END),0) FROM journal_lines l"
                " JOIN ledger_accounts a ON a.id=l.account_id WHERE a.owner_user_id=? AND a.type='LIABILITY'", (user_id,))
            if open_orders or open_loans or wallet:
                raise Conflict("cannot erase while orders/loans are open or wallet balance is non-zero",
                               details={"open_orders": open_orders, "open_loans": open_loans, "wallet_minor": wallet})
            tag = hashlib.sha256(user_id.encode()).hexdigest()[:12]
            self.db.execute("UPDATE users SET phone=?, email=NULL, full_name=NULL, password_hash=?, status='DELETED', updated_at=? WHERE id=?",
                            (f"deleted:{tag}", "!" + secrets.token_hex(16), self.ctx.now_iso(), user_id))
            self.db.execute("UPDATE kyc_records SET id_last4='****', provider_reference=NULL WHERE user_id=?", (user_id,))
            self.db.execute("DELETE FROM otp_codes WHERE phone IN (SELECT phone FROM users WHERE id=?)", (user_id,))
            self.db.execute("DELETE FROM notifications WHERE user_id=?", (user_id,))
            self.revoke_all_sessions(user_id)
            self.ctx.audit.record(actor_id=actor.user_id, action="USER_ERASED", resource_type="user", resource_id=user_id, context={"reason": reason})
