"""Tests con una base PostgreSQL + PostGIS real (nunca SQLite).
Variables: TEST_DATABASE_URL (base de prueba, se borra y se vuelve a crear el esquema)."""
import os
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, text

AQUI = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(AQUI)
RAIZ = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)
sys.path.insert(0, os.path.join(RAIZ, "scripts"))

TEST_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://postgres@localhost:5432/radar_test")
# la app apunta a la base de prueba y acepta cookies por http (el cliente de prueba no usa https)
os.environ["DATABASE_URL"] = TEST_URL
os.environ["COOKIE_SECURE"] = "false"
os.environ["CATALOGO_FONDO"] = "0"  # en las pruebas la recarga es inmediata
os.environ["PRECALENTAR"] = "0"
os.environ.setdefault("JWT_SECRET", "secreto-de-prueba-" + "x" * 40)


def _alembic(*args):
    env = {**os.environ, "DATABASE_URL": TEST_URL}
    subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env, check=True,
                   capture_output=True)


@pytest.fixture()
def pg_url():
    """Esquema limpio en cada test que lo pide."""
    eng = create_engine(TEST_URL)
    with eng.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    eng.dispose()
    _alembic("upgrade", "head")
    return TEST_URL


# ------------------------------------------------------------------ API
@pytest.fixture()
def app_db(pg_url):
    from app import db as dbmod
    from app.core.deps import limite_auth
    dbmod.engine.dispose()
    limite_auth.reiniciar()
    return pg_url


@pytest.fixture()
def client(app_db):
    from fastapi.testclient import TestClient

    from app.main import app
    with TestClient(app) as c:
        yield c


def nuevo_cliente():
    from fastapi.testclient import TestClient

    from app.main import app
    return TestClient(app)


@pytest.fixture()
def crear_usuario(app_db):
    """Crea un usuario directo en la base (para preparar los tests)."""
    from app.core.security import hash_password
    from app.db import SessionLocal
    from app.models import Usuario

    def _crear(usuario, clave="Clave1234", rol="agente", debe_cambiar=False, activo=True, nombre=None):
        with SessionLocal() as db:
            u = Usuario(nombre=nombre or usuario.title(), apellido="", usuario=usuario, rol=rol,
                        hash_password=hash_password(clave), debe_cambiar_password=debe_cambiar, activo=activo)
            db.add(u)
            db.commit()
            return u.id
    return _crear


def login(c, usuario, clave="Clave1234"):
    r = c.post("/auth/login", json={"usuario": usuario, "password": clave})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}
