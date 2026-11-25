"""Migración SQLite (El Ojo de Dios) -> PostgreSQL (Radar Prop) sobre una base chica armada en el test,
con el mismo esquema que propiedades.db y cambios todavía sin consolidar en el archivo -wal."""
import json
import os
import shutil
import sqlite3

import pytest
from migrar_sqlite_a_postgres import migrar
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

ESQUEMA = """
CREATE TABLE props(id INTEGER PRIMARY KEY, titulo TEXT, tipo TEXT, operacion TEXT, direccion TEXT, barrio TEXT,
  ciudad TEXT, inmobiliaria TEXT, moneda TEXT, precio REAL, dormitorios INTEGER, dorm_fuente TEXT, banos INTEGER,
  sup_cub REAL, sup_tot REAL, antiguedad TEXT, estado TEXT, patio TEXT, cochera TEXT, apto_credito TEXT, pileta TEXT,
  parrilla TEXT, detalles TEXT, descripcion TEXT, estado_aviso TEXT DEFAULT 'pendiente', alta TEXT, ultima_verif TEXT,
  precio_anterior REAL, cambio_precio TEXT, intentos INTEGER DEFAULT 0, detectada TEXT, detectada_desde TEXT,
  fecha_baja TEXT, ia_json TEXT, ia_resumen TEXT, ia_fecha TEXT, ia_intentos INTEGER, exterior TEXT,
  estacionamiento TEXT, pago TEXT, expensas TEXT, m2_base REAL, lat REAL, lng REAL, fuente TEXT DEFAULT 'BBP',
  url TEXT, pub_txt TEXT, pub_aprox TEXT, amoblado TEXT);
CREATE TABLE historial(id INTEGER, fecha TEXT, moneda TEXT, antes REAL, despues REAL);
CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE pedidos(id INTEGER PRIMARY KEY AUTOINCREMENT, datos TEXT, creado TEXT, visto_hasta TEXT, activo INTEGER DEFAULT 1);
"""
COLS = ("id, titulo, tipo, operacion, direccion, barrio, ciudad, inmobiliaria, moneda, precio, dormitorios, "
        "estado_aviso, alta, ultima_verif, detectada, detectada_desde, fecha_baja, pub_aprox, pub_txt, lat, lng, "
        "fuente, url, detalles")


def _fila(**k):
    base = dict(titulo="Casa en Venta en Centro", tipo="Casa", operacion="Venta", direccion="Zapiola 1473",
                barrio="Centro", ciudad="Bahía Blanca", inmobiliaria="Inmo X", moneda="USD", precio=160000,
                dormitorios=3, estado_aviso="activo", alta="2026-11-21", ultima_verif="2026-11-24 10:00:00",
                detectada=None, detectada_desde=None, fecha_baja=None, pub_aprox=None, pub_txt=None,
                lat=-38.7183, lng=-62.2663, fuente="BBP", url=None, detalles='{"Dormitorios": "3 Dormitorios"}')
    base.update(k)
    return tuple(base[c.strip()] if c.strip() != "id" else k["id"] for c in COLS.split(","))


@pytest.fixture()
def sqlite_ojo(tmp_path):
    ruta = str(tmp_path / "propiedades.db")
    con = sqlite3.connect(ruta)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(ESQUEMA)
    filas = [
        # BBP y ZP con el MISMO número: no se pueden mezclar
        _fila(id=60773311, detectada_desde="2026-11-24 10:00:00", detectada="2026-11-24 10:15:00"),
        _fila(id=1000000001, fuente="ZP", url="https://www.zonaprop.com.ar/propiedades/-60773311.html",
              precio=95000, moneda="USD", pub_aprox="2025-03-10 08:00:00"),
        _fila(id=1000000002, fuente="IBB", url="https://ibb.com.ar/listings/casa-en-venta-3-dormitorios-en-zapiola-1473",
              pub_txt="Publicado hace 3 meses", operacion="Alquiler", moneda="ARS", precio=650000),
        # baja con fecha real, baja de planilla, coordenada (0,0)
        _fila(id=500, estado_aviso="baja", fecha_baja="2026-11-23 18:00:00"),
        _fila(id=501, estado_aviso="baja", fecha_baja="2026-11-21 (planilla)", ultima_verif="2026-11-21 (planilla)"),
        _fila(id=502, lat=0.0, lng=0.0, fuente="", detalles="esto no es json"),
    ]
    # 13 avisos en el mismo punto genérico del portal
    filas += [_fila(id=1000 + i, lat=-38.7118, lng=-62.2521) for i in range(13)]
    con.executemany(f"INSERT INTO props({COLS}) VALUES({','.join('?' * len(COLS.split(',')))})", filas)
    con.executemany("INSERT INTO historial VALUES(?,?,?,?,?)",
                    [(60773311, "2026-11-22 09:00:00", "USD", 170000, 165000),
                     (60773311, "2026-11-24 09:00:00", "USD", 165000, 160000)])
    con.executemany("INSERT INTO meta VALUES(?,?)", [
        ("dolar", json.dumps({"valor": 1695.1, "tipo": "Bolsa", "fecha": "2026-11-24T21:02:00.000Z"})),
        ("inicio_base", "2026-11-21 02:54:30")])
    con.execute("INSERT INTO pedidos(datos, creado, visto_hasta, activo) VALUES(?,?,?,1)",
                (json.dumps({"nombre": "Silvia", "telefono": "2915", "presu": 160000, "moneda": "USD", "texto": "casa 3 dorm"}),
                 "2026-11-23 10:00:00", "2026-11-24 09:00:00"))
    con.commit()
    # se copia con la conexión abierta: los últimos cambios siguen en el -wal, sin consolidar
    destino = str(tmp_path / "copia")
    os.makedirs(destino)
    for suf in ("", "-wal", "-shm"):
        if os.path.exists(ruta + suf):
            shutil.copy2(ruta + suf, os.path.join(destino, "propiedades.db" + suf))
    con.close()
    return os.path.join(destino, "propiedades.db")


