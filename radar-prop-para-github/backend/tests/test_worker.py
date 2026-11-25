"""Worker contra un sitio falso y una base PostgreSQL real."""
import os
from datetime import datetime

import pytest
from sqlalchemy import create_engine, text

from tests import sitio_falso as sf


@pytest.fixture()
def sitio(monkeypatch):
    estado_original = {k: (dict(v) if isinstance(v, dict) else set(v) if isinstance(v, set) else list(v))
                       for k, v in sf.ESTADO.items()}
    srv, base = sf.arrancar()
    monkeypatch.setenv("RADAR_SITIO_BBP", base + "/bbp")
    monkeypatch.setenv("RADAR_SITIO_IBB", base + "/ibb")
    from worker import actualizar as w
    monkeypatch.setitem(w.CFG, "sitemap_minimo", 1)
    monkeypatch.setitem(w.CFG, "ibb_minimo", 1)
    monkeypatch.setitem(w.CFG, "pausa_seg", 0)
    yield base
    srv.shutdown()
    sf.ESTADO.clear()
    sf.ESTADO.update(estado_original)


def _sembrar(url):
    """Lo que ya estaba en la base (como quedó después de la migración)."""
    eng = create_engine(url)
    with eng.begin() as c:
        c.execute(text("""
            INSERT INTO propiedades (plataforma, id_externo, id_legado, url, titulo, tipo, operacion, ciudad, moneda,
                precio, estado, intentos, datos_extra, ubicacion_valida, primera_vez_vista, ultima_vez_vista)
            VALUES
            ('BBP','95001',95001,'u','Casa en Venta en Zapiola 1473, Palihue, Bahía Blanca','Casa','Venta','Bahía Blanca',
             'USD',165000,'activa',0,'{}',false,'2026-11-01','2026-11-20'),
            ('BBP','94000',94000,'u','Casa vieja','Casa','Venta','Bahía Blanca','USD',80000,'activa',0,'{}',false,
             '2026-10-01','2026-11-20'),
            ('BBP','93000',93000,'u','Casa planilla','Casa','Venta','Bahía Blanca','USD',70000,'pendiente',0,'{}',false,
             '2026-10-01',NULL)
        """))
        c.execute(text("INSERT INTO meta (clave, valor) VALUES ('ultima_revision_sitemap', '2026-11-25 10:00:00')"))
    eng.dispose()


def _filas(url, sql, **kw):
    eng = create_engine(url)
    with eng.connect() as c:
        r = c.execute(text(sql), kw).mappings().all()
    eng.dispose()
    return r


def test_corrida_completa_contra_sitio_falso(pg_url, sitio):
    from worker.actualizar import correr
    _sembrar(pg_url)
    r = correr(pg_url, solo=("bbp", "ibb"))
    assert r["estado"] == "ok", r
    assert r["bbp"] == {"en_sitio": 3, "nuevas": 2, "reactivar": 0, "posibles_bajas": 1}

    props = {p["id_externo"]: p for p in _filas(pg_url, "SELECT * FROM propiedades")}
    # nueva detectada: ventana exacta desde la revisión anterior hasta ahora, con fotos y fecha de las fotos
    n = props["95002"]
    assert n["estado"] == "activa" and n["precio"] == 120000 and n["moneda"] == "USD"
    assert n["publicada_desde"] == datetime(2026, 11, 25, 10, 0)
    assert n["publicada_hasta"] is not None and n["fecha_publicacion"] == n["publicada_hasta"]
    assert n["pub_aprox"] == datetime(2026, 11, 23, 10, 0)  # Last-Modified 13:00 GMT = 10:00 en Bahía Blanca
    assert len(n["fotos"]) == 2 and n["ubicacion_valida"] is True
    assert n["m2_cubiertos"] == 120 and n["dormitorios"] == 3 and n["amoblado"] == "Amoblado"
    assert n["datos_extra"]["dorm_fuente"] == "ficha" and n["id_legado"] is None
    # alquiler en pesos: precio_ars igual al precio, sin convertir
    assert props["95003"]["precio_ars"] == 450000
    # cambio de precio: queda el anterior y una fila en el historial; los datos viejos se conservan
    v = props["95001"]
    assert v["precio"] == 158000 and v["precio_anterior"] == 165000 and v["cambio_precio"] is not None
    assert v["id_legado"] == 95001 and v["publicada_desde"] is None
    hist = _filas(pg_url, "SELECT * FROM historial_precios")
    assert [(h["precio_anterior"], h["precio"]) for h in hist] == [(165000, 158000)]
    # no figura en el sitemap y la ficha da 404: baja confirmada
    assert props["94000"]["estado"] == "baja" and props["94000"]["fecha_baja"] is not None
    assert props["93000"]["estado"] == "baja"

    # IBB: los dos avisos entran; el apto crédito sale del filtro oficial del sitio
    casa = props["casa-en-venta-3-dormitorios-en-zapiola-1473"]
    assert casa["plataforma"] == "IBB" and casa["operacion"] == "Venta" and casa["apto_credito"] == "Sí"
    assert casa["barrio"] == "Palihue" and casa["pub_txt"] == "Publicado hace 3 días"
    assert casa["publicada_desde"] is None  # primera lectura de IBB: no hay ventana anterior, no se inventa
    alq = props["departamento-en-alquiler-en-soler-111"]
    assert alq["operacion"] == "Alquiler" and alq["moneda"] == "ARS"

    corrida = _filas(pg_url, "SELECT * FROM corridas_actualizacion")[0]
    assert corrida["estado"] == "ok" and corrida["nuevas"] == 4 and corrida["bajas"] == 1 and corrida["fin"]
    meta = {m["clave"]: m["valor"] for m in _filas(pg_url, "SELECT clave, valor FROM meta")}
    assert meta["ultima_revision_sitemap"] > "2026-11-25 10:00:00" and "ibb_ultima_revision" in meta


