"""Mapa de valores, paso 1: inmuebles (un mismo inmueble aunque se republique o esté en varios portales),
vínculo aviso -> inmueble, eventos con fecha exacta y umbrales editables.

Revision ID: 0004_inmuebles
Revises: 0003_solicitudes
"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0004_inmuebles"
down_revision = "0003_solicitudes"
branch_labels = None
depends_on = None

# meses = días / 30. VERDE: se dio de baja en <= verde; ROJO: sigue activa o se dio de baja después de rojo.
UMBRALES = [
    ("verde_meses.Departamento", 3, "Depto/Dúplex: verde si se dio de baja en hasta estos meses"),
    ("rojo_meses.Departamento", 5, "Depto/Dúplex: rojo si pasa estos meses"),
    ("verde_meses.Casa", 4, "Casa: verde si se dio de baja en hasta estos meses"),
    ("rojo_meses.Casa", 5, "Casa: rojo si pasa estos meses"),
    ("verde_meses.Terreno", 8, "Terreno: verde si se dio de baja en hasta estos meses"),
    ("rojo_meses.Terreno", 10, "Terreno: rojo si pasa estos meses"),
    ("verde_meses.Galpón", 5, "Galpón: verde si se dio de baja en hasta estos meses"),
    ("rojo_meses.Galpón", 8, "Galpón: rojo si pasa estos meses"),
    ("republicacion_max_dias", 120, "Si un aviso vuelve a aparecer dentro de estos días es el mismo inmueble"),
    ("republicacion_metros", 30, "Distancia máxima entre avisos del mismo inmueble"),
    ("republicacion_m2_pct", 5, "Diferencia máxima de m² (%) entre avisos del mismo inmueble"),
    ("republicacion_precio_pct_simultaneo", 15, "Diferencia máxima de precio (%) si están publicados a la vez"),
    ("republicacion_precio_pct", 30, "Diferencia máxima de precio (%) en una republicación"),
]


def upgrade():
    op.create_table(
        "inmuebles",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("grupo_tipo", sa.String(40), nullable=False),
        sa.Column("operacion", sa.String(40), nullable=False),
        sa.Column("dir_clave", sa.String(200), nullable=False, server_default=""),
        sa.Column("dormitorios", sa.Integer),
        sa.Column("m2", sa.Numeric(14, 2)),
        sa.Column("lat", sa.Numeric(10, 7)),
        sa.Column("lng", sa.Numeric(10, 7)),
        sa.Column("primera_alta", sa.DateTime),
        sa.Column("primera_alta_exacta", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("ultima_baja", sa.DateTime),          # vacío mientras quede algún aviso activo
        sa.Column("avisos_activos", sa.Integer, nullable=False, server_default="0"),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_inmuebles_busqueda", "inmuebles", ["operacion", "grupo_tipo"])
    op.create_index("ix_inmuebles_dir", "inmuebles", ["dir_clave"])

    op.create_table(
        "inmueble_avisos",
        sa.Column("propiedad_id", sa.BigInteger, sa.ForeignKey("propiedades.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("inmueble_id", sa.BigInteger, sa.ForeignKey("inmuebles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("regla", sa.String(40), nullable=False),   # nuevo | direccion | distancia
        sa.Column("detalle", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("vinculado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_inmueble_avisos_inmueble", "inmueble_avisos", ["inmueble_id"])

    op.create_table(
        "eventos_aviso",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("propiedad_id", sa.BigInteger, sa.ForeignKey("propiedades.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),   # alta | baja | reaparece | precio
        sa.Column("fecha", sa.DateTime, nullable=False),
        sa.Column("exacta", sa.Boolean, nullable=False, server_default=sa.true()),  # false = reconstruida/aproximada
        sa.Column("moneda", sa.String(5)),
        sa.Column("precio", sa.Numeric(16, 2)),
        sa.Column("precio_anterior", sa.Numeric(16, 2)),
        sa.Column("origen", sa.String(20), nullable=False, server_default="corrida"),  # corrida | historico
        sa.UniqueConstraint("propiedad_id", "tipo", "fecha", name="uq_evento_aviso"),
    )
    op.create_index("ix_eventos_aviso_prop", "eventos_aviso", ["propiedad_id", "fecha"])
    op.create_index("ix_eventos_aviso_fecha", "eventos_aviso", ["tipo", "fecha"])

    t = op.create_table(
        "config_umbrales",
        sa.Column("clave", sa.String(60), primary_key=True),
        sa.Column("valor", sa.Numeric(10, 2), nullable=False),
        sa.Column("descripcion", sa.Text, nullable=False, server_default=""),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("actualizado_por", sa.Integer, sa.ForeignKey("usuarios.id", ondelete="SET NULL")),
    )
    op.bulk_insert(t, [{"clave": c, "valor": v, "descripcion": d} for c, v, d in UMBRALES])


def downgrade():
    op.drop_table("config_umbrales")
    op.drop_table("eventos_aviso")
    op.drop_table("inmueble_avisos")
    op.drop_table("inmuebles")
