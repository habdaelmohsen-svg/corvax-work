"""Application-level envelope encryption for sensitive ERP fields.

Ciphertext format: ``enc:v1:<kid>:<base64(nonce|ciphertext|tag)>``.
Keys are supplied as a JSON key ring through FIELD_ENCRYPTION_KEYS_JSON. Development
uses a deterministic local-only key derived from SECRET_KEY; production validation
rejects that fallback and requires an explicit key ring.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from functools import lru_cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

_PREFIX = "enc:v1:"


def _decode_key(value: str) -> bytes:
    try:
        key = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except Exception as exc:  # pragma: no cover - defensive config path
        raise ValueError("Invalid base64 field-encryption key") from exc
    if len(key) not in {16, 24, 32}:
        raise ValueError("Field-encryption keys must decode to 16, 24 or 32 bytes")
    return key


@lru_cache(maxsize=1)
def encryption_keyring() -> dict[str, bytes]:
    configured = settings.field_encryption_keys
    if configured:
        return {kid: _decode_key(value) for kid, value in configured.items()}
    # Local-only deterministic fallback. Production configuration rejects it.
    material = hashlib.sha256(
        f"CORVAX-FIELD-ENCRYPTION|{settings.field_encryption_active_kid}|{settings.secret_key}".encode()
    ).digest()
    return {settings.field_encryption_active_kid: material}


def encrypt_text(value: str | None, *, aad: bytes | None = None) -> str | None:
    if value is None or value == "":
        return value
    if value.startswith(_PREFIX):
        return value
    keys = encryption_keyring()
    kid = settings.field_encryption_active_kid
    if kid not in keys:
        raise ValueError(f"Active field-encryption key {kid!r} is not configured")
    nonce = os.urandom(12)
    ciphertext = AESGCM(keys[kid]).encrypt(nonce, value.encode("utf-8"), aad)
    payload = base64.urlsafe_b64encode(nonce + ciphertext).decode().rstrip("=")
    return f"{_PREFIX}{kid}:{payload}"


def decrypt_text(value: object | None, *, aad: bytes | None = None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        # Legacy numeric columns remain readable while the Alembic data migration
        # rewrites them into encrypted text.
        return str(value)
    if value == "" or not value.startswith(_PREFIX):
        # Legacy plaintext remains readable during controlled migration only.
        return value
    try:
        _, _, kid, payload = value.split(":", 3)
        raw = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        nonce, ciphertext = raw[:12], raw[12:]
        key = encryption_keyring()[kid]
        return AESGCM(key).decrypt(nonce, ciphertext, aad).decode("utf-8")
    except Exception as exc:
        raise ValueError("Sensitive field decryption failed") from exc


def blind_index(value: str | None, *, purpose: str) -> str | None:
    """Return a deterministic HMAC index for equality checks without plaintext."""
    if value is None or value == "":
        return None
    key = encryption_keyring()[settings.field_encryption_active_kid]
    normalized = value.strip().upper().encode("utf-8")
    return hmac.new(key, purpose.encode() + b"|" + normalized, hashlib.sha256).hexdigest()


def ciphertext_present(value: object) -> bool:
    return isinstance(value, str) and value.startswith(_PREFIX)
