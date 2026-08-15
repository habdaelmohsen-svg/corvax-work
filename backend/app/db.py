from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

if settings.database_url.startswith("sqlite"):
    db_path = settings.database_url.removeprefix("sqlite:///")
    if db_path and db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

database_url = settings.database_url
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {
    "connect_timeout": 10,
    "application_name": "corvax",
}
engine_options = {
    "pool_pre_ping": True,
    "connect_args": connect_args,
}
if not database_url.startswith("sqlite"):
    # Keep a bounded, healthy pool for the API and the single serialized
    # DGTERA worker. Recycle idle managed-PostgreSQL connections before a
    # provider/network lifetime can turn them into random OperationalErrors.
    engine_options.update({
        "pool_size": 5,
        "max_overflow": 5,
        "pool_timeout": 10,
        "pool_recycle": 300,
        "pool_use_lifo": True,
    })
engine = create_engine(database_url, **engine_options)
if database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        """Make local/tests enforce the same CASCADE contracts as PostgreSQL."""
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
