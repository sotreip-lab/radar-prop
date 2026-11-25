"""Mi cuenta: mis datos y mis sesiones abiertas."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import Actual, ip_de, usuario_logueado
from app.db import get_db
from app.models import Sesion
from app.schemas.usuarios import SesionOut, UsuarioOut
from app.services.auditoria import registrar

router = APIRouter(prefix="/me", tags=["mi cuenta"])


def sesiones_de(db: Session, user_id: int, actual_id: int | None = None) -> list[SesionOut]:
    filas = db.scalars(select(Sesion).where(Sesion.user_id == user_id, Sesion.revocada.is_(False))
                       .order_by(Sesion.ultima_actividad.desc())).all()
    return [SesionOut(id=s.id, dispositivo=s.dispositivo, ip=str(s.ip) if s.ip else None, creada_en=s.creada_en,
                      ultima_actividad=s.ultima_actividad, actual=s.id == actual_id) for s in filas]


@router.get("", response_model=UsuarioOut)
def yo(a: Actual = Depends(usuario_logueado)):
    return a.usuario


@router.get("/sesiones", response_model=list[SesionOut])
def mis_sesiones(a: Actual = Depends(usuario_logueado), db: Session = Depends(get_db)):
    return sesiones_de(db, a.id, a.sesion_id)


@router.delete("/sesiones/{sesion_id}", status_code=204)
def cerrar_sesion(sesion_id: int, request: Request, a: Actual = Depends(usuario_logueado), db: Session = Depends(get_db)):
    s = db.get(Sesion, sesion_id)
    if not s or s.user_id != a.id:  # nunca se puede tocar la sesión de otro usuario
        raise HTTPException(404, "No encontramos esa sesión.")
    s.revocada = True
    registrar(db, a.id, "cerrar_sesion", "sesion", sesion_id, ip=ip_de(request))
    db.commit()
