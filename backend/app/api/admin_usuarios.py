"""Pantalla "Equipo" (solo admin): alta, edición, desactivación y contraseñas de los usuarios. Nunca se borra un
usuario: se desactiva y su historial se conserva."""
import re
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import Actual, ip_de, solo_admin, ultimo_admin_activo
from app.core.security import hash_password, password_temporal
from app.db import get_db
from app.models import Actividad, Sesion, Usuario
from app.schemas.usuarios import ActividadOut, SesionOut, UsuarioCreadoOut, UsuarioCrearIn, UsuarioEditarIn, UsuarioOut
from app.services.auditoria import registrar

from .me import sesiones_de

router = APIRouter(prefix="/admin", tags=["equipo"])


def _usuario(db: Session, uid: int) -> Usuario:
    u = db.get(Usuario, uid)
    if not u:
        raise HTTPException(404, "No encontramos ese usuario.")
    return u


def _choca(db: Session, campo, valor: str | None, excepto: int | None = None) -> bool:
    if not valor:
        return False
    q = select(Usuario.id).where(func.lower(campo) == valor.lower())
    if excepto:
        q = q.where(Usuario.id != excepto)
    return db.scalar(q.limit(1)) is not None


def _whatsapp(u: Usuario, clave: str, nuevo: bool) -> tuple[str, str | None]:
    texto = (f"Hola {u.nombre}! {'Te creé el usuario' if nuevo else 'Te generé una contraseña nueva'} en Radar Prop.\n"
             f"Entrá en {settings.app_url}\nUsuario: {u.usuario}\nContraseña temporal: {clave}\n"
             f"Al ingresar te va a pedir que la cambies por una tuya.")
    tel = re.sub(r"\D", "", u.telefono or "")
    if tel:
        tel = tel.lstrip("0")
        if not tel.startswith("54"):
            tel = "549" + re.sub(r"^(\d{3,4})15", r"\1", tel)
        return texto, f"https://wa.me/{tel}?text={quote(texto)}"
    return texto, f"https://wa.me/?text={quote(texto)}"


def _cerrar_sesiones(db: Session, uid: int):
    db.execute(update(Sesion).where(Sesion.user_id == uid, Sesion.revocada.is_(False)).values(revocada=True))


@router.get("/usuarios", response_model=list[UsuarioOut])
def listar(a: Actual = Depends(solo_admin), db: Session = Depends(get_db)):
    return db.scalars(select(Usuario).order_by(Usuario.activo.desc(), Usuario.nombre)).all()


@router.post("/usuarios", response_model=UsuarioCreadoOut, status_code=201)
def crear(datos: UsuarioCrearIn, request: Request, a: Actual = Depends(solo_admin), db: Session = Depends(get_db)):
    if _choca(db, Usuario.usuario, datos.usuario):
        raise HTTPException(409, "Ya existe un usuario con ese nombre de usuario.")
    if _choca(db, Usuario.email, datos.email):
        raise HTTPException(409, "Ya existe un usuario con ese email.")
    clave = password_temporal()
    u = Usuario(nombre=datos.nombre.strip(), apellido=(datos.apellido or "").strip(), usuario=datos.usuario.strip(),
                email=datos.email, telefono=datos.telefono, rol=datos.rol, hash_password=hash_password(clave),
                debe_cambiar_password=True, activo=True, creado_por=a.id)
    db.add(u)
    db.flush()
    registrar(db, a.id, "crear_usuario", "usuario", u.id, {"usuario": u.usuario, "rol": u.rol}, ip_de(request))
    db.commit()
    texto, link = _whatsapp(u, clave, True)
    # la contraseña temporal se devuelve UNA sola vez: en la base solo queda su hash
    return UsuarioCreadoOut(usuario=UsuarioOut.model_validate(u), password_temporal=clave, texto_whatsapp=texto,
                            link_whatsapp=link)


