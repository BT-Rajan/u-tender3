from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

settings = get_settings()

# READ COMMITTED: a request sees rows committed by other requests after it started.
# MySQL's default REPEATABLE READ would keep a stale snapshot for the length of a session.
engine = create_engine(settings.database_url, pool_pre_ping=True, isolation_level="READ COMMITTED")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Every MySQL session runs in UTC, the same zone the app stores times in. Server-side timestamps
# (created_at defaults) were otherwise written in the database server's local zone and read back as UTC.
from sqlalchemy import event as _event  # noqa: E402
from sqlalchemy.engine import Engine as _Engine  # noqa: E402


@_event.listens_for(_Engine, "connect")
def _use_utc_session(dbapi_connection, _record) -> None:
    if type(dbapi_connection).__module__.startswith("pymysql"):
        cursor = dbapi_connection.cursor()
        cursor.execute("SET time_zone = '+00:00'")
        cursor.close()
