"""Búsqueda, semáforo (borde ±5.000), zona del mapa, historial por usuario, bloqueo optimista e idempotencia."""
from sqlalchemy import create_engine, text

from tests.conftest import nuevo_cliente


def _sembrar(url):
    eng = create_engine(url)
    filas = [
        # (id_externo, tipo, precio, dormitorios, barrio, lat, lng, publicada_hasta, direccion)
        ("1001", "Casa", 155000, 3, "Centro", -38.7183, -62.2663, "2026-11-25 10:00:00", "Zapiola 100"),
        ("1002", "Casa", 165000, 3, "Centro", -38.7190, -62.2670, None, "Zapiola 200"),
        ("1003", "Casa", 165001, 3, "Centro", -38.7300, -62.2900, None, "Zapiola 300"),
        ("1004", "Casa", 154999, 2, "Palihue", -38.6900, -62.2300, None, "Alem 10"),
        ("1005", "Departamento", 170000, 2, "Centro", None, None, None, "Alem 20"),
        ("1006", "Casa", 171200, 3, "Centro", -38.7185, -62.2665, None, "Alem 30"),
        ("1007", "Casa", 184000, 3, "Centro", -38.7185, -62.2665, None, "Alem 40"),
        ("1008", "Casa", 111111111, 3, "Centro", -38.7185, -62.2665, None, "Alem 50"),
    ]
    with eng.begin() as c:
        for ide, tipo, precio, dorm, barrio, lat, lng, pub, dire in filas:
            c.execute(text("""
                INSERT INTO propiedades (plataforma, id_externo, url, titulo, tipo, operacion, ciudad, barrio, direccion, moneda,
                  precio, dormitorios, estado, intentos, datos_extra, ubicacion_valida, ubicacion, lat, lng, publicada_hasta,
                  publicada_desde, primera_vez_vista, inmobiliaria, m2_base)
                VALUES ('BBP', :i, :url, :tit, :t, 'Venta', 'Bahía Blanca', :b, :d, 'USD', :p, :dorm, 'activa', 0, '{}', :v,
                  ST_GeogFromText(:wkt), :lat, :lng, CAST(:pub AS timestamp), CAST(:desde AS timestamp), '2026-11-20', 'Inmo Uno', 100)
            """), {"i": ide, "t": tipo, "b": barrio, "d": dire, "p": precio, "dorm": dorm, "v": lat is not None, "lat": lat,
                   "lng": lng, "pub": pub, "url": f"https://www.bahiablancapropiedades.com/propiedad/{ide}/",
                   "tit": f"{tipo} en Venta", "wkt": f"SRID=4326;POINT({lng} {lat})" if lat is not None else None,
                   "desde": "2026-11-25 09:45:00" if pub else None})
        c.execute(text("INSERT INTO meta (clave, valor) VALUES ('ultima_actualizacion', '2026-11-25 10:15:00')"))
    eng.dispose()
    from app.services import catalogo
    catalogo.reiniciar_catalogo()


def _login(c, usuario, clave):
    r = c.post("/auth/login", json={"usuario": usuario, "password": clave})
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def _agente(client, admin_h, usuario):
    r = client.post("/admin/usuarios", json={"nombre": usuario.title(), "usuario": usuario, "rol": "agente"}, headers=admin_h)
    tmp = r.json()["password_temporal"]
    h = _login(client, usuario, tmp)
    r = client.post("/auth/cambiar-password", json={"actual": tmp, "nueva": "Clave1234"}, headers=h)
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def _admin(client, crear_usuario):
    crear_usuario("jefa", rol="admin")
    return _login(client, "jefa", "Clave1234")


def _ids(r):
    return {x["id"]: x for x in r.json()["items"]}


def test_semaforo_borde_5000_y_precios_de_relleno(client, app_db, crear_usuario):
    _sembrar(app_db)
    h = _admin(client, crear_usuario)
    r = client.post("/propiedades/buscar", json={"filtros": {"b": 160000}}, headers=h)
    assert r.status_code == 200
    por_precio = {x["precio"]: x["color"] for x in r.json()["items"]}
    assert por_precio[155000] == "Verde" and por_precio[165000] == "Verde"   # justo en el borde: Verde
    assert por_precio[165001] == "Violeta"                                   # un dólar más: Violeta
    assert por_precio[154999] == "Amarillo"                                  # más barata que el Verde: nunca Verde
    assert por_precio[171200] == "Violeta"                                   # +7% = 171.200
    assert por_precio[184000] == "Amarillo"                                  # hasta +15%
    assert 111111111 not in por_precio                                       # precio de relleno: no entra
    assert r.json()["colores"]["Verde"] == 2
    orden = [x["color"] for x in r.json()["items"]]
    assert orden == sorted(orden, key=["Verde", "Violeta", "Amarillo"].index)


def test_paginacion_maximo_100(client, app_db, crear_usuario):
    _sembrar(app_db)
    h = _admin(client, crear_usuario)
    assert client.post("/propiedades/buscar", json={"limite": 101}, headers=h).status_code == 422
    r = client.post("/propiedades/buscar", json={"limite": 2, "offset": 2}, headers=h)
    assert r.json()["offset"] == 2 and len(r.json()["items"]) == 2 and r.json()["total"] == 8  # sin presupuesto, el de precio de relleno aparece (como en El Ojo de Dios)


