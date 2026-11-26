"""Contraseñas (Argon2id), tokens de acceso (JWT corto) y de renovación (aleatorio, guardado como hash)."""
import hashlib
import re
import secrets
import string
import threading
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import settings

# Argon2id con los parámetros mínimos que recomienda OWASP (19 MiB, 2 pasadas). Los de fábrica usan 64 MiB por
# cálculo: en el servidor gratis (512 MB) diez ingresos a la vez lo dejaban sin memoria.
_ph = PasswordHasher(time_cost=2, memory_cost=19 * 1024, parallelism=1)
# Como mucho 2 cálculos de contraseña a la vez; el resto espera su turno (unos milisegundos), no tumba el servidor.
_turnos = threading.BoundedSemaphore(2)
ALG = "HS256"


def hash_password(clave: str) -> str:
    with _turnos:
        return _ph.hash(clave)


def verificar_password(hash_guardado: str, clave: str) -> bool:
    try:
        with _turnos:
            return _ph.verify(hash_guardado, clave)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def necesita_rehash(hash_guardado: str) -> bool:
    """True si la contraseña se guardó con los parámetros viejos (se vuelve a guardar al ingresar)."""
    try:
        return _ph.check_needs_rehash(hash_guardado)
    except InvalidHashError:
        return False


def password_valida(clave: str) -> str | None:
    """Devuelve el motivo si no sirve, o None si está bien."""
    if len(clave) < 8:
        return "La contraseña tiene que tener al menos 8 caracteres."
    if not re.search(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]", clave) or not re.search(r"\d", clave):
        return "La contraseña tiene que tener letras y números."
    return None


def password_temporal() -> str:
    """10 caracteres sin letras que se confunden (0/O, 1/l/I), con letras y números garantizados."""
    letras = "".join(c for c in string.ascii_letters if c not in "OolIL")
    digitos = "23456789"
    while True:
        c = "".join(secrets.choice(letras + digitos) for _ in range(10))
        if password_valida(c) is None and any(ch in digitos for ch in c):
            return c


def crear_access_token(user_id: int, sesion_id: int, rol: str, debe_cambiar: bool) -> str:
    ahora = datetime.now(UTC)
    datos = {"sub": str(user_id), "sid": sesion_id, "rol": rol, "dcp": debe_cambiar,
             "iat": ahora, "exp": ahora + timedelta(minutes=settings.access_minutos)}
    return jwt.encode(datos, settings.jwt_secret, algorithm=ALG)


def leer_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[ALG])
    except jwt.PyJWTError:
        return None


def nuevo_refresh() -> tuple[str, str]:
    """(token para la cookie, hash para la base)."""
    t = secrets.token_urlsafe(48)
    return t, hash_refresh(t)


def hash_refresh(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
