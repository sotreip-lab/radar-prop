"""Criterio de aceptación de la Fase 1 sobre los datos reales: 20 propiedades al azar por plataforma tienen los
mismos datos en El Ojo de Dios y en Radar Prop. Se corre solo si se indican las dos bases:
    RADAR_SQLITE_REAL=ruta/propiedades.db  RADAR_PG_REAL=postgresql+psycopg://...  pytest tests/test_muestra_real.py
"""
import json
import os
import random
import shutil
import sqlite3
import tempfile
from decimal import Decimal

import pytest
from migrar_sqlite_a_postgres import MAPEO_DIRECTO, copia_con_checkpoint, fecha
from sqlalchemy import create_engine, text

SQLITE = os.environ.get("RADAR_SQLITE_REAL")
PG = os.environ.get("RADAR_PG_REAL")
pytestmark = pytest.mark.skipif(not (SQLITE and PG), reason="faltan RADAR_SQLITE_REAL y RADAR_PG_REAL")

FECHAS = {"detectada": "publicada_hasta", "detectada_desde": "publicada_desde", "pub_aprox": "pub_aprox",
          "alta": "primera_vez_vista", "fecha_baja": "fecha_baja", "cambio_precio": "cambio_precio",
          "ultima_verif": "ultima_vez_vista"}
NUMEROS = {"precio": "precio", "precio_anterior": "precio_anterior", "sup_cub": "m2_cubiertos",
           "sup_tot": "m2_totales", "m2_base": "m2_base", "lat": "lat", "lng": "lng"}


@pytest.fixture(scope="module")
def bases():
    tmp = tempfile.mkdtemp()
    src = sqlite3.connect(copia_con_checkpoint(SQLITE, tmp))
    src.row_factory = sqlite3.Row
    eng = create_engine(PG)
    yield src, eng
    src.close()
    eng.dispose()
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.mark.parametrize("plataforma", ["BBP", "IBB", "ZP"])
def test_20_al_azar_iguales(bases, plataforma):
    src, eng = bases
    ids = [r[0] for r in src.execute("SELECT id FROM props WHERE COALESCE(NULLIF(fuente,''),'BBP')=?", (plataforma,))]
    muestra = random.Random(2026).sample(ids, min(20, len(ids)))
    distintos = []
    with eng.connect() as pg:
        for pid in muestra:
            a = src.execute("SELECT * FROM props WHERE id=?", (pid,)).fetchone()
            b = pg.execute(text("SELECT * FROM propiedades WHERE id_legado=:i"), {"i": pid}).mappings().one()
            assert b["plataforma"] == plataforma
            for viejo, nuevo in MAPEO_DIRECTO.items():
                if a[viejo] != b[nuevo]:
                    distintos.append((pid, viejo, a[viejo], b[nuevo]))
            for viejo, nuevo in NUMEROS.items():
                va = None if a[viejo] is None else Decimal(str(a[viejo]))
                vb = b[nuevo]
                if (va is None) != (vb is None) or (va is not None and abs(va - Decimal(vb)) > Decimal("0.0001")):
                    distintos.append((pid, viejo, a[viejo], vb))
            for viejo, nuevo in FECHAS.items():
                if fecha(a[viejo])[0] != b[nuevo]:
                    distintos.append((pid, viejo, a[viejo], b[nuevo]))
            estado = {"activo": "activa", "baja": "baja"}.get(a["estado_aviso"], a["estado_aviso"])
            if estado != b["estado"]:
                distintos.append((pid, "estado_aviso", a["estado_aviso"], b["estado"]))
            if a["detalles"] and json.loads(a["detalles"]) != b["detalles"]:
                distintos.append((pid, "detalles", "...", "..."))
    assert not distintos, distintos[:10]


def test_historial_y_dolar_iguales(bases):
    src, eng = bases
    with eng.connect() as pg:
        viejo = sorted((i, f, round(a, 2), round(d, 2)) for i, f, _, a, d in src.execute("SELECT * FROM historial"))
        nuevo = sorted((li, f.strftime("%Y-%m-%d %H:%M:%S"), round(float(a), 2), round(float(d), 2)) for li, f, a, d in pg.execute(text(
            "SELECT p.id_legado, h.fecha, h.precio_anterior, h.precio FROM historial_precios h "
            "JOIN propiedades p ON p.id=h.propiedad_id")))
        assert viejo == nuevo
        assert src.execute("SELECT v FROM meta WHERE k='dolar'").fetchone()[0] == pg.execute(
            text("SELECT valor FROM meta WHERE clave='dolar'")).scalar()
