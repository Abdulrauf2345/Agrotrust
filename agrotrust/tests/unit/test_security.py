import base64
import json
import unittest
from datetime import timedelta

import jwt

from agrotrust.config.settings import ConfigError, Settings
from agrotrust.security.passwords import hash_password, validate_password_strength, verify_password
from agrotrust.security.permissions import ALL_PERMISSIONS, ROLE_PERMISSIONS, Principal, Role
from agrotrust.security.pii import mask_email, mask_phone, redact
from agrotrust.security.rate_limit import InMemoryRateLimiter, Policy
from agrotrust.security.tokens import TokenService, hash_token, new_refresh_token
from agrotrust.shared.clock import FrozenClock
from agrotrust.shared.errors import AuthenticationFailed, PermissionDenied, RateLimited, ValidationFailed


class PasswordTests(unittest.TestCase):
    def test_roundtrip_and_salting(self):
        h1, h2 = hash_password("Correct-horse-9"), hash_password("Correct-horse-9")
        self.assertNotEqual(h1, h2)
        self.assertNotIn("Correct-horse-9", h1)
        self.assertTrue(verify_password("Correct-horse-9", h1))
        self.assertFalse(verify_password("wrong-horse-99", h1))
        self.assertFalse(verify_password("x", "garbage"))

    def test_strength(self):
        for bad in ("short1", "onlyletterslong", "1234567890", "password123"):
            with self.assertRaises(ValidationFailed):
                validate_password_strength(bad)
        validate_password_strength("Str0ng-enough-pw")


class TokenTests(unittest.TestCase):
    def setUp(self):
        self.clock = FrozenClock()
        self.svc = TokenService("s" * 40, "agrotrust", 900, self.clock)

    def test_roundtrip(self):
        tok, ttl = self.svc.create_access_token("u1")
        self.assertEqual(ttl, 900)
        self.assertEqual(self.svc.decode_access_token(tok)["sub"], "u1")

    def test_expiry_uses_injected_clock(self):
        tok, _ = self.svc.create_access_token("u1")
        self.clock.advance(seconds=901)
        with self.assertRaises(AuthenticationFailed):
            self.svc.decode_access_token(tok)

    def test_tampering_and_wrong_key(self):
        tok, _ = self.svc.create_access_token("u1")
        with self.assertRaises(AuthenticationFailed):
            self.svc.decode_access_token(tok[:-2] + "xx")
        other = TokenService("z" * 40, "agrotrust", 900, self.clock)
        with self.assertRaises(AuthenticationFailed):
            other.decode_access_token(tok)

    def test_alg_none_rejected(self):
        header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).rstrip(b"=")
        payload = base64.urlsafe_b64encode(json.dumps({
            "sub": "admin", "iss": "agrotrust", "typ": "access", "jti": "1",
            "exp": int(self.clock.now().timestamp()) + 999}).encode()).rstrip(b"=")
        forged = (header + b"." + payload + b".").decode()
        with self.assertRaises(AuthenticationFailed):
            self.svc.decode_access_token(forged)

    def test_wrong_issuer_and_type(self):
        bad = jwt.encode({"sub": "u", "iss": "evil", "typ": "access", "jti": "1",
                          "exp": int(self.clock.now().timestamp()) + 60}, "s" * 40, algorithm="HS256")
        with self.assertRaises(AuthenticationFailed):
            self.svc.decode_access_token(bad)
        bad2 = jwt.encode({"sub": "u", "iss": "agrotrust", "typ": "refresh", "jti": "1",
                           "exp": int(self.clock.now().timestamp()) + 60}, "s" * 40, algorithm="HS256")
        with self.assertRaises(AuthenticationFailed):
            self.svc.decode_access_token(bad2)

    def test_refresh_token_helpers(self):
        a, b = new_refresh_token(), new_refresh_token()
        self.assertNotEqual(a, b)
        self.assertEqual(len(hash_token(a)), 64)