def test_segunda_corrida_detecta_bajas_y_vueltas(pg_url, sitio):
    from worker.actualizar import correr
    _sembrar(pg_url)
    correr(pg_url, solo=("bbp", "ibb"))
    del sf.ESTADO["bbp"]["95003"]
    sf.ESTADO["bbp"]["95004"] = ("U$S 99.000", "PH en Venta en Alem 10, Centro, Bahía Blanca", "INMO TRES")
    del sf.ESTADO["ibb"]["departamento-en-alquiler-en-soler-111"]
    r = correr(pg_url, solo=("bbp", "ibb"))
    assert r["estado"] == "ok" and r["nuevas"] == 1 and r["bajas"] == 2
    props = {p["id_externo"]: p for p in _filas(pg_url, "SELECT id_externo, estado, publicada_desde FROM propiedades")}
    assert props["95003"]["estado"] == "baja"
    assert props["departamento-en-alquiler-en-soler-111"]["estado"] == "baja"
    assert props["95004"]["estado"] == "activa" and props["95004"]["publicada_desde"] > datetime(2026, 11, 25, 10, 0)
    # vuelve a publicarse
    sf.ESTADO["bbp"]["95003"] = ("$ 470.000", "Departamento en Alquiler en Caronti 190 2ºE, Centro, Bahía Blanca", "X")
    correr(pg_url, solo=("bbp",))
    assert _filas(pg_url, "SELECT estado, fecha_baja FROM propiedades WHERE id_externo='95003'")[0] == {
        "estado": "activa", "fecha_baja": None}


def test_ibb_406_sin_cabecera_y_errores_de_red_no_rompen(pg_url, sitio, monkeypatch):
    """Si un sitio no responde, se registra el error y la corrida sigue con el otro."""
    from worker.actualizar import correr
    monkeypatch.setenv("RADAR_SITIO_IBB", "http://127.0.0.1:9")  # puerto cerrado
    r = correr(pg_url, solo=("bbp", "ibb"))
    assert r["estado"] == "ok" and r["errores"] == 1 and r["nuevas"] == 3
    det = _filas(pg_url, "SELECT detalle FROM corridas_actualizacion")[0]["detalle"]
    assert any("IBB: no se pudo leer el listado" in a for a in det["avisos"])


def test_otra_corrida_activa_no_toca_nada(pg_url, sitio):
    from worker.actualizar import CANDADO, correr
    eng = create_engine(pg_url)
    with eng.connect() as c:
        c.execute(text("SELECT pg_advisory_lock(:k)"), {"k": CANDADO})
        assert correr(pg_url, solo=("bbp",)) == {"estado": "salteada"}
        c.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": CANDADO})
    eng.dispose()
    assert _filas(pg_url, "SELECT COUNT(*) AS n FROM corridas_actualizacion")[0]["n"] == 0


def test_sin_tiempo_queda_parcial_y_la_ventana_no_avanza(pg_url, sitio):
    from worker.actualizar import correr
    _sembrar(pg_url)
    r = correr(pg_url, max_minutos=0, solo=("bbp",))
    assert r["estado"] == "parcial" and r["nuevas"] == 0
    meta = {m["clave"]: m["valor"] for m in _filas(pg_url, "SELECT clave, valor FROM meta")}
    assert meta["ultima_revision_sitemap"] == "2026-11-25 10:00:00"  # la próxima corrida usa la misma ventana


def test_url_de_supabase_se_pasa_a_psycopg():
    from worker.actualizar import url_psycopg
    assert url_psycopg("postgresql://u:p@h:5432/postgres") == "postgresql+psycopg://u:p@h:5432/postgres"
    assert url_psycopg("postgresql+pg8000://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert os.environ.get("DATABASE_URL")  # los tests nunca usan una base real por error
