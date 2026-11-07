"""Wires every module's service objects together behind one ``Container``.

This is the composition root: exactly one place that knows how all the pieces fit, so the API
layer (and tests) never construct services by hand with the wrong dependencies.
"""
from __future__ import annotations

from ..config.settings import Settings
from ..db.database import Database
from ..events.outbox import Outbox
from ..integrations.identity_verification import MockIdentityProvider
from ..integrations.notification_providers import mock_providers
from ..integrations.payment_providers import MockPaymentProvider
from ..modules.admin.service import AdminService
from ..modules.analytics.service import AnalyticsService
from ..modules.audit.service import AuditService
from ..modules.escrow.service import EscrowService
from ..modules.farms.service import FarmService
from ..modules.files.service import FileService, InMemoryStorage
from ..modules.identity.service import IdentityService
from ..modules.insurance.service import InsuranceService
from ..modules.inventory.service import InventoryService
from ..modules.ledger.service import LedgerService
from ..modules.lending.service import LendingService
from ..modules.logistics.service import LogisticsService
from ..modules.marketplace.service import MarketplaceService
from ..modules.ml.service import MLService
from ..modules.notifications.service import NotificationService
from ..modules.offline_sync.service import OfflineSyncService
from ..modules.organizations.service import OrganizationService
from ..modules.orders.service import OrderService
from ..modules.payments.idempotency import IdempotencyService
from ..modules.payments.service import PaymentService
from ..modules.traceability.service import TraceabilityService
from ..security.rate_limit import InMemoryRateLimiter
from ..security.tokens import TokenService
from ..shared.clock import SystemClock
from ..shared.context import Context


class Container:
    def __init__(self, settings: Settings | None = None, db_path: str | None = None):
        self.settings = settings or Settings.from_env()
        self.clock = SystemClock()
        if db_path is None:
            import tempfile
            db_path = tempfile.NamedTemporaryFile(prefix="agrotrust_", suffix=".db", delete=False).name
        self.db = Database(db_path)
        self.db.init_schema()
        self.outbox = Outbox(self.db, self.clock)
        self.audit = AuditService(self.db, self.clock)
        self.ctx = Context(db=self.db, clock=self.clock, settings=self.settings, audit=self.audit, outbox=self.outbox)

        self.rate_limiter = InMemoryRateLimiter(self.clock)
        self.tokens = TokenService(self.settings.jwt_secret, self.settings.jwt_issuer,
                                   self.settings.access_token_ttl_s, self.clock)
        self.notifications = NotificationService(self.ctx, mock_providers())
        self.identity = IdentityService(self.ctx, self.tokens, self.notifications, MockIdentityProvider())
        self.organizations = OrganizationService(self.ctx)
        self.files = FileService(self.ctx, InMemoryStorage())
        self.farms = FarmService(self.ctx, self.files)

        self.ledger = LedgerService(self.ctx)
        self.ledger.ensure_system_accounts()
        self.idempotency = IdempotencyService(self.db, self.clock)
        self.market = MarketplaceService(self.ctx)
        self.escrow = EscrowService(self.ctx, self.ledger)
        self.orders = OrderService(self.ctx, self.market, self.escrow, self.idempotency)
        self.payment_provider = MockPaymentProvider(self.settings.webhook_secret)
        self.payments = PaymentService(self.ctx, self.ledger, self.payment_provider)

        self.traceability = TraceabilityService(self.ctx)
        self.inventory = InventoryService(self.ctx)
        self.logistics = LogisticsService(self.ctx)
        self.lending = LendingService(self.ctx, self.ledger, self.idempotency)
        self.insurance = InsuranceService(self.ctx, self.ledger)
        self.offline_sync = OfflineSyncService(self.ctx)
        self.offline_sync.register("farm_visit", lambda p, payload: self.farms.record_visit(
            p, payload["farm_id"], lat=payload["lat"], lon=payload["lon"], client_id=payload["client_id"],
            observations=payload.get("observations", "")))
        self.analytics = AnalyticsService(self.ctx)
        self.ml = MLService(self.ctx)
        self.admin = AdminService(self.ctx, self.identity, self.organizations, self.audit)

        self.identity.seed_roles()
        self._seed_dev_reference_data()

    def _seed_dev_reference_data(self) -> None:
        """Reference data (crops) that a real deployment seeds via an admin/ops process, not a
        public endpoint. Seeded here purely so a fresh local/Postman run always has something
        to reference immediately - harmless no-op if it already exists (e.g. re-seeded against
        a persistent db_path across restarts)."""
        with self.db.transaction():
            for code, name, unit in (("MAIZE", "Maize", "KG"), ("RICE", "Rice", "KG"), ("CASSAVA", "Cassava", "KG")):
                self.db.execute(
                    "INSERT INTO crops(id,code,name,default_unit,active) VALUES (?,?,?,?,1)"
                    " ON CONFLICT(code) DO NOTHING", (f"crop-{code.lower()}", code, name, unit))
