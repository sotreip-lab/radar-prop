"""Mapa de valores, paso 1: eventos de cada aviso y agrupación de avisos en inmuebles.

Un *inmueble* junta todos los avisos de una misma propiedad física en venta:
- el mismo inmueble publicado a la vez en BBP e IBB, y
- el mismo inmueble que se da de baja y se vuelve a publicar (republicación), para que el tiempo en el
  mercado cuente desde la primera vez y no se reinicie.

Reglas para decir "es el mismo inmueble" (precisión antes que cobertura: si hay dudas, NO se une):
1. Mismo grupo de tipo (Departamento, Casa, Terreno...) y misma operación.
2. Misma dirección normalizada, o a <= `republicacion_metros` si alguna de las dos no tiene número.
   Si las dos tienen dirección con número y son distintas, no se unen aunque estén cerca.
   La distancia no se usa si esas coordenadas se repiten en 3 o más avisos (loteos, punto genérico del barrio).
3. m² conocidos en los dos y con diferencia <= `republicacion_m2_pct` %.
4. Departamentos: misma cantidad de dormitorios (conocida en los dos).
5. Nunca se unen dos avisos del mismo portal que estuvieron activos al mismo tiempo (dos unidades
   iguales en un mismo edificio).
5b. Si los dos tienen precio real (no de relleno) en la misma moneda: hasta
   `republicacion_precio_pct_simultaneo` % de diferencia si estuvieron publicados a la vez, o
   `republicacion_precio_pct` % si es una republicación (pudo haber bajado el precio).
6. Si el inmueble ya no tenía avisos activos, el aviso nuevo tiene que aparecer dentro de
   `republicacion_max_dias` desde la última baja; si no, se toma como una venta nueva.

Todo queda rastreable: `inmueble_avisos.regla` y `detalle` dicen por qué se unió cada aviso.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta

from sqlalchemy import BigInteger, Column, Float, Integer, MetaData, String, Table, insert, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.services.sectores.comun import clave_direccion, grupo_tipo, precio_valido

log = logging.getLogger("radar.valuacion")

OPERACIONES = ("Venta",)
DEFAULTS = {"republicacion_max_dias": 120, "republicacion_metros": 30, "republicacion_m2_pct": 5,
            "republicacion_precio_pct_simultaneo": 15, "republicacion_precio_pct": 30}


# ------------------------------------------------------------------ configuración
def umbrales(db: Session) -> dict[str, float]:
    filas = db.execute(text("SELECT clave, valor FROM config_umbrales")).all()
    return {**DEFAULTS, **{c: float(v) for c, v in filas}}


# ------------------------------------------------------------------ eventos
_INS_EVENTO = text(
    "INSERT INTO eventos_aviso (propiedad_id, tipo, fecha, exacta, moneda, precio, precio_anterior, origen) "
    "VALUES (:pid, :tipo, :fecha, :exacta, :moneda, :precio, :ant, :origen) "
    "ON CONFLICT ON CONSTRAINT uq_evento_aviso DO NOTHING")


def registrar_evento(db: Session, propiedad_id: int, tipo: str, fecha: datetime, *, moneda=None, precio=None,
                     precio_anterior=None, exacta: bool = True, origen: str = "corrida"):
    db.execute(_INS_EVENTO, {"pid": propiedad_id, "tipo": tipo, "fecha": fecha, "exacta": exacta, "moneda": moneda,
                             "precio": precio, "ant": precio_anterior, "origen": origen})


def inicio_seguimiento(db: Session) -> datetime | None:
    """Desde cuándo Radar Prop ve los avisos aparecer. Lo que ya estaba ese día no tiene alta exacta."""
    v = db.scalar(text("SELECT valor FROM meta WHERE clave = 'seguimiento_desde'"))
    if v:
        return datetime.fromisoformat(v)
    m = db.scalar(text("SELECT min(primera_vez_vista) FROM propiedades"))
    if m is not None:
        db.execute(text("INSERT INTO meta (clave, valor) VALUES ('seguimiento_desde', :v) "
                        "ON CONFLICT (clave) DO NOTHING"), {"v": m.isoformat(sep=" ")})
    return m


def reconstruir_historico(db: Session) -> dict[str, int]:
    """Eventos para lo que ya estaba en la base antes de este módulo. Idempotente.
    - alta: si el aviso apareció después del primer día de seguimiento, la fecha es exacta (primera vez visto).
      Si ya estaba, se usa la fecha de publicación estimada; es exacta solo si el actualizador viejo la detectó
      en una ventana de 2 días o menos (BBP), y si no queda marcada como aproximada.
    - baja: fecha_baja detectada por el actualizador (aproximada si vino de una planilla).
    - precio: historial de precios."""
    ini = inicio_seguimiento(db)
    corte = (ini + timedelta(days=1)) if ini else datetime(1900, 1, 1)
    altas = db.execute(text(
        "INSERT INTO eventos_aviso (propiedad_id, tipo, fecha, exacta, moneda, precio, origen) "
        "SELECT p.id, 'alta', "
        "  CASE WHEN p.primera_vez_vista > :corte THEN p.primera_vez_vista "
        "       ELSE COALESCE(LEAST(p.fecha_publicacion, p.primera_vez_vista), p.primera_vez_vista, "
        "                     p.creado_en::timestamp) END, "
        "  COALESCE(p.primera_vez_vista > :corte, false) OR COALESCE(p.publicada_hasta - p.publicada_desde "
        "    <= interval '2 days' AND p.fecha_publicacion = p.publicada_hasta, false), p.moneda, "
        "  COALESCE((SELECT h.precio_anterior FROM historial_precios h WHERE h.propiedad_id = p.id "
        "            ORDER BY h.fecha LIMIT 1), p.precio), 'historico' "
        "FROM propiedades p "
        "WHERE NOT EXISTS (SELECT 1 FROM eventos_aviso e WHERE e.propiedad_id = p.id AND e.tipo = 'alta') "
        "ON CONFLICT ON CONSTRAINT uq_evento_aviso DO NOTHING"), {"corte": corte}).rowcount
    bajas = db.execute(text(
        "INSERT INTO eventos_aviso (propiedad_id, tipo, fecha, exacta, moneda, precio, origen) "
        "SELECT p.id, 'baja', p.fecha_baja, p.fecha_baja_origen IS NULL, p.moneda, p.precio, 'historico' "
        "FROM propiedades p WHERE p.estado = 'baja' AND p.fecha_baja IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM eventos_aviso e WHERE e.propiedad_id = p.id AND e.tipo = 'baja') "
        "ON CONFLICT ON CONSTRAINT uq_evento_aviso DO NOTHING")).rowcount
    precios = db.execute(text(
        "INSERT INTO eventos_aviso (propiedad_id, tipo, fecha, exacta, moneda, precio, precio_anterior, origen) "
        "SELECT h.propiedad_id, 'precio', h.fecha, true, h.moneda, h.precio, h.precio_anterior, 'historico' "
        "FROM historial_precios h "
        "ON CONFLICT ON CONSTRAINT uq_evento_aviso DO NOTHING")).rowcount
    return {"altas": altas, "bajas": bajas, "precios": precios}


# ------------------------------------------------------------------ agrupación en inmuebles
def _metros(la1, ln1, la2, ln2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = p2 - p1, math.radians(ln2 - ln1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _punto(lat, lng):
    return (round(lat, 5), round(lng, 5))


_MD = MetaData()
_T_INM = Table("inmuebles", _MD, Column("id", BigInteger, primary_key=True), Column("grupo_tipo", String),
               Column("operacion", String), Column("dir_clave", String), Column("dormitorios", Integer),
               Column("m2", Float), Column("lat", Float), Column("lng", Float))
_T_VINC = Table("inmueble_avisos", _MD, Column("propiedad_id", BigInteger, primary_key=True),
                Column("inmueble_id", BigInteger), Column("regla", String), Column("detalle", JSONB))


def _celda(lat, lng):
    return (round(lat / 0.0005), round(lng / 0.0005))  # ~55 m


class Aviso:
    __slots__ = ("id", "plataforma", "grupo", "operacion", "dir", "dorm", "m2", "lat", "lng", "alta", "alta_exacta",
                 "baja", "activo", "moneda", "precio")

    def __init__(self, f, ahora):
        self.id, self.plataforma = f.id, f.plataforma
        self.grupo, self.operacion = grupo_tipo(f.tipo or ""), f.operacion
        self.dir = clave_direccion(f.direccion or "")
        self.dorm = f.dormitorios
        if self.grupo in ("Terreno", "Quinta / Campo"):
            m2 = f.m2_totales or f.m2_base
        else:
            m2 = f.m2_cubiertos or f.m2_base
        self.m2 = float(m2) if m2 else None
        ok = f.ubicacion_valida and f.lat is not None and f.lng is not None
        self.lat, self.lng = (float(f.lat), float(f.lng)) if ok else (None, None)
        self.alta, self.alta_exacta = f.alta or ahora, bool(f.alta_exacta)
        self.activo = f.estado != "baja"
        pv = float(f.precio) if f.precio is not None else 0
        self.moneda, self.precio = f.moneda, (pv if precio_valido(pv, f.moneda or "USD") else None)
        self.baja = None if self.activo else (f.fecha_baja or ahora)

    def hasta(self, ahora):
        return self.baja or ahora


class Inmueble:
    __slots__ = ("id", "grupo", "dir", "dorm", "m2", "lat", "lng", "avisos")

    def __init__(self, id_, a: Aviso):
        self.id, self.grupo, self.dir, self.dorm, self.m2 = id_, a.grupo, a.dir, a.dorm, a.m2
        self.lat, self.lng = a.lat, a.lng
        self.avisos: list[Aviso] = []

    def activos(self):
        return sum(1 for a in self.avisos if a.activo)

    def ultima_baja(self):
        return None if self.activos() else max((a.baja for a in self.avisos), default=None)


def coincide(inm: Inmueble, a: Aviso, cfg: dict, ahora: datetime,
             repetidas: frozenset = frozenset()) -> tuple[str, dict] | None:
    """Devuelve (regla, detalle) si el aviso es del inmueble, o None. Ver reglas en el docstring del módulo."""
    if inm.grupo != a.grupo:
        return None
    if inm.dir and a.dir:
        if inm.dir != a.dir:
            return None
        regla, det = "direccion", {"direccion": a.dir}
    elif None not in (inm.lat, a.lat):
        if _punto(inm.lat, inm.lng) in repetidas or _punto(a.lat, a.lng) in repetidas:
            return None
        d = _metros(inm.lat, inm.lng, a.lat, a.lng)
        if d > cfg["republicacion_metros"]:
            return None
        regla, det = "distancia", {"metros": round(d, 1)}
    else:
        return None
    if not inm.m2 or not a.m2:
        return None
    dif = abs(inm.m2 - a.m2) / max(inm.m2, a.m2) * 100
    if dif > cfg["republicacion_m2_pct"]:
        return None
    det["m2_dif_pct"] = round(dif, 1)
    if a.grupo == "Departamento" and (inm.dorm is None or a.dorm is None or inm.dorm != a.dorm):
        return None
    for b in inm.avisos:
        a_la_vez = a.alta < b.hasta(ahora) and b.alta < a.hasta(ahora)
        if b.plataforma == a.plataforma and a_la_vez:  # mismo portal, activos a la vez -> dos unidades distintas
            return None
        if a.precio and b.precio and a.moneda == b.moneda:
            dif_p = abs(a.precio - b.precio) / min(a.precio, b.precio) * 100
            tope = cfg["republicacion_precio_pct_simultaneo"] if a_la_vez else cfg["republicacion_precio_pct"]
            if dif_p > tope:
                return None
            det["precio_dif_pct"] = max(det.get("precio_dif_pct", 0), round(dif_p, 1))
    ub = inm.ultima_baja()
    if ub is not None:
        hueco = (a.alta - ub).days
        if hueco > cfg["republicacion_max_dias"]:
            return None
        det["dias_sin_publicar"] = max(hueco, 0)
    return regla, det


_SEL_AVISOS = """
SELECT p.id, p.plataforma, p.tipo, p.operacion, p.moneda, p.precio, p.direccion, p.dormitorios, p.m2_cubiertos, p.m2_totales, p.m2_base,
       p.lat, p.lng, p.ubicacion_valida, p.estado, p.fecha_baja, ev.fecha AS alta, ev.exacta AS alta_exacta,
       ia.inmueble_id
