"""Build a fully wired Context for module tests."""
from agrotrust.config.settings import Settings
from agrotrust.events.outbox import Outbox
from agrotrust.modules.audit.service import AuditService
from agrotrust.shared.context import Context
from tests.helpers import DbTestCase


class CtxTestCase(DbTestCase):
    def setUp(self):
        super().setUp()
        self.settings = Settings(env="testing", jwt_secret="test-secret-test-secret-test-secret-1234")
        self.ctx = Context(db=self.db, clock=self.clock, settings=self.settings,
                           audit=AuditService(self.db, self.clock), outbox=Outbox(self.db, self.clock))


from agrotrust.security.permissions import ROLE_PERMISSIONS, Principal  # noqa: E402


def make_principal(user_id: str, *roles: str) -> Principal:
    perms = set()
    for r in roles:
        perms |= ROLE_PERMISSIONS[r]
    return Principal(user_id=user_id, roles=frozenset(roles), permissions=frozenset(perms))


def insert_user(db, user_id: str, phone_suffix: str | None = None) -> None:
    with db.transaction():
        db.execute("INSERT INTO users(id,phone,full_name,password_hash,status,created_at,updated_at)"
                   " VALUES (?,?,?,?,?,?,?)",
                   (user_id, "+23480000" + (phone_suffix or str(abs(hash(user_id)) % 10**5).zfill(5)) + "1", user_id,
                    "x", "ACTIVE", "t", "t"))


def insert_crop(db, code="MAIZE", unit="KG"):
    from agrotrust.shared.ids import new_id
    cid = new_id()
    with db.transaction():
        db.execute("INSERT INTO crops(id,code,name,default_unit,active) VALUES (?,?,?,?,1)", (cid, code, code.title(), unit))
    return cid
