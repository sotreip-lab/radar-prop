"""Búsqueda, mapa, detalle y estado de la base. Las propiedades son de solo lectura para los usuarios (las escribe
el worker); lo personal (historial de búsquedas y de propiedades vistas) se guarda por user_id en segundo plano."""
import json
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.deps import Actual, usuario_actual
from app.db import SessionLocal, engine, get_db
from app.models import Busqueda, PropiedadVista, Seleccion
from app.scraper.red import ahora_local
from app.services.catalogo import Filtros, catalogo, lineas_viv
from app.services.textos import resumen_filtros

router = APIRouter(tags=["propiedades"])

SiNo = Literal["", "si", "no"]


class FiltrosIn(BaseModel):
    mon: Literal["USD", "ARS"] = "USD"
    b: float = Field(0, ge=0, le=1e12)
    pct_abajo: float = Field(15, ge=0, le=100)
    rojas: bool = False
    pmin: float = Field(0, ge=0, le=1e12)
    pmax: float = Field(0, ge=0, le=1e12)
    oper: str = Field("Venta", max_length=40)
    ciudad: str = Field("Bahía Blanca", max_length=80)
    tipos: list[str] = Field(default_factory=list, max_length=60)
    barrios: list[str] = Field(default_factory=list, max_length=300)
    sin_barrio: bool = False
    dorm: Literal["", "0", "1", "2", "3", "4", "5"] = ""
    dorm_modo: Literal["exacto", "min"] = "exacto"
    banos: int = Field(0, ge=0, le=20)
    supmin: float = Field(0, ge=0, le=1e7)
    patio: SiNo = ""
    cochera: SiNo = ""
    pileta: SiNo = ""
    balcon: SiNo = ""
    parrilla: SiNo = ""
    amoblado: SiNo = ""
    credito: Literal["", "si", "si_nc"] = ""
    estrenar: bool = False
    kw: str = Field("", max_length=200)
    nuevas_horas: int = Field(0, ge=0, le=24 * 365)
    margen: int = Field(0, ge=0, le=5000)
    sin_dato: bool = False
    sin_ubic: bool = False
    excl: bool = True
    bajas: bool = False
    bajo_precio: bool = False
    margen_neg: bool = False
    dmin: int | None = Field(None, ge=0, le=100000)
    dmax: int | None = Field(None, ge=0, le=100000)
    m2max: float = Field(0, ge=0, le=1e9)
    bajo_min: float = Field(0, ge=0, le=100)
    cuota_max: float = Field(0, ge=0, le=1e12)
    plataforma: Literal["todas", "BBP", "IBB", "ZP"] = "todas"
    qg: str = Field("", max_length=500)
    solo_ids: list[int] | None = Field(None, max_length=5000)
    solo_seleccion: bool = False
    orden: Literal["", "color", "precio", "dif", "usdm2", "detectada", "vsb", "dormitorios", "sup_cub", "tipo", "barrio",
                   "fuente", "direccion", "antiguedad", "inmobiliaria"] = ""
    orden_dir: int = 1


class Zona(BaseModel):
    """Zona dibujada en el mapa: un polígono GeoJSON (el rectángulo también es un polígono)."""
    type: Literal["Polygon"]
    coordinates: list[list[list[float]]] = Field(min_length=1, max_length=1)


class BuscarIn(BaseModel):
    filtros: FiltrosIn = Field(default_factory=lambda: FiltrosIn.model_validate({}))
    zona: Zona | None = None
    offset: int = Field(0, ge=0, le=100000)
    limite: int = Field(50, ge=1, le=100)
    registrar: bool = False  # guardar en "Mi historial" (el navegador lo pide cuando el usuario deja de tocar filtros)


def _zona_dist(zona: Zona | None, margen: int) -> dict[int, float] | None:
    """Con PostGIS: distancia en metros de cada propiedad a la zona (0 = adentro), solo hasta el margen."""
    if zona is None:
        return None
    anillo = zona.coordinates[0]
    if len(anillo) < 4 or len(anillo) > 500:
        raise HTTPException(422, "La zona dibujada no es válida.")
    geo = json.dumps(zona.model_dump())
    with engine.connect() as c:
        filas = c.execute(text(
            "SELECT id, ST_Distance(ubicacion, g) FROM propiedades, "
            "(SELECT ST_SetSRID(ST_GeomFromGeoJSON(:geo), 4326)::geography AS g) z "
            "WHERE ubicacion IS NOT NULL AND ST_DWithin(ubicacion, g, :m)"), {"geo": geo, "m": max(margen, 0)}).all()
    return {i: float(d) for i, d in filas}


def _mi_seleccion(db: Session, uid: int) -> set[int]:
    return set(db.scalars(select(Seleccion.propiedad_id).where(Seleccion.user_id == uid)))


def _registrar_busqueda(uid: int, filtros: dict, zona: dict | None, n: int):
    """No repite la misma búsqueda seguida (por ejemplo, al volver a abrir la app con los mismos filtros)."""
    with SessionLocal() as db:
        ult = db.scalar(select(Busqueda).where(Busqueda.user_id == uid).order_by(Busqueda.id.desc()).limit(1))
        if ult and ult.filtros == filtros and ult.zona == zona:
            ult.cantidad_resultados = n
        else:
            db.add(Busqueda(user_id=uid, filtros=filtros, zona=zona, cantidad_resultados=n))
        db.commit()


