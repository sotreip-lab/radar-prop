"""Mapa de valores, paso 1: reglas de republicación (sin base) y eventos + vínculo (con base)."""
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.services.valuacion.inmuebles import DEFAULTS, Aviso, Inmueble, coincide

AHORA = datetime(2026, 12, 1, 12)
CFG = dict(DEFAULTS)


def aviso(id=1, plataforma="BBP", tipo="Departamento", direccion="Zapiola 1473", dorm=2, m2=60, lat=-38.71, lng=-62.27,
          alta=AHORA - timedelta(days=30), estado="activa", baja=None, precio=100000, moneda="USD", valida=True):
    f = SimpleNamespace(id=id, plataforma=plataforma, tipo=tipo, operacion="Venta", direccion=direccion, dormitorios=dorm,
                        m2_cubiertos=m2, m2_totales=m2, m2_base=m2, lat=lat, lng=lng, ubicacion_valida=valida,
                        estado=estado, fecha_baja=baja, alta=alta, alta_exacta=True, precio=precio, moneda=moneda)
    return Aviso(f, AHORA)


def inmueble_con(*avs):
    inm = Inmueble(100, avs[0])
    inm.avisos.extend(avs)
    return inm


def test_mismo_aviso_en_dos_portales_se_une():
    inm = inmueble_con(aviso(1, "BBP"))
    r = coincide(inm, aviso(2, "IBB", direccion="ZAPIOLA 1473, Centro"), CFG, AHORA)
    assert r and r[0] == "direccion"


def test_mismo_portal_activos_a_la_vez_no_se_une():
    inm = inmueble_con(aviso(1, "BBP"))
    assert coincide(inm, aviso(2, "BBP"), CFG, AHORA) is None


def test_republicacion_en_el_mismo_portal_se_une():
    viejo = aviso(1, "BBP", alta=AHORA - timedelta(days=200), estado="baja", baja=AHORA - timedelta(days=40))
    r = coincide(inmueble_con(viejo), aviso(2, "BBP", alta=AHORA - timedelta(days=10), precio=90000), CFG, AHORA)
    assert r and r[1]["dias_sin_publicar"] == 30


def test_republicacion_muy_tarde_es_otra_venta():
    viejo = aviso(1, "BBP", alta=AHORA - timedelta(days=400), estado="baja", baja=AHORA - timedelta(days=200))
    assert coincide(inmueble_con(viejo), aviso(2, "BBP", alta=AHORA - timedelta(days=5)), CFG, AHORA) is None


def test_m2_distintos_o_dormitorios_distintos_no_se_une():
    inm = inmueble_con(aviso(1))
    assert coincide(inm, aviso(2, "IBB", m2=70), CFG, AHORA) is None
    assert coincide(inm, aviso(2, "IBB", dorm=3), CFG, AHORA) is None
    assert coincide(inm, aviso(2, "IBB", tipo="Casa"), CFG, AHORA) is None


def test_direcciones_distintas_no_se_une_aunque_esten_cerca():
    inm = inmueble_con(aviso(1))
    assert coincide(inm, aviso(2, "IBB", direccion="Zapiola 1475"), CFG, AHORA) is None


def test_sin_numero_usa_distancia_salvo_coordenada_repetida():
    inm = inmueble_con(aviso(1, tipo="Terreno", direccion="Plache", m2=300, dorm=None))
    a = aviso(2, "IBB", tipo="Terreno", direccion="Plache S/N", m2=300, dorm=None, lat=-38.71005)
    assert coincide(inm, a, CFG, AHORA)[0] == "distancia"
    assert coincide(inm, a, CFG, AHORA, frozenset({(-38.71, -62.27)})) is None
    lejos = aviso(3, "IBB", tipo="Terreno", direccion="Plache S/N", m2=300, dorm=None, lat=-38.7110)
    assert coincide(inm, lejos, CFG, AHORA) is None


def test_precio_muy_distinto_a_la_vez_son_dos_unidades():
    inm = inmueble_con(aviso(1, precio=212800))
    assert coincide(inm, aviso(2, "IBB", precio=85000), CFG, AHORA) is None
    # precio de relleno no cuenta como dato
    assert coincide(inm, aviso(2, "IBB", precio=111111111), CFG, AHORA) is not None


# ------------------------------------------------------------------ con base
def test_eventos_y_vinculo_en_la_base(pg_url):
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    from app.services.valuacion import inmuebles as v

    eng = create_engine(pg_url)
    with Session(eng) as db, db.begin():
        ins = text("INSERT INTO propiedades (plataforma, id_externo, tipo, operacion, direccion, dormitorios, m2_cubiertos,"
                   " moneda, precio, estado, fecha_baja, primera_vez_vista, intentos, ubicacion_valida) VALUES "
                   "(:pl, :id, 'Departamento', 'Venta', 'Zapiola 1473', 2, 60, 'USD', :pr, :est, :fb, :pv, 0, false)")
        db.execute(ins, dict(pl="BBP", id="1", pr=100000, est="baja", fb=datetime(2026, 7, 10), pv=datetime(2026, 6, 20)))
        db.execute(ins, dict(pl="IBB", id="a", pr=102000, est="baja", fb=datetime(2026, 7, 11), pv=datetime(2026, 6, 25)))
        db.execute(ins, dict(pl="BBP", id="2", pr=95000, est="activa", fb=None, pv=datetime(2026, 8, 5)))
        db.execute(ins, dict(pl="BBP", id="3", pr=99000, est="activa", fb=None, pv=datetime(2026, 8, 6)))  # otra unidad
        r = v.preparar(db)
    assert r["historico"]["altas"] == 4 and r["historico"]["bajas"] == 2
    assert r["inmuebles_nuevos"] == 2 and r["republicaciones_unidas"] == 2
    with Session(eng) as db:
        inm = db.execute(text("SELECT i.primera_alta, i.avisos_activos, i.ultima_baja, count(*) n FROM inmuebles i "
                              "JOIN inmueble_avisos ia ON ia.inmueble_id = i.id GROUP BY i.id ORDER BY n DESC")).all()
        assert inm[0].n == 3 and inm[0].primera_alta == datetime(2026, 6, 20) and inm[0].avisos_activos == 1
        assert inm[0].ultima_baja is None
        # alta del primer día de seguimiento = aproximada; las siguientes, exactas
        ex = dict(db.execute(text("SELECT p.id_externo, e.exacta FROM eventos_aviso e JOIN propiedades p "
                                  "ON p.id = e.propiedad_id WHERE e.tipo = 'alta'")).all())
        assert ex == {"1": False, "a": True, "2": True, "3": True}
    with Session(eng) as db, db.begin():
        assert v.preparar(db) == {"avisos_nuevos": 0, "inmuebles_nuevos": 0, "republicaciones_unidas": 0}
    eng.dispose()
