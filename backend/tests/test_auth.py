"""Ingreso, renovación rotativa, sesiones múltiples, bloqueo y contraseñas."""
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from tests.conftest import login, nuevo_cliente


def test_login_ok_y_me(client, crear_usuario):
    crear_usuario("bautista", rol="admin")
    r = client.post("/auth/login", json={"usuario": "BAUTISTA", "password": "Clave1234"})  # sin distinguir mayúsculas
    assert r.status_code == 200
    j = r.json()
    assert j["usuario"]["usuario"] == "bautista" and j["expira_en_seg"] == 900
    assert "rp_refresh" in r.cookies
    me = client.get("/me", headers={"Authorization": "Bearer " + j["access_token"]})
    assert me.status_code == 200 and me.json()["rol"] == "admin"
    assert "hash_password" not in me.json()


def test_credenciales_mal_mismo_mensaje(client, crear_usuario):
    crear_usuario("ana")
    a = client.post("/auth/login", json={"usuario": "ana", "password": "mal12345"})
    b = client.post("/auth/login", json={"usuario": "noexiste", "password": "mal12345"})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_sin_sesion_no_hay_acceso(client):
    assert client.get("/me").status_code == 401
    assert client.get("/admin/usuarios").status_code == 401
    assert client.get("/selecciones", headers={"Authorization": "Bearer basura"}).status_code == 401
    assert client.get("/health").status_code == 200  # la única pública junto con /auth/login


def test_bloqueo_tras_5_intentos(client, crear_usuario):
    crear_usuario("ana")
    for _ in range(5):
        assert client.post("/auth/login", json={"usuario": "ana", "password": "mal12345"}).status_code == 401
    r = client.post("/auth/login", json={"usuario": "ana", "password": "Clave1234"})
    assert r.status_code == 423 and "minutos" in r.json()["detail"]
    from app.db import SessionLocal
    from app.models import Usuario
    with SessionLocal() as db:  # pasado el bloqueo vuelve a entrar
        u = db.scalar(select(Usuario).where(Usuario.usuario == "ana"))
        u.bloqueado_hasta = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert client.post("/auth/login", json={"usuario": "ana", "password": "Clave1234"}).status_code == 200


def test_limite_por_ip_en_auth(client):
    codigos = [client.post("/auth/login", json={"usuario": "x", "password": "y"}).status_code for _ in range(22)]
    assert codigos[-1] == 429 and 401 in codigos


def test_refresh_rotativo(client, crear_usuario):
    crear_usuario("ana")
    login(client, "ana")
    viejo = client.cookies.get("rp_refresh")
    r = client.post("/auth/refresh")
    assert r.status_code == 200 and r.json()["access_token"]
    nuevo = client.cookies.get("rp_refresh")
    assert nuevo and nuevo != viejo
    otro = nuevo_cliente()
    otro.cookies.set("rp_refresh", viejo, path="/auth")
    assert otro.post("/auth/refresh").status_code == 401  # el token ya usado no sirve más


def test_varias_sesiones_y_cerrar_una(client, crear_usuario):
    crear_usuario("ana")
    h_pc = login(client, "ana")
    cel = nuevo_cliente()
    h_cel = login(cel, "ana")
    ses = client.get("/me/sesiones", headers=h_pc).json()
    assert len(ses) == 2 and sum(s["actual"] for s in ses) == 1
    id_cel = next(s["id"] for s in ses if not s["actual"])
    assert client.delete(f"/me/sesiones/{id_cel}", headers=h_pc).status_code == 204
    assert cel.get("/me", headers=h_cel).status_code == 401      # el celular quedó afuera al instante
    assert cel.post("/auth/refresh").status_code == 401
    assert client.get("/me", headers=h_pc).status_code == 200    # la PC sigue


def test_logout(client, crear_usuario):
    crear_usuario("ana")
    h = login(client, "ana")
    assert client.post("/auth/logout", headers=h).status_code == 204
    assert client.get("/me", headers=h).status_code == 401


def test_cambio_obligatorio_de_clave_temporal(client, crear_usuario):
    crear_usuario("nuevo", clave="Temporal12", debe_cambiar=True)
    r = client.post("/auth/login", json={"usuario": "nuevo", "password": "Temporal12"})
    assert r.json()["debe_cambiar_password"] is True
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    assert client.get("/selecciones", headers=h).status_code == 403  # no puede usar la app todavía
    assert client.get("/me", headers=h).status_code == 200
    mal = client.post("/auth/cambiar-password", json={"actual": "Temporal12", "nueva": "corta"}, headers=h)
    assert mal.status_code == 400 and "8 caracteres" in mal.json()["detail"]
    sin_num = client.post("/auth/cambiar-password", json={"actual": "Temporal12", "nueva": "solamenteletras"}, headers=h)
    assert sin_num.status_code == 400 and "números" in sin_num.json()["detail"]
    ok = client.post("/auth/cambiar-password", json={"actual": "Temporal12", "nueva": "MiClaveNueva9"}, headers=h)
    assert ok.status_code == 200 and ok.json()["debe_cambiar_password"] is False
    h2 = {"Authorization": "Bearer " + ok.json()["access_token"]}
    assert client.get("/selecciones", headers=h2).status_code == 200
    assert client.post("/auth/login", json={"usuario": "nuevo", "password": "MiClaveNueva9"}).status_code == 200


def test_password_guardada_con_argon2id(app_db, crear_usuario):
    uid = crear_usuario("ana")
    from app.db import SessionLocal
    from app.models import Usuario
    with SessionLocal() as db:
        h = db.get(Usuario, uid).hash_password
    assert h.startswith("$argon2id$") and "Clave1234" not in h


def test_errores_en_espanol_sin_datos_internos(client):
    r = client.post("/auth/login", json={"usuario": ""})
    assert r.status_code == 422 and r.json()["detail"].startswith("Revisá los datos")