def test_zona_dibujada_con_postgis(client, app_db, crear_usuario):
    _sembrar(app_db)
    h = _admin(client, crear_usuario)
    zona = {"type": "Polygon", "coordinates": [[[-62.27, -38.722], [-62.26, -38.722], [-62.26, -38.715], [-62.27, -38.715], [-62.27, -38.722]]]}
    r = client.post("/propiedades/mapa", json={"filtros": {}, "zona": zona}, headers=h)
    dentro = {p[0] for p in r.json()["puntos"] if p[4] == "dentro"}
    assert dentro == {1, 2, 6, 7, 8} and r.json()["sin_ubic_ocultas"] == 1      # el depto sin ubicación no aparece
    r = client.post("/propiedades/mapa", json={"filtros": {"margen": 3000}, "zona": zona}, headers=h)
    assert {p[4] for p in r.json()["puntos"]} == {"dentro", "cerca"}    # con margen aparecen las cercanas


def test_cada_uno_ve_solo_su_historial(client, app_db, crear_usuario):
    _sembrar(app_db)
    admin = _admin(client, crear_usuario)
    ana, beto = _agente(client, admin, "ana"), _agente(client, admin, "beto")
    client.post("/propiedades/buscar", json={"filtros": {"tipos": ["Casa"]}, "registrar": True}, headers=ana)
    client.post("/propiedades/buscar", json={"filtros": {"tipos": ["Departamento"]}, "registrar": True}, headers=beto)
    pid = client.post("/propiedades/buscar", json={}, headers=ana).json()["items"][0]["id"]
    client.get(f"/propiedades/{pid}", headers=ana)
    ha = client.get("/historial/busquedas", headers=ana).json()
    hb = client.get("/historial/busquedas", headers=beto).json()
    assert [x["texto"] for x in ha] == ["Venta · Casa"] and [x["texto"] for x in hb] == ["Venta · Departamento"]
    assert len(client.get("/historial/vistas", headers=ana).json()) == 1
    assert client.get("/historial/vistas", headers=beto).json() == []
    # un agente no puede pedir el historial de otro; el admin sí
    uid_ana = client.get("/me", headers=ana).json()["id"]
    assert client.get(f"/historial/busquedas?usuario_id={uid_ana}", headers=beto).status_code == 403
    assert len(client.get(f"/historial/busquedas?usuario_id={uid_ana}", headers=admin).json()) == 1


def test_dos_usuarios_a_la_vez(app_db, crear_usuario):
    """Dos sesiones distintas buscando en paralelo: cada una registra y ve solo lo suyo."""
    from concurrent.futures import ThreadPoolExecutor
    _sembrar(app_db)
    c1 = nuevo_cliente()
    admin = _admin(c1, crear_usuario)
    ana, beto = _agente(c1, admin, "ana"), _agente(c1, admin, "beto")
    c2 = nuevo_cliente()

    def buscar(args):
        cli, h, tipo = args
        return cli.post("/propiedades/buscar", json={"filtros": {"tipos": [tipo]}, "registrar": True}, headers=h).status_code
    with ThreadPoolExecutor(4) as ex:
        estados = list(ex.map(buscar, [(c1, ana, "Casa"), (c2, beto, "Departamento")] * 5))
    assert set(estados) == {200}
    import time
    time.sleep(0.5)
    assert {x["texto"] for x in c1.get("/historial/busquedas", headers=ana).json()} == {"Venta · Casa"}
    assert {x["texto"] for x in c2.get("/historial/busquedas", headers=beto).json()} == {"Venta · Departamento"}


def test_comprador_bloqueo_optimista_409(client, app_db, crear_usuario):
    _sembrar(app_db)
    admin = _admin(client, crear_usuario)
    ana = _agente(client, admin, "ana")
    r = client.post("/clientes", json={"datos": {"nombre": "Juan", "tipos": ["Casa"], "presu": 160000}}, headers=ana)
    cid, v = r.json()["id"], r.json()["version"]
    assert client.put(f"/clientes/{cid}", json={"datos": {"nombre": "Juan A", "tipos": ["Casa"], "presu": 160000}, "version": v}, headers=admin).status_code == 200
    r = client.put(f"/clientes/{cid}", json={"datos": {"nombre": "Juan B"}, "version": v}, headers=ana)
    assert r.status_code == 409 and "Otro usuario modificó esto" in r.json()["detail"]
    lista = client.get("/clientes", headers=ana).json()
    assert lista[0]["datos"]["nombre"] == "Juan A" and lista[0]["coinciden"] == 5 and lista[0]["es_mia"]


def test_ficha_idempotente_y_pagina_publica(client, app_db, crear_usuario, monkeypatch):
    _sembrar(app_db)
    h = _admin(client, crear_usuario)
    from app.api import fichas
    monkeypatch.setattr(fichas, "_datos_vivos", lambda o, d, f: ({**o, "descripcion": d, "precio": o["precio_publicado"],
                                                                  "ref": o["id_externo"], "_verificada": False}, []))
    ids = [x["id"] for x in client.post("/propiedades/buscar", json={"limite": 2}, headers=h).json()["items"]]
    cuerpo = {"ids": ids, "cliente": "Juan", "clave_idempotencia": "toque-1"}
    a = client.post("/fichas", json=cuerpo, headers=h).json()
    b = client.post("/fichas", json=cuerpo, headers=h).json()
    assert a["id"] == b["id"] and a["enlace"].startswith("/f/")
    pagina = client.get(a["enlace"])              # sin sesión: es para el cliente
    assert pagina.status_code == 200 and "Selección de propiedades para Juan" in pagina.text
    assert client.get("/f/no-existe").status_code == 404
    assert len(client.get("/historial/fichas", headers=h).json()) == 1


def test_sin_sesion_no_hay_datos(client, app_db, crear_usuario):
    _sembrar(app_db)
    for ruta in ("/propiedades/buscar", "/propiedades/mapa"):
        assert client.post(ruta, json={}).status_code == 401
    for ruta in ("/estado", "/credito", "/clientes", "/mercado", "/captacion", "/historial/busquedas", "/excel"):
        assert client.get(ruta).status_code == 401
