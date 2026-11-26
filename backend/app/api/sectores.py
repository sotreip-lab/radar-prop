"""Mapa de valores (m² por zona según bajas probablemente vendidas) y Captación (dueños directos + señales).
Mismo cálculo que los sectores de El Ojo de Dios; los datos salen de la base central."""
import csv
import io
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import Actual, usuario_actual
from app.db import get_db
from app.models import CaptacionDueno, CaptacionSeguimiento
from app.scraper.red import ahora_local
from app.services.auditoria import registrar
from app.services.catalogo import catalogo
from app.services.planillas import leer_xlsx
from app.services.sectores import captacion, comun, mercado, zonas

router = APIRouter(tags=["sectores"])
OTRO_USUARIO = "Otro usuario modificó esto. Recargá para ver los cambios."
_CACHE: dict = {"v": None, "t": 0.0, "datos": None}
_CACHE_CAP: dict = {"v": None, "datos": None}
_LOCK = threading.Lock()
_LOCK_CAP = threading.Lock()

CAMPOS_LEGADO = ("id", "tipo", "operacion", "direccion", "barrio", "ciudad", "inmobiliaria", "moneda", "dormitorios",
                 "sup_cub", "sup_tot", "m2_base", "lat", "lng", "estado_aviso", "fecha_baja", "detectada", "pub_aprox",
                 "alta", "fuente", "url", "titulo", "descripcion")


def filas_legado() -> list[dict]:
    """Propiedades con los nombres de columna de El Ojo de Dios (el precio tal cual se publicó)."""
    return [{**{k: o[k] for k in CAMPOS_LEGADO}, "precio": o["precio_publicado"]} for o in catalogo().data]


def _dolar() -> float:
    return float(catalogo().dolar.get("valor") or 0)


def _marcas(db: Session) -> dict:
    return {pid: res for pid, res in db.execute(
        select(CaptacionSeguimiento.propiedad_id, CaptacionSeguimiento.resultado)
        .where(CaptacionSeguimiento.propiedad_id.is_not(None), CaptacionSeguimiento.resultado.in_(("vendida", "no_vendida"))))}


# ------------------------------------------------------------------ mapa de valores
@router.get("/mercado")
def mercado_datos(forzar: bool = False, a: Actual = Depends(usuario_actual), db: Session = Depends(get_db)):
    cat = catalogo()
    marcas = _marcas(db)
    clave = (cat.version, tuple(sorted(marcas.items())))
    with _LOCK:
        if forzar or _CACHE["datos"] is None or _CACHE["v"] != clave or time.monotonic() - _CACHE["t"] > 600:
            _CACHE["datos"] = mercado.calcular(filas_legado(), _dolar(), marcas, cat.inicio)
            _CACHE["v"], _CACHE["t"] = clave, time.monotonic()
        return _CACHE["datos"]


@router.get("/mercado/capa")
def mercado_capa(c: str = Query("barrios", pattern="^(barrios|cpu)$"), a: Actual = Depends(usuario_actual)):
    return zonas.para_mapa(c)


# ------------------------------------------------------------------ captación
def _seguimiento(db: Session) -> dict:
    return {s.clave: {"clave": s.clave, "prop_id": s.propiedad_id, "dueno_id": s.dueno_id, "senal": s.senal, "estado": s.estado,
                      "resultado": s.resultado, "notas": s.notas, "version": s.version,
                      "actualizado": s.actualizado_en.isoformat() if s.actualizado_en else None}
            for s in db.scalars(select(CaptacionSeguimiento))}


def _duenos_legado(db: Session) -> list[dict]:
    return [{"id": d.id, "origen": d.origen, "url": d.url, "titulo": d.titulo, "tipo": d.tipo, "operacion": d.operacion,
             "direccion": d.direccion, "barrio": d.barrio, "ciudad": d.ciudad, "moneda": d.moneda,
             "precio": float(d.precio) if d.precio is not None else None, "dorm": d.dormitorios,
             "m2": float(d.m2) if d.m2 is not None else None, "nombre": d.nombre, "telefono": d.telefono, "notas": d.notas,
             "alta": d.creado_en.strftime("%Y-%m-%d %H:%M") if d.creado_en else "", "version": d.version}
            for d in db.scalars(select(CaptacionDueno).where(CaptacionDueno.activo.is_(True)).order_by(CaptacionDueno.id.desc()))]


@router.get("/captacion")
def captacion_datos(a: Actual = Depends(usuario_actual), db: Session = Depends(get_db)):
    s, MED, activas, dolar = _senales()
    return {"senales": s, "duenos": captacion.duenos(MED, _duenos_legado(db), activas, dolar),
            "seguimiento": _seguimiento(db), "dolar": dolar}


def _senales():
    """Las señales de captación solo cambian cuando llegan datos nuevos: se calculan una vez por versión del catálogo."""
    cat = catalogo()
    with _LOCK_CAP:
        if _CACHE_CAP["v"] != cat.version or _CACHE_CAP["datos"] is None:
            filas = filas_legado()
            hist = {o["id"]: [(x[1], x[2]) for x in o["hist"] if x[1] is not None and x[2] is not None] for o in cat.data if o["hist"]}
            dolar = _dolar()
            s, med = captacion.senales(filas, hist, dolar)
            _CACHE_CAP["datos"] = (s, med, [f for f in filas if f["estado_aviso"] == "activo"], dolar)
            _CACHE_CAP["v"] = cat.version
        return _CACHE_CAP["datos"]


