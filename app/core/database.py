from typing import Generator
from sqlmodel import Session, create_engine
from app.core.config import get_settings

settings = get_settings()

# Check database protocol for SQLite sync issues
connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.database_url, connect_args=connect_args)

def get_db() -> Generator[Session, None, None]:
    """Yield a database session (dependency injection)."""
    with Session(engine) as session:
        yield session
