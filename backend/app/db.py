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
