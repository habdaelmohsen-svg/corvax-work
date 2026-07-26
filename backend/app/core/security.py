from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import struct
import time
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import settings

PBKDF2_ITERATIONS = 310_000
JWT_ISSUER = "corvax-business-platform"
JWT_AUDIENCE = "corvax-api"


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iteration_text, salt_text, digest_text = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            base64.b64decode(salt_text),
            int(iteration_text),
        )
        return hmac.compare_digest(base64.b64encode(digest).decode(), digest_text)
    except (ValueError, TypeError):
        return False


def validate_password_strength(password: str) -> list[str]:
    errors: list[str] = []
    if len(password) < settings.password_min_length:
        errors.append(f"Password must contain at least {settings.password_min_length} characters")
    if not re.search(r"[A-Z]", password):
        errors.append("Password must include an uppercase letter")
    if not re.search(r"[a-z]", password):
        errors.append("Password must include a lowercase letter")
    if not re.search(r"\d", password):
        errors.append("Password must include a number")
    if not re.search(r"[^A-Za-z0-9]", password):
        errors.append("Password must include a special character")
    return errors


def generate_mfa_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _totp_code(secret: str, counter: int, digits: int = 6) -> str:
    padded = secret + "=" * (-len(secret) % 8)
    key = base64.b32decode(padded, casefold=True)
    message = struct.pack(">Q", counter)
    digest = hmac.new(key, message, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10**digits)
    return f"{value:0{digits}d}"


def verify_totp(secret: str, code: str, *, at_time: int | None = None, window: int = 1) -> bool:
    if not code or not code.isdigit() or len(code) != 6:
        return False
    counter = int((at_time or int(time.time())) // 30)
    return any(hmac.compare_digest(_totp_code(secret, counter + offset), code) for offset in range(-window, window + 1))


def mfa_uri(secret: str, email: str) -> str:
    from urllib.parse import quote

    return f"otpauth://totp/{quote(settings.mfa_issuer)}:{quote(email)}?secret={secret}&issuer={quote(settings.mfa_issuer)}&algorithm=SHA1&digits=6&period=30"


@lru_cache(maxsize=1)
def _development_keypair() -> tuple[str, str]:
    """Generate an in-process key pair for development and isolated tests only."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


def _private_key_pem() -> str:
    if settings.jwt_private_key_pem:
        return settings.jwt_private_key_pem.replace("\\n", "\n")
    if settings.jwt_private_key_path:
        return Path(settings.jwt_private_key_path).read_text()
    return _development_keypair()[0]


def _public_keyring() -> dict[str, str]:
    keys = dict(settings.jwt_public_keys)
    if not keys:
        keys[settings.jwt_active_kid] = _development_keypair()[1]
    return keys


def create_access_token(
    user_id: int,
    session_id: str,
    token_version: int,
    minutes: int | None = None,
) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=minutes or settings.access_token_minutes)
    payload = {
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "sub": str(user_id),
        "sid": session_id,
        "ver": token_version,
        "type": "access",
        "jti": secrets.token_urlsafe(18),
        "iat": now,
        "nbf": now,
        "exp": expires,
    }
    token = jwt.encode(
        payload,
        _private_key_pem(),
        algorithm=settings.jwt_algorithm,
        headers={"kid": settings.jwt_active_kid, "typ": "JWT"},
    )
    return token, expires


# Backward-compatible name used by earlier modules and verification scripts.
def create_token(user_id: int, session_id: str, token_version: int, minutes: int | None = None) -> tuple[str, datetime]:
    return create_access_token(user_id, session_id, token_version, minutes)


def decode_token(token: str) -> dict:
    try:
        header = jwt.get_unverified_header(token)
        kid = str(header.get("kid") or "")
        key = _public_keyring().get(kid)
        if not key:
            raise ValueError("unknown signing key")
        payload = jwt.decode(
            token,
            key,
            algorithms=[settings.jwt_algorithm],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
            options={"require": ["exp", "iat", "nbf", "sub", "sid", "ver", "type", "jti"]},
        )
        if payload.get("type") != "access":
            raise ValueError("invalid token type")
        return payload
    except (jwt.PyJWTError, ValueError, KeyError, TypeError) as exc:
        raise ValueError("invalid or expired token") from exc


def create_refresh_token() -> tuple[str, str, datetime]:
    raw = secrets.token_urlsafe(64)
    expires = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_days)
    return raw, hash_refresh_token(raw), expires


def hash_refresh_token(token: str) -> str:
    return hmac.new(settings.secret_key.encode(), token.encode(), hashlib.sha256).hexdigest()


def verify_refresh_token(token: str, stored_hash: str | None) -> bool:
    if not token or not stored_hash:
        return False
    return hmac.compare_digest(hash_refresh_token(token), stored_hash)
