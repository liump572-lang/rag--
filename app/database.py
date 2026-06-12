import time

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

engine = create_engine(
    settings.database_url,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def wait_for_database(timeout_seconds: int = 60, interval_seconds: float = 2.0) -> None:
    """Wait until the database accepts connections during container startup."""
    deadline = time.monotonic() + timeout_seconds
    last_error: OperationalError | None = None

    while time.monotonic() < deadline:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return
        except OperationalError as exc:
            last_error = exc
            time.sleep(interval_seconds)

    if last_error is not None:
        raise last_error


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
