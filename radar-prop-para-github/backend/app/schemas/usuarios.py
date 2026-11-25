from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Rol = Literal["admin", "agente"]


class LoginIn(BaseModel):
    usuario: str = Field(min_length=1, max_length=160)  # usuario o email
    password: str = Field(min_length=1, max_length=200)
    dispositivo: str | None = Field(None, max_length=200)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expira_en_seg: int
    debe_cambiar_password: bool
    usuario: "UsuarioOut"


class CambiarPasswordIn(BaseModel):
    actual: str = Field(min_length=1, max_length=200)
    nueva: str = Field(min_length=1, max_length=200)


class UsuarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    apellido: str
    usuario: str
    email: str | None
    telefono: str | None
    rol: str
    activo: bool
    solicitud_pendiente: bool = False
    debe_cambiar_password: bool
    creado_en: datetime
    ultimo_ingreso: datetime | None


def _limpio(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return v or None


class UsuarioCrearIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=80)
    apellido: str = Field("", max_length=80)
    usuario: str = Field(min_length=3, max_length=60, pattern=r"^[A-Za-z0-9._-]+$")
    email: str | None = Field(None, max_length=160, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    telefono: str | None = Field(None, max_length=40)
    rol: Rol = "agente"

    _limpiar = field_validator("email", "telefono", mode="before")(lambda v: _limpio(v))


class SolicitudAccesoIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=80)
    apellido: str = Field("", max_length=80)
    usuario: str = Field(min_length=3, max_length=60, pattern=r"^[A-Za-z0-9._-]+$")
    email: str | None = Field(None, max_length=160, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    telefono: str | None = Field(None, max_length=40)
    password: str = Field(min_length=1, max_length=200)

    _limpiar = field_validator("email", "telefono", mode="before")(lambda v: _limpio(v))


class UsuarioEditarIn(BaseModel):
    nombre: str | None = Field(None, min_length=1, max_length=80)
    apellido: str | None = Field(None, max_length=80)
    usuario: str | None = Field(None, min_length=3, max_length=60, pattern=r"^[A-Za-z0-9._-]+$")
    email: str | None = Field(None, max_length=160)
    telefono: str | None = Field(None, max_length=40)
    rol: Rol | None = None


class UsuarioCreadoOut(BaseModel):
    usuario: UsuarioOut
    password_temporal: str
    texto_whatsapp: str
    link_whatsapp: str | None


class SesionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    dispositivo: str | None
    ip: str | None
    creada_en: datetime
    ultima_actividad: datetime
    actual: bool = False


class ActividadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int | None
    accion: str
    entidad: str | None
    entidad_id: str | None
    detalle: dict
    ip: str | None
    creada_en: datetime


TokenOut.model_rebuild()
