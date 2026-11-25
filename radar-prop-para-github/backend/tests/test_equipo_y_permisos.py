"""Pantalla Equipo (solo admin), validaciones, auditoría y aislamiento entre usuarios."""
import pytest

from tests.conftest import login, nuevo_cliente


@pytest.fixture()
def admin(client, crear_usuario):
    crear_usuario("bautista", rol="admin")
    return login(client, "bautista")


def _cambiar_clave(c, usuario, temporal, nueva="ClaveFinal77"):
    r = c.post("/auth/login", json={"usuario": usuario, "password": temporal})
    assert r.status_code == 200 and r.json()["debe_cambiar_password"]
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    r = c.post("/auth/cambiar-password", json={"actual": temporal, "nueva": nueva}, headers=h)
    assert r.status_code == 200
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def test_criterio_fase2_alta_de_agente_y_primer_ingreso(client, admin):
    r = client.post("/admin/usuarios", headers=admin, json={"nombre": "Sofía", "apellido": "Pérez", "usuario": "sofia",
                                                             "telefono": "291 15 512-2322", "rol": "agente"})
    assert r.status_code == 201
    j = r.json()
    temporal = j["password_temporal"]
    assert len(temporal) == 10 and "sofia" in j["texto_whatsapp"] and temporal in j["texto_whatsapp"]
    assert j["link_whatsapp"].startswith("https://wa.me/549291")
    assert j["usuario"]["debe_cambiar_password"] is True
    agente = nuevo_cliente()
    h = _cambiar_clave(agente, "sofia", temporal)
    assert agente.get("/me", headers=h).json()["debe_cambiar_password"] is False
    # el agente no puede usar ninguna ruta de admin
    for metodo, ruta in [("get", "/admin/usuarios"), ("post", "/admin/usuarios"), ("get", "/admin/actividad"),
                         ("post", "/admin/usuarios/1/desactivar"), ("post", "/admin/usuarios/1/resetear-password"),
                         ("delete", "/admin/usuarios/1/sesiones"), ("patch", "/admin/usuarios/1")]:
        kw = {"json": {"nombre": "x", "usuario": "xyz"}} if metodo in ("post", "patch") else {}
        assert getattr(agente, metodo)(ruta, headers=h, **kw).status_code == 403, ruta


def test_usuario_unico_sin_mayusculas_y_validaciones(client, admin):
    assert client.post("/admin/usuarios", headers=admin, json={"nombre": "A", "usuario": "Juan"}).status_code == 201
    r = client.post("/admin/usuarios", headers=admin, json={"nombre": "B", "usuario": "JUAN"})
    assert r.status_code == 409 and "Ya existe" in r.json()["detail"]
    assert client.post("/admin/usuarios", headers=admin, json={"nombre": "B", "usuario": "con espacio"}).status_code == 422
    assert client.post("/admin/usuarios", headers=admin, json={"nombre": "B", "usuario": "bb", "email": "malo"}).status_code == 422


def test_desactivar_corta_sesiones_al_instante_y_reactivar(client, admin, crear_usuario):
    uid = crear_usuario("ana")
    cel = nuevo_cliente()
    h = login(cel, "ana")
    assert client.post(f"/admin/usuarios/{uid}/desactivar", headers=admin).status_code == 200
    assert cel.get("/me", headers=h).status_code == 401
    assert cel.post("/auth/refresh").status_code == 401
    assert cel.post("/auth/login", json={"usuario": "ana", "password": "Clave1234"}).status_code == 401
    assert client.post(f"/admin/usuarios/{uid}/reactivar", headers=admin).status_code == 200
    assert cel.post("/auth/login", json={"usuario": "ana", "password": "Clave1234"}).status_code == 200


def test_ultimo_admin_y_autodesactivacion(client, admin):
    yo = client.get("/me", headers=admin).json()["id"]
    r = client.post(f"/admin/usuarios/{yo}/desactivar", headers=admin)
    assert r.status_code == 400 and "a vos mismo" in r.json()["detail"]
    r = client.patch(f"/admin/usuarios/{yo}", headers=admin, json={"rol": "agente"})
    assert r.status_code == 400 and "último administrador" in r.json()["detail"]
    otro = client.post("/admin/usuarios", headers=admin, json={"nombre": "G", "usuario": "guillermo", "rol": "admin"}).json()
    assert client.patch(f"/admin/usuarios/{yo}", headers=admin, json={"rol": "agente"}).status_code == 200  # ya hay otro admin
    assert otro["usuario"]["rol"] == "admin"


