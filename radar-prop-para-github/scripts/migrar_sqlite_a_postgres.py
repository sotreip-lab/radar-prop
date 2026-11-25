"""Pasa la base de El Ojo de Dios (SQLite) a la base central de Radar Prop (PostgreSQL + PostGIS).

Uso:
    DATABASE_URL=postgresql+psycopg://... python scripts/migrar_sqlite_a_postgres.py RUTA/propiedades.db [RUTA/captacion.db]

- Copia propiedades.db y su -wal a una carpeta temporal y hace el checkpoint SOBRE LA COPIA
  (el original no se toca ni se bloquea: la app vieja puede seguir andando).
- Es idempotente: correrlo varias veces no duplica nada (ON CONFLICT por (plataforma, id_externo)).
- Todo va en una sola transacción: si algo falla, no queda nada a medias.
- Al final imprime los conteos de origen contra destino y termina con error si no coinciden.
"""
import argparse
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from collections import Counter
from datetime import datetime
from decimal import Decimal

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "backend"))

from sqlalchemy import func, select, text  # noqa: E402
from sqlalchemy.dialects.postgresql import insert  # noqa: E402

from app.db_util import engine_para  # noqa: E402
from app.models import CaptacionDueno, CaptacionSeguimiento, Cliente, HistorialPrecio, Meta, Propiedad  # noqa: E402
from app.scraper.ids import id_externo, url_de  # noqa: E402

LOTE = 1000


# ------------------------------------------------------------------ lectura segura del SQLite
def copia_con_checkpoint(ruta_db: str, destino: str) -> str:
    """Copia la base y sus archivos -wal/-shm, y consolida el WAL en la copia."""
    copia = os.path.join(destino, "propiedades.db")
    shutil.copy2(ruta_db, copia)
    for suf in ("-wal", "-shm"):
        if os.path.exists(ruta_db + suf):
            shutil.copy2(ruta_db + suf, copia + suf)
    con = sqlite3.connect(copia)
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()
    return copia


def fecha(v):
    """'2026-11-24 10:15:00' / '2026-11-24' / '2026-11-21 (planilla)' -> (datetime | None, origen | None)."""
    if not v:
        return None, None
    s = str(v).strip()
    origen = None
    if "(" in s:
        origen = s[s.index("(") + 1:s.rindex(")")] if ")" in s else s[s.index("(") + 1:]
        s = s[:s.index("(")].strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt), origen
        except ValueError:
            pass
    return None, origen or s  # formato desconocido: no se inventa, queda el texto como origen


def num(v):
    if v is None or v == "":
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


def coordenadas_genericas(con) -> set:
    """Puntos repetidos en muchos avisos: son la ubicación por defecto del portal, no la real."""
    cuenta: Counter = Counter()
    for la, ln in con.execute("SELECT lat, lng FROM props WHERE lat IS NOT NULL AND lng IS NOT NULL"):
        cuenta[(round(la, 4), round(ln, 4))] += 1
    return {k for k, n in cuenta.items() if n > 12}


MAPEO_DIRECTO = {  # columna vieja -> columna nueva (mismo dato, sin transformar)
    "titulo": "titulo", "tipo": "tipo", "operacion": "operacion", "direccion": "direccion", "barrio": "barrio",
    "ciudad": "ciudad", "inmobiliaria": "inmobiliaria", "moneda": "moneda", "dormitorios": "dormitorios",
    "banos": "banos", "antiguedad": "antiguedad", "estado": "estado_inmueble", "patio": "patio",
    "cochera": "cochera", "apto_credito": "apto_credito", "pileta": "pileta", "parrilla": "parrilla",
    "descripcion": "descripcion", "intentos": "intentos", "ia_resumen": "ia_resumen", "ia_intentos": "ia_intentos",
    "exterior": "exterior", "estacionamiento": "estacionamiento", "pago": "pago", "expensas": "expensas",
    "pub_txt": "pub_txt", "amoblado": "amoblado",
}
ESTADOS = {"activo": "activa", "baja": "baja", "pendiente": "pendiente"}


