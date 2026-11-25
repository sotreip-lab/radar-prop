"""Página guardada de cada ficha para el cliente (link secreto) e índices del historial.

Revision ID: 0002_fichas_html
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002_fichas_html"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "fichas_html",
        sa.Column("ficha_id", sa.BigInteger, sa.ForeignKey("fichas_generadas.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("token", sa.String(60), nullable=False, unique=True),
        sa.Column("cliente", sa.String(160), nullable=False, server_default=""),
        sa.Column("html", sa.Text, nullable=False),
        sa.Column("creada_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_busquedas_user_fecha", "busquedas", ["user_id", "creada_en"])
    op.create_index("ix_fichas_user_fecha", "fichas_generadas", ["user_id", "creada_en"])


def downgrade():
    op.drop_index("ix_fichas_user_fecha", "fichas_generadas")
    op.drop_index("ix_busquedas_user_fecha", "busquedas")
    op.drop_table("fichas_html")