def test_resetear_password_y_cerrar_sesiones(client, admin, crear_usuario):
    uid = crear_usuario("ana")
    cel = nuevo_cliente()
    h = login(cel, "ana")
    r = client.post(f"/admin/usuarios/{uid}/resetear-password", headers=admin)
    assert r.status_code == 200 and r.json()["usuario"]["debe_cambiar_password"]
    assert cel.get("/me", headers=h).status_code == 401
    assert cel.post("/auth/login", json={"usuario": "ana", "password": "Clave1234"}).status_code == 401
    _cambiar_clave(cel, "ana", r.json()["password_temporal"])
    h2 = login(nuevo_cliente(), "ana", "ClaveFinal77")
    assert client.delete(f"/admin/usuarios/{uid}/sesiones", headers=admin).status_code == 204
    assert cel.get("/me", headers=h2).status_code == 401


def test_auditoria_registra_acciones(client, admin, crear_usuario):
    uid = crear_usuario("ana")
    client.post(f"/admin/usuarios/{uid}/desactivar", headers=admin)
    acciones = [x["accion"] for x in client.get("/admin/actividad", headers=admin).json()]
    assert "desactivar_usuario" in acciones and "login" in acciones
    solo_ana = client.get(f"/admin/actividad?usuario_id={uid}", headers=admin).json()
    assert all(x["user_id"] == uid for x in solo_ana)


def _propiedades(n=3):
    from app.db import SessionLocal
    from app.models import Propiedad
    with SessionLocal() as db:
        ps = [Propiedad(plataforma="BBP", id_externo=str(9000 + i), id_legado=9000 + i, estado="activa",
                        ubicacion_valida=False, intentos=0) for i in range(n)]
        db.add_all(ps)
        db.commit()
        return [p.id for p in ps]


def test_aislamiento_entre_agentes(client, crear_usuario):
    crear_usuario("ana")
    crear_usuario("beto")
    p1, p2, p3 = _propiedades()
    ha = login(client, "ana")
    b = nuevo_cliente()
    hb = login(b, "beto")
    assert client.post("/selecciones", headers=ha, json={"propiedad_ids": [p1, p2]}).json() == [p1, p2]
    assert b.post("/selecciones", headers=hb, json={"propiedad_ids": [p3]}).json() == [p3]
    assert b.get("/selecciones", headers=hb).json() == [p3]            # beto no ve la de ana
    b.delete(f"/selecciones/{p1}", headers=hb)                          # ni puede borrarle nada
    b.delete("/selecciones", headers=hb)
    assert client.get("/selecciones", headers=ha).json() == [p1, p2]
    # mandar un user_id desde el navegador no cambia nada
    client.post("/selecciones?user_id=2", headers=ha, json={"propiedad_ids": [p3], "user_id": 2})
    assert b.get("/selecciones", headers=hb).json() == []
    # un agente no puede cerrar sesiones de otro
    ses_beto = login(nuevo_cliente(), "beto")
    sid = nuevo_cliente().get("/me/sesiones", headers=ses_beto).json()[0]["id"]
    assert client.delete(f"/me/sesiones/{sid}", headers=ha).status_code == 404


def test_importar_seleccion_de_el_ojo_de_dios(client, crear_usuario):
    crear_usuario("ana")
    ids = _propiedades(2)
    h = login(client, "ana")
    r = client.post("/selecciones/importar-ojo-de-dios", headers=h, json={"ids_legado": [9000, 9001, 123456]})
    assert r.json() == {"importadas": 2, "no_encontradas": 1}
    assert sorted(client.get("/selecciones", headers=h).json()) == sorted(ids)


def test_dos_usuarios_en_paralelo(app_db, crear_usuario):
    """Dos sesiones distintas trabajando al mismo tiempo: cada una ve solo lo suyo."""
    from concurrent.futures import ThreadPoolExecutor
    crear_usuario("ana")
    crear_usuario("beto")
    ids = _propiedades(20)

    def trabajar(usuario, mis_ids):
        c = nuevo_cliente()
        h = login(c, usuario)
        for p in mis_ids:
            assert c.post("/selecciones", headers=h, json={"propiedad_ids": [p]}).status_code == 200
        return sorted(c.get("/selecciones", headers=h).json())

    with ThreadPoolExecutor(2) as ex:
        fa = ex.submit(trabajar, "ana", ids[:10])
        fb = ex.submit(trabajar, "beto", ids[10:])
    assert fa.result() == sorted(ids[:10]) and fb.result() == sorted(ids[10:])