FROM propiedades p
LEFT JOIN LATERAL (SELECT e.fecha, e.exacta FROM eventos_aviso e
                   WHERE e.propiedad_id = p.id AND e.tipo = 'alta' ORDER BY e.fecha LIMIT 1) ev ON true
LEFT JOIN inmueble_avisos ia ON ia.propiedad_id = p.id
WHERE p.operacion = ANY(:ops)
"""


def vincular(db: Session, ahora: datetime | None = None) -> dict[str, int]:
    """Asigna a un inmueble cada aviso de venta que todavía no tiene. Los ya asignados no se mueven."""
    ahora = ahora or datetime.now()
    cfg = umbrales(db)
    filas = db.execute(text(_SEL_AVISOS), {"ops": list(OPERACIONES)}).all()
    inmuebles: dict[int, Inmueble] = {}
    por_dir: dict[tuple, list[Inmueble]] = {}
    por_celda: dict[tuple, list[Inmueble]] = {}

    def indexar(inm: Inmueble, op: str):
        if inm.dir:
            por_dir.setdefault((op, inm.grupo, inm.dir), []).append(inm)
        if inm.lat is not None:
            por_celda.setdefault((op, inm.grupo, *_celda(inm.lat, inm.lng)), []).append(inm)

    cuenta: dict[tuple, int] = {}
    for f in filas:
        if f.ubicacion_valida and f.lat is not None and f.lng is not None:
            k = _punto(float(f.lat), float(f.lng))
            cuenta[k] = cuenta.get(k, 0) + 1
    repetidas = frozenset(k for k, n in cuenta.items() if n >= 3)
    pendientes: list[tuple[Aviso, str]] = []
    for f in sorted(filas, key=lambda f: (f.alta or ahora, f.id)):
        a = Aviso(f, ahora)
        if f.inmueble_id is None:
            pendientes.append((a, f.operacion))
            continue
        inm = inmuebles.get(f.inmueble_id)
        if inm is None:
            inm = inmuebles[f.inmueble_id] = Inmueble(f.inmueble_id, a)
            indexar(inm, f.operacion)
        inm.avisos.append(a)

    # 1) se decide todo en memoria (los inmuebles nuevos con id provisorio negativo)
    nuevos = unidos = 0
    altas_inm: list[tuple[Inmueble, str]] = []
    vinculos: list[tuple[Aviso, Inmueble, str, dict]] = []
    for a, op in pendientes:
        cands: list[Inmueble] = []
        if a.dir:
            cands += por_dir.get((op, a.grupo, a.dir), [])
        if a.lat is not None:
            cy, cx = _celda(a.lat, a.lng)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    cands += por_celda.get((op, a.grupo, cy + dy, cx + dx), [])
        mejor = None
        vistos = set()
        for inm in cands:
            if id(inm) in vistos:
                continue
            vistos.add(id(inm))
            r = coincide(inm, a, cfg, ahora, repetidas)
            if r is None:
                continue
            clave = (0 if r[0] == "direccion" else 1, r[1].get("metros", 0), r[1]["m2_dif_pct"], inm.id)
            if mejor is None or clave < mejor[0]:
                mejor = (clave, inm, r)
        if mejor is None:
            nuevos += 1
            inm = Inmueble(-nuevos, a)
            altas_inm.append((inm, op))
            indexar(inm, op)
            regla, det = "nuevo", {}
        else:
            _, inm, (regla, det) = mejor
            det["con_aviso"] = inm.avisos[0].id if inm.avisos else None
            unidos += 1
        inm.avisos.append(a)
        vinculos.append((a, inm, regla, det))
    # 2) se graba en bloque (pocas idas y vueltas a la base, importa con Supabase lejos)
    if altas_inm:
        ids = db.execute(insert(_T_INM).returning(_T_INM.c.id, sort_by_parameter_order=True), [
            {"grupo_tipo": inm.grupo, "operacion": op, "dir_clave": inm.dir, "dormitorios": inm.dorm, "m2": inm.m2,
             "lat": inm.lat, "lng": inm.lng} for inm, op in altas_inm]).scalars().all()
        for (inm, _), nid in zip(altas_inm, ids, strict=True):
            inm.id = nid
    if vinculos:
        db.execute(insert(_T_VINC), [{"propiedad_id": a.id, "inmueble_id": inm.id, "regla": regla,
                                      "detalle": det} for a, inm, regla, det in vinculos])
    resumir(db)
    return {"avisos_nuevos": len(pendientes), "inmuebles_nuevos": nuevos, "republicaciones_unidas": unidos}


def resumir(db: Session):
    """Recalcula fechas y estado de todos los inmuebles a partir de sus avisos (barato: una sola consulta)."""
    db.execute(text("""
        UPDATE inmuebles i SET
          primera_alta = s.primera_alta,
          primera_alta_exacta = s.exacta,
          avisos_activos = s.activos,
          ultima_baja = s.ultima_baja,
          actualizado_en = now()
        FROM (
          SELECT ia.inmueble_id,
                 min(ev.fecha) AS primera_alta,
                 COALESCE((array_agg(ev.exacta ORDER BY ev.fecha) FILTER (WHERE ev.fecha IS NOT NULL))[1], false)
                   AS exacta,
                 count(*) FILTER (WHERE p.estado <> 'baja') AS activos,
                 CASE WHEN count(*) FILTER (WHERE p.estado <> 'baja') = 0 THEN max(p.fecha_baja) END AS ultima_baja
          FROM inmueble_avisos ia
          JOIN propiedades p ON p.id = ia.propiedad_id
          LEFT JOIN LATERAL (
            SELECT e.fecha, e.exacta FROM eventos_aviso e
            WHERE e.propiedad_id = p.id AND e.tipo = 'alta' ORDER BY e.fecha LIMIT 1
          ) ev ON true
          GROUP BY ia.inmueble_id
        ) s
        WHERE s.inmueble_id = i.id
          AND (i.primera_alta IS DISTINCT FROM s.primera_alta OR i.avisos_activos <> s.activos
               OR i.ultima_baja IS DISTINCT FROM s.ultima_baja OR i.primera_alta_exacta <> s.exacta)
    """))


def preparar(db: Session) -> dict:
    """Lo que corre al final de cada actualización: historial (la primera vez) + vincular avisos nuevos."""
    out = {}
    if db.scalar(text("SELECT valor FROM meta WHERE clave = 'valuacion_historico'")) != "ok":
        out["historico"] = reconstruir_historico(db)
        db.execute(text("INSERT INTO meta (clave, valor) VALUES ('valuacion_historico', 'ok') "
                        "ON CONFLICT (clave) DO UPDATE SET valor = 'ok'"))
    out.update(vincular(db))
    return out
