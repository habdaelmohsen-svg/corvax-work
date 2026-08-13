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
    historical_backfill_window,
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
            if not connection:
                continue
            current_ok = True
            if connection_is_due(connection):
                start_date, end_date = catchup_window(connection)
                try:
                    result = sync_connection(db, connection, start_date, end_date, connection.created_by)
                    logger.info(
                        "DGTERA automatic current sales sync completed",
                        extra={"connection_id": connection.id, "start": str(start_date), "end": str(end_date), "result": result},
                    )
                except DgteraSyncBusy:
                    current_ok = False
                    logger.info("DGTERA sales sync already running", extra={"connection_id": connection.id})
                except (DgteraRemoteError, ValueError) as exc:
                    current_ok = False
                    logger.error(
                        "DGTERA automatic current sales sync failed",
                        extra={"connection_id": connection.id, "start": str(start_date), "end": str(end_date), "error": str(exc)},
                    )
                except Exception:  # noqa: BLE001 - scheduler must continue after one failed company
                    current_ok = False
                    logger.exception(
                        "Unexpected DGTERA current-sales scheduler failure",
                        extra={"connection_id": connection.id, "start": str(start_date), "end": str(end_date)},
                    )
            if not current_ok:
                continue

            # Import one seven-day historical slice on every poll.  This runs
            # independently of the five-minute live refresh, so the 2025
            # history progresses without delaying today's sales updates.
            history_window = historical_backfill_window(db, connection)
            if history_window is None:
                continue
            history_start, history_end = history_window
            try:
                result = sync_connection(
                    db,
                    connection,
                    history_start,
                    history_end,
                    connection.created_by,
                    mark_current_sync=False,
                )
                logger.info(
                    "DGTERA historical sales backfill completed",
                    extra={
                        "connection_id": connection.id,
                        "start": str(history_start),
                        "end": str(history_end),
                        "result": result,
                    },
                )
            except DgteraSyncBusy:
                logger.info("DGTERA historical sales backfill already running", extra={"connection_id": connection.id})
            except (DgteraRemoteError, ValueError) as exc:
                logger.error(
                    "DGTERA historical sales backfill failed",
                    extra={
                        "connection_id": connection.id,
                        "start": str(history_start),
                        "end": str(history_end),
                        "error": str(exc),
                    },
                )
            except Exception:  # noqa: BLE001 - keep the next poll alive
                logger.exception(
                    "Unexpected DGTERA historical backfill failure",
                    extra={"connection_id": connection.id, "start": str(history_start), "end": str(history_end)},
                )


async def scheduler_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(run_due_syncs)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - one discovery failure must not kill the scheduler task
            logger.exception("DGTERA scheduler poll failed; retrying on the next interval")
        await asyncio.sleep(max(30, settings.dgtera_scheduler_poll_seconds))