class PermissionTests(unittest.TestCase):
    def test_farmer_cannot_release_escrow_or_create_orders(self):
        farmer = ROLE_PERMISSIONS[Role.FARMER]
        self.assertNotIn("escrow:release_own", farmer)
        self.assertNotIn("escrow:release", farmer)
        self.assertNotIn("order:create", farmer)
        self.assertNotIn("farm:verify", farmer)

    def test_agent_cannot_trade_or_verify(self):
        agent = ROLE_PERMISSIONS[Role.FIELD_AGENT]
        self.assertNotIn("farm:verify", agent)
        self.assertNotIn("order:create", agent)

    def test_only_admin_has_platform_powers(self):
        for role, perms in ROLE_PERMISSIONS.items():
            if role != Role.PLATFORM_ADMIN:
                for p in ("user:manage", "role:manage", "escrow:release", "dispute:resolve", "farm:verify",
                          "ledger:view", "audit:view", "config:manage"):
                    self.assertNotIn(p, perms, f"{role} must not have {p}")

    def test_principal(self):
        p = Principal("u", frozenset({"FARMER"}), frozenset({"farm:create"}), {"o1": "ADMIN"})
        p.require("farm:create")
        with self.assertRaises(PermissionDenied):
            p.require("farm:verify")
        self.assertTrue(p.is_org_admin("o1"))
        self.assertFalse(p.is_org_member("o2"))
        admin = Principal("a", frozenset({"PLATFORM_ADMIN"}), frozenset({"*"}))
        admin.require("anything:at:all")
        self.assertIn("farm:verify", ALL_PERMISSIONS)


class RateLimitTests(unittest.TestCase):
    def test_sliding_window(self):
        clock = FrozenClock()
        rl = InMemoryRateLimiter(clock, {"login": Policy(3, 60), "default": Policy(100, 60)})
        for _ in range(3):
            rl.check("login", "1.2.3.4")
        with self.assertRaises(RateLimited) as ctx:
            rl.check("login", "1.2.3.4")
        self.assertGreater(ctx.exception.details["retry_after_s"], 0)
        rl.check("login", "other-ip")           # independent identity
        clock.advance(seconds=61)
        rl.check("login", "1.2.3.4")            # window expired


class SettingsTests(unittest.TestCase):
    def test_dev_defaults_ok(self):
        Settings().validate()

    def test_production_rejects_insecure_config(self):
        with self.assertRaises(ConfigError) as ctx:
            Settings(env="production").validate()
        msg = str(ctx.exception)
        for needle in ("jwt_secret", "mock payment", "webhook_secret", "in-memory"):
            self.assertIn(needle, msg)

    def test_production_accepts_good_config(self):
        Settings(env="production", jwt_secret="x" * 40, payment_provider="paystack", webhook_secret="w" * 20,
                 storage_backend="s3", cors_origins=("https://app.agrotrust.ng",)).validate()

    def test_from_env(self):
        s = Settings.from_env({"AGROTRUST_ACCESS_TOKEN_TTL_S": "60", "AGROTRUST_CORS_ORIGINS": "https://a.com, https://b.com"})
        self.assertEqual(s.access_token_ttl_s, 60)
        self.assertEqual(s.cors_origins, ("https://a.com", "https://b.com"))


class PiiTests(unittest.TestCase):
    def test_masking_and_redaction(self):
        self.assertEqual(mask_phone("+2348012345678"), "+234*******678")
        self.assertEqual(mask_email("amina@example.com"), "a***@example.com")
        out = redact({"password": "x", "nested": {"api_key": "k", "ok": 1}, "list": [{"otp": "1"}], "name": "n"})
        self.assertEqual(out["password"], "[REDACTED]")
        self.assertEqual(out["nested"], {"api_key": "[REDACTED]", "ok": 1})
        self.assertEqual(out["list"], [{"otp": "[REDACTED]"}])
        self.assertEqual(out["name"], "n")


if __name__ == "__main__":
    unittest.main()
