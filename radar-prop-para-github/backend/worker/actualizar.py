"""Worker de Radar Prop: lee Bahía Blanca Propiedades e IBB y actualiza la base central.

    DATABASE_URL=postgresql://... python -m worker.actualizar [--modo rapida|completa] [--max-minutos 11]

Misma lógica que la actualización de El Ojo de Dios:
  1. sitemap de BBP: avisos nuevos, que volvieron a publicarse y posibles bajas (la baja se confirma abriendo la ficha);
  2. fichas pendientes o con error de red;
  3. si el sitemap falla, respaldo por número de aviso;
  4. re-lectura rotativa de las fichas verificadas hace más tiempo (precios al día);
  5. IBB con su listado completo.
Lo nuevo:
  - un candado en la base (pg_try_advisory_lock): si hay otra corrida activa, esta termina sin tocar nada;
  - cada corrida queda registrada en `corridas_actualizacion` (con errores incluidos);
  - límite de tiempo: si se acaba, lo que falta queda para la próxima corrida (lo nuevo va primero);
  - guardado en lotes con transacción: si algo falla a mitad, lo ya confirmado queda y nada queda a medias.
"""
import argparse
import json
import logging
import os
import sys
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db_util import engine_para
from app.models import CorridaActualizacion, HistorialPrecio, Meta, Propiedad
from app.scraper import bbp, ibb
from app.scraper.ids import id_externo
from app.scraper.red import ahora_local, bajar, fecha_ultima_modificacion
from app.scraper.texto import detectar_amoblado
from app.services.valuacion import inmuebles as valuacion

CANDADO = 72_340_01          # número fijo del candado de la base (cualquier valor, siempre el mismo)
LOTE = 50                    # fichas por transacción
log = logging.getLogger("worker")

CFG: dict[str, Any] = {
    "hilos": int(os.environ.get("RADAR_HILOS", "8")),
    "pausa_seg": 0.05,
    "fallos_seguidos_para_cortar": 40,
    "reverificar_por_ronda": int(os.environ.get("RADAR_REVERIFICAR", "300")),
    "ibb_reverificar_por_ronda": int(os.environ.get("RADAR_IBB_REVERIFICAR", "120")),
    "ibb_minimo": int(os.environ.get("RADAR_IBB_MINIMO", "300")),
    "sitemap_minimo": int(os.environ.get("RADAR_SITEMAP_MINIMO", "1000")),
}


class SinTiempo(Exception):
    pass


def url_psycopg(url: str) -> str:
    """Acepta la URL como la da Supabase (postgresql://) o con otro driver (+pg8000) y usa psycopg."""
    url = url.strip()
    esquema, resto = url.split("://", 1)
    return f"postgresql+psycopg://{resto}" if esquema.startswith("postgres") else url


def _dec(v) -> Decimal | None:
    return None if v is None else Decimal(str(v))


def _fecha(v) -> datetime | None:
    if not v:
        return None
    if isinstance(v, datetime):
        return v
    s = str(v).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:19], fmt)
        except ValueError:
            pass
    return None