@router.patch("/usuarios/{uid}", response_model=UsuarioOut)
def editar(uid: int, datos: UsuarioEditarIn, request: Request, a: Actual = Depends(solo_admin), db: Session = Depends(get_db)):
    u = _usuario(db, uid)
    cambios = datos.model_dump(exclude_unset=True)
    if "usuario" in cambios and _choca(db, Usuario.usuario, cambios["usuario"], uid):
        raise HTTPException(409, "Ya existe un usuario con ese nombre de usuario.")
    if cambios.get("email"):
        cambios["email"] = cambios["email"].strip() or None
        if cambios["email"] and _choca(db, Usuario.email, cambios["email"], uid):
            raise HTTPException(409, "Ya existe un usuario con ese email.")
    if cambios.get("rol") and cambios["rol"] != "admin" and u.rol == "admin" and u.activo and ultimo_admin_activo(db, uid):
        raise HTTPException(400, "No podés quitarle el rol de admin: es el último administrador activo.")
    for k, v in cambios.items():
        setattr(u, k, v)
    registrar(db, a.id, "editar_usuario", "usuario", uid, {"cambios": list(cambios)}, ip_de(request))
    db.commit()
    return u


@router.post("/usuarios/{uid}/desactivar", response_model=UsuarioOut)
def desactivar(uid: int, request: Request, a: Actual = Depends(solo_admin), db: Session = Depends(get_db)):
    u = _usuario(db, uid)
    if uid == a.id:
        raise HTTPException(400, "No podés desactivarte a vos mismo.")
    if u.rol == "admin" and u.activo and ultimo_admin_activo(db, uid):
        raise HTTPException(400, "No podés desactivar al último administrador activo.")
    u.activo = False
    _cerrar_sesiones(db, uid)  # deja de poder usar la app en el acto
    registrar(db, a.id, "desactivar_usuario", "usuario", uid, ip=ip_de(request))
    db.commit()
    return u


@router.post("/usuarios/{uid}/reactivar", response_model=UsuarioOut)
def reactivar(uid: int, request: Request, a: Actual = Depends(solo_admin), db: Session = Depends(get_db)):
    u = _usuario(db, uid)
    u.activo = True
    u.intentos_fallidos = 0
    u.bloqueado_hasta = None
    registrar(db, a.id, "reactivar_usuario", "usuario", uid, ip=ip_de(request))
    db.commit()
    return u


@router.post("/usuarios/{uid}/resetear-password", response_model=UsuarioCreadoOut)
def resetear(uid: int, request: Request, a: Actual = Depends(solo_admin), db: Session = Depends(get_db)):
    u = _usuario(db, uid)
    clave = password_temporal()
    u.hash_password = hash_password(clave)
    u.debe_cambiar_password = True
    u.intentos_fallidos = 0
    u.bloqueado_hasta = None
    _cerrar_sesiones(db, uid)
    registrar(db, a.id, "resetear_password", "usuario", uid, ip=ip_de(request))
    db.commit()
    texto, link = _whatsapp(u, clave, False)
    return UsuarioCreadoOut(usuario=UsuarioOut.model_validate(u), password_temporal=clave, texto_whatsapp=texto,
                            link_whatsapp=link)


@router.get("/usuarios/{uid}/sesiones", response_model=list[SesionOut])
def sesiones(uid: int, a: Actual = Depends(solo_admin), db: Session = Depends(get_db)):
    _usuario(db, uid)
    return sesiones_de(db, uid)


@router.delete("/usuarios/{uid}/sesiones", status_code=204)
def cerrar_todas(uid: int, request: Request, a: Actual = Depends(solo_admin), db: Session = Depends(get_db)):
    _usuario(db, uid)
    _cerrar_sesiones(db, uid)
    registrar(db, a.id, "cerrar_sesiones_usuario", "usuario", uid, ip=ip_de(request))
    db.commit()


@router.get("/actividad", response_model=list[ActividadOut])
def actividad(a: Actual = Depends(solo_admin), db: Session = Depends(get_db), usuario_id: int | None = None,
              q: str | None = Query(None, max_length=60), limite: int = Query(100, ge=1, le=100),
              antes_de_id: int | None = None):
    consulta = select(Actividad).order_by(Actividad.id.desc()).limit(limite)
    if usuario_id:
        consulta = consulta.where(Actividad.user_id == usuario_id)
    if antes_de_id:
        consulta = consulta.where(Actividad.id < antes_de_id)
    if q:
        consulta = consulta.where(or_(Actividad.accion.ilike(f"%{q}%"), Actividad.entidad.ilike(f"%{q}%")))
    filas = db.scalars(consulta).all()
    return [ActividadOut(id=x.id, user_id=x.user_id, accion=x.accion, entidad=x.entidad, entidad_id=x.entidad_id,
                         detalle=x.detalle, ip=str(x.ip) if x.ip else None, creada_en=x.creada_en) for x in filas]
