from __future__ import annotations

import argparse
import logging
import os
import socket
import time

from app.core.observability import configure_logging
from app.db import SessionLocal
from app.models import BackgroundJob
from app.services.mrp import claim_next_mrp_job, execute_claimed_mrp_job

logger = logging.getLogger("corvax.worker.mrp")


def run_once(worker_id: str) -> bool:
    with SessionLocal() as db:
        job = claim_next_mrp_job(db, worker_id=worker_id)
        if job is None:
            db.rollback()
            return False
        job_id = job.id
        db.commit()
    with SessionLocal() as db:
        job = db.get(BackgroundJob, job_id)
        if job is None:
            return False
        execute_claimed_mrp_job(db, job, worker_id=worker_id)
        logger.info("mrp_job_completed", extra={"job_id": job_id, "worker_id": worker_id})
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description="CORVAX durable MRP background worker")
    parser.add_argument("--once", action="store_true", help="Process at most one job and exit")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()
    configure_logging()
    worker_id = os.getenv("WORKER_ID") or f"{socket.gethostname()}:{os.getpid()}"
    while True:
        try:
            worked = run_once(worker_id)
        except Exception:
            logger.exception("mrp_job_failed", extra={"worker_id": worker_id})
            worked = True
        if args.once:
            break
        if not worked:
            time.sleep(max(0.2, args.poll_seconds))


if __name__ == "__main__":
    main()