def _correr(datos: BuscarIn, a: Actual, db: Session):
    cat = catalogo()
    f = datos.filtros
    F = Filtros.de_dict(f.model_dump(exclude={"solo_seleccion"}))
    sel = _mi_seleccion(db, a.id)
    if f.solo_seleccion:
        F.solo_ids = list(sel)
    return cat, cat.buscar(F, _zona_dist(datos.zona, f.margen if datos.zona else 0)), sel


@router.post("/propiedades/buscar")
def buscar(datos: BuscarIn, tareas: BackgroundTasks, a: Actual = Depends(usuario_actual), db: Session = Depends(get_db)):
    cat, r, sel = _correr(datos, a, db)
    res = r["res"]
    hace24 = (ahora_local() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    pagina = [cat.fila_lista(x, sel, hace24) for x in res[datos.offset:datos.offset + datos.limite]]
    if datos.registrar and datos.offset == 0:
        tareas.add_task(_registrar_busqueda, a.id, datos.filtros.model_dump(exclude_defaults=True),
                        datos.zona.model_dump() if datos.zona else None, len(res))
    return {"total": len(res), "offset": datos.offset, "items": pagina, "plataformas": r["plataformas"], "dups": r["dups"],
            "colores": r["colores"], "sin_ubic_ocultas": r["sin_ubic_ocultas"], "actualizado": cat.ultima,
            "resumen": resumen_filtros(datos.filtros.model_dump(), datos.zona is not None)}


@router.post("/propiedades/mapa")
def mapa(datos: BuscarIn, a: Actual = Depends(usuario_actual), db: Session = Depends(get_db)):
    """Puntos livianos de TODOS los resultados: [id, lat, lng, color, zona, precio, moneda, seleccionada]."""
    cat, r, sel = _correr(datos, a, db)
    puntos, sin = [], 0
    for x in r["res"]:
        o = x["o"]
        if o["lat"] is None:
            sin += 1
            continue
        puntos.append([o["id"], round(o["lat"], 6), round(o["lng"], 6), x["color"], x["zona"] or "",
                       o["precio"], o["moneda"], 1 if o["id"] in sel else 0])
    return {"puntos": puntos, "sin_ubicacion": sin, "sin_ubic_ocultas": r["sin_ubic_ocultas"]}


class LoteIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)


@router.post("/propiedades/lote")
def lote(datos: LoteIn, a: Actual = Depends(usuario_actual), db: Session = Depends(get_db)):
    """Propiedades puntuales (la selección, las de un comprador), en el orden pedido y sin aplicar filtros."""
    cat = catalogo()
    sel = _mi_seleccion(db, a.id)
    hace24 = (ahora_local() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    return [cat.fila_lista({"o": cat.por_id[i], "color": "", "zona": "", "dif": None, "obs": "", "usdm2": None}, sel, hace24)
            for i in datos.ids if i in cat.por_id]


@router.get("/propiedades/opciones")
def opciones(operacion: str = Query("Venta", max_length=40), ciudad: str = Query("", max_length=80),
             a: Actual = Depends(usuario_actual)):
    return catalogo().opciones(operacion, ciudad)


def _registrar_vista(uid: int, pid: int, precio):
    with SessionLocal() as db:
        db.add(PropiedadVista(user_id=uid, propiedad_id=pid, precio_al_ver=precio))
        db.commit()


@router.get("/propiedades/{pid}")
def detalle(pid: int, tareas: BackgroundTasks, a: Actual = Depends(usuario_actual), db: Session = Depends(get_db)):
    cat = catalogo()
    d = cat.detalle(pid)
    if not d:
        raise HTTPException(404, "No encontré esa propiedad.")
    fila = db.execute(text("SELECT descripcion, fotos, datos_extra FROM propiedades WHERE id=:i"), {"i": pid}).first()
    if fila:
        d["descripcion"] = fila[0] or ""
        d["fotos"] = fila[1] or []
    d["seleccionada"] = pid in _mi_seleccion(db, a.id)
    tareas.add_task(_registrar_vista, a.id, pid, d.get("precio_publicado"))
    return d


@router.get("/estado")
def estado(a: Actual = Depends(usuario_actual), db: Session = Depends(get_db)):
    """Última actualización, conteos y novedades (la app lo consulta cada 60 s)."""
    cat = catalogo()
    hace24 = (ahora_local() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    act = [o for o in cat.data if o["estado_aviso"] == "activo"]
    nuevas = sum(1 for o in act if o["detectada"] and o["detectada"] >= hace24)
    ult = db.execute(text("SELECT inicio, fin, estado, nuevas, bajas, cambios_precio FROM corridas_actualizacion "
                          "ORDER BY id DESC LIMIT 1")).first()
    return {"actualizado": cat.ultima, "activas": len(act), "bajas": len(cat.data) - len(act), "nuevas_24h": nuevas,
            "dolar": cat.dolar, "inicio_base": cat.inicio,
            "ultima_corrida": {"fin": ult[1].isoformat() if ult and ult[1] else None, "estado": ult[2] if ult else None,
                               "nuevas": ult[3] if ult else 0, "bajas": ult[4] if ult else 0,
                               "cambios_precio": ult[5] if ult else 0} if ult else None}


@router.get("/credito")
def credito(a: Actual = Depends(usuario_actual)):
    cat = catalogo()
    c = cat.credito
    return {"uva": c.get("uva"), "lineas": lineas_viv(c), "leido": c.get("leido", ""), "lineas_leidas": c.get("lineas_leidas", ""),
            "plazo_anios": c.get("plazo_anios", 20), "dolar": cat.dolar,
            "linea_defecto": cat.ldef}