def fila_a_propiedad(r: sqlite3.Row, genericas: set) -> dict:
    cols = r.keys()
    plat = (r["fuente"] or "").strip().upper() or "BBP"
    ide = id_externo(plat, r["id"], r["url"])
    d = {nuevo: r[viejo] for viejo, nuevo in MAPEO_DIRECTO.items()}
    d.update(plataforma=plat, id_externo=ide, id_legado=r["id"], url=url_de(plat, ide, r["url"]))
    d["precio"] = num(r["precio"])
    d["precio_anterior"] = num(r["precio_anterior"])
    d["precio_ars"] = d["precio"] if (r["moneda"] or "") == "ARS" else None
    d["m2_cubiertos"], d["m2_totales"], d["m2_base"] = num(r["sup_cub"]), num(r["sup_tot"]), num(r["m2_base"])
    d["estado"] = ESTADOS.get((r["estado_aviso"] or "").strip(), r["estado_aviso"] or "pendiente")
    extra = {}
    # fechas
    d["cambio_precio"], _ = fecha(r["cambio_precio"])
    d["publicada_hasta"], _ = fecha(r["detectada"])
    d["publicada_desde"], _ = fecha(r["detectada_desde"])
    d["pub_aprox"], _ = fecha(r["pub_aprox"])
    d["primera_vez_vista"], _ = fecha(r["alta"])
    d["ultima_vez_vista"], d["ultima_verif_origen"] = fecha(r["ultima_verif"])
    d["fecha_baja"], d["fecha_baja_origen"] = fecha(r["fecha_baja"])
    d["ia_fecha"], _ = fecha(r["ia_fecha"])
    # la mejor estimación para ordenar: la ventana exacta si se vio aparecer; si no, la aproximada
    d["fecha_publicacion"] = d["publicada_hasta"] or d["pub_aprox"]
    # JSON guardado como texto
    for viejo, nuevo in (("detalles", "detalles"), ("ia_json", "ia_json")):
        v = r[viejo]
        if v:
            try:
                d[nuevo] = json.loads(v)
            except (ValueError, TypeError):
                d[nuevo] = None
                extra[f"{viejo}_texto"] = v  # no era JSON válido: se guarda tal cual
        else:
            d[nuevo] = None
    # ubicación: se guarda siempre lo que vino; el punto del mapa solo si es creíble
    la, ln = r["lat"], r["lng"]
    d["lat"], d["lng"] = num(la), num(ln)
    valida = la is not None and ln is not None and abs(la) > 1 and abs(ln) > 1
    if valida and (round(la, 4), round(ln, 4)) in genericas:
        valida = False
        extra["coordenada_generica"] = True
    d["ubicacion_valida"] = valida
    d["ubicacion"] = f"SRID=4326;POINT({ln} {la})" if valida else None
    # columnas viejas sin lugar propio
    if r["dorm_fuente"]:
        extra["dorm_fuente"] = r["dorm_fuente"]
    conocidas = set(MAPEO_DIRECTO) | {"id", "fuente", "url", "precio", "precio_anterior", "sup_cub", "sup_tot",
                                      "m2_base", "estado_aviso", "cambio_precio", "detectada", "detectada_desde",
                                      "pub_aprox", "alta", "ultima_verif", "fecha_baja", "ia_fecha", "detalles",
                                      "ia_json", "lat", "lng", "dorm_fuente"}
    for c in cols:  # cualquier columna que se agregue en el futuro a props no se pierde
        if c not in conocidas and r[c] is not None:
            extra[c] = r[c]
    d["datos_extra"] = extra
    return d


