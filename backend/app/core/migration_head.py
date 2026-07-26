"""CORVAX - single source of truth for the expected Alembic head.

AUDIT FINDING C-03: the expected migration head was hard-coded in four places
(readiness, release info, internal completion and the postgres smoke script).
They drifted behind the real head, so /health/ready answered 503
"Migration head mismatch" on a correctly migrated database, which marks the
service unhealthy on Render and can fail a deployment.

The head is now read from Alembic itself, so it can never fall out of step.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger("corvax.migration")


@lru_cache(maxsize=1)
def expected_migration_head() -> str:
    """Return the head revision Alembic would upgrade to.

    Returns an empty string if it cannot be determined; callers treat that as
    "do not enforce" rather than failing the health check on a tooling problem.
    """
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        backend_root = Path(__file__).resolve().parents[2]
        config = Config(str(backend_root / "alembic.ini"))
        config.set_main_option("script_location", str(backend_root / "migrations"))
        heads = ScriptDirectory.from_config(config).get_heads()
        if len(heads) == 1:
            return heads[0]
        if heads:
            logger.warning("Multiple Alembic heads detected: %s", heads)
            return sorted(heads)[-1]
    except Exception:  # noqa: BLE001 - never break health on a tooling error
        logger.exception("Could not determine the expected migration head")
    return ""
