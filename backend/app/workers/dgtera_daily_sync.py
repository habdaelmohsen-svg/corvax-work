"""In-process automatic DGTERA sales scheduler.

Every active connection is refreshed at five-minute intervals.  The source
query itself enforces each Riyadh sales day as 00:01 through 23:59, so the
scheduler time never changes which day owns an order.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.core.config import settings
from app.db import SessionLocal
from app.models import DgteraConnection
from app.services.dgtera_connector import DgteraRemoteError
from app.services.dgtera_sales_sync import (
    DgteraSyncBusy,
    catchup_window,
    connection_is_due,
    sync_connection,
)


logger = logging.getLogger("corvax.dgtera.scheduler")


def run_due_syncs() -> None:
    with SessionLocal() as discovery_db:
        connection_ids = list(discovery_db.scalars(
            select(DgteraConnection.id).where(
                DgteraConnection.active.is_(True),
                DgteraConnection.last_tested_at.is_not(None),
            )
        ).all())
    for connection_id in connection_ids:
        with SessionLocal() as db:
            connection = db.get(DgteraConnection, connection_id)
            if not connection or not connection_is_due(connection):
                continue
            start_date, end_date = catchup_window(connection)
            try:
                result = sync_connection(db, connection, start_date, end_date, connection.created_by)
                logger.info(
                    "DGTERA automatic sales sync completed",
                    extra={"connection_id": connection.id, "start": str(start_date), "end": str(end_date), "result": result},
                )
            except DgteraSyncBusy:
                logger.info("DGTERA sales sync already running", extra={"connection_id": connection.id})
            except (DgteraRemoteError, ValueError) as exc:
                logger.error(
                    "DGTERA automatic sales sync failed",
                    extra={"connection_id": connection.id, "start": str(start_date), "end": str(end_date), "error": str(exc)},
                )
            except Exception:  # noqa: BLE001 - scheduler must continue after one failed company
                logger.exception(
                    "Unexpected DGTERA scheduler failure",
                    extra={"connection_id": connection.id, "start": str(start_date), "end": str(end_date)},
                )


async def scheduler_loop() -> None:
    while True:
        await asyncio.to_thread(run_due_syncs)
        await asyncio.sleep(max(30, settings.dgtera_scheduler_poll_seconds))