# ------------------------------------------------------------------ migración
def migrar(ruta_db: str, url_pg: str, ruta_captacion: str | None = None, silencioso: bool = False,
           verificar_certificado: bool = True) -> dict:
    tmp = tempfile.mkdtemp(prefix="migracion_radar_")
    try:
        copia = copia_con_checkpoint(ruta_db, tmp)
        src = sqlite3.connect(copia)
        src.row_factory = sqlite3.Row
        genericas = coordenadas_genericas(src)
        engine = engine_para(url_pg, verificar_certificado=verificar_certificado)
        with engine.begin() as pg:
            # propiedades
            filas = src.execute("SELECT * FROM props ORDER BY id").fetchall()
            props = [fila_a_propiedad(r, genericas) for r in filas]
            for i in range(0, len(props), LOTE):
                lote = props[i:i + LOTE]
                ins = insert(Propiedad).values(lote)
                actualizar = {c: ins.excluded[c] for c in lote[0] if c not in ("plataforma", "id_externo")}
                actualizar["actualizado_en"] = func.now()
                pg.execute(ins.on_conflict_do_update(constraint="uq_propiedades_plataforma_id", set_=actualizar))
            id_nuevo = dict(pg.execute(select(Propiedad.id_legado, Propiedad.id)).all())
            # historial de precios
            hist = []
            for hid, f, mon, antes, despues in src.execute("SELECT id, fecha, moneda, antes, despues FROM historial"):
                if hid not in id_nuevo:
                    continue
                dt, _ = fecha(f)
                hist.append(dict(propiedad_id=id_nuevo[hid], fecha=dt, moneda=mon,
                                 precio_anterior=num(antes), precio=num(despues)))
            if hist:
                pg.execute(insert(HistorialPrecio).values(hist).on_conflict_do_nothing(constraint="uq_hist_precio"))
            # meta
            meta = [dict(clave=k, valor=v) for k, v in src.execute("SELECT k, v FROM meta")]
            meta.append(dict(clave="migrado_desde_ojo_de_dios", valor=datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            ins = insert(Meta).values(meta)
            pg.execute(ins.on_conflict_do_update(index_elements=["clave"], set_={"valor": ins.excluded.valor,
                                                                                 "actualizado_en": func.now()}))
            # compradores (tabla pedidos)
            ped = []
            for pid, datos, creado, visto, activo in src.execute("SELECT id, datos, creado, visto_hasta, activo FROM pedidos"):
                try:
                    j = json.loads(datos or "{}")
                except ValueError:
                    j = {"texto_original": datos}
                # campos de El Ojo de Dios (ui.html, formADatos): nombre, telefono, presu, moneda, texto, obs,
                # operacion, tipos, dorm, barrios, patio, cochera, credito, amoblado. Todo queda además en `filtros`.
                ped.append(dict(id_legado=pid, nombre=str(j.get("nombre") or "")[:160],
                                telefono=(str(j.get("telefono") or "") or None), pedido=j.get("texto") or j.get("obs") or None,
                                presupuesto=num(j.get("presu")), moneda=j.get("moneda") or None,
                                filtros={**j, "visto_hasta": visto}, activo=bool(activo),
                                creado_en=fecha(creado)[0] or datetime.now()))
            if ped:
                ins = insert(Cliente).values(ped)
                pg.execute(ins.on_conflict_do_update(index_elements=["id_legado"],
                                                     set_={c: ins.excluded[c] for c in ped[0] if c != "id_legado"}))
            # captación (base aparte)
            n_cap = {"duenos": 0, "seguimiento": 0}
            if ruta_captacion and os.path.exists(ruta_captacion):
                n_cap = migrar_captacion(ruta_captacion, pg, id_nuevo)
        resultado = verificar(src, engine, n_cap)
        src.close()
        engine.dispose()
        if not silencioso:
            imprimir(resultado)
        return resultado
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def migrar_captacion(ruta: str, pg, id_nuevo: dict) -> dict:
    c = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    duenos = []
    for r in c.execute("SELECT * FROM duenos"):
        duenos.append(dict(id_legado=r["id"], origen=r["origen"], url=r["url"], titulo=r["titulo"], tipo=r["tipo"],
                           operacion=r["operacion"], direccion=r["direccion"], barrio=r["barrio"], ciudad=r["ciudad"],
                           moneda=r["moneda"], precio=num(r["precio"]), dormitorios=r["dorm"], m2=num(r["m2"]),
                           nombre=r["nombre"], telefono=r["telefono"], notas=r["notas"], activo=bool(r["activo"]),
                           creado_en=fecha(r["alta"])[0] or datetime.now()))
    if duenos:
        ins = insert(CaptacionDueno).values(duenos)
        pg.execute(ins.on_conflict_do_update(index_elements=["id_legado"],
                                             set_={k: ins.excluded[k] for k in duenos[0] if k != "id_legado"}))
    dueno_nuevo = dict(pg.execute(select(CaptacionDueno.id_legado, CaptacionDueno.id)).all())
    seg = []
    for r in c.execute("SELECT * FROM seguimiento"):
        seg.append(dict(clave=r["clave"], propiedad_id=id_nuevo.get(r["prop_id"]), dueno_id=dueno_nuevo.get(r["dueno_id"]),
                        senal=r["senal"], estado=r["estado"] or "por_contactar", resultado=r["resultado"] or "",
                        notas=r["notas"] or "", actualizado_en=fecha(r["actualizado"])[0] or datetime.now()))
    if seg:
        ins = insert(CaptacionSeguimiento).values(seg)
        pg.execute(ins.on_conflict_do_update(index_elements=["clave"],
                                             set_={k: ins.excluded[k] for k in seg[0] if k != "clave"}))
    c.close()
    return {"duenos": len(duenos), "seguimiento": len(seg)}


# ------------------------------------------------------------------ verificación de conteos
def verificar(src, engine, n_cap) -> dict:
    origen = {
        "props": src.execute("SELECT COUNT(*) FROM props").fetchone()[0],
        "historial": src.execute("SELECT COUNT(*) FROM historial WHERE id IN (SELECT id FROM props)").fetchone()[0],
        "meta": src.execute("SELECT COUNT(*) FROM meta").fetchone()[0],
        "pedidos": src.execute("SELECT COUNT(*) FROM pedidos").fetchone()[0],
        "captacion_duenos": n_cap["duenos"], "captacion_seguimiento": n_cap["seguimiento"],
    }
    por_fuente_src = {f"{f}/{e}": n for f, e, n in src.execute(
        "SELECT COALESCE(NULLIF(TRIM(fuente),''),'BBP'), estado_aviso, COUNT(*) FROM props GROUP BY 1,2")}
    with engine.connect() as pg:
        destino = {
            "props": pg.scalar(select(func.count()).select_from(Propiedad)),
            "historial": pg.scalar(select(func.count()).select_from(HistorialPrecio)),
            "meta": pg.scalar(select(func.count()).select_from(Meta).where(Meta.clave != "migrado_desde_ojo_de_dios")),
            "pedidos": pg.scalar(select(func.count()).select_from(Cliente).where(Cliente.id_legado.is_not(None))),
            "captacion_duenos": pg.scalar(select(func.count()).select_from(CaptacionDueno).where(CaptacionDueno.id_legado.is_not(None))),
            "captacion_seguimiento": pg.scalar(select(func.count()).select_from(CaptacionSeguimiento)),
        }
        inv = {v: k for k, v in ESTADOS.items()}
        por_fuente_dst = {f"{p}/{inv.get(e, e)}": n for p, e, n in pg.execute(
            text("SELECT plataforma, estado, COUNT(*) FROM propiedades GROUP BY 1,2"))}
        con_mapa = pg.scalar(text("SELECT COUNT(*) FROM propiedades WHERE ubicacion IS NOT NULL"))
    ok = origen == destino and por_fuente_src == por_fuente_dst
    return {"ok": ok, "origen": origen, "destino": destino, "por_fuente_origen": por_fuente_src,
            "por_fuente_destino": por_fuente_dst, "con_ubicacion_valida": con_mapa}


def imprimir(r: dict):
    print("\nTABLA                     ORIGEN   DESTINO")
    for k in r["origen"]:
        marca = "OK" if r["origen"][k] == r["destino"][k] else "DISTINTO"
        print(f"  {k:<22}{r['origen'][k]:>8}  {r['destino'][k]:>8}   {marca}")
    print("\nPLATAFORMA / ESTADO       ORIGEN   DESTINO")
    for k in sorted(set(r["por_fuente_origen"]) | set(r["por_fuente_destino"])):
        a, b = r["por_fuente_origen"].get(k, 0), r["por_fuente_destino"].get(k, 0)
        print(f"  {k:<22}{a:>8}  {b:>8}   {'OK' if a == b else 'DISTINTO'}")
    print(f"\nPropiedades con punto en el mapa: {r['con_ubicacion_valida']}")
    print("\nRESULTADO:", "los conteos coinciden" if r["ok"] else "HAY DIFERENCIAS")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Migra El Ojo de Dios (SQLite) a Radar Prop (PostgreSQL)")
    ap.add_argument("sqlite", help="ruta a propiedades.db")
    ap.add_argument("captacion", nargs="?", help="ruta a modulos/datos/captacion.db (opcional)")
    a = ap.parse_args()
    url = os.environ.get("DATABASE_URL")
    if not url:
        from app.core.config import settings
        url = settings.database_url
    res = migrar(a.sqlite, url, a.captacion)
    sys.exit(0 if res["ok"] else 1)