class Corrida:
    def __init__(self, eng, modo: str, max_minutos: float):
        self.eng = eng
        self.con_eventos = False
        self.modo = modo
        self.limite = time.monotonic() + max_minutos * 60
        self.c = {"nuevas": 0, "actualizadas": 0, "bajas": 0, "cambios_precio": 0, "errores": 0}
        self.detalle: dict = {"pendiente_por_tiempo": [], "avisos": []}
        self.genericas: set[tuple[float, float]] = set()

    # ------------------------------------------------------------ tiempo
    def evento(self, db: Session, *args, **kw):
        """Evento para el mapa de valores (si la base ya tiene la tabla: la migración la aplica el deploy de la API)."""
        if self.con_eventos:
            valuacion.registrar_evento(db, *args, **kw)

    def queda_tiempo(self) -> bool:
        return time.monotonic() < self.limite

    def aviso(self, msg: str):
        log.info(msg)
        self.detalle["avisos"].append(msg[:300])

    # ------------------------------------------------------------ meta
    def meta_get(self, db: Session, clave: str) -> str | None:
        return db.scalar(select(Meta.valor).where(Meta.clave == clave))

    def meta_set(self, db: Session, clave: str, valor: str):
        db.execute(insert(Meta).values(clave=clave, valor=valor).on_conflict_do_update(
            index_elements=[Meta.clave], set_={"valor": valor, "actualizado_en": func.now()}))

    # ------------------------------------------------------------ ubicación
    def cargar_genericas(self, db: Session):
        """Puntos repetidos en más de 12 avisos: son la ubicación por defecto del portal, no la real."""
        filas = db.execute(text(
            "SELECT round(lat::numeric, 4), round(lng::numeric, 4) FROM propiedades "
            "WHERE lat IS NOT NULL AND lng IS NOT NULL GROUP BY 1, 2 HAVING COUNT(*) > 12")).all()
        self.genericas = {(float(a), float(b)) for a, b in filas}

    def ubicacion(self, lat, lng, extra: dict) -> tuple[str | None, bool]:
        extra.pop("coordenada_generica", None)
        if lat is None or lng is None or abs(lat) <= 1 or abs(lng) <= 1:
            return None, False
        if (round(lat, 4), round(lng, 4)) in self.genericas:
            extra["coordenada_generica"] = True
            return None, False
        return f"SRID=4326;POINT({lng} {lat})", True

    # ------------------------------------------------------------ guardado
    def guardar(self, db: Session, plat: str, ide: str, url: str, d: dict, ventana: tuple | None,
                fotos: list[str], buscar_pub: bool = False):
        """Inserta o actualiza un aviso leído bien. Mismas reglas que guardar_resultado / ibb_guardar."""
        ahora = ahora_local()
        existente = db.scalar(select(Propiedad).where(Propiedad.plataforma == plat, Propiedad.id_externo == ide))
        nueva = existente is None
        estado_ant = existente.estado if existente is not None else None
        if existente is not None:
            p = existente
        else:
            p = Propiedad(plataforma=plat, id_externo=ide, primera_vez_vista=ahora, datos_extra={}, intentos=0)
            db.add(p)
        extra = dict(p.datos_extra or {})
        detalles = d.get("detalles") or {}
        valores = {
            "url": url, "inmobiliaria": d.get("inmobiliaria"), "direccion": d.get("direccion"),
            "moneda": d.get("moneda"), "dormitorios": d.get("dormitorios"), "banos": d.get("banos"),
            "m2_cubiertos": _dec(d.get("sup_cub")), "m2_totales": _dec(d.get("sup_tot")), "m2_base": _dec(d.get("m2_base")),
            "antiguedad": d.get("antiguedad"), "estado_inmueble": d.get("estado"), "patio": d.get("patio"),
            "cochera": d.get("cochera"), "apto_credito": d.get("apto_credito"), "pileta": d.get("pileta"),
            "parrilla": d.get("parrilla"), "detalles": detalles, "descripcion": d.get("descripcion"),
            "exterior": d.get("exterior"), "estacionamiento": d.get("estacionamiento"), "pago": d.get("pago"),
            "expensas": d.get("expensas"),
            "amoblado": detectar_amoblado(d.get("titulo"), json.dumps(detalles, ensure_ascii=False), d.get("descripcion")),
        }
        # si la ficha no trae estos datos, queda el que ya estaba (p. ej. cargado por planilla)
        for campo in ("titulo", "tipo", "operacion", "barrio", "ciudad"):
            nuevo_v = d.get(campo)
            if nueva or nuevo_v:
                valores[campo] = nuevo_v
        precio = _dec(d.get("precio"))
        if not nueva and p.precio is not None and precio is not None and abs(p.precio - precio) > Decimal("0.5"):
            if (p.moneda or "") == (d.get("moneda") or ""):
                self.evento(db, p.id, "precio", ahora, moneda=d.get("moneda"), precio=precio,
                                           precio_anterior=p.precio)
            p.precio_anterior, p.cambio_precio = p.precio, ahora
            self.c["cambios_precio"] += 1
            if (p.moneda or "") == (d.get("moneda") or ""):
                db.execute(insert(HistorialPrecio).values(
                    propiedad_id=p.id, fecha=ahora, moneda=d.get("moneda"), precio_anterior=p.precio, precio=precio,
                ).on_conflict_do_nothing(constraint="uq_hist_precio"))
        valores["precio"] = precio
        valores["precio_ars"] = precio if d.get("moneda") == "ARS" else None
        if not nueva and (p.descripcion or "") != (d.get("descripcion") or ""):
            valores.update(ia_json=None, ia_fecha=None, ia_resumen=None)  # cambió el texto: análisis viejo no sirve
        for k, v in valores.items():
            setattr(p, k, v)
        if d.get("dorm_fuente"):
            extra["dorm_fuente"] = d["dorm_fuente"]
        lat, lng = d.get("lat") or None, d.get("lng") or None
        p.lat, p.lng = lat, lng
        p.ubicacion, p.ubicacion_valida = self.ubicacion(lat, lng, extra)
        if fotos:
            p.fotos = fotos
        if d.get("pub_txt"):
            p.pub_txt = d["pub_txt"][:120]
        if d.get("pub_aprox") and p.pub_aprox is None:
            p.pub_aprox = _fecha(d["pub_aprox"])
        if buscar_pub and p.pub_aprox is None and fotos:
            fechas = [f for f in (fecha_ultima_modificacion(u) for u in fotos[:2]) if f]
            if fechas:
                p.pub_aprox = min(fechas)
        if nueva and ventana is not None:
            desde, hasta = ventana
            if plat == "BBP" or desde is not None:
                p.publicada_desde, p.publicada_hasta = desde, hasta
        p.fecha_publicacion = p.publicada_hasta or p.pub_aprox or p.fecha_publicacion
        p.estado, p.fecha_baja, p.fecha_baja_origen = "activa", None, None
        p.ultima_vez_vista, p.ultima_verif_origen, p.intentos = ahora, None, 0
        p.datos_extra = extra
        p.actualizado_en = func.now()
        if nueva:
            db.flush()  # para tener el id
            self.evento(db, p.id, "alta", ahora, moneda=p.moneda, precio=precio)
        elif estado_ant == "baja":
            self.evento(db, p.id, "reaparece", ahora, moneda=p.moneda, precio=precio)
        self.c["nuevas" if nueva else "actualizadas"] += 1

    def marcar_baja(self, db: Session, plat: str, ide: str):
        ahora = ahora_local()
        fila = db.execute(select(Propiedad.id, Propiedad.estado, Propiedad.moneda, Propiedad.precio).where(
            Propiedad.plataforma == plat, Propiedad.id_externo == ide)).first()
        if fila is None or fila.estado == "baja":
            return
        estado_ant = fila.estado
        self.evento(db, fila.id, "baja", ahora, moneda=fila.moneda, precio=fila.precio)
        db.execute(update(Propiedad).where(Propiedad.plataforma == plat, Propiedad.id_externo == ide).values(
            estado="baja", fecha_baja=ahora, fecha_baja_origen=None, ultima_vez_vista=ahora, actualizado_en=func.now()))
        if estado_ant == "activa":
            self.c["bajas"] += 1

    def marcar_error(self, db: Session, plat: str, ide: str):
        db.execute(text(
            "UPDATE propiedades SET intentos = intentos + 1, "
            "estado = CASE WHEN estado = 'pendiente' THEN 'error' ELSE estado END "
            "WHERE plataforma = :p AND id_externo = :i"), {"p": plat, "i": ide})
        self.c["errores"] += 1

    # ------------------------------------------------------------ lotes en paralelo
    def procesar(self, nombre: str, items: list, bajar_uno: Callable, guardar_uno: Callable):
        """Baja en paralelo y guarda en el hilo principal, de a LOTE fichas por transacción."""
        if not items:
            return
        log.info("%s: %d", nombre, len(items))
        hechos = 0
        for i in range(0, len(items), LOTE):
            if not self.queda_tiempo():
                self.detalle["pendiente_por_tiempo"].append({"fase": nombre, "faltaron": len(items) - hechos})
                raise SinTiempo(nombre)
            parte = items[i:i + LOTE]
            with ThreadPoolExecutor(max_workers=CFG["hilos"]) as ex:
                resultados = list(ex.map(bajar_uno, parte))
            with Session(self.eng) as db, db.begin():
                for item, res in zip(parte, resultados, strict=True):
                    try:
                        with db.begin_nested():
                            guardar_uno(db, item, res)
                    except Exception as e:  # un aviso raro no frena al resto
                        self.c["errores"] += 1
                        self.aviso(f"{nombre} {item}: {type(e).__name__}: {e}")
            hechos += len(parte)