def test_conteos_coinciden_e_idempotente(pg_url, sqlite_ojo):
    tam_wal = os.path.getsize(sqlite_ojo + "-wal") if os.path.exists(sqlite_ojo + "-wal") else 0
    r1 = migrar(sqlite_ojo, pg_url, silencioso=True)
    assert r1["ok"], r1
    assert r1["destino"]["props"] == 19 and r1["destino"]["historial"] == 2 and r1["destino"]["pedidos"] == 1
    # el original no se tocó (el checkpoint se hizo sobre una copia)
    assert (os.path.getsize(sqlite_ojo + "-wal") if os.path.exists(sqlite_ojo + "-wal") else 0) == tam_wal
    r2 = migrar(sqlite_ojo, pg_url, silencioso=True)  # segunda corrida: nada duplicado
    assert r2["ok"] and r2["destino"] == r1["destino"]


def test_mismo_numero_distinta_plataforma_quedan_separados(pg_url, sqlite_ojo):
    migrar(sqlite_ojo, pg_url, silencioso=True)
    with create_engine(pg_url).connect() as c:
        filas = c.execute(text("SELECT plataforma, id_externo, id_legado, precio FROM propiedades "
                               "WHERE id_externo='60773311' ORDER BY plataforma")).all()
    assert [(f[0], f[2], float(f[3])) for f in filas] == [("BBP", 60773311, 160000.0), ("ZP", 1000000001, 95000.0)]


def test_publicacion_bajas_ubicacion_y_extras(pg_url, sqlite_ojo):
    migrar(sqlite_ojo, pg_url, silencioso=True)
    with create_engine(pg_url).connect() as c:
        q = lambda sql: c.execute(text(sql)).mappings().one()  # noqa: E731
        p = q("SELECT publicada_desde, publicada_hasta, pub_aprox FROM propiedades WHERE id_legado=60773311")
        assert str(p["publicada_desde"]) == "2026-11-24 10:00:00" and str(p["publicada_hasta"]) == "2026-11-24 10:15:00"
        assert q("SELECT pub_txt FROM propiedades WHERE plataforma='IBB'")["pub_txt"] == "Publicado hace 3 meses"
        z = q("SELECT pub_aprox, fecha_publicacion FROM propiedades WHERE plataforma='ZP'")
        assert str(z["pub_aprox"]) == "2025-03-10 08:00:00"
        assert q("SELECT precio_ars FROM propiedades WHERE plataforma='IBB'")["precio_ars"] == 650000
        b = q("SELECT estado, fecha_baja, fecha_baja_origen FROM propiedades WHERE id_legado=501")
        assert b["estado"] == "baja" and str(b["fecha_baja"]) == "2026-11-21 00:00:00" and b["fecha_baja_origen"] == "planilla"
        cero = q("SELECT ubicacion_valida, ubicacion IS NULL AS sin_punto, lat, datos_extra FROM propiedades WHERE id_legado=502")
        assert cero["ubicacion_valida"] is False and cero["sin_punto"] and float(cero["lat"]) == 0.0
        assert cero["datos_extra"]["detalles_texto"] == "esto no es json"  # no se pierde
        gen = q("SELECT COUNT(*) AS n, bool_and(NOT ubicacion_valida) AS todas FROM propiedades WHERE id_legado BETWEEN 1000 AND 1012")
        assert gen["n"] == 13 and gen["todas"]
        ok = q("SELECT ST_Y(ubicacion::geometry) AS lat FROM propiedades WHERE id_legado=60773311")
        assert abs(ok["lat"] + 38.7183) < 1e-6
        h = c.execute(text("SELECT fecha, precio_anterior, precio FROM historial_precios ORDER BY fecha")).all()
        assert [(float(a), float(b)) for _, a, b in h] == [(170000, 165000), (165000, 160000)]
        dolar = json.loads(c.execute(text("SELECT valor FROM meta WHERE clave='dolar'")).scalar())
        assert dolar["valor"] == 1695.1 and dolar["tipo"] == "Bolsa"
        cli = q("SELECT nombre, presupuesto, moneda, pedido FROM clientes")
        assert (cli["nombre"], float(cli["presupuesto"]), cli["moneda"], cli["pedido"]) == ("Silvia", 160000.0, "USD", "casa 3 dorm")


def test_unique_impide_duplicar(pg_url, sqlite_ojo):
    migrar(sqlite_ojo, pg_url, silencioso=True)
    with create_engine(pg_url).begin() as c, pytest.raises(IntegrityError):
        c.execute(text("INSERT INTO propiedades(plataforma, id_externo, estado, ubicacion_valida, intentos) "
                       "VALUES('BBP','60773311','activa',false,0)"))
