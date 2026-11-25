"""Modelos de la base central de Radar Prop (PostgreSQL 16 + PostGIS).

Datos compartidos (propiedades, historial de precios, corridas): los escribe solo el worker.
Datos personales (búsquedas, vistas, selecciones, alertas): cada fila tiene user_id.
Datos compartidos editables por personas (clientes, captación): columna `version` para bloqueo optimista.
"""
from datetime import datetime
from decimal import Decimal

from geoalchemy2 import Geography
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _creado():
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ------------------------------------------------------------------ usuarios y sesiones
class Usuario(Base):
    __tablename__ = "usuarios"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80))
    apellido: Mapped[str] = mapped_column(String(80), default="")
    usuario: Mapped[str] = mapped_column(String(60))
    email: Mapped[str | None] = mapped_column(String(160))
    telefono: Mapped[str | None] = mapped_column(String(40))
    rol: Mapped[str] = mapped_column(String(10), default="agente")  # admin | agente
    hash_password: Mapped[str] = mapped_column(Text)
    debe_cambiar_password: Mapped[bool] = mapped_column(Boolean, default=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    intentos_fallidos: Mapped[int] = mapped_column(Integer, default=0)
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = _creado()
    ultimo_ingreso: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index("ux_usuarios_usuario", func.lower(text("usuario")), unique=True),
        Index("ux_usuarios_email", func.lower(text("email")), unique=True, postgresql_where=text("email IS NOT NULL")),
    )


class Sesion(Base):
    __tablename__ = "sesiones"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    refresh_hash: Mapped[str] = mapped_column(String(128), unique=True)
    dispositivo: Mapped[str | None] = mapped_column(String(200))
    ip: Mapped[str | None] = mapped_column(INET)
    creada_en: Mapped[datetime] = _creado()
    ultima_actividad: Mapped[datetime] = _creado()
    expira_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revocada: Mapped[bool] = mapped_column(Boolean, default=False)


# ------------------------------------------------------------------ propiedades (las escribe solo el worker)
class Propiedad(Base):
    __tablename__ = "propiedades"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    plataforma: Mapped[str] = mapped_column(String(10))                 # BBP | IBB | ZP
    id_externo: Mapped[str] = mapped_column(String(300))                # número o slug del aviso en su sitio
    id_legado: Mapped[int | None] = mapped_column(BigInteger, unique=True)  # id de El Ojo de Dios (selecciones, fichas)
    url: Mapped[str | None] = mapped_column(Text)
    titulo: Mapped[str | None] = mapped_column(Text)
    tipo: Mapped[str | None] = mapped_column(String(80))
    operacion: Mapped[str | None] = mapped_column(String(40))
    ciudad: Mapped[str | None] = mapped_column(String(80))
    barrio: Mapped[str | None] = mapped_column(String(120))
    direccion: Mapped[str | None] = mapped_column(Text)
    inmobiliaria: Mapped[str | None] = mapped_column(String(200))
    moneda: Mapped[str | None] = mapped_column(String(5))
    precio: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    precio_ars: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))  # solo si el aviso está en pesos
    precio_anterior: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    cambio_precio: Mapped[datetime | None] = mapped_column(DateTime)
    dormitorios: Mapped[int | None] = mapped_column(Integer)
    ambientes: Mapped[int | None] = mapped_column(Integer)
    banos: Mapped[int | None] = mapped_column(Integer)
    m2_cubiertos: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    m2_totales: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    m2_base: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    patio: Mapped[str | None] = mapped_column(String(40))
    cochera: Mapped[str | None] = mapped_column(String(40))
    pileta: Mapped[str | None] = mapped_column(String(40))
    parrilla: Mapped[str | None] = mapped_column(String(40))
    amoblado: Mapped[str | None] = mapped_column(String(40))
    apto_credito: Mapped[str | None] = mapped_column(String(60))
    pago: Mapped[str | None] = mapped_column(String(80))
    exterior: Mapped[str | None] = mapped_column(Text)
    estacionamiento: Mapped[str | None] = mapped_column(Text)
    expensas: Mapped[str | None] = mapped_column(String(80))
    antiguedad: Mapped[str | None] = mapped_column(String(60))
    estado_inmueble: Mapped[str | None] = mapped_column(String(60))
    detalles: Mapped[dict | None] = mapped_column(JSONB)
    descripcion: Mapped[str | None] = mapped_column(Text)
    fotos: Mapped[list | None] = mapped_column(JSONB)
    lat: Mapped[float | None] = mapped_column(Numeric(10, 7))           # tal cual vino del sitio
    lng: Mapped[float | None] = mapped_column(Numeric(10, 7))
    ubicacion = mapped_column(Geography("POINT", srid=4326, spatial_index=False), nullable=True)  # solo si es válida
    ubicacion_valida: Mapped[bool] = mapped_column(Boolean, default=False)
    # Fecha de publicación: nunca se inventa una hora exacta
    publicada_desde: Mapped[datetime | None] = mapped_column(DateTime)  # ventana detectada_desde -> detectada
    publicada_hasta: Mapped[datetime | None] = mapped_column(DateTime)
    pub_txt: Mapped[str | None] = mapped_column(String(120))            # texto del sitio (IBB)
    pub_aprox: Mapped[datetime | None] = mapped_column(DateTime)        # aproximada (BBP: fecha de las fotos)
    fecha_publicacion: Mapped[datetime | None] = mapped_column(DateTime)  # la mejor estimación, para ordenar
    primera_vez_vista: Mapped[datetime | None] = mapped_column(DateTime)
    ultima_vez_vista: Mapped[datetime | None] = mapped_column(DateTime)
    ultima_verif_origen: Mapped[str | None] = mapped_column(String(40))  # p. ej. "planilla"
    estado: Mapped[str] = mapped_column(String(12), default="activa")     # activa | baja | pendiente
    fecha_baja: Mapped[datetime | None] = mapped_column(DateTime)
    fecha_baja_origen: Mapped[str | None] = mapped_column(String(40))     # p. ej. "planilla"
    intentos: Mapped[int] = mapped_column(Integer, default=0)
    ia_json: Mapped[dict | None] = mapped_column(JSONB)
    ia_resumen: Mapped[str | None] = mapped_column(Text)
    ia_fecha: Mapped[datetime | None] = mapped_column(DateTime)
    ia_intentos: Mapped[int | None] = mapped_column(Integer)
    grupo_duplicado_id: Mapped[int | None] = mapped_column(BigInteger)
    datos_extra: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    creado_en: Mapped[datetime] = _creado()
    actualizado_en: Mapped[datetime] = _creado()
    __table_args__ = (
        UniqueConstraint("plataforma", "id_externo", name="uq_propiedades_plataforma_id"),
        Index("ix_prop_precio", "precio"),
        Index("ix_prop_tipo", "tipo"),
        Index("ix_prop_operacion", "operacion"),
        Index("ix_prop_dormitorios", "dormitorios"),
        Index("ix_prop_barrio", "barrio"),
        Index("ix_prop_estado", "estado"),
        Index("ix_prop_fecha_pub", "fecha_publicacion"),
        Index("ix_prop_plataforma", "plataforma"),
        Index("ix_prop_ubicacion", "ubicacion", postgresql_using="gist"),
    )


