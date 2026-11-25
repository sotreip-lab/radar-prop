"""Registro de actividad (auditoría): quién hizo qué y cuándo."""
from sqlalchemy.orm import Session

from app.models import Actividad


def registrar(db: Session, user_id: int | None, accion: str, entidad: str | None = None, entidad_id=None,
              detalle: dict | None = None, ip: str | None = None) -> None:
    db.add(Actividad(user_id=user_id, accion=accion, entidad=entidad,
                     entidad_id=None if entidad_id is None else str(entidad_id), detalle=detalle or {}, ip=ip))
