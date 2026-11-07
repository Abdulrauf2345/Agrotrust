"""File storage abstraction (S3-compatible in production) with strict upload validation."""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Protocol

from ...security.permissions import Principal
from ...shared.context import Context
from ...shared.errors import NotFound, UnauthorizedResourceAccess, ValidationFailed
from ...shared.ids import new_id

# content-type -> (extension, magic-byte check)
_SIGNATURES = {
    "image/jpeg": ("jpg", lambda b: b[:3] == b"\xff\xd8\xff"),
    "image/png": ("png", lambda b: b[:8] == b"\x89PNG\r\n\x1a\n"),
    "image/webp": ("webp", lambda b: b[:4] == b"RIFF" and b[8:12] == b"WEBP"),
    "application/pdf": ("pdf", lambda b: b[:5] == b"%PDF-"),
}


class ObjectStorage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class InMemoryStorage:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def put(self, key, data, content_type):
        self.objects[key] = data

    def get(self, key):
        try:
            return self.objects[key]
        except KeyError:
            raise NotFound("object not found")

    def delete(self, key):
        self.objects.pop(key, None)


class LocalFsStorage:
    """Development storage (MinIO/S3 via integrations/s3_storage.py in real deployments)."""

    def __init__(self, root: str):
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root not in p.parents:
            raise ValidationFailed("invalid storage key")   # path traversal guard
        return p

    def put(self, key, data, content_type):
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get(self, key):
        p = self._path(key)
        if not p.exists():
            raise NotFound("object not found")
        return p.read_bytes()

    def delete(self, key):
        self._path(key).unlink(missing_ok=True)


def sanitize_filename(name: str) -> str:
    base = os.path.basename((name or "").replace("\\", "/"))
    base = re.sub(r"[^\w.\- ]", "_", base)[:100].strip(". ")
    return base or "upload"


class FileService:
    def __init__(self, ctx: Context, storage: ObjectStorage):
        self.ctx, self.storage = ctx, storage

    def upload(self, principal: Principal, *, filename: str, content_type: str, data: bytes,
               classification: str = "INTERNAL") -> dict:
        principal.require("file:upload")
        if content_type not in _SIGNATURES:
            raise ValidationFailed("unsupported file type", details={"allowed": sorted(_SIGNATURES)})
        if not data:
            raise ValidationFailed("empty file")
        if len(data) > self.ctx.settings.max_upload_bytes:
            raise ValidationFailed("file too large", details={"max_bytes": self.ctx.settings.max_upload_bytes})
        ext, matches = _SIGNATURES[content_type]
        if not matches(data):
            raise ValidationFailed("file content does not match its declared type")   # spoofed content-type
        file_id = new_id()
        key = f"{principal.user_id}/{file_id}.{ext}"      # never derived from the client filename
        self.storage.put(key, data, content_type)
        with self.ctx.db.transaction():
            self.ctx.db.execute(
                "INSERT INTO files(id, owner_id, storage_key, filename, content_type, size_bytes, sha256, classification, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (file_id, principal.user_id, key, sanitize_filename(filename), content_type, len(data),
                 hashlib.sha256(data).hexdigest(), classification, self.ctx.now_iso()))
            self.ctx.audit.record(actor_id=principal.user_id, action="FILE_UPLOADED", resource_type="file", resource_id=file_id,
                                  new={"content_type": content_type, "size": len(data)})
        return {"id": file_id, "content_type": content_type, "size_bytes": len(data)}

    def download(self, principal: Principal, file_id: str) -> tuple[dict, bytes]:
        meta = self.ctx.db.one("SELECT * FROM files WHERE id=?", (file_id,))
        if not meta:
            raise NotFound("file not found")
        if meta["owner_id"] != principal.user_id and not principal.is_admin:
            raise UnauthorizedResourceAccess("you do not have access to this file")
        return meta, self.storage.get(meta["storage_key"])

    def owned(self, principal: Principal, file_id: str) -> None:
        """Assert the caller owns the file (used before attaching to farms/listings)."""
        row = self.ctx.db.one("SELECT owner_id FROM files WHERE id=?", (file_id,))
        if not row:
            raise NotFound("file not found")
        if row["owner_id"] != principal.user_id:
            raise UnauthorizedResourceAccess("you can only attach files you uploaded")
