"""UTC time helpers.

Database DateTime columns remain timezone-naive for backward compatibility, but every
value is generated from an aware UTC clock before the timezone marker is removed.
This avoids the deprecated the legacy naive-UTC constructor API while preserving existing schema
semantics.
"""
from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return the current UTC time as a naive datetime for legacy DB columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_now_aware() -> datetime:
    """Return the current UTC time with timezone information."""
    return datetime.now(timezone.utc)
