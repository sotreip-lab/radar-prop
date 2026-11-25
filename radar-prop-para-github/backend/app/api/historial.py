"""Mi historial (búsquedas, propiedades vistas, fichas) y búsquedas guardadas.

Cada usuario ve solo lo suyo. El admin puede pedir el de otro con ?usuario_id= (y queda en la auditoría).
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.deps import Actual, usuario_actual
from app.db import get_db
from app.models import Busqueda, BusquedaGuardada, Cliente, FichaGenerada, PropiedadVista, Usuario
from app.scraper.red import ZONA
from app.services.auditoria import registrar
from app.services.catalogo import Filtros, catalogo
from app.services.textos import resumen_filtros

router = APIRouter(prefix="/historial", tags=["historial"])
guardadas = APIRouter(prefix="/busquedas-guardadas", tags=["historial"])


def _de_quien(a: Actual, usuario_id: int | None, db: Session) -> int:
    if usuario_id is None or usuario_id == a.id:
        return a.id
    if not a.es_admin:
        raise HTTPException(403, "Solo podés ver tu propio historial.")
    if not db.get(Usuario, usuario_id):
        raise HTTPException(404, "No existe ese usuario.")
    return usuario_id


def _rango(q, col, desde: datetime | None, hasta: datetime | None):
    if desde:
        q = q.where(col >= desde)
    if hasta:
        q = q.where(col <= hasta)
    return q


def _nuevas_desde(filtros: dict, desde: datetime) -> int:
    """Cuántas propiedades de esa búsqueda aparecieron después (con la ventana de publicación real)."""
    try:
        F = Filtros.de_dict(filtros)
    except Exception:
        return 0
    local = desde.astimezone(ZONA).replace(tzinfo=None) if desde.tzinfo else desde  # las fechas de la base son de Bahía Blanca
    corte = local.strftime("%Y-%m-%d %H:%M:%S")
    r = catalogo().buscar(F)
    return sum(1 for x in r["res"] if (x["o"]["detectada"] or "") > corte)


@router.get("/busquedas")
def busquedas(q: str = Query("", max_length=100), desde: datetime | None = None, hasta: datetime | None = None,
              usuario_id: int | None = None, antes_de_id: int | None = None, a: Actual = Depends(usuario_actual),
              db: Session = Depends(get_db)):
    uid = _de_quien(a, usuario_id, db)
    sel = _rango(select(Busqueda).where(Busqueda.user_id == uid), Busqueda.creada_en, desde, hasta)
    if antes_de_id:
        sel = sel.where(Busqueda.id < antes_de_id)
    filas = list(db.scalars(sel.order_by(Busqueda.id.desc()).limit(200 if q else 30)))
    out = []
    for b in filas:
        texto = resumen_filtros(b.filtros or {}, bool(b.zona))
        if q and q.lower() not in texto.lower():
            continue
        out.append({"id": b.id, "creada_en": b.creada_en.isoformat(), "texto": texto, "filtros": b.filtros, "zona": b.zona,
                    "cantidad": b.cantidad_resultados, "nuevas": _nuevas_desde(b.filtros or {}, b.creada_en) if not b.zona else None})
        if len(out) >= 30:
            break
    return out


@router.get("/vistas")
def vistas(q: str = Query("", max_length=100), desde: datetime | None = None, hasta: datetime | None = None,
           usuario_id: int | None = None, a: Actual = Depends(usuario_actual), db: Session = Depends(get_db)):
    """Las últimas 200 propiedades vistas (una vez cada una), con el precio de hoy y si cambió o se dio de baja."""
    uid = _de_quien(a, usuario_id, db)
    ult = _rango(select(PropiedadVista.propiedad_id, func.max(PropiedadVista.vista_en).label("vista"),
                        func.min(PropiedadVista.precio_al_ver).label("precio_al_ver"))
                 .where(PropiedadVista.user_id == uid), PropiedadVista.vista_en, desde, hasta)
    filas = db.execute(ult.group_by(PropiedadVista.propiedad_id).order_by(func.max(PropiedadVista.vista_en).desc()).limit(200)).all()
    cat = catalogo()
    out = []
    for pid, vista, p_ver in filas:
        o = cat.por_id.get(pid)
        if not o:
            continue
        if q and q.lower() not in (o["_n"] + " " + (o["tipo"] or "").lower()):
            continue
        ahora = o["precio_publicado"]
        out.append({"id": pid, "vista_en": vista.isoformat(), "tipo": o["tipo"], "barrio": o["barrio"], "direccion": o["direccion"],
                    "moneda": o["moneda"], "precio": ahora, "precio_al_ver": float(p_ver) if p_ver is not None else None,
                    "cambio_precio": bool(p_ver is not None and ahora is not None and abs(float(p_ver) - ahora) > 0.5),
                    "baja": o["estado_aviso"] == "baja", "foto": o["foto"], "fuente": o["fuente"], "url": o["url"]})
    return out


@router.get("/fichas")
def fichas(desde: datetime | None = None, hasta: datetime | None = None, usuario_id: int | None = None,
           a: Actual = Depends(usuario_actual), db: Session = Depends(get_db)):
    uid = _de_quien(a, usuario_id, db)
    filas = db.execute(_rango(select(FichaGenerada, Cliente.nombre).outerjoin(Cliente, Cliente.id == FichaGenerada.cliente_id)
                              .where(FichaGenerada.user_id == uid), FichaGenerada.creada_en, desde, hasta)
                       .order_by(FichaGenerada.id.desc()).limit(200)).all()
    return [{"id": f.id, "tipo": f.tipo, "enlace": f.enlace, "cantidad": len(f.propiedades_ids or []), "cliente": nombre,
             "creada_en": f.creada_en.isoformat()} for f, nombre in filas]


@router.delete("", status_code=204)
def borrar_mi_historial(a: Actual = Depends(usuario_actual), db: Session = Depends(get_db)):
    """Borra MI historial de búsquedas y de propiedades vistas (las fichas enviadas quedan: son registro de trabajo)."""
    db.execute(delete(Busqueda).where(Busqueda.user_id == a.id))
    db.execute(delete(PropiedadVista).where(PropiedadVista.user_id == a.id))
    registrar(db, a.id, "borrar_historial", "usuario", a.id)
    db.commit()


# ------------------------------------------------------------------ búsquedas guardadas
class GuardarIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    filtros: dict
    zona: dict | None = None


@guardadas.get("")
def listar(a: Actual = Depends(usuario_actual), db: Session = Depends(get_db)):
    return [{"id": g.id, "nombre": g.nombre, "filtros": g.filtros, "zona": g.zona, "texto": resumen_filtros(g.filtros or {}, bool(g.zona)),
             "creada_en": g.creada_en.isoformat()}
            for g in db.scalars(select(BusquedaGuardada).where(BusquedaGuardada.user_id == a.id).order_by(BusquedaGuardada.id.desc()))]


@guardadas.post("", status_code=201)
def guardar(datos: GuardarIn, a: Actual = Depends(usuario_actual), db: Session = Depends(get_db)):
    g = BusquedaGuardada(user_id=a.id, nombre=datos.nombre.strip(), filtros=datos.filtros, zona=datos.zona)
    db.add(g)
    db.commit()
    return {"id": g.id}


@guardadas.delete("/{gid}", status_code=204)
def borrar(gid: int, a: Actual = Depends(usuario_actual), db: Session = Depends(get_db)):
    db.execute(delete(BusquedaGuardada).where(BusquedaGuardada.id == gid, BusquedaGuardada.user_id == a.id))
    db.commit()