def precalentar(db: Session) -> None:
    """Deja calculado lo pesado apenas arranca el servidor, para que la primera persona no espere."""
    mercado_datos(db=db, a=None)  # type: ignore[arg-type]
    _senales()


class SeguirIn(BaseModel):
    clave: str = Field(min_length=1, max_length=80)
    prop_id: int | None = None
    dueno_id: int | None = None
    senal: str = Field("", max_length=40)
    estado: str | None = Field(None, pattern="^(por_contactar|contactado|captada|descartada)$")
    resultado: str | None = Field(None, pattern="^(|vendida|no_vendida)$")
    notas: str | None = Field(None, max_length=2000)
    version: int | None = None


@router.post("/captacion/seguir")
def seguir(datos: SeguirIn, a: Actual = Depends(usuario_actual), db: Session = Depends(get_db)):
    s = db.get(CaptacionSeguimiento, datos.clave, with_for_update=True)
    if s is None:
        s = CaptacionSeguimiento(clave=datos.clave, propiedad_id=datos.prop_id, dueno_id=datos.dueno_id, senal=datos.senal,
                                 estado="por_contactar", resultado="", notas="")
        db.add(s)
    elif datos.version is not None and datos.version != s.version:
        raise HTTPException(409, OTRO_USUARIO)
    for k in ("estado", "resultado", "notas"):
        v = getattr(datos, k)
        if v is not None:
            setattr(s, k, v)
    s.actualizado_por = a.id
    s.actualizado_en = ahora_local()
    db.commit()
    return {"ok": True, "version": s.version}


class DuenoIn(BaseModel):
    datos: dict = Field(default_factory=dict)
    id: int | None = None
    borrar: int | None = None
    version: int | None = None


def _guardar_dueno(db: Session, d: dict, origen: str, uid: int) -> tuple[int, bool]:
    d = captacion._limpiar(d)
    if not (d.get("url") or d.get("direccion") or d.get("telefono")):
        raise ValueError("Cargá al menos el link, la dirección o el teléfono")
    campos = {"dormitorios" if k == "dorm" else k: v for k, v in d.items()}
    if d.get("url"):
        ya = db.scalar(select(CaptacionDueno).where(CaptacionDueno.url == d["url"], CaptacionDueno.activo.is_(True)))
        if ya:
            for k, v in campos.items():
                if k != "origen":
                    setattr(ya, k, v)
            return ya.id, False
    campos.setdefault("origen", origen)
    nuevo = CaptacionDueno(**campos, creado_por=uid, activo=True)
    db.add(nuevo)
    db.flush()
    return nuevo.id, True


@router.post("/captacion/dueno")
def dueno(datos: DuenoIn, a: Actual = Depends(usuario_actual), db: Session = Depends(get_db)):
    if datos.borrar:
        d = db.get(CaptacionDueno, datos.borrar)
        if d:
            d.activo = False
            registrar(db, a.id, "borrar_dueno", "captacion_dueno", d.id)
            db.commit()
        return {"ok": True}
    try:
        if datos.id:
            d = db.get(CaptacionDueno, datos.id, with_for_update=True)
            if not d:
                raise HTTPException(404, "No encontré ese dueño.")
            if datos.version is not None and datos.version != d.version:
                raise HTTPException(409, OTRO_USUARIO)
            for k, v in captacion._limpiar(datos.datos).items():
                if k != "origen":
                    setattr(d, "dormitorios" if k == "dorm" else k, v)
            db.commit()
            return {"ok": True}
        nid, nuevo = _guardar_dueno(db, datos.datos, "Manual", a.id)
        db.commit()
        return {"ok": True, "id": nid, "nuevo": nuevo}
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


@router.post("/captacion/importar")
async def importar(request: Request, nombre: str = Query("planilla.xlsx", max_length=200), a: Actual = Depends(usuario_actual),
                   db: Session = Depends(get_db)):
    data = await request.body()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "La planilla es muy grande (máximo 15 MB).")
    try:
        if nombre.lower().endswith((".xlsx", ".xlsm")):
            hojas = [(n, f) for n, f, _ in leer_xlsx(data)]
        else:
            txt = data.decode("utf-8-sig", "replace")
            dia = csv.Sniffer().sniff(txt[:2000], delimiters=";,\t") if txt.strip() else csv.excel
            hojas = [("csv", list(csv.reader(io.StringIO(txt), dia)))]
    except Exception:
        raise HTTPException(400, "No pude leer la planilla. Guardala como .xlsx o .csv y probá de nuevo.") from None
    nuevos = act = 0
    for _, filas in hojas:
        hi, mapa = None, {}
        for i, f in enumerate(filas[:10]):
            m = {}
            for j, c in enumerate(f):
                cn = comun.norm(str(c))
                for k, alias in captacion.CAMPOS.items():
                    if k not in m and any(cn == comun.norm(x) or cn.startswith(comun.norm(x) + " ") for x in alias):
                        m[k] = j
            if len(m) >= 2:
                hi, mapa = i, m
                break
        if hi is None:
            continue
        for f in filas[hi + 1:]:
            d = {k: (f[j] if j < len(f) else "") for k, j in mapa.items()}
            if not any(str(v).strip() for v in d.values()):
                continue
            try:
                _, es_nuevo = _guardar_dueno(db, d, "Planilla", a.id)
                nuevos += es_nuevo
                act += not es_nuevo
            except ValueError:
                pass
    registrar(db, a.id, "importar_duenos", "captacion_dueno", None, {"nuevos": nuevos, "actualizados": act})
    db.commit()
    return {"ok": True, "nuevos": nuevos, "actualizados": act}
