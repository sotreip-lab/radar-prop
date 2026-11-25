"""Solicitudes de acceso: cualquiera puede pedir un usuario y queda pendiente hasta que un admin lo apruebe.

Revision ID: 0003_solicitudes
Revises: 0002_fichas_html
"""
import sqlalchemy as sa
from alembic import op

revision = "0003_solicitudes"
down_revision = "0002_fichas_html"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("usuarios", sa.Column("solicitud_pendiente", sa.Boolean, nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("usuarios", "solicitud_pendiente")
