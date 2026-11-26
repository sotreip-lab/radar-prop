"""Catálogo de propiedades en memoria del servidor, con la misma lógica de El Ojo de Dios (ui.html).

En El Ojo de Dios el navegador bajaba TODAS las propiedades y filtraba ahí (funciones evaluar, bandas,
prepAnalisis, claveDup...). Acá esa misma lógica corre en el servidor y al navegador solo le llega la página
pedida (máximo 100) o los puntos livianos del mapa.

- Se carga una vez y se recarga sola cuando el worker termina una corrida (meta.ultima_actualizacion cambia).
- Cada fila usa los nombres de columna de la app vieja (fuente, estado_aviso, detectada, sup_cub...) para que
  las reglas se puedan comparar línea por línea con ui.html. El `id` es el id nuevo de `propiedades`.
- Nada se inventa: si un dato no está, queda None y la regla lo trata igual que la app vieja.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.memoria import liberar_memoria
from app.core.texto import sin_marcas
from app.scraper.red import ahora_local
from app.services.credito_lineas import condiciones, simular

PLAT_NOM = {"BBP": "Bahía Blanca Propiedades", "IBB": "IBB", "ZP": "ZonaProp"}
PLAT_CORTO = {"BBP": "BBP", "IBB": "IBB", "ZP": "ZONAPROP"}
PLAT_ORDEN = {"BBP": 0, "IBB": 1, "ZP": 2}
INMOBILIARIAS_EXCLUIDAS = ["re/max", "remax", "re max", "maidana", "etherra", "ge inmobiliaria", "g.e. inmobiliaria",
                           "g.e inmobiliaria"]
TIPO_VIV = re.compile(r"^(casa|departamento|ph|duplex|dúplex|chalet|triplex)", re.I)
BENEF_GRAL = re.compile(r"todos|sueldo|dependencia|cuenta", re.I)


def norm(s: Any) -> str:
    return sin_marcas(str(s or "")).lower()


def js_round(x: float) -> int:
    """Math.round de JavaScript (las mitades redondean hacia arriba; el round de Python redondea al par)."""
    return math.floor(x + 0.5)


def to_fixed(x: float, dec: int = 1) -> str:
    """Number.toFixed de JavaScript: redondea el valor binario exacto, con las mitades hacia arriba."""
    from decimal import ROUND_HALF_UP, Decimal
    q = Decimal(1).scaleb(-dec)
    return str(Decimal(x).quantize(q, rounding=ROUND_HALF_UP))


def _f(v) -> float | None:
    return None if v is None else float(v)


def _txt(d: datetime | None, solo_fecha: bool = False) -> str | None:
    if d is None:
        return None
    return d.strftime("%Y-%m-%d") if solo_fecha else d.strftime("%Y-%m-%d %H:%M:%S")


def _fecha_aprox(d: datetime | None) -> str | None:
    """pub_aprox tal como lo guardaba la app vieja: con hora (fecha de las fotos de BBP) o solo el día (IBB)."""
    if d is None:
        return None
    return _txt(d, solo_fecha=(d.hour, d.minute, d.second) == (0, 0, 0))


def mediana(a: list[float]) -> float | None:
    if not a:
        return None
    b = sorted(a)
    m = len(b) >> 1
    return b[m] if len(b) % 2 else (b[m - 1] + b[m]) / 2


def precio_real(p, mon, op) -> bool:
    """precioReal() de ui.html: precios de relleno (111.111.111, 123.456.789...) no sirven para comparar."""
    if not p or p <= 0:
        return False
    d = str(js_round(p))
    if len(d) >= 5 and len(set(d)) == 1:
        return False
    if len(d) >= 6 and ("123456789".startswith(d[:6]) or "987654321".startswith(d[:6])):
        return False
    if op != "Venta":
        return p >= (20 if mon == "USD" else 1000)
    if mon == "ARS":
        return p >= 100000
    return 1000 <= p <= 20e6


def bandas(b: float, mon: str) -> dict:
    """USD: regla del Rol (±5.000 y +7%). Pesos: ±5% y +7%."""
    if mon == "ARS":
        return {"loV": b * 0.95, "hiV": b * 1.05, "topV": b * 1.07}
    return {"loV": b - 5000, "hiV": b + 5000, "topV": max(b * 1.07, b + 5000)}


def fmt(n) -> str:
    return "" if n is None else f"{js_round(n):,}".replace(",", ".")


def sim(m) -> str:
    return "$" if m == "ARS" else "USD"


def dias_desde(f: str | None, ahora: datetime) -> int | None:
    """diasDesde() de ui.html. Igual que en el navegador, una fecha sin hora ("2026-11-11") cuenta como la
    medianoche UTC, que en Bahía Blanca son las 21 h del día anterior."""
    if not f:
        return None
    try:
        if len(f.strip()) <= 10:
            d = datetime.strptime(f[:10], "%Y-%m-%d") - timedelta(hours=3)
        else:
            d = datetime.strptime(f[:19], "%Y-%m-%d %H:%M:%S")
        return max(0, math.floor((ahora - d).total_seconds() / 86400))
    except ValueError:
        return None


def clave_dir(direccion: str | None) -> str | None:
    d = re.sub(r"[^a-z0-9]", "", norm((direccion or "").split(",")[0]))
    return d if re.search(r"\d", d) and len(d) >= 5 else None


def clave_dup(o: dict) -> str | None:
    if not o.get("precio") or not o.get("direccion"):
        return None
    d = clave_dir(o["direccion"])
    if not d:
        return None
    return f"{d}|{js_round(o['precio'] / 1000)}|{o.get('operacion') or ''}|{o.get('moneda') or ''}"


# ------------------------------------------------------------------ textos de publicación (pubCorta / pubTitulo)
def _dm(t: str | None) -> str:
    return f"{t[8:10]}/{t[5:7]}" if t else ""


def _hm(t: str | None) -> str:
    return t[11:16] if t else ""


def pub_corta(o: dict, inicio: str) -> str:
    if o.get("detectada") and o.get("detectada_desde"):
        return f"{_dm(o['detectada'])} {_hm(o['detectada'])}"
    if o.get("detectada"):
        return f"≤ {_dm(o['detectada'])} {_hm(o['detectada'])}"
    if o.get("pub_txt"):
        t = re.sub(r"^Publicado\s+", "", o["pub_txt"], flags=re.I)
        return "≈ " + re.sub(r"alrededor de ", "", t, flags=re.I)
    if o.get("pub_aprox"):
        return f"≈ {_dm(o['pub_aprox'])}/{o['pub_aprox'][2:4]}"
    return f"antes {_dm(inicio)}"


def pub_titulo(o: dict, inicio: str) -> str:
    if o.get("detectada") and o.get("detectada_desde"):
        mismo = o["detectada_desde"][:10] == o["detectada"][:10]
        return (f"Publicada entre {_dm(o['detectada_desde'])} {_hm(o['detectada_desde'])} y "
                f"{'' if mismo else _dm(o['detectada']) + ' '}{_hm(o['detectada'])} hs")
    if o.get("detectada"):
        return f"Ya estaba publicada cuando se detectó por primera vez ({_dm(o['detectada'])} {_hm(o['detectada'])} hs)"
    if o.get("pub_txt"):
        extra = f" (≈ {_dm(o['pub_aprox'] + ' ')}/{o['pub_aprox'][:4]})" if o.get("pub_aprox") else ""
        return f"Según {PLAT_NOM.get(o['fuente'], o['fuente'])}: {o['pub_txt']}{extra}"
    if o.get("pub_aprox"):
        return (f"Fotos del aviso subidas el {_dm(o['pub_aprox'])}/{o['pub_aprox'][:4]} (el sitio no informa la fecha "
                "de publicación; es la mejor aproximación)")
    return f"Ya estaba publicada al crear la base ({_dm(inicio)}); el sitio no informa la fecha original"


def miles(n) -> str:
    """Formato de miles de app.py (el de Python, no el redondeo de JavaScript)."""
    return f"{n:,.0f}".replace(",", ".")


def ficha_whatsapp(r: dict) -> str:
    """ficha_whatsapp() de app.py: texto fijo listo para copiar."""
    if r.get("estado_aviso") == "baja":
        return "Publicación dada de baja (link no existe más)"
    barrio, direc = (r.get("barrio") or "").strip(), (r.get("direccion") or "").strip()
    bd = ", ".join(x for x in (barrio, direc) if x) or "-"
    dorm = r.get("dormitorios")
    dorm_t = "-" if dorm is None else ("Monoambiente" if dorm == 0 else str(dorm))
    precio, mon = r.get("precio_publicado"), r.get("moneda")
    simb = "$" if mon == "ARS" else "U$S"
    pres = f"{simb} {miles(precio)}" if precio else "Consultar"
    m2 = r.get("m2_base")
    pm2 = f"{simb} {miles(precio / m2)}" if (precio and m2) else "-"
    lineas = [
        f"*Inmueble:* {r.get('tipo') or 'No figura'}",
        f"*Ciudad:* {r.get('ciudad') or 'No figura'}",
        f"*Barrio y dirección:* {bd}",
        f"*Dormitorios:* {dorm_t}",
        f"*Espacio exterior:* {r.get('exterior') or 'No figura'}",
        f"*🚗 Estacionamiento:* {r.get('estacionamiento') or 'No figura'}",
    ]
    if r.get("amoblado") not in (None, "", "No figura"):
        lineas.append(f"*🛋️ Amoblado:* {'Sí' if r['amoblado'] == 'Amoblado' else r['amoblado']}")
    lineas += [
        f"*Pago:* {r.get('pago') or 'Contado (no figura apto crédito)'}",
        f"*💰Presupuesto:* {pres}",
        f"*Antigüedad:* {r.get('antiguedad') or 'No figura'}",
        f"*m2:* {miles(m2) if m2 else '-'}",
        f"*Precio por M2:* {pm2}",
    ]
    return "\n".join(lineas)


# ------------------------------------------------------------------ crédito UVA (sistema francés)
def lineas_viv(cred: dict) -> list[dict]:
    return [ln for ln in (cred or {}).get("lineas", []) if ln.get("destino") == "Vivienda única"]


def candidatas(cred: dict) -> list[dict]:
    """Líneas de uso general (no exclusivas de empleados públicos), de la más barata a la más cara."""
    viv = lineas_viv(cred)
    cand = [ln for ln in viv if ln.get("es_banco") is not False and BENEF_GRAL.search(ln.get("beneficiario") or "")
            and not re.search(r"públic", ln.get("beneficiario") or "", re.I)
            and not re.search(r"p[uú]blico", ln.get("linea") or "", re.I) and ln.get("ltv", 100) <= 80]
    return sorted(cand or viv, key=lambda ln: ln["tea"])


def linea_defecto(cred: dict) -> dict | None:
    lista = candidatas(cred)
    return lista[0] if lista else None


def precio_pesos(o: dict, dolar: float) -> float | None:
    if not o.get("precio"):
        return None
    if o.get("moneda") == "ARS":
        return o["precio"] if o["precio"] >= 15e6 else None  # menos de $15 M suele ser un aviso en dólares mal cargado
    return o["precio"] * dolar if dolar else None


def calc_cuota(o: dict, ln: dict | list[dict], cred: dict, dolar: float, anios: int | None = None,
               ltv: float | None = None) -> dict | None:
    """Simula con la línea dada. Con una lista, usa la más barata para la que la propiedad califica (o None)."""
    pp = precio_pesos(o, dolar)
    if not pp or not ln:
        return None
    uva = (cred.get("uva") or {}).get("valor")
    plazo = anios or cred.get("plazo_anios", 20)
    for x in ln if isinstance(ln, list) else [ln]:
        r = simular(pp, x, uva, plazo, ltv)
        if r and (r["califica"] or not isinstance(ln, list)):
            return {**r, "linea": _linea_corta(x)}
    return None


def _linea_corta(ln: dict) -> dict:
    return {k: ln.get(k) for k in ("banco", "linea", "tea", "beneficiario", "rci", "ltv", "plazo", "monto_max", "nota")}


# ------------------------------------------------------------------ filtros
@dataclass
class Filtros:
    mon: str = "USD"
    b: float = 0                    # presupuesto
    pct_abajo: float = 15
    rojas: bool = False
    pmin: float = 0
    pmax: float = 0
    oper: str = "Venta"
    ciudad: str = "Bahía Blanca"
    tipos: list[str] = field(default_factory=list)
    barrios: list[str] = field(default_factory=list)
    sin_barrio: bool = False
    dorm: str = ""                  # "" | "0".."5" ("5" = 5 o más)
    dorm_modo: str = "exacto"       # exacto | min
    banos: int = 0
    supmin: float = 0
    patio: str = ""                 # "" | si | no
    cochera: str = ""
    pileta: str = ""
    balcon: str = ""
    parrilla: str = ""
    amoblado: str = ""
    credito: str = ""               # "" | si
    estrenar: bool = False
    kw: str = ""
    nuevas_horas: int = 0
    margen: int = 0                 # metros alrededor de la zona dibujada
    sin_dato: bool = False          # incluir los que no informan un dato
    sin_ubic: bool = False          # incluir avisos sin ubicación cuando hay zona
    excl: bool = True               # sin inmobiliarias excluidas
    bajas: bool = False
    bajo_precio: bool = False
    margen_neg: bool = False
    dmin: int | None = None
    dmax: int | None = None
    m2max: float = 0
    bajo_min: float = 0
    cuota_max: float = 0
    plataforma: str = "todas"
    qg: str = ""                    # buscador en toda la base (ID, link o texto): ignora los demás filtros
    solo_ids: list[int] | None = None
    orden: str = ""                 # "" (semáforo) | precio | dif | usdm2 | detectada | vsb | dormitorios | sup_cub
    orden_dir: int = 1

    @classmethod
    def de_dict(cls, d: dict) -> Filtros:
        f = cls()
        for k, v in (d or {}).items():
            if hasattr(f, k) and v is not None:
                setattr(f, k, v)
        return f


def leer_qg(v: str) -> dict | None:
    v = (v or "").strip()
    if not v:
        return None
    m = re.search(r"https?://\S+", v, re.I)
    if m:
        u = re.sub(r"[?#].*$", "", m.group(0).lower()).rstrip("/")
        ide = re.search(r"bahiablancapropiedades\.com/propiedad/(\d+)", u)
        return {"url": None if ide else re.sub(r"^https?://(www\.)?", "", u), "id": ide.group(1) if ide else None,
                "w": [], "bbp": bool(ide)}
    if re.fullmatch(r"\d{4,}", v):
        return {"id": v, "url": None, "w": []}
    return {"id": None, "url": None, "w": norm(v).split()}


# ------------------------------------------------------------------ catálogo
SQL_PROPS = """
SELECT p.id, p.plataforma, p.id_externo, p.id_legado, p.url, p.titulo, p.tipo, p.operacion, p.direccion, p.barrio,
       p.ciudad, p.inmobiliaria, p.moneda, p.precio, p.precio_anterior, p.cambio_precio, p.dormitorios, p.banos,
       p.m2_cubiertos, p.m2_totales, p.m2_base, p.antiguedad, p.estado_inmueble, p.patio, p.cochera, p.apto_credito,
       p.pileta, p.parrilla, p.exterior, p.estacionamiento, p.pago, p.expensas, p.amoblado, left(p.descripcion, 1500) AS descripcion,
       p.ubicacion_valida, p.lat, p.lng, p.estado, p.primera_vez_vista, p.ultima_vez_vista, p.ultima_verif_origen,
       p.fecha_baja, p.fecha_baja_origen, p.publicada_desde, p.publicada_hasta, p.pub_txt, p.pub_aprox,
       p.ia_resumen, p.ia_json, p.datos_extra->>'dorm_fuente' AS dorm_fuente, p.fotos->>0 AS foto
