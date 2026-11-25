"""Ingreso, renovación de sesión, salida y cambio de contraseña."""
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import Actual, ip_de, limite_auth, usuario_logueado
from app.core.security import crear_access_token, hash_password, hash_refresh, nuevo_refresh, password_valida, verificar_password
from app.db import get_db
from app.models import Sesion, Usuario
from app.schemas.usuarios import CambiarPasswordIn, LoginIn, TokenOut, UsuarioOut
from app.services.auditoria import registrar

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(limite_auth)])
COOKIE = "rp_refresh"
CREDENCIALES_MAL = "Usuario o contraseña incorrectos."


def _poner_cookie(resp: Response, token: str):
    resp.set_cookie(COOKIE, token, max_age=settings.refresh_dias * 86400, httponly=True, secure=settings.cookie_secure,
                    samesite="lax", path=settings.cookie_path)


def _salida(u: Usuario, s: Sesion) -> TokenOut:
    return TokenOut(access_token=crear_access_token(u.id, s.id, u.rol, u.debe_cambiar_password),
                    expira_en_seg=settings.access_minutos * 60, debe_cambiar_password=u.debe_cambiar_password,
                    usuario=UsuarioOut.model_validate(u))


@router.post("/login", response_model=TokenOut)
def login(datos: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ident = datos.usuario.strip().lower()
    u = db.scalar(select(Usuario).where(or_(func.lower(Usuario.usuario) == ident, func.lower(Usuario.email) == ident))
                  .with_for_update())
    ip = ip_de(request)
    ahora = datetime.now(UTC)
    if not u:
        hash_password("x")  # tarda lo mismo que con un usuario real: no revela qué usuarios existen
        raise HTTPException(401, CREDENCIALES_MAL)
    if u.bloqueado_hasta and u.bloqueado_hasta > ahora:
        minutos = int((u.bloqueado_hasta - ahora).total_seconds() // 60) + 1
        raise HTTPException(423, f"Demasiados intentos fallidos. Probá de nuevo en {minutos} minutos.")
    if not verificar_password(u.hash_password, datos.password) or not u.activo:
        if u.activo:
            u.intentos_fallidos += 1
            if u.intentos_fallidos >= settings.login_max_intentos:
                u.bloqueado_hasta = ahora + timedelta(minutes=settings.bloqueo_minutos)
                u.intentos_fallidos = 0
                registrar(db, u.id, "usuario_bloqueado", "usuario", u.id, ip=ip)
        registrar(db, u.id, "login_fallido", "usuario", u.id, ip=ip)
        db.commit()
        raise HTTPException(401, CREDENCIALES_MAL)
    u.intentos_fallidos = 0
    u.bloqueado_hasta = None
    u.ultimo_ingreso = ahora
    token, h = nuevo_refresh()
    disp = datos.dispositivo or (request.headers.get("user-agent") or "")[:200] or None
    s = Sesion(user_id=u.id, refresh_hash=h, dispositivo=disp, ip=ip, expira_en=ahora + timedelta(days=settings.refresh_dias))
    db.add(s)
    db.flush()
    registrar(db, u.id, "login", "sesion", s.id, {"dispositivo": disp}, ip)
    db.commit()
    _poner_cookie(response, token)
    return _salida(u, s)


@router.post("/refresh", response_model=TokenOut)
def refresh(request: Request, response: Response, db: Session = Depends(get_db),
            rp_refresh: str | None = Cookie(None)):
    if not rp_refresh:
        raise HTTPException(401, "Tu sesión venció. Volvé a ingresar.")
    s = db.scalar(select(Sesion).where(Sesion.refresh_hash == hash_refresh(rp_refresh)).with_for_update())
    ahora = datetime.now(UTC)
    if not s or s.revocada or (s.expira_en and s.expira_en < ahora):
        raise HTTPException(401, "Tu sesión venció. Volvé a ingresar.")
    u = db.get(Usuario, s.user_id)
    if not u or not u.activo:
        s.revocada = True
        db.commit()
        raise HTTPException(401, "Tu sesión venció. Volvé a ingresar.")
    # rotación: el token usado deja de servir y se entrega uno nuevo
    token, h = nuevo_refresh()
    s.refresh_hash = h
    s.ultima_actividad = ahora
    s.expira_en = ahora + timedelta(days=settings.refresh_dias)
    ip = ip_de(request)
    if ip:
        s.ip = ip
    db.commit()
    _poner_cookie(response, token)
    return _salida(u, s)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, a: Actual = Depends(usuario_logueado), db: Session = Depends(get_db)):
    db.execute(update(Sesion).where(Sesion.id == a.sesion_id).values(revocada=True))
    registrar(db, a.id, "logout", "sesion", a.sesion_id, ip=ip_de(request))
    db.commit()
    response.delete_cookie(COOKIE, path=settings.cookie_path)


@router.post("/cambiar-password", response_model=TokenOut)
def cambiar_password(datos: CambiarPasswordIn, request: Request, a: Actual = Depends(usuario_logueado),
                     db: Session = Depends(get_db)):
    u = a.usuario
    if not verificar_password(u.hash_password, datos.actual):
        raise HTTPException(400, "La contraseña actual no es correcta.")
    motivo = password_valida(datos.nueva)
    if motivo:
        raise HTTPException(400, motivo)
    if datos.nueva == datos.actual:
        raise HTTPException(400, "La contraseña nueva tiene que ser distinta de la actual.")
    u.hash_password = hash_password(datos.nueva)
    u.debe_cambiar_password = False
    # se cierran las demás sesiones abiertas (la actual sigue)
    db.execute(update(Sesion).where(Sesion.user_id == u.id, Sesion.id != a.sesion_id).values(revocada=True))
    registrar(db, u.id, "cambio_password", "usuario", u.id, ip=ip_de(request))
    db.commit()
    s = db.get(Sesion, a.sesion_id)
    assert s is not None
    return _salida(u, s)
