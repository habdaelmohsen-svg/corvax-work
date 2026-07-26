from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.core.crypto import decrypt_text, encrypt_text


class EncryptedString(TypeDecorator[str]):
    """Transparent AES-GCM encrypted text column."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return encrypt_text(str(value))

    def process_result_value(self, value, dialect):
        return decrypt_text(value)


class EncryptedDecimal(TypeDecorator[Decimal]):
    """Encrypted decimal stored as text and returned as ``Decimal``."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return encrypt_text(format(Decimal(str(value)), "f"))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        plain = decrypt_text(value)
        return Decimal(str(plain))