class HistorialPrecio(Base):
    __tablename__ = "historial_precios"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    propiedad_id: Mapped[int] = mapped_column(ForeignKey("propiedades.id"), index=True)
    fecha: Mapped[datetime] = mapped_column(DateTime)
    moneda: Mapped[str | None] = mapped_column(String(5))
    precio_anterior: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    precio: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    __table_args__ = (UniqueConstraint("propiedad_id", "fecha", "precio_anterior", "precio", name="uq_hist_precio"),)


class Meta(Base):
    __tablename__ = "meta"
    clave: Mapped[str] = mapped_column(String(80), primary_key=True)
    valor: Mapped[str | None] = mapped_column(Text)
    actualizado_en: Mapped[datetime] = _creado()


class CorridaActualizacion(Base):
    __tablename__ = "corridas_actualizacion"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    modo: Mapped[str] = mapped_column(String(20), default="rapida")
    inicio: Mapped[datetime] = _creado()
    fin: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    nuevas: Mapped[int] = mapped_column(Integer, default=0)
    actualizadas: Mapped[int] = mapped_column(Integer, default=0)
    bajas: Mapped[int] = mapped_column(Integer, default=0)
    cambios_precio: Mapped[int] = mapped_column(Integer, default=0)
    errores: Mapped[int] = mapped_column(Integer, default=0)
    estado: Mapped[str] = mapped_column(String(20), default="corriendo")
    detalle: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))


# ------------------------------------------------------------------ datos por usuario
class Busqueda(Base):
    __tablename__ = "busquedas"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    filtros: Mapped[dict] = mapped_column(JSONB)
    zona: Mapped[dict | None] = mapped_column(JSONB)  # GeoJSON
    cantidad_resultados: Mapped[int | None] = mapped_column(Integer)
    creada_en: Mapped[datetime] = _creado()


class BusquedaGuardada(Base):
    __tablename__ = "busquedas_guardadas"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    filtros: Mapped[dict] = mapped_column(JSONB)
    zona: Mapped[dict | None] = mapped_column(JSONB)
    creada_en: Mapped[datetime] = _creado()


class PropiedadVista(Base):
    __tablename__ = "propiedades_vistas"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    propiedad_id: Mapped[int] = mapped_column(ForeignKey("propiedades.id"))
    precio_al_ver: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    vista_en: Mapped[datetime] = _creado()
    __table_args__ = (Index("ix_vistas_user_fecha", "user_id", "vista_en"),)


