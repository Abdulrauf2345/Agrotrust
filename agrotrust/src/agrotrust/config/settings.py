"""Environment-driven configuration with per-environment guard rails.

Note: the production stack should use ``pydantic-settings`` (see docs/adr/ADR-013);
this dataclass keeps the same contract (env vars in, validated immutable object out)
and is what the test-suite exercises.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from typing import Mapping

ENVIRONMENTS = ("development", "testing", "staging", "production")
_INSECURE_DEFAULT = "change-me-insecure-dev-secret-change-me"


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    env: str = "development"
    database_url: str = "sqlite:///./agrotrust.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = _INSECURE_DEFAULT
    jwt_issuer: str = "agrotrust"
    access_token_ttl_s: int = 15 * 60
    refresh_token_ttl_s: int = 30 * 24 * 3600
    otp_ttl_s: int = 300
    otp_max_attempts: int = 5
    max_failed_logins: int = 5
    lockout_s: int = 15 * 60
    platform_fee_bps: int = 100          # 1.00% of the released amount
    max_upload_bytes: int = 5 * 1024 * 1024
    max_visit_distance_m: float = 1500.0
    # geographic sanity box (Nigeria, generous). Configurable for expansion.
    geo_min_lat: float = 3.9
    geo_max_lat: float = 14.8
    geo_min_lon: float = 2.5
    geo_max_lon: float = 15.0
    payment_provider: str = "mock"
    paystack_secret_key: str = ""
    flutterwave_secret_hash: str = ""
    flutterwave_secret_key: str = ""
    webhook_secret: str = "dev-webhook-secret"
    storage_backend: str = "memory"
    s3_bucket: str = ""
    s3_endpoint_url: str = ""
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    sentry_dsn: str = ""
    log_level: str = "INFO"
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        kwargs: dict = {}
        for f in fields(cls):
            if f.name == "extra":
                continue
            raw = env.get("AGROTRUST_" + f.name.upper())
            if raw is None:
                continue
            if f.type in ("int", int):
                kwargs[f.name] = int(raw)
            elif f.type in ("float", float):
                kwargs[f.name] = float(raw)
            elif f.name == "cors_origins":
                kwargs[f.name] = tuple(x.strip() for x in raw.split(",") if x.strip())
            else:
                kwargs[f.name] = raw
        s = cls(**kwargs)
        s.validate()
        return s

    def validate(self) -> None:
        if self.env not in ENVIRONMENTS:
            raise ConfigError(f"env must be one of {ENVIRONMENTS}")
        if self.env in ("staging", "production"):
            problems = []
            if self.jwt_secret == _INSECURE_DEFAULT or len(self.jwt_secret) < 32:
                problems.append("jwt_secret must be set to a random value of >= 32 chars")
            if self.payment_provider == "mock":
                problems.append("mock payment provider is not allowed")
            if "*" in self.cors_origins:
                problems.append("wildcard CORS origin is not allowed")
            if self.webhook_secret == "dev-webhook-secret":
                problems.append("webhook_secret must be set")
            if self.storage_backend == "memory":
                problems.append("in-memory file storage is not allowed")
            if problems:
                raise ConfigError("; ".join(problems))
        if not (0 <= self.platform_fee_bps <= 2000):
            raise ConfigError("platform_fee_bps out of range")