FROM propiedades p WHERE p.estado IN ('activa', 'baja')
ORDER BY p.id_legado NULLS LAST, p.id
"""


class Catalogo:
    def __init__(self, engine: Engine, refresco_seg: int = 30):
        self.engine = engine
        self.refresco_seg = refresco_seg
        self.lock = threading.Lock()
        self.version = ""
        self.revisado = 0.0
        self.data: list[dict] = []
        self.por_id: dict[int, dict] = {}
        self.dolar: dict = {}
        self.credito: dict = {}
        self.inicio = ""
        self.ultima = ""
        self.excluidas = [norm(x) for x in INMOBILIARIAS_EXCLUIDAS]
        self.ldef: dict | None = None
        self.lcand: list[dict] = []
        self.recargando = False

    # -------------------------------------------------------------- carga
    def _version_actual(self, c) -> str:
        r = c.execute(text("SELECT (SELECT valor FROM meta WHERE clave='ultima_actualizacion'), "
                           "(SELECT COUNT(*) FROM propiedades), (SELECT MAX(actualizado_en) FROM propiedades), "
                           "(SELECT md5(string_agg(valor, '|' ORDER BY clave)) FROM meta WHERE clave IN ('credito', 'dolar'))")).first()
        return f"{r[0]}|{r[1]}|{r[2]}|{r[3]}"

    def asegurar(self) -> Catalogo:
        if self.data and time.monotonic() - self.revisado < self.refresco_seg:
            return self
        with self.lock:
            if self.data and time.monotonic() - self.revisado < self.refresco_seg:
                return self
            crudo = None
            with self.engine.connect() as c:
                v = self._version_actual(c)
                if not self.data:
                    crudo = self._leer(c)
                elif v != self.version:
                    if RECARGA_EN_FONDO:
                        # Hay datos nuevos (pasó el actualizador): se cargan aparte y se cambian de una vez.
                        # Mientras tanto se sigue respondiendo con los anteriores, así nadie espera la recarga.
                        if not self.recargando:
                            self.recargando = True
                            threading.Thread(target=_recargar_en_fondo, args=(self, v), daemon=True).start()
                    else:
                        crudo = self._leer(c)
            if crudo is not None:
                self._procesar(*crudo)
                self.version = v
                del crudo
                liberar_memoria()
            self.revisado = time.monotonic()
        return self

    def forzar(self):
        self.revisado = 0
        self.version = ""

    def _cargar(self, c):
        self._procesar(*self._leer(c))

    def _leer(self, c):
        """Solo lee de la base (rápido); el procesamiento se hace después, ya sin ocupar una conexión."""
        meta = dict(c.execute(text("SELECT clave, valor FROM meta")).all())
        hist_filas = c.execute(text("SELECT propiedad_id, fecha, precio_anterior, precio FROM historial_precios ORDER BY fecha")).all()
        filas = c.execute(text(SQL_PROPS)).mappings().all()
        return meta, hist_filas, filas

    def _procesar(self, meta, hist_filas, filas):
        try:
            self.dolar = json.loads(meta.get("dolar") or "{}")
        except ValueError:
            self.dolar = {}
        try:
            self.credito = json.loads(meta.get("credito") or "{}")
        except ValueError:
            self.credito = {}
        self.credito.setdefault("plazo_anios", 20)
        self.inicio = meta.get("inicio_base") or ""
        self.ultima = meta.get("ultima_actualizacion") or ""
        hist: dict[int, list] = {}
        for pid, fe, an, de in hist_filas:
            hist.setdefault(pid, []).append([_txt(fe), _f(an), _f(de)])
        data = [self._fila(r, hist.get(r["id"], [])) for r in filas]
        self.data = data
        self.por_id = {o["id"]: o for o in data}
        self.credito["lineas"] = [condiciones(x) for x in self.credito.get("lineas") or []]
        self.lcand = candidatas(self.credito)
        self.ldef = self.lcand[0] if self.lcand else None
        self._analisis()

    def _fila(self, r, hist) -> dict:
        ia = r["ia_json"] if isinstance(r["ia_json"], dict) else None
        o = {
            "id": r["id"], "fuente": r["plataforma"], "id_externo": r["id_externo"], "id_legado": r["id_legado"],
            "url": r["url"], "titulo": r["titulo"], "tipo": r["tipo"], "operacion": r["operacion"],
            "direccion": r["direccion"], "barrio": r["barrio"], "ciudad": r["ciudad"], "inmobiliaria": r["inmobiliaria"],
            "moneda": r["moneda"], "precio": _f(r["precio"]), "precio_anterior": _f(r["precio_anterior"]),
            "cambio_precio": _txt(r["cambio_precio"]), "dormitorios": r["dormitorios"], "dorm_fuente": r["dorm_fuente"],
            "banos": r["banos"], "sup_cub": _f(r["m2_cubiertos"]), "sup_tot": _f(r["m2_totales"]), "m2_base": _f(r["m2_base"]),
            "antiguedad": r["antiguedad"], "estado": r["estado_inmueble"], "patio": r["patio"], "cochera": r["cochera"],
            "apto_credito": r["apto_credito"], "pileta": r["pileta"], "parrilla": r["parrilla"], "exterior": r["exterior"],
            "estacionamiento": r["estacionamiento"], "pago": r["pago"], "expensas": r["expensas"], "amoblado": r["amoblado"],
            "descripcion": r["descripcion"] or "",
            "lat": _f(r["lat"]) if r["ubicacion_valida"] else None, "lng": _f(r["lng"]) if r["ubicacion_valida"] else None,
            "estado_aviso": "activo" if r["estado"] == "activa" else "baja",
            "alta": _txt(r["primera_vez_vista"], True),
            "ultima_verif": (_txt(r["ultima_vez_vista"]) or "") + (f" ({r['ultima_verif_origen']})" if r["ultima_verif_origen"] else ""),
            "fecha_baja": (_txt(r["fecha_baja"]) or "") + (f" ({r['fecha_baja_origen']})" if r["fecha_baja_origen"] else "") or None,
            "detectada": _txt(r["publicada_hasta"]), "detectada_desde": _txt(r["publicada_desde"]),
            "pub_txt": r["pub_txt"], "pub_aprox": _fecha_aprox(r["pub_aprox"]),
            "ia_resumen": r["ia_resumen"], "foto": r["foto"], "hist": hist,
        }
        o["fecha_baja"] = o["fecha_baja"] or None
        o["_alertas"] = ia.get("alertas") if ia and isinstance(ia.get("alertas"), list) else []
        o["_n"] = norm(" ".join(str(x or "") for x in (o["titulo"], o["direccion"], o["barrio"], o["descripcion"])))
        inmo = norm(o["inmobiliaria"])
        o["_excl"] = any(x in inmo for x in self.excluidas)
        o["_barrio"] = (o["barrio"] or "").strip()
        o["precio_publicado"] = o["precio"]
        o["_precio_falso"] = None
        if o["precio"] and not precio_real(o["precio"], o["moneda"], o["operacion"]):
            o["_precio_falso"], o["precio"] = o["precio"], None
        o["balcon"] = "Sí" if re.search(r"Balc|Terraza", o["exterior"] or "") else "No informado"
        return o

    def _analisis(self):
        """prepAnalisis() de ui.html: m² contra el barrio, rentabilidad, misma propiedad con otro precio,
        días en el mercado, bajas de precio, cuota de crédito y margen de negociación."""
        ahora = ahora_local()
        act = [o for o in self.data if o["estado_aviso"] == "activo"]
        g: dict[str, list] = {}
        for o in act:
            if not o["precio"] or not o["m2_base"] or o["m2_base"] < 15:
                continue
            v = o["precio"] / o["m2_base"]
            g.setdefault(f"b|{o['operacion']}|{o['tipo']}|{o['moneda']}|{o['ciudad']}|{o['_barrio']}", []).append(v)
            g.setdefault(f"c|{o['operacion']}|{o['tipo']}|{o['moneda']}|{o['ciudad']}", []).append(v)
        med = {k: {"med": mediana(v), "n": len(v)} for k, v in g.items()}
        ga: dict[str, list] = {}
        dv = float(self.dolar.get("valor") or 0)

        def tcorto(tipo):
            t = norm(tipo)
            return "dep" if t.startswith("dep") else "casa" if t.startswith("casa") else t
        for o in act:
            if o["operacion"] != "Alquiler" or not o["precio"] or o["dormitorios"] is None:
                continue
            ars = (o["precio"] * dv if dv else None) if o["moneda"] == "USD" else o["precio"]
            if not ars or ars < 50000:
                continue
            t, d = tcorto(o["tipo"]), min(o["dormitorios"], 4)
            ga.setdefault(f"b|{t}|{d}|{o['ciudad']}|{o['_barrio']}", []).append(ars)
            ga.setdefault(f"c|{t}|{d}|{o['ciudad']}", []).append(ars)
        gd: dict[str, list] = {}
        for o in act:
            if not o["precio"] or not o["direccion"]:
                continue
            d = re.sub(r"[^a-z0-9]", "", norm(o["direccion"].split(",")[0]))
            if not re.search(r"\d", d) or len(d) < 5:
                continue
            gd.setdefault(f"{d}|{o['operacion']}|{norm(o['tipo'])}|{'' if o['dormitorios'] is None else o['dormitorios']}|{o['moneda']}",
                          []).append(o)
        for o in self.data:
            o["_vsb"] = o["_renta"] = o["_otros_precios"] = o["_cuota"] = None
            o["_margen"] = ""
            o["_dias"], o["_dias_exacto"], o["_bajas"], o["_baja_pct"] = None, False, 0, 0.0
            if o["estado_aviso"] != "activo":
                continue
            if o["precio"] and o["m2_base"] and o["m2_base"] >= 15:
                v = o["precio"] / o["m2_base"]
                b = med.get(f"b|{o['operacion']}|{o['tipo']}|{o['moneda']}|{o['ciudad']}|{o['_barrio']}")
                c = med.get(f"c|{o['operacion']}|{o['tipo']}|{o['moneda']}|{o['ciudad']}")
                ref = ({**b, "nivel": "barrio", "donde": o["_barrio"]} if o["_barrio"] and b and b["n"] >= 5
                       else {**c, "nivel": "ciudad", "donde": o["ciudad"]} if c and c["n"] >= 8 else None)
                if ref and abs(v / ref["med"] - 1) <= 1.5:
                    o["_vsb"] = {"pct": (v / ref["med"] - 1) * 100, "med": ref["med"], "n": ref["n"],
                                 "nivel": "vs barrio" if ref["nivel"] == "barrio" else "vs ciudad", "donde": ref["donde"]}
            if (o["operacion"] == "Venta" and o["moneda"] == "USD" and (o["precio"] or 0) >= 15000 and dv
                    and o["dormitorios"] is not None and TIPO_VIV.search(o["tipo"] or "")):
                t, d = tcorto(o["tipo"]), min(o["dormitorios"], 4)
                b2, c2 = ga.get(f"b|{t}|{d}|{o['ciudad']}|{o['_barrio']}"), ga.get(f"c|{t}|{d}|{o['ciudad']}")
                ref2 = ({"a": b2, "nivel": "mismo barrio"} if o["_barrio"] and b2 and len(b2) >= 4
                        else {"a": c2, "nivel": "misma ciudad"} if c2 and len(c2) >= 6 else None)
                if ref2:
                    alq = mediana(ref2["a"])
                    assert alq is not None
                    pct = alq * 12 / dv / o["precio"] * 100
                    if 1 <= pct <= 15:
                        o["_renta"] = {"pct": pct, "alq": alq, "n": len(ref2["a"]), "nivel": ref2["nivel"], "dolar": dv}
            if o["precio"] and o["direccion"]:
                d = re.sub(r"[^a-z0-9]", "", norm(o["direccion"].split(",")[0]))
                gr = gd.get(f"{d}|{o['operacion']}|{norm(o['tipo'])}|{'' if o['dormitorios'] is None else o['dormitorios']}|{o['moneda']}", [])
                distintos = len({js_round(x["precio"] / 1000) for x in gr})
                otros = [] if distintos > 3 else [
                    x for x in gr if x is not o and (x["fuente"] != o["fuente"] or norm(x["inmobiliaria"]) != norm(o["inmobiliaria"]))
                    and 0.01 < abs(x["precio"] - o["precio"]) / o["precio"] <= 0.25
                    and ((abs(x["m2_base"] - o["m2_base"]) / o["m2_base"] <= 0.1) if (x["m2_base"] and o["m2_base"])
                         else bool(TIPO_VIV.search(o["tipo"] or "") and o["dormitorios"] is not None))]
                if otros:
                    o["_otros_precios"] = [{"id": x["id"], "fuente": x["fuente"], "inmobiliaria": x["inmobiliaria"],
                                            "precio": x["precio"], "moneda": x["moneda"], "url": x["url"]} for x in otros]
            f = o["detectada"] or o["pub_aprox"]
            o["_dias"], o["_dias_exacto"] = dias_desde(f, ahora), bool(f)
            if o["_dias"] is None and o["alta"]:
                o["_dias"] = dias_desde(o["alta"] + " 00:00:00", ahora)
            h = o["hist"]
            o["_bajas"] = sum(1 for x in h if x[2] is not None and x[1] is not None and x[2] < x[1])
            max_p = max([o["precio"] or 0] + [x[1] or 0 for x in h])
            o["_baja_pct"] = (1 - o["precio"] / max_p) * 100 if o["precio"] and max_p > o["precio"] else 0.0
            if (o["operacion"] == "Venta" and re.match(r"^Sí", o["apto_credito"] or "") and TIPO_VIV.search(o["tipo"] or "")
                    and self.ldef):
                o["_cuota"] = calc_cuota(o, self.lcand, self.credito, dv)
            mas_barata = bool(o["_otros_precios"] and any(x["precio"] < o["precio"] for x in o["_otros_precios"]))
            o["_margen"] = ("alto" if ((o["_dias_exacto"] and o["_dias"] >= 365) or o["_bajas"] >= 2 or o["_baja_pct"] >= 8)
                            else "medio" if ((o["_dias_exacto"] and o["_dias"] >= 180) or o["_bajas"] >= 1 or mas_barata) else "")

    # -------------------------------------------------------------- opciones de los filtros
    def opciones(self, operacion: str, ciudad: str) -> dict:
        def contar(arr, f):
            m: dict[str, int] = {}
            for o in arr:
                k = f(o)
                if k:
                    m[k] = m.get(k, 0) + 1
            return sorted(m.items(), key=lambda x: -x[1])
        act = [o for o in self.data if o["estado_aviso"] == "activo"]
        base = [o for o in act if o["operacion"] == operacion]
        b2 = [o for o in base if not ciudad or o["ciudad"] == ciudad]
        barrios = sorted((x for x in contar(b2, lambda o: o["_barrio"]) if not re.match(r"^\d", x[0])), key=lambda x: x[0])
        return {"operaciones": contar(act, lambda o: o["operacion"]), "ciudades": contar(base, lambda o: o["ciudad"]),
                "tipos": contar(b2, lambda o: o["tipo"]), "barrios": barrios}

    # -------------------------------------------------------------- evaluar (semáforo)
    def evaluar(self, o: dict, F: Filtros, ctx: dict) -> dict | None:
        obs: list[str] = []
        amarillo = False
        if ctx.get("solo_ids") is not None and o["id"] not in ctx["solo_ids"]:
            return None
        QG = ctx.get("qg")
        if QG:
            if not self._qg_match(o, QG):
                return None
            return {"o": o, "color": "", "orden": 9 if o["estado_aviso"] == "baja" else 0, "zona": "", "dif": None,
                    "obs": "dada de baja" if o["estado_aviso"] == "baja" else "",
                    "usdm2": (o["precio"] / o["m2_base"]) if (o["precio"] and o["m2_base"]) else None}
        if o["estado_aviso"] == "baja" and not F.bajas:
            return None
        if o["operacion"] != F.oper:
            return None
        if F.ciudad and o["ciudad"] != F.ciudad:
            return None
        if ctx["tipos"] and o["tipo"] not in ctx["tipos"]:
            return None
        if F.excl and o["_excl"]:
            return None
        if ctx["barrios"]:
            if not o["_barrio"]:
                if not F.sin_barrio:
                    return None
                amarillo = True
                obs.append("barrio no informado")
            elif o["_barrio"] not in ctx["barrios"]:
                return None
        if ctx["kw"] and not all(w in o["_n"] for w in ctx["kw"]):
            return None
        zona = None
        ocultar_ubic = False
        dist = ctx.get("zona_dist")
        if dist is not None:
            if o["lat"] is None:
                if not F.sin_ubic:
                    ocultar_ubic = True
                else:
                    amarillo = True
                    obs.append("sin ubicación en el mapa")
                    zona = "sin"
            else:
                dd = dist.get(o["id"])
                if dd is None:
                    return None
                if dd <= 0.5:
                    zona = "dentro"
                else:
                    zona = "cerca"
                    obs.append(f"a {js_round(dd / 10) * 10} m de la zona")
        if ctx["nuevas"]:
            f = o["detectada"] or (o["pub_aprox"] + " 23:59:59" if (F.nuevas_horas >= 72 and o["pub_aprox"]) else None)
            if not (f and f >= ctx["nuevas"]):
                return None
        if F.bajo_precio and not (o["precio_anterior"] and o["precio"] is not None and o["precio"] < o["precio_anterior"]):
            return None
        if F.margen_neg and not o["_margen"]:
            return None
        if F.dmin is not None or F.dmax is not None:
            if o["_dias"] is None or not o["_dias_exacto"]:
                return None
            if F.dmin is not None and o["_dias"] < F.dmin:
                return None
            if F.dmax is not None and o["_dias"] > F.dmax:
                return None
        if F.bajo_min and not (o["_baja_pct"] >= F.bajo_min or (
                o["precio_anterior"] and o["precio"] is not None and o["precio"] < o["precio_anterior"]
                and (1 - o["precio"] / o["precio_anterior"]) * 100 >= F.bajo_min)):
            return None
        if F.cuota_max:
            if not o["_cuota"] or o["_cuota"]["cuota"] > F.cuota_max:
                return None
        if F.m2max:
            if not (o["precio"] and o["m2_base"] and o["moneda"] == F.mon):
                return None
            if o["precio"] / o["m2_base"] > F.m2max:
                return None
        if F.dorm != "":
            d = int(F.dorm)
            if o["dormitorios"] is None:
                if not F.sin_dato:
                    return None
                amarillo = True
                obs.append("dormitorios no informados")
            else:
                ok = o["dormitorios"] >= 5 if F.dorm == "5" else (o["dormitorios"] >= d if F.dorm_modo == "min" else o["dormitorios"] == d)
                if not ok:
                    return None
                if o["dorm_fuente"] == "descripción":
                    obs.append("dorm. según descripción")
                elif o["dorm_fuente"] == "IA":
                    obs.append("dorm. según IA")
        if F.banos:
            if o["banos"] is None:
                if not F.sin_dato:
                    return None
                amarillo = True
                obs.append("baños no informados")
            elif o["banos"] < F.banos:
                return None
        if F.supmin:
            if o["sup_cub"] is None:
                if not F.sin_dato:
                    return None
                amarillo = True
                obs.append("m² no informados")
            elif o["sup_cub"] < F.supmin:
                return None
        for k in ("patio", "cochera", "pileta", "balcon", "parrilla"):
            want = getattr(F, k)
            if not want:
                continue
            v = o.get(k) or "No informado"
            if v == "No informado":
                if want == "no":
                    continue
                if not F.sin_dato:
                    return None
                amarillo = True
                obs.append(k + " no informado")
                continue
            si = v.startswith("Sí")
            if (want == "si") != si:
                return None
            if "desc." in v:
                obs.append(k + " según descripción")
            elif "IA" in v:
                obs.append(k + " según IA")
        if F.amoblado:
            v = o["amoblado"] or "No figura"
            amo = v in ("Amoblado", "Semi amoblado", "A elección")
            if F.amoblado == "si":
                if not amo:
                    return None
                if v != "Amoblado":
                    obs.append(v.lower())
            elif v in ("Amoblado", "Semi amoblado"):
                return None
        if F.credito:
            v = o["apto_credito"] or "No confirmado"
            if v.startswith("No (") or v == "No":
                return None
            # "si": solo las que el aviso (o su descripción / la IA) confirma como aptas crédito.
            # "si_nc": además las que no dicen nada (van en amarillo), como hacía El Ojo de Dios.
            if v == "No confirmado" and F.credito == "si":
                return None
            if v == "No confirmado":
                amarillo = True
                obs.append("crédito no confirmado")
            elif "desc." in v:
                obs.append("crédito según descripción")
            elif "IA" in v:
                obs.append("crédito según IA")
        estr = re.compile(r"estrenar|construcci", re.I)
        if F.estrenar and not estr.search(f"{o['antiguedad']} {o['estado']} {o['descripcion']}"):
            return None
        if estr.search(o["antiguedad"] or ""):
            obs.append(o["antiguedad"])
        p = o["precio"] if (o["moneda"] == F.mon and o["precio"]) else None
        color, barata, dif = "Verde", False, None
        if F.pmin and p is not None and p < F.pmin:
            return None
        if F.pmax and p is not None and p > F.pmax:
            return None
        S = sim(F.mon)
        if p is None:
            if (F.b or F.pmin or F.pmax) and not F.sin_dato:
                return None
            if F.b or F.pmin or F.pmax:
                amarillo = True
                obs.append(("precio en pesos" if o["moneda"] == "ARS" else "precio en dólares")
                           if (o["precio"] and o["moneda"] and o["moneda"] != F.mon) else "precio no informado")
        elif F.b:
            b = F.b
            dif = p - b
            bd = bandas(b, F.mon)
            top_a, piso, top_r = b * 1.15, b * (1 - F.pct_abajo / 100), b * 1.30
            if p < piso:
                return None
            if p < bd["loV"]:
                color, barata = "Amarillo", True
                obs.insert(0, f"{S} {fmt(bd['loV'] - p)} por debajo del rango Verde")
            elif p <= bd["hiV"]:
                color = "Verde"
            elif p <= bd["topV"]:
                color = "Violeta"
                obs.insert(0, f"FRANJA VIOLETA +{to_fixed((p / b - 1) * 100)}%")
            elif p <= top_a:
                color = "Amarillo"
                obs.insert(0, f"+{to_fixed((p / b - 1) * 100)}% sobre presupuesto")
            elif F.rojas and p <= top_r:
                color = "Rojo"
                obs.insert(0, f"+{to_fixed((p / b - 1) * 100)}% sobre presupuesto")
            else:
                return None
        if not F.b:
            color = ""
        elif amarillo and color != "Rojo":
            color = "Amarillo"
        if not o["inmobiliaria"] and o["estado_aviso"] == "activo" and o["fuente"] == "BBP":
            obs.append("inmobiliaria sin verificar todavía")
        if o["_alertas"]:
            obs.append("IA: " + "; ".join(map(str, o["_alertas"])))
        if o["precio_anterior"] and o["precio"] is not None and o["precio"] != o["precio_anterior"]:
            obs.append(f"precio antes {sim(o['moneda'])} {fmt(o['precio_anterior'])} (cambió {o['cambio_precio']})")
        orden = {"Verde": 0, "Violeta": 1, "Amarillo": 3 if barata else 2, "Rojo": 4, "": 0}[color]
        if ocultar_ubic:
            ctx["sin_ubic_ocultas"] = ctx.get("sin_ubic_ocultas", 0) + 1
            return None
        orden_z = 10 if zona == "cerca" else 20 if zona == "sin" else 0
        return {"o": o, "color": color, "orden": orden + orden_z, "zona": zona, "dif": dif, "obs": " · ".join(obs),
                "usdm2": (p / o["m2_base"]) if (p and o["m2_base"]) else None}

    def _qg_match(self, o: dict, QG: dict) -> bool:
        if QG.get("id") or QG.get("url"):
            if QG.get("id") and (str(o["id"]) == QG["id"] or str(o.get("id_legado") or "") == QG["id"]
                                 or (o["fuente"] == "BBP" and o["id_externo"] == QG["id"])):
                return True
            u = re.sub(r"[?#].*$", "", (o["url"] or "").lower())
            return bool(QG.get("url") and QG["url"] in u)
        if "_q" not in o:
            o["_q"] = norm(" ".join(str(x or "") for x in (o["direccion"], o["barrio"], o["titulo"], o["inmobiliaria"],
                                                            o["tipo"], o["ciudad"], o["id"], o["id_externo"])))
        return all(w in o["_q"] for w in QG["w"])

    # -------------------------------------------------------------- buscar
    def buscar(self, F: Filtros, zona_dist: dict[int, float] | None = None) -> dict:
        ctx: dict = {
            "tipos": set(F.tipos or []), "barrios": set(F.barrios or []), "kw": norm(F.kw).split() if F.kw else [],
            "nuevas": (ahora_local() - timedelta(hours=F.nuevas_horas)).strftime("%Y-%m-%d %H:%M:%S") if F.nuevas_horas else "",
            "zona_dist": zona_dist, "qg": leer_qg(F.qg), "solo_ids": set(F.solo_ids) if F.solo_ids is not None else None,
        }
        todos = []
        plat_cnt: dict[str, int] = {}
        for o in self.data:
            r = self.evaluar(o, F, ctx)
            if r:
                todos.append(r)
                plat_cnt[o["fuente"]] = plat_cnt.get(o["fuente"], 0) + 1
        res: list[dict] = []
        dups = 0
        if F.plataforma != "todas":
            res = [r for r in todos if r["o"]["fuente"] == F.plataforma]
        else:  # misma propiedad en varias plataformas: una sola fila con todas sus etiquetas
            todos.sort(key=lambda r: PLAT_ORDEN.get(r["o"]["fuente"], 9))
            vistos: dict[str, dict] = {}
            for r in todos:
                k = clave_dup(r["o"])
                gq = vistos.get(k) if k else None
                if gq and gq["o"]["fuente"] != r["o"]["fuente"] and not any(x["fuente"] == r["o"]["fuente"] for x in gq.get("otros") or []):
                    gq["otros"] = (gq.get("otros") or []) + [r["o"]]
                    dups += 1
                    continue
                r["otros"] = None
                if k and not gq:
                    vistos[k] = r
                res.append(r)
        self._ordenar(res, F)
        colores = {"Verde": 0, "Violeta": 0, "Amarillo": 0, "Rojo": 0}
        for r in res:
            if r["color"]:
                colores[r["color"]] += 1
        return {"res": res, "plataformas": plat_cnt, "dups": dups, "colores": colores,
                "sin_ubic_ocultas": ctx.get("sin_ubic_ocultas", 0)}

    @staticmethod
    def _ordenar(res: list[dict], F: Filtros):
        if not F.orden:
            res.sort(key=lambda r: (r["orden"], -(r["o"]["precio"] if r["o"]["precio"] is not None else -1)))
            return
        k, d = F.orden, (1 if F.orden_dir >= 0 else -1)

        def g(r):
            o = r["o"]
            if k == "color":
                return r["orden"]
            if k == "dif":
                return r["dif"]
            if k == "usdm2":
                return r["usdm2"]
            if k == "detectada":
                return o["detectada"] or o["pub_aprox"] or None
            if k == "vsb":
                return o["_vsb"]["pct"] if o["_vsb"] else None
            return o.get(k)
        con = [r for r in res if g(r) is not None]
        sin = [r for r in res if g(r) is None]
        con.sort(key=g, reverse=d < 0)
        res[:] = con + sin

    # -------------------------------------------------------------- salida liviana
    def fila_lista(self, r: dict, seleccion: set[int], ahora_24h: str) -> dict:
        o = r["o"]
        otros = r.get("otros") or []
        return {
            "id": o["id"], "fuente": o["fuente"], "plataformas": [{"fuente": x["fuente"], "url": x["url"], "id": x["id"]} for x in [o, *otros]],
            "url": o["url"], "color": r["color"], "zona": r["zona"], "dif": r["dif"], "obs": r["obs"], "usdm2": r["usdm2"],
            "tipo": o["tipo"], "operacion": o["operacion"], "dormitorios": o["dormitorios"], "dorm_fuente": o["dorm_fuente"],
            "barrio": o["barrio"], "direccion": o["direccion"], "ciudad": o["ciudad"], "moneda": o["moneda"], "precio": o["precio"],
            "precio_falso": o["_precio_falso"], "sup_cub": o["sup_cub"], "sup_tot": o["sup_tot"], "m2_base": o["m2_base"],
            "exterior": o["exterior"], "estacionamiento": o["estacionamiento"], "amoblado": o["amoblado"], "pago": o["pago"],
            "antiguedad": o["antiguedad"], "inmobiliaria": o["inmobiliaria"], "foto": o["foto"], "lat": o["lat"], "lng": o["lng"],
            "estado_aviso": o["estado_aviso"], "pub_corta": pub_corta(o, self.inicio), "pub_titulo": pub_titulo(o, self.inicio),
            "nueva": bool(o["detectada"] and o["detectada"] >= ahora_24h),
            "bajo": bool(o["precio_anterior"] and o["precio"] is not None and o["precio"] < o["precio_anterior"]),
            "otro_precio": o["_otros_precios"], "vsb": o["_vsb"], "renta": o["_renta"],
            "cuota": {k: o["_cuota"][k] for k in ("cuota", "prestamo", "anios", "ltv", "ingreso")} | {"banco": o["_cuota"]["linea"]["banco"]}
            if o["_cuota"] else None,
            "dias": o["_dias"] if o["_dias_exacto"] else None, "bajas": o["_bajas"], "baja_pct": o["_baja_pct"],
            "margen": o["_margen"], "seleccionada": o["id"] in seleccion, "ficha": ficha_whatsapp(o),
        }

    def detalle(self, pid: int) -> dict | None:
        o = self.por_id.get(pid)
        if not o:
            return None
        neg = []
        S = sim(o["moneda"])
        if o["estado_aviso"] == "activo":
            if o["_dias"] is not None:
                txt = f"{o['_dias']} días" if o["_dias_exacto"] else f"más de {o['_dias']} días (desde que se vigila)"
                if o["fuente"] == "BBP" and o["pub_aprox"] and not o["detectada"]:
                    txt += " (según la fecha de las fotos del aviso)"
                neg.append(["En el mercado", txt])
            if o["hist"]:
                h = " · ".join(f"{_dm(x[0])}/{x[0][2:4]}: {S} {fmt(x[1])} → {fmt(x[2])}" for x in o["hist"])
                if o["_baja_pct"] >= 1:
                    h += f" · −{o['_baja_pct']:.1f}% desde el máximo".replace(".", ",")
                neg.append(["Historial de precio", h])
            if o["_vsb"]:
                v = o["_vsb"]
                neg.append(["Precio por m²", f"{S} {fmt(o['precio'] / o['m2_base'])} · mediana {v['donde']} {S} {fmt(v['med'])} "
                            f"({v['n']} {o['tipo'] or ''}) → {'+' if v['pct'] > 0 else ''}{v['pct']:.0f}% "
                            + ("más cara que el promedio" if v["pct"] > 5 else "más barata que el promedio" if v["pct"] < -5
                               else "en línea con el mercado")])
            if o["_renta"]:
                rr = o["_renta"]
                neg.append(["Rentabilidad estimada", f"≈ {rr['pct']:.1f}".replace(".", ",") + f"% anual bruto · alquiler típico "
                            f"$ {fmt(rr['alq'])}/mes ({rr['n']} alquileres, {rr['nivel']}) · dólar "
                            f"{self.dolar.get('tipo', '')} $ {fmt(rr['dolar'])}"])
        return {**{k: v for k, v in o.items() if not k.startswith("_") and k not in ("hist",)},
                "historial": o["hist"], "pub_titulo": pub_titulo(o, self.inicio), "pub_corta": pub_corta(o, self.inicio),
                "otro_precio": o["_otros_precios"], "vsb": o["_vsb"], "renta": o["_renta"], "margen": o["_margen"],
                "negociar": neg, "alertas_ia": o["_alertas"], "precio_falso": o["_precio_falso"],
                "cuota": o["_cuota"], "credito_posible": bool(o["estado_aviso"] == "activo" and o["operacion"] == "Venta"
                                                               and lineas_viv(self.credito) and precio_pesos(o, float(self.dolar.get("valor") or 0)))}


_CAT: Catalogo | None = None
_CAT_LOCK = threading.Lock()


RECARGA_EN_FONDO = os.environ.get("CATALOGO_FONDO", "1") == "1"


def _recargar_en_fondo(viejo: Catalogo, version: str) -> None:
    global _CAT
    try:
        nuevo = Catalogo(viejo.engine, viejo.refresco_seg)
        with nuevo.engine.connect() as c:
            crudo = nuevo._leer(c)
        nuevo._procesar(*crudo)
        del crudo
        nuevo.version, nuevo.revisado = version, time.monotonic()
        with _CAT_LOCK:
            if _CAT is viejo:
                _CAT = nuevo
        liberar_memoria()
        # deja listos también el mapa de valores y la captación con los datos nuevos
        from app.api.sectores import precalentar
        from app.db import SessionLocal
        with SessionLocal() as db:
            precalentar(db)
        liberar_memoria()
    except Exception:  # noqa: BLE001 — si falla, se sigue con los datos anteriores y se reintenta en la próxima consulta
        logging.getLogger("radar").exception("no se pudo recargar el catálogo")
    finally:
        viejo.recargando = False


def catalogo() -> Catalogo:
    global _CAT
    if _CAT is None:
        with _CAT_LOCK:
            if _CAT is None:
                from app.db import engine
                _CAT = Catalogo(engine)
    return _CAT.asegurar()


def reiniciar_catalogo():
    global _CAT
    _CAT = None
