"""SQLAlchemy engine and session factory for Flouria"""

import os
from urllib.parse import quote_plus
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _database_url() -> str:
    """
    Resolve the database URL.

    Preference order:
      1. DATABASE_URL, if set (any full SQLAlchemy URL).
      2. Built from the same POSTGRES_* variables the db container uses
         (.env), so there's one source of truth and the password is
         URL-encoded here instead of hand-escaped in compose/ini files.
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        user = os.environ.get("POSTGRES_USER", "postgres")
        password = os.environ.get("POSTGRES_PASSWORD", "")
        host = os.environ.get("POSTGRES_HOST", "localhost")
        port = os.environ.get("POSTGRES_PORT", "5432")
        name = os.environ.get("POSTGRES_DB", "postgres")
        auth = f"{user}:{quote_plus(password)}" if password else user
        url = f"postgresql://{auth}@{host}:{port}/{name}"

    # Newer SQLAlchemy releases resolve a bare "postgresql://" to the psycopg
    # (v3) driver; we install psycopg2-binary, so name the driver explicitly.
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


DATABASE_URL = _database_url()
SQL_ECHO = os.environ.get("SQL_ECHO", "0") == "1"

engine = create_engine(DATABASE_URL, echo=SQL_ECHO, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency: one session per request, always closed"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
