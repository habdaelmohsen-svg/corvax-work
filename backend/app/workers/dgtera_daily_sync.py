"""In-process automatic DGTERA sales scheduler.

Every active connection is refreshed at two-minute intervals.  The source
query itself enforces each Riyadh sales day as 00:00 through 23:59:59, so the
scheduler time never changes which day owns an order.
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
HISTORY_CHUNKS_PER_CYCLE = 24


def _date_windows(dates: list) -> list[tuple]:
    """Group changed business dates into connector-safe contiguous windows."""
    if not dates:
        return []
    result = []
    start = previous = dates[0]
    for current in dates[1:]:
        if (current - previous).days != 1 or (current - start).days >= 31:
            result.append((start, previous))
            start = current
        previous = current
    result.append((start, previous))
    return result


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
            changed_dates = []
            current_window = None
            if connection_is_due(connection):
                watermark = connection.last_sync_at or (utc_now() - timedelta(minutes=5))
                try:
                    changed_dates = changed_historical_sales_dates(connection, watermark)
                except (DgteraRemoteError, ValueError) as exc:
                    # The current window still runs. The rolling full audit is
                    # the independent safety net for a failed change feed poll.
                    logger.error(
                        "DGTERA changed-order discovery failed",
                        extra={"connection_id": connection.id, "error": str(exc)},
                    )
                start_date, end_date = catchup_window(connection)
                current_window = (start_date, end_date)
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

            # Reconcile every older business date whose Odoo write_date moved,
            # including cancellations. Current-window dates were already read.
            if current_window and changed_dates:
                changed_dates = [
                    value for value in changed_dates
                    if not (current_window[0] <= value <= current_window[1])
                ]
                for changed_start, changed_end in _date_windows(changed_dates):
                    try:
                        sync_connection(
                            db, connection, changed_start, changed_end,
                            connection.created_by, mark_current_sync=False,
                        )
                    except DgteraSyncBusy:
                        break
                    except (DgteraRemoteError, ValueError):
                        logger.exception(
                            "DGTERA changed historical sales reconciliation failed",
                            extra={"connection_id": connection.id, "start": str(changed_start), "end": str(changed_end)},
                        )
                        break
                    except Exception:  # noqa: BLE001 - strict mismatch must not stop the scheduler
                        logger.exception(
                            "Unexpected DGTERA changed-history reconciliation failure",
                            extra={"connection_id": connection.id, "start": str(changed_start), "end": str(changed_end)},
                        )
                        break

            # Drain the complete 2025+ history in bounded 31-day slices during
            # the same background cycle.  Partial totals must not remain on the
            # executive dashboard for twenty separate scheduler polls.
            for _ in range(HISTORY_CHUNKS_PER_CYCLE):
                history_window = historical_backfill_window(db, connection)
                if history_window is None:
                    break
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
                    break
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
                    break
                except Exception:  # noqa: BLE001 - keep the next poll alive
                    logger.exception(
                        "Unexpected DGTERA historical backfill failure",
                        extra={"connection_id": connection.id, "start": str(history_start), "end": str(history_end)},
                    )
                    break

            # Once the initial history is complete, re-read the stalest slice.
            # This catches hard deletions or source anomalies that do not emit a
            # usable write_date change event.
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
