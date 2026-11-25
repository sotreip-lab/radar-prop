"""Compradores (los "pedidos" de El Ojo de Dios) y sus alertas.

- Los compradores son del equipo: todos los ven, cualquiera los edita. Para que dos personas no se pisen, cada
  edición manda la `version` que tenía; si otro lo cambió antes, la respuesta es 409 y la app avisa.
- La alerta es del agente asignado (o de quien lo cargó): solo a él le aparecen las propiedades nuevas que encajan.
- La regla de "encaja" es pedMatch() de ui.html, sin cambios.
"""
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.deps import Actual, usuario_actual
from app.db import get_db
from app.models import Alerta, AlertaCoincidencia, Cliente, Usuario
from app.scraper.red import ahora_local
from app.services.auditoria import registrar
from app.services.catalogo import bandas, catalogo, norm

router = APIRouter(tags=["compradores"])
OTRO_USUARIO = "Otro usuario modificó esto. Recargá para ver los cambios."


class PedidoDatos(BaseModel):
    """Mismos campos que el formulario de compradores de El Ojo de Dios."""
    nombre: str = Field(min_length=1, max_length=160)
    telefono: str = Field("", max_length=40)
    operacion: str = Field("Venta", max_length=40)
    ciudad: str = Field("Bahía Blanca", max_length=80)
    tipos: list[str] = Field(default_factory=list, max_length=20)
    presu: float | None = Field(None, ge=0, le=1e12)
    moneda: str = Field("USD", pattern="^(USD|ARS)$")
    dorm: int | None = Field(None, ge=0, le=20)
    barrios: list[str] = Field(default_factory=list, max_length=50)
    patio: str = Field("", pattern="^(|si)$")
    cochera: str = Field("", pattern="^(|si)$")
    credito: str = Field("", pattern="^(|si)$")
    amoblado: str = Field("", pattern="^(|si|no)$")
    obs: str = Field("", max_length=2000)
    texto: str = Field("", max_length=6000)


class ClienteIn(BaseModel):
    datos: PedidoDatos
    asignado_a: int | None = None
    version: int | None = None  # obligatoria al editar


def coincide(d: dict, o: dict) -> bool:
    """pedMatch() de ui.html."""
    if o["estado_aviso"] != "activo" or o["_excl"]:
        return False
    if o["operacion"] != (d.get("operacion") or "Venta"):
        return False
    if d.get("ciudad") != "" and o["ciudad"] != (d.get("ciudad") or "Bahía Blanca"):
        return False
    tipos = [norm(t) for t in d.get("tipos") or [] if norm(t)]
    if tipos and not any(norm(o["tipo"]).startswith(t[:4]) for t in tipos):
        return False
    if d.get("dorm") not in (None, "") and not (o["dormitorios"] is not None and o["dormitorios"] >= int(d["dorm"])):
        return False
    if d.get("presu"):
        mon = d.get("moneda") or "USD"
        if not o["precio"] or o["moneda"] != mon:
            return False
        top = bandas(float(d["presu"]), mon)["topV"]
        if o["precio"] > top or o["precio"] < float(d["presu"]) * 0.7:
            return False
    barrios = [norm(b) for b in d.get("barrios") or [] if norm(b)]
    if barrios and not any(b in norm(o["_barrio"]) or b in norm(o["direccion"]) for b in barrios):
        return False
    if d.get("patio") == "si" and not re.search(r"patio|jard|parque", f"{o['exterior'] or ''} {o['patio'] or ''}", re.I):
        return False
    if d.get("cochera") == "si" and not (o["estacionamiento"] or "").startswith("Sí"):
        return False
    if d.get("credito") == "si" and o["pago"] != "Apto crédito":
        return False
    if d.get("amoblado") == "si" and not re.match(r"^(Amoblado|Semi|A elec)", o["amoblado"] or ""):
        return False
    if d.get("amoblado") == "no" and re.match(r"^(Amoblado|Semi)", o["amoblado"] or ""):
        return False
    return True


def fecha_alta(o: dict) -> str:
    return o["detectada"] or (o["alta"] + " 00:00:00" if o["alta"] else "")


def _salida(c: Cliente, alerta: Alerta | None, usuarios: dict[int, str]) -> dict:
    cat = catalogo()
    d = c.filtros or {}
    todas = [o for o in cat.data if coincide(d, o)]
    visto = alerta.visto_hasta.strftime("%Y-%m-%d %H:%M:%S") if alerta and alerta.visto_hasta else ""
    nuevas = [o["id"] for o in todas if fecha_alta(o) > visto] if alerta else []
    return {"id": c.id, "version": c.version, "datos": d, "activo": c.activo, "asignado_a": c.asignado_a,
            "asignado_nombre": usuarios.get(c.asignado_a or 0), "creado_por": c.creado_por,
            "creado_en": c.creado_en.isoformat() if c.creado_en else None, "coinciden": len(todas),
            "ids": [o["id"] for o in todas][:500], "nuevas": nuevas, "es_mia": bool(alerta), "alerta_id": alerta.id if alerta else None}


def _alerta_de(db: Session, c: Cliente) -> None:
    """La alerta queda a nombre del agente asignado (o de quien lo cargó) y con los mismos filtros."""
    dueno = c.asignado_a or c.creado_por
    alertas = list(db.scalars(select(Alerta).where(Alerta.cliente_id == c.id)))
    actual = next((x for x in alertas if x.user_id == dueno), None)
    for x in alertas:
        if x is not actual:
            x.activa = False
    if dueno and c.activo:
        if actual is None:
            db.add(Alerta(user_id=dueno, cliente_id=c.id, filtros=c.filtros, activa=True, visto_hasta=ahora_local()))
        else:
            actual.filtros, actual.activa = c.filtros, True
    elif actual is not None:
        actual.activa = False


