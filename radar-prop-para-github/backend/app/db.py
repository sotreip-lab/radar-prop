"""Conexión a PostgreSQL con pool y tiempo máximo por consulta."""
import os
from collections.abc import Iterator

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db_util import engine_para, normalizar_url


def crear_engine(url: str | None = None):
    url = normalizar_url(url or os.environ.get("DATABASE_URL") or settings.database_url)  # la de Supabase viene sin driver
    kw: dict = {}
    if "+psycopg" in url:
        kw["connect_args"] = {"options": f"-c statement_timeout={settings.db_statement_timeout_ms}"}
    return engine_para(url, pool_size=settings.db_pool_size, max_overflow=settings.db_max_overflow,
                       pool_pre_ping=True, pool_timeout=10, **kw)


engine = crear_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
