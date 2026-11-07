import unittest

from agrotrust.modules.admin.service import AdminService
from agrotrust.modules.identity.service import IdentityService
from agrotrust.modules.organizations.service import OrganizationService
from agrotrust.security.permissions import Principal, Role
from agrotrust.shared.errors import PermissionDenied, ValidationFailed
from tests.helpers_ctx import CtxTestCase, insert_user, make_principal


class AdminTests(CtxTestCase):
    def setUp(self):
        super().setUp()
        self.orgs = OrganizationService(self.ctx)
        self.admin_svc = AdminService(self.ctx, None, self.orgs, self.ctx.audit)
        insert_user(self.db, "farmer1", "11111")
        with self.db.transaction():
            self.db.execute("INSERT INTO roles(name,self_register) VALUES ('FARMER',1) ON CONFLICT(name) DO NOTHING")
            self.db.execute("INSERT INTO roles(name,self_register) VALUES ('BUYER',1) ON CONFLICT(name) DO NOTHING")
            self.db.execute("INSERT INTO user_roles(user_id,role,granted_at) VALUES ('farmer1','FARMER',?)",
                            (self.ctx.now_iso(),))
        self.farmer = make_principal("farmer1", Role.FARMER)
        self.admin = Principal(user_id="farmer1", roles=frozenset({Role.PLATFORM_ADMIN}), permissions=frozenset({"*"}))

    def test_list_users_requires_permission(self):
        with self.assertRaises(PermissionDenied):
            self.admin_svc.list_users(self.farmer)
        res = self.admin_svc.list_users(self.admin)
        self.assertGreaterEqual(res["total"], 1)

    def test_user_detail_includes_roles(self):
        detail = self.admin_svc.user_detail(self.admin, "farmer1")
        self.assertIn("FARMER", detail["roles"])

    def test_user_detail_not_found(self):
        with self.assertRaises(ValidationFailed):
            self.admin_svc.user_detail(self.admin, "no-such-user")

    def test_config_round_trip_and_audited(self):
        self.admin_svc.set_config(self.admin, "platform_fee_bps", "150")
        cfg = self.admin_svc.platform_config(self.admin)
        self.assertEqual(cfg["platform_fee_bps"], "150")
        trail = self.admin_svc.audit_trail(self.admin, resource_type="system_config", resource_id="platform_fee_bps")
        self.assertEqual(len(trail), 1)
        self.assertEqual(trail[0]["action"], "CONFIG_CHANGED")

    def test_config_requires_permission(self):
        with self.assertRaises(PermissionDenied):
            self.admin_svc.set_config(self.farmer, "x", "y")

    def test_filter_by_role(self):
        insert_user(self.db, "buyer1", "22222")
        with self.db.transaction():
            self.db.execute("INSERT INTO user_roles(user_id,role,granted_at) VALUES ('buyer1','BUYER',?)",
                            (self.ctx.now_iso(),))
        res = self.admin_svc.list_users(self.admin, role="BUYER")
        ids = [u["id"] for u in res["items"]]
        self.assertIn("buyer1", ids)
        self.assertNotIn("farmer1", ids)


if __name__ == "__main__":
    unittest.main()