def _usuarios(db: Session) -> dict[int, str]:
    return {u.id: f"{u.nombre} {u.apellido}".strip() for u in db.scalars(select(Usuario))}


@router.get("/equipo/nombres")
def nombres(a: Actual = Depends(usuario_actual), db: Session = Depends(get_db)):
    """Solo nombre e id de los usuarios activos (para asignar compradores). Los datos completos son del admin."""
    return [{"id": u.id, "nombre": f"{u.nombre} {u.apellido}".strip()}
            for u in db.scalars(select(Usuario).where(Usuario.activo.is_(True)).order_by(Usuario.nombre))]


@router.get("/clientes")
def listar(solo_mios: bool = Query(False), a: Actual = Depends(usuario_actual), db: Session = Depends(get_db)):
    mias = {x.cliente_id: x for x in db.scalars(select(Alerta).where(Alerta.user_id == a.id, Alerta.activa.is_(True)))}
    q = select(Cliente).where(Cliente.activo.is_(True)).order_by(Cliente.id)
    us = _usuarios(db)
    return [_salida(c, mias.get(c.id), us) for c in db.scalars(q) if not solo_mios or c.id in mias]


@router.post("/clientes", status_code=201)
def crear(datos: ClienteIn, a: Actual = Depends(usuario_actual), db: Session = Depends(get_db)):
    d = datos.datos.model_dump()
    c = Cliente(nombre=d["nombre"], telefono=d["telefono"] or None, pedido=d["texto"] or d["obs"] or None, presupuesto=d["presu"],
                moneda=d["moneda"], filtros=d, activo=True, asignado_a=datos.asignado_a or a.id, creado_por=a.id)
    db.add(c)
    db.flush()
    _alerta_de(db, c)
    registrar(db, a.id, "crear_comprador", "cliente", c.id, {"nombre": c.nombre})
    db.commit()
    return {"id": c.id, "version": c.version}


@router.put("/clientes/{cid}")
def editar(cid: int, datos: ClienteIn, a: Actual = Depends(usuario_actual), db: Session = Depends(get_db)):
    c = db.get(Cliente, cid, with_for_update=True)
    if not c or not c.activo:
        raise HTTPException(404, "No encontré ese comprador.")
    if datos.version is None or datos.version != c.version:
        raise HTTPException(409, OTRO_USUARIO)
    d = datos.datos.model_dump()
    c.nombre, c.telefono, c.filtros = d["nombre"], d["telefono"] or None, d
    c.pedido, c.presupuesto, c.moneda = d["texto"] or d["obs"] or None, d["presu"], d["moneda"]
    if datos.asignado_a:
        c.asignado_a = datos.asignado_a
    _alerta_de(db, c)
    registrar(db, a.id, "editar_comprador", "cliente", c.id)
    db.commit()
    return {"id": c.id, "version": c.version}


@router.delete("/clientes/{cid}", status_code=204)
def borrar(cid: int, version: int = Query(...), a: Actual = Depends(usuario_actual), db: Session = Depends(get_db)):
    c = db.get(Cliente, cid, with_for_update=True)
    if not c:
        raise HTTPException(404, "No encontré ese comprador.")
    if version != c.version:
        raise HTTPException(409, OTRO_USUARIO)
    c.activo = False  # nunca se borra: queda en el historial
    _alerta_de(db, c)
    registrar(db, a.id, "borrar_comprador", "cliente", c.id)
    db.commit()


@router.post("/clientes/{cid}/visto", status_code=204)
def marcar_visto(cid: int, a: Actual = Depends(usuario_actual), db: Session = Depends(get_db)):
    al = db.scalar(select(Alerta).where(Alerta.cliente_id == cid, Alerta.user_id == a.id, Alerta.activa.is_(True)))
    if not al:
        raise HTTPException(404, "Ese comprador no es tuyo.")
    al.visto_hasta = ahora_local()
    db.commit()


@router.get("/notificaciones")
def notificaciones(a: Actual = Depends(usuario_actual), db: Session = Depends(get_db)):
    """Propiedades nuevas que encajan con MIS compradores. Quedan registradas en alertas_coincidencias."""
    cat = catalogo()
    out = []
    alertas = list(db.scalars(select(Alerta).where(Alerta.user_id == a.id, Alerta.activa.is_(True))))
    for al in alertas:
        c = db.get(Cliente, al.cliente_id) if al.cliente_id else None
        if not c or not c.activo:
            continue
        visto = al.visto_hasta.strftime("%Y-%m-%d %H:%M:%S") if al.visto_hasta else ""
        nuevas = [o for o in cat.data if fecha_alta(o) > visto and coincide(c.filtros or {}, o)]
        if nuevas:
            db.execute(insert(AlertaCoincidencia).values([{"alerta_id": al.id, "propiedad_id": o["id"]} for o in nuevas[:500]])
                       .on_conflict_do_nothing(constraint="uq_alerta_prop"))
            out.append({"cliente_id": c.id, "nombre": c.nombre, "nuevas": [o["id"] for o in nuevas][:200], "cantidad": len(nuevas)})
    db.commit()
    return {"total": sum(x["cantidad"] for x in out), "compradores": out}
