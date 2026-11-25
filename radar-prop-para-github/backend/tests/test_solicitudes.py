"""Solicitud de acceso: cualquiera la pide, queda pendiente, el admin aprueba o rechaza."""
from tests.conftest import login, nuevo_cliente

SOL = {"nombre": "Lucía", "apellido": "Pérez", "usuario": "lucia", "email": "lucia@mail.com",
       "telefono": "291 4111111", "password": "MiClave2026"}


def test_solicitar_aprobar_e_ingresar(client, crear_usuario):
    crear_usuario("bautista", rol="admin")
    r = client.post("/auth/solicitar-acceso", json=SOL)
    assert r.status_code == 201
    # pendiente: con la clave correcta avisa que falta aprobación; con una incorrecta, el mensaje genérico
    r = client.post("/auth/login", json={"usuario": "lucia", "password": "MiClave2026"})
    assert r.status_code == 403 and "aprobada" in r.json()["detail"]
    assert client.post("/auth/login", json={"usuario": "lucia", "password": "otra12345"}).status_code == 401
    # repetida: el usuario ya está tomado
    assert client.post("/auth/solicitar-acceso", json=SOL).status_code == 409

    adm = nuevo_cliente()
    h = login(adm, "bautista")
    assert adm.get("/admin/solicitudes-pendientes", headers=h).json() == {"cantidad": 1}
    lista = adm.get("/admin/usuarios", headers=h).json()
    assert lista[0]["usuario"] == "lucia" and lista[0]["solicitud_pendiente"] is True and lista[0]["activo"] is False
    uid = lista[0]["id"]
    r = adm.post(f"/admin/usuarios/{uid}/aprobar", headers=h)
    assert r.status_code == 200 and r.json()["activo"] is True and r.json()["solicitud_pendiente"] is False
    assert adm.get("/admin/solicitudes-pendientes", headers=h).json() == {"cantidad": 0}

    c = nuevo_cliente()
    r = c.post("/auth/login", json={"usuario": "lucia", "password": "MiClave2026"})
    assert r.status_code == 200 and r.json()["usuario"]["rol"] == "agente"
    assert r.json()["debe_cambiar_password"] is False


def test_rechazar_libera_el_usuario(client, crear_usuario):
    crear_usuario("bautista", rol="admin")
    assert client.post("/auth/solicitar-acceso", json=SOL).status_code == 201
    adm = nuevo_cliente()
    h = login(adm, "bautista")
    uid = adm.get("/admin/usuarios", headers=h).json()[0]["id"]
    assert adm.post(f"/admin/usuarios/{uid}/rechazar", headers=h).status_code == 204
    assert all(u["usuario"] != "lucia" for u in adm.get("/admin/usuarios", headers=h).json())
    assert client.post("/auth/login", json={"usuario": "lucia", "password": "MiClave2026"}).status_code == 401
    assert client.post("/auth/solicitar-acceso", json=SOL).status_code == 201  # puede volver a pedirlo


def test_solicitud_valida_datos_y_no_da_permisos(client, crear_usuario):
    crear_usuario("bautista", rol="admin")
    assert client.post("/auth/solicitar-acceso", json={**SOL, "password": "corta"}).status_code == 400
    assert client.post("/auth/solicitar-acceso", json={**SOL, "usuario": "con espacio"}).status_code == 422
    assert client.post("/auth/solicitar-acceso", json={**SOL, "usuario": "BAUTISTA"}).status_code == 409
    # no se puede pedir rol admin: el campo se ignora
    assert client.post("/auth/solicitar-acceso", json={**SOL, "rol": "admin"}).status_code == 201
    adm = nuevo_cliente()
    h = login(adm, "bautista")
    u = next(x for x in adm.get("/admin/usuarios", headers=h).json() if x["usuario"] == "lucia")
    assert u["rol"] == "agente"
    # un agente no puede aprobar
    crear_usuario("ana")
    ag = nuevo_cliente()
    assert ag.post(f"/admin/usuarios/{u['id']}/aprobar", headers=login(ag, "ana")).status_code == 403