# ================================================================== Bahía Blanca Propiedades
def actualizar_bbp(cr: Corrida, ventana: tuple):
    """La ventana de publicación avanza solo cuando se terminó de detectar todo lo nuevo; si no, la próxima
    corrida usa la misma fecha de inicio (la ventana queda más ancha, nunca se inventa una hora)."""
    with Session(cr.eng) as db:
        conocidos = dict(db.execute(select(Propiedad.id_externo, Propiedad.estado)
                                    .where(Propiedad.plataforma == "BBP")).all())

    def bajar_uno(ide):
        r = bbp.bajar_ficha(ide)
        time.sleep(CFG["pausa_seg"])
        return r

    def guardar_uno_con(ventana_n):
        def guardar_uno(db, ide, r):
            if r.estado == "ok":
                d = bbp.analizar_ficha(r.html)
                cr.guardar(db, "BBP", ide, f"{bbp.sitio_bbp()}/propiedad/{ide}/", d, ventana_n,
                           bbp.fotos_de_ficha(r.html), buscar_pub=True)
            elif r.estado == "baja":
                cr.marcar_baja(db, "BBP", ide)
            else:
                cr.marcar_error(db, "BBP", ide)
        return guardar_uno

    def ventana_cerrada():
        with Session(cr.eng) as db, db.begin():
            cr.meta_set(db, "ultima_revision_sitemap", ventana[1].strftime("%Y-%m-%d %H:%M:%S"))

    try:
        en_sitio = bbp.ids_del_sitemap(CFG["sitemap_minimo"])
    except Exception as e:
        en_sitio = None
        cr.aviso(f"BBP: no se pudo leer el sitemap ({e}); sigo con el método por número de aviso")
    if en_sitio is not None:
        nuevas = sorted(en_sitio - set(conocidos), key=int, reverse=True)
        reactivar = sorted(i for i in en_sitio if conocidos.get(i) == "baja")
        posibles_bajas = sorted(i for i, e in conocidos.items() if e == "activa" and i not in en_sitio)
        cr.detalle["bbp"] = {"en_sitio": len(en_sitio), "nuevas": len(nuevas), "reactivar": len(reactivar),
                             "posibles_bajas": len(posibles_bajas)}
        cr.procesar("BBP nuevas", nuevas, bajar_uno, guardar_uno_con(ventana))
        ventana_cerrada()
        cr.procesar("BBP vueltas a publicar", reactivar, bajar_uno, guardar_uno_con(None))
        cr.procesar("BBP posibles bajas", posibles_bajas, bajar_uno, guardar_uno_con(None))

    with Session(cr.eng) as db:
        pend = list(db.scalars(select(Propiedad.id_externo).where(
            Propiedad.plataforma == "BBP", Propiedad.estado.in_(("pendiente", "error")), Propiedad.intentos < 5)
            .order_by(text("CASE WHEN operacion='Venta' THEN 0 ELSE 1 END, "
                           "CASE WHEN ciudad='Bahía Blanca' THEN 0 ELSE 1 END, id DESC"))))
    cr.procesar("BBP pendientes", pend, bajar_uno, guardar_uno_con(None))

    if en_sitio is None:
        buscar_ids_nuevas(cr, ventana, guardar_uno_con(ventana))
        ventana_cerrada()

    with Session(cr.eng) as db:
        base = select(Propiedad.id_externo).where(Propiedad.plataforma == "BBP", Propiedad.estado == "activa")
        if cr.modo == "completa":
            viejas = list(db.scalars(base.order_by(Propiedad.ultima_vez_vista.asc().nulls_first())))
        else:
            sin_datos = list(db.scalars(base.where(
                (func.coalesce(Propiedad.inmobiliaria, "") == "") | Propiedad.lat.is_(None))
                .order_by(Propiedad.id.desc()).limit(CFG["reverificar_por_ronda"])))
            resto = CFG["reverificar_por_ronda"] - len(sin_datos)
            viejas = sin_datos + (list(db.scalars(base.where(
                func.coalesce(Propiedad.inmobiliaria, "") != "", Propiedad.lat.is_not(None))
                .order_by(Propiedad.ultima_vez_vista.asc().nulls_first(), Propiedad.id.desc()).limit(resto))) if resto > 0 else [])
    cr.procesar("BBP re-lectura rotativa", viejas, bajar_uno, guardar_uno_con(None))


