"""Dependencias de las rutas: sesión de base, usuario logueado, permisos y límite de pedidos."""
import ipaddress
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import leer_access_token
from app.db import get_db
from app.models import Sesion, Usuario


def ip_de(request: Request) -> str | None:
    """IP del usuario (detrás del proxy del hosting viene en X-Forwarded-For). Si no es una IP válida, None."""
    fwd = request.headers.get("x-forwarded-for")
    ip = fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else None)
    try:
        return str(ipaddress.ip_address(ip)) if ip else None
    except ValueError:
        return None


@dataclass
class Actual:
    usuario: Usuario
    sesion_id: int

    @property
    def id(self) -> int:
        return self.usuario.id

    @property
    def es_admin(self) -> bool:
        return self.usuario.rol == "admin"


NO_AUTORIZADO = HTTPException(401, "Tu sesión venció. Volvé a ingresar.")


def _actual(db: Session, authorization: str | None) -> Actual:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise NO_AUTORIZADO
    datos = leer_access_token(authorization.split(" ", 1)[1].strip())
    if not datos:
        raise NO_AUTORIZADO
    u = db.get(Usuario, int(datos["sub"]))
    s = db.get(Sesion, int(datos["sid"]))
    # se revisa en cada pedido: un usuario desactivado o una sesión cerrada dejan de andar al instante
    if not u or not u.activo or not s or s.revocada or s.user_id != u.id:
        raise NO_AUTORIZADO
    return Actual(usuario=u, sesion_id=s.id)


def usuario_logueado(db: Session = Depends(get_db), authorization: str | None = Header(None)) -> Actual:
    """Cualquier usuario con sesión, aunque tenga que cambiar la contraseña (para /me y cambiar-password)."""
    return _actual(db, authorization)


def usuario_actual(db: Session = Depends(get_db), authorization: str | None = Header(None)) -> Actual:
    a = _actual(db, authorization)
    if a.usuario.debe_cambiar_password:
        raise HTTPException(403, "Antes de seguir tenés que cambiar tu contraseña temporal.")
    return a


def solo_admin(a: Actual = Depends(usuario_actual)) -> Actual:
    if not a.es_admin:
        raise HTTPException(403, "Esta sección es solo para administradores.")
    return a


def ultimo_admin_activo(db: Session, excepto_id: int) -> bool:
    otros = db.scalar(select(Usuario.id).where(Usuario.rol == "admin", Usuario.activo.is_(True),
                                               Usuario.id != excepto_id).limit(1))
    return otros is None


# ------------------------------------------------------------------ límite de pedidos por IP (rutas /auth)
class LimitePorIP:
    def __init__(self) -> None:
        self.ventanas: dict[str, deque] = defaultdict(deque)
        self.lock = Lock()

    def reiniciar(self) -> None:
        with self.lock:
            self.ventanas.clear()

    def __call__(self, request: Request) -> None:
        clave = ip_de(request) or "?"
        ahora = time.monotonic()
        with self.lock:
            v = self.ventanas[clave]
            while v and ahora - v[0] > 60:
                v.popleft()
            if len(v) >= settings.auth_pedidos_por_minuto:
                raise HTTPException(429, "Demasiados intentos seguidos. Esperá un minuto y probá de nuevo.")
            v.append(ahora)


limite_auth = LimitePorIP()