class Seleccion(Base):
    __tablename__ = "selecciones"
    user_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), primary_key=True)
    propiedad_id: Mapped[int] = mapped_column(ForeignKey("propiedades.id"), primary_key=True)
    agregada_en: Mapped[datetime] = _creado()


class Cliente(Base):
    """Compradores (en El Ojo de Dios: tabla `pedidos`)."""
    __tablename__ = "clientes"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(160), default="")
    telefono: Mapped[str | None] = mapped_column(String(40))
    pedido: Mapped[str | None] = mapped_column(Text)
    presupuesto: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    moneda: Mapped[str | None] = mapped_column(String(5))
    filtros: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    asignado_a: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), index=True)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = _creado()
    actualizado_en: Mapped[datetime] = _creado()
    version: Mapped[int] = mapped_column(Integer, default=1)
    id_legado: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    __mapper_args__ = {"version_id_col": version}


class Alerta(Base):
    __tablename__ = "alertas"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("clientes.id"))
    filtros: Mapped[dict] = mapped_column(JSONB)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    visto_hasta: Mapped[datetime | None] = mapped_column(DateTime)
    creada_en: Mapped[datetime] = _creado()


class AlertaCoincidencia(Base):
    __tablename__ = "alertas_coincidencias"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    alerta_id: Mapped[int] = mapped_column(ForeignKey("alertas.id"), index=True)
    propiedad_id: Mapped[int] = mapped_column(ForeignKey("propiedades.id"))
    notificada: Mapped[bool] = mapped_column(Boolean, default=False)
    creada_en: Mapped[datetime] = _creado()
    __table_args__ = (UniqueConstraint("alerta_id", "propiedad_id", name="uq_alerta_prop"),)


class FichaGenerada(Base):
    __tablename__ = "fichas_generadas"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("clientes.id"))
    propiedades_ids: Mapped[list] = mapped_column(JSONB)
    tipo: Mapped[str] = mapped_column(String(12))  # web | whatsapp | excel | panel
    enlace: Mapped[str | None] = mapped_column(Text)
    clave_idempotencia: Mapped[str | None] = mapped_column(String(80), unique=True)
    creada_en: Mapped[datetime] = _creado()


class Actividad(Base):
    __tablename__ = "actividad"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), index=True)
    accion: Mapped[str] = mapped_column(String(60))
    entidad: Mapped[str | None] = mapped_column(String(40))
    entidad_id: Mapped[str | None] = mapped_column(String(80))
    detalle: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    ip: Mapped[str | None] = mapped_column(INET)
    creada_en: Mapped[datetime] = _creado()
    __table_args__ = (Index("ix_actividad_fecha", "creada_en"),)


# ------------------------------------------------------------------ captación (sector aparte, hoy vacío)
class CaptacionDueno(Base):
    __tablename__ = "captacion_duenos"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    origen: Mapped[str | None] = mapped_column(String(40))
    url: Mapped[str | None] = mapped_column(Text)
    titulo: Mapped[str | None] = mapped_column(Text)
    tipo: Mapped[str | None] = mapped_column(String(80))
    operacion: Mapped[str | None] = mapped_column(String(40))
    direccion: Mapped[str | None] = mapped_column(Text)
    barrio: Mapped[str | None] = mapped_column(String(120))
    ciudad: Mapped[str | None] = mapped_column(String(80))
    moneda: Mapped[str | None] = mapped_column(String(5))
    precio: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    dormitorios: Mapped[int | None] = mapped_column(Integer)
    m2: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    nombre: Mapped[str | None] = mapped_column(String(160))
    telefono: Mapped[str | None] = mapped_column(String(40))
    notas: Mapped[str | None] = mapped_column(Text)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = _creado()
    version: Mapped[int] = mapped_column(Integer, default=1)
    id_legado: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    __mapper_args__ = {"version_id_col": version}


class CaptacionSeguimiento(Base):
    __tablename__ = "captacion_seguimiento"
    clave: Mapped[str] = mapped_column(String(80), primary_key=True)
    propiedad_id: Mapped[int | None] = mapped_column(ForeignKey("propiedades.id"))
    dueno_id: Mapped[int | None] = mapped_column(ForeignKey("captacion_duenos.id"))
    senal: Mapped[str | None] = mapped_column(String(40))
    estado: Mapped[str] = mapped_column(String(20), default="por_contactar")
    resultado: Mapped[str] = mapped_column(String(20), default="")
    notas: Mapped[str] = mapped_column(Text, default="")
    actualizado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    actualizado_en: Mapped[datetime] = _creado()
    version: Mapped[int] = mapped_column(Integer, default=1)
    __mapper_args__ = {"version_id_col": version}