def buscar_ids_nuevas(cr: Corrida, ventana: tuple, guardar_uno: Callable):
    """Respaldo del sitemap: prueba números por encima del más alto conocido hasta N fallos seguidos."""
    with Session(cr.eng) as db:
        tope = db.scalar(text("SELECT MAX(id_externo::bigint) FROM propiedades WHERE plataforma='BBP' "
                              "AND id_externo ~ '^[0-9]+$'")) or 95000
    siguiente, fallos = int(tope) + 1, 0
    while fallos < CFG["fallos_seguidos_para_cortar"]:
        if not cr.queda_tiempo():
            raise SinTiempo("BBP búsqueda por número")
        ids = [str(i) for i in range(siguiente, siguiente + 20)]
        siguiente += 20
        with ThreadPoolExecutor(max_workers=CFG["hilos"]) as ex:
            res = list(ex.map(bbp.bajar_ficha, ids))
        with Session(cr.eng) as db, db.begin():
            for ide, r in zip(ids, res, strict=True):  # en orden, para contar fallos seguidos
                if r.estado == "ok":
                    fallos = 0
                    with db.begin_nested():
                        guardar_uno(db, ide, r)
                else:
                    fallos += 1


# ================================================================== IBB
def actualizar_ibb(cr: Corrida):
    with Session(cr.eng) as db:
        anterior = _fecha(cr.meta_get(db, "ibb_ultima_revision"))
    t_ahora = ahora_local()
    try:
        avisos, credito = ibb.enumerar(CFG["ibb_minimo"])
    except Exception as e:
        cr.aviso(f"IBB: no se pudo leer el listado ({e})")
        cr.c["errores"] += 1
        return
    por_ide = {id_externo("IBB", url=u): u for u in avisos}
    with Session(cr.eng) as db:
        conocidos = dict(db.execute(select(Propiedad.id_externo, Propiedad.estado)
                                    .where(Propiedad.plataforma == "IBB")).all())
        nuevas = [i for i in por_ide if i not in conocidos]
        reactivar = [i for i in por_ide if conocidos.get(i) == "baja"]
        faltan = [i for i, e in conocidos.items() if e == "activa" and i not in por_ide]
        if cr.modo == "completa":
            viejas = [i for i, e in conocidos.items() if e == "activa" and i in por_ide]
        else:
            viejas = [i for i in db.scalars(select(Propiedad.id_externo).where(
                Propiedad.plataforma == "IBB", Propiedad.estado == "activa")
                .order_by(Propiedad.ultima_vez_vista.asc().nulls_first()).limit(CFG["ibb_reverificar_por_ronda"]))
                if i in por_ide]
        urls_bd = dict(db.execute(select(Propiedad.id_externo, Propiedad.url).where(Propiedad.plataforma == "IBB")).all())
    cr.detalle["ibb"] = {"en_sitio": len(avisos), "nuevas": len(nuevas), "faltan": len(faltan)}

    def url_de(ide):
        return por_ide.get(ide) or urls_bd.get(ide) or f"{ibb.sitio_ibb()}/listings/{ide}"

    def bajar_uno(ide):
        r = ibb.bajar_ibb(url_de(ide))
        time.sleep(CFG["pausa_seg"])
        return r

    def guardar_con(ventana_n):
        def guardar_uno(db, ide, r):
            url = url_de(ide)
            if r.estado == "ok":
                d = ibb.analizar(r.html, url, avisos.get(url), credito)
                cr.guardar(db, "IBB", ide, url, d, ventana_n, ibb.fotos(r.html))
            elif r.estado == "baja":
                cr.marcar_baja(db, "IBB", ide)
            else:
                cr.marcar_error(db, "IBB", ide)
        return guardar_uno

    cr.procesar("IBB nuevas", nuevas, bajar_uno, guardar_con((anterior, t_ahora)))
    with Session(cr.eng) as db, db.begin():
        cr.meta_set(db, "ibb_ultima_revision", t_ahora.strftime("%Y-%m-%d %H:%M:%S"))
    cr.procesar("IBB vueltas a publicar", reactivar, bajar_uno, guardar_con(None))
    cr.procesar("IBB posibles bajas", faltan, bajar_uno, guardar_con(None))
    if credito:  # apto crédito oficial también para las que no se releen en esta corrida
        slugs = [id_externo("IBB", url=u) for u in credito]
        with Session(cr.eng) as db, db.begin():
            db.execute(update(Propiedad).where(
                Propiedad.plataforma == "IBB", Propiedad.id_externo.in_(slugs),
                func.coalesce(Propiedad.apto_credito, "") != "Sí").values(apto_credito="Sí", pago="Apto crédito"))
    cr.procesar("IBB re-lectura rotativa", [i for i in viejas if i not in nuevas], bajar_uno, guardar_con(None))


