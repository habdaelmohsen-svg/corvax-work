"""In-process automatic DGTERA sales scheduler.

Every active connection is refreshed at two-minute intervals.  The source
query enforces each DGTERA Branch Sales source date as 00:00 through 23:59:59,
so CORVAX uses the exact same report-day ownership without a timezone shift.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select

from app.core.config import settings
from app.db import SessionLocal
from app.models import DgteraConnection
from app.services.dgtera_connector import DgteraRemoteError
from app.services.dgtera_sales_sync import (
    DgteraSyncBusy,
    catchup_window,
    changed_historical_sales_dates,
    connection_is_due,
    historical_recheck_window,
    historical_backfill_window,
    sync_connection,
)
from app.core.time import utc_now


logger = logging.getLogger("corvax.dgtera.scheduler")
HISTORY_CHUNKS_PER_CYCLE = max(1, min(31, settings.dgtera_history_days_per_cycle))
CHANGED_DAYS_PER_CYCLE = max(1, min(7, settings.dgtera_changed_days_per_cycle))


def _date_windows(dates: list) -> list[tuple]:
    """Return auditable one-day windows; never create a large correction job."""
    return [(current, current) for current in sorted(set(dates))]


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
            # One scheduler cycle is one serialized queue: current day first,
            # then at most one historical day.  The former implementation ran
            # current, changed-history, four backfill days and a rolling audit
            # together, starving report requests and repeatedly recycling the
            # managed PostgreSQL connection.
            if not connection_is_due(connection):
                continue
            watermark = connection.last_sync_at or (utc_now() - timedelta(minutes=5))
            start_date, end_date = catchup_window(connection)
            try:
                result = sync_connection(db, connection, start_date, end_date, connection.created_by)
                logger.info(
                    "DGTERA automatic current sales sync completed",
                    extra={"connection_id": connection.id, "start": str(start_date), "end": str(end_date), "result": result},
                )
            except DgteraSyncBusy:
                logger.info("DGTERA sales sync already running", extra={"connection_id": connection.id})
                continue
            except (DgteraRemoteError, ValueError) as exc:
                logger.error(
                    "DGTERA automatic current sales sync failed",
                    extra={"connection_id": connection.id, "start": str(start_date), "end": str(end_date), "error": str(exc)},
                )
                continue
            except Exception:  # noqa: BLE001 - scheduler must continue after one failed company
                logger.exception(
                    "Unexpected DGTERA current-sales scheduler failure",
                    extra={"connection_id": connection.id, "start": str(start_date), "end": str(end_date)},
                )
                continue

            # Drain several independently committed business days per cycle.
            # Each day remains a separate source read, transaction and strict
            # proof, so acceleration cannot turn into one unsafe year-sized
            # database transaction.  Stop at the first failure and retry that
            # exact day on the next two-minute cycle.
            imported_history = False
            for _ in range(HISTORY_CHUNKS_PER_CYCLE):
                history_window = historical_backfill_window(db, connection)
                if history_window is None:
                    break
                imported_history = True
                history_start, history_end = history_window
                try:
                    result = sync_connection(
                        db, connection, history_start, history_end,
                        connection.created_by, mark_current_sync=False,
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
                    break
                except (DgteraRemoteError, ValueError) as exc:
                    logger.error(
                        "DGTERA historical sales backfill failed",
                        extra={"connection_id": connection.id, "start": str(history_start), "end": str(history_end), "error": str(exc)},
                    )
                    break
                except Exception:  # noqa: BLE001 - keep the next poll alive
                    logger.exception(
                        "Unexpected DGTERA historical backfill failure",
                        extra={"connection_id": connection.id, "start": str(history_start), "end": str(history_end)},
                    )
                    break
            if imported_history:
                # Changed-date discovery is intentionally postponed until the
                # contiguous history queue has been drained.
                continue

            # Only after backfill completion, recheck at most one changed day.
            try:
                changed_dates = changed_historical_sales_dates(connection, watermark)
            except (DgteraRemoteError, ValueError) as exc:
                logger.error(
                    "DGTERA changed-order discovery failed",
                    extra={"connection_id": connection.id, "error": str(exc)},
                )
                changed_dates = []
            changed_dates = [
                value for value in sorted(set(changed_dates))
                if not (start_date <= value <= end_date)
            ][:CHANGED_DAYS_PER_CYCLE]
            if changed_dates:
                changed_start = changed_end = changed_dates[0]
                try:
                    sync_connection(
                        db, connection, changed_start, changed_end,
                        connection.created_by, mark_current_sync=False,
                    )
                except DgteraSyncBusy:
                    logger.info("DGTERA changed-history sync already running", extra={"connection_id": connection.id})
                except Exception:  # noqa: BLE001 - later cycles must remain alive
                    logger.exception(
                        "DGTERA changed historical sales reconciliation failed",
                        extra={"connection_id": connection.id, "start": str(changed_start), "end": str(changed_end)},
                    )
                continue

            # Finally, when there is no queued backfill or changed day, re-read
            # one stalest completed day as the rolling audit.
            audit_window = historical_recheck_window(db, connection)
            if audit_window is not None:
                audit_start, audit_end = audit_window
                try:
                    sync_connection(
                        db, connection, audit_start, audit_end,
                        connection.created_by, mark_current_sync=False,
                    )
                except DgteraSyncBusy:
                    logger.info("DGTERA rolling history audit already running", extra={"connection_id": connection.id})
                except (DgteraRemoteError, ValueError):
                    logger.exception(
                        "DGTERA rolling full-history audit failed",
                        extra={"connection_id": connection.id, "start": str(audit_start), "end": str(audit_end)},
                    )
                except Exception:  # noqa: BLE001 - keep later scheduler polls alive
                    logger.exception(
                        "Unexpected DGTERA rolling full-history audit failure",
                        extra={"connection_id": connection.id, "start": str(audit_start), "end": str(audit_end)},
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
