"""Migraciones de Alembic. La URL de la base sale de DATABASE_URL (nunca del código)."""
import os
from logging.config import fileConfig

from geoalchemy2 import alembic_helpers
from sqlalchemy import pool

from alembic import context
from app.db_util import engine_para
from app.models import Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def _url():
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    from app.core.config import settings  # solo si no vino por variable de entorno
    return settings.database_url


URL = _url()


def run_migrations_offline():
    context.configure(url=URL, target_metadata=target_metadata, literal_binds=True,
                      include_object=alembic_helpers.include_object,
                      process_revision_directives=alembic_helpers.writer,
                      render_item=alembic_helpers.render_item)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    engine = engine_para(URL, verificar_certificado=os.environ.get("RADAR_SSL_SIN_VERIFICAR") != "1",
                         poolclass=pool.NullPool)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata,
                          include_object=alembic_helpers.include_object,
                          process_revision_directives=alembic_helpers.writer,
                          render_item=alembic_helpers.render_item)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