# ================================================================== dólar
def actualizar_dolar(cr: Corrida):
    """Dólar bolsa (MEP), mismo formato que El Ojo de Dios en meta['dolar']; se lee cada 6 horas."""
    with Session(cr.eng) as db, db.begin():
        try:
            d = json.loads(cr.meta_get(db, "dolar") or "{}")
        except ValueError:
            d = {}
        hace6 = (ahora_local() - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S")
        if d.get("leido") and d["leido"] > hace6:
            return
        r = bajar("https://dolarapi.com/v1/dolares/bolsa", timeout=15, reintentos=2)
        if r.estado != "ok":
            cr.aviso(f"Dólar: no se pudo actualizar ({r.motivo})")
            return
        j = json.loads(r.html or "{}")
        v = float(j.get("venta") or 0)
        if v > 0:
            nuevo = {"valor": v, "tipo": j.get("nombre") or "bolsa", "fecha": j.get("fechaActualizacion", ""),
                     "leido": ahora_local().strftime("%Y-%m-%d %H:%M:%S")}
            cr.meta_set(db, "dolar", json.dumps(nuevo))


# ================================================================== crédito UVA (una vez por día)
def actualizar_credito_uva(cr: Corrida):
    from app.scraper import credito
    with Session(cr.eng) as db:
        try:
            anterior = json.loads(cr.meta_get(db, "credito") or "{}")
        except ValueError:
            anterior = {}
    nuevo = credito.actualizar(anterior)
    if nuevo:
        with Session(cr.eng) as db, db.begin():
            cr.meta_set(db, "credito", credito.a_json(nuevo))
        cr.aviso(f"Crédito: UVA {((nuevo.get('uva') or {}).get('valor'))}, {len(nuevo.get('lineas') or [])} líneas")


# ================================================================== corrida completa
def preparar_valuacion(cr: "Corrida"):
    """Inmuebles y republicaciones para el mapa de valores. Nunca frena la actualización."""
    if not cr.con_eventos:
        cr.aviso("Mapa de valores: falta aplicar la migración 0004 en la base; se saltea")
        return
    try:
        with Session(cr.eng) as db, db.begin():
            cr.detalle["valuacion"] = valuacion.preparar(db)
    except Exception as e:
        cr.aviso(f"Mapa de valores: {type(e).__name__}: {e}")
        log.exception("valuación")


def correr(url: str, modo: str = "rapida", max_minutos: float = 11, solo: Iterable[str] = ("bbp", "ibb", "dolar")) -> dict:
    eng = engine_para(url_psycopg(url), pool_size=2, max_overflow=2, pool_pre_ping=True)
    candado = eng.connect()
    try:
        if not candado.scalar(text("SELECT pg_try_advisory_lock(:k)"), {"k": CANDADO}):
            log.info("Otra actualización está corriendo; esta se saltea.")
            return {"estado": "salteada"}
        candado.commit()
        cr = Corrida(eng, modo, max_minutos)
        with Session(eng) as db, db.begin():
            fila = CorridaActualizacion(modo=modo, estado="corriendo", detalle={})
            db.add(fila)
            db.flush()
            corrida_id = fila.id
            cr.cargar_genericas(db)
            cr.con_eventos = db.scalar(text("SELECT to_regclass('public.eventos_aviso') IS NOT NULL"))
            anterior = _fecha(cr.meta_get(db, "ultima_revision_sitemap"))
        t_ahora = ahora_local()
        estado = "ok"
        try:
            if "dolar" in solo:
                actualizar_dolar(cr)
                try:
                    actualizar_credito_uva(cr)
                except Exception as e:  # el crédito nunca frena la actualización de propiedades
                    cr.aviso(f"Crédito: {type(e).__name__}: {e}")
            if "bbp" in solo:
                actualizar_bbp(cr, (anterior, t_ahora))
            if "ibb" in solo:
                actualizar_ibb(cr)
            preparar_valuacion(cr)
            with Session(eng) as db, db.begin():
                cr.meta_set(db, "ultima_actualizacion", ahora_local().strftime("%Y-%m-%d %H:%M:%S"))
                if modo == "completa":
                    cr.meta_set(db, "ultima_completa", ahora_local().strftime("%Y-%m-%d %H:%M:%S"))
        except SinTiempo as e:
            estado = "parcial"
            cr.aviso(f"Se terminó el tiempo en «{e}»; sigue en la próxima corrida")
            preparar_valuacion(cr)
        except Exception as e:
            estado = "error"
            cr.aviso(f"ERROR: {type(e).__name__}: {e}")
            log.exception("error en la corrida")
        with Session(eng) as db, db.begin():
            db.execute(update(CorridaActualizacion).where(CorridaActualizacion.id == corrida_id).values(
                fin=func.now(), estado=estado, detalle=cr.detalle, **cr.c))
        resumen = {"estado": estado, **cr.c, **{k: v for k, v in cr.detalle.items() if k in ("bbp", "ibb")}}
        log.info("Fin: %s", json.dumps(resumen, ensure_ascii=False))
        return resumen
    finally:
        try:
            candado.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": CANDADO})
            candado.close()
        finally:
            eng.dispose()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Actualiza la base de Radar Prop desde los sitios")
    ap.add_argument("--modo", choices=("rapida", "completa"), default="rapida")
    ap.add_argument("--max-minutos", type=float, default=11)
    ap.add_argument("--solo", default="bbp,ibb,dolar", help="bbp,ibb,dolar (por defecto, todo)")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        print("Falta DATABASE_URL (en GitHub: Settings → Secrets → Actions).", file=sys.stderr)
        return 2
    r = correr(url, a.modo, a.max_minutos, tuple(x.strip() for x in a.solo.split(",")))
    return 1 if r.get("estado") == "error" else 0


if __name__ == "__main__":
    sys.exit(main())
