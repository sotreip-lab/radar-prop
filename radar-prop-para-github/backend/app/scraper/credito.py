"""Datos oficiales para la cuota de un crédito hipotecario UVA (copia del sector Crédito de El Ojo de Dios).

  - Valor de la UVA: API de Estadísticas del BCRA (variable 31); si falla, ArgentinaDatos.
  - Líneas hipotecarias de cada banco: API de Régimen de Transparencia del BCRA.
El worker lo lee una vez por día y lo guarda en meta['credito']. Si un día el BCRA no responde, queda la lectura
anterior (nunca se inventan tasas).
"""
import json
import logging
import re
import ssl
import urllib.error
import urllib.request
from datetime import timedelta

from app.scraper.red import UA, ahora_local
from app.scraper.texto import norm

log = logging.getLogger("worker")

URL_UVA = "https://api.bcra.gob.ar/estadisticas/v4.0/monetarias/31?desde={d}&hasta={h}"
URL_UVA_ALT = "https://api.argentinadatos.com/v1/finanzas/indices/uva"
URL_HIPO = "https://api.bcra.gob.ar/transparencia/v1.0/Prestamos/Hipotecarios"
DESTINOS = ("Vivienda propia, única y permanente", "Vivienda adicional o 2da vivienda")
TERRITORIOS = ("0", "2")  # 0 = todo el país, 2 = provincia de Buenos Aires


def _bajar_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read().decode("utf-8"))
    except (ssl.SSLError, urllib.error.URLError) as e:
        # El certificado de api.bcra.gob.ar suele venir sin la cadena intermedia y Python lo rechaza.
        # Son datos públicos de solo lectura: se reintenta sin verificar el certificado, solo para ese sitio.
        if "api.bcra.gob.ar" in url and "CERTIFICATE" in str(e).upper():
            ctx = ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=40, context=ctx) as r:
                return json.loads(r.read().decode("utf-8"))
        raise


def _leer_uva():
    hoy = ahora_local().date()
    try:
        j = _bajar_json(URL_UVA.format(d=hoy - timedelta(days=15), h=hoy))
        det = j["results"][0]["detalle"]
        ult = max((x for x in det if x["fecha"] <= str(hoy)), key=lambda x: x["fecha"])
        return {"valor": float(ult["valor"]), "fecha": ult["fecha"], "fuente": "BCRA"}
    except Exception as e:
        log.info(f"Crédito: UVA del BCRA no disponible ({str(e)[:90]}), pruebo fuente alternativa")
    j = _bajar_json(URL_UVA_ALT)
    ult = max((x for x in j if str(x.get("fecha", "")) <= str(hoy)), key=lambda x: x["fecha"])
    return {"valor": float(ult["valor"]), "fecha": ult["fecha"], "fuente": "ArgentinaDatos"}


def _banco_corto(n):
    k = norm(n)
    for clave, nombre in (("nacion argentina", "Nación"), ("galicia", "Galicia"), ("provincia de buenos aires", "Provincia"),
                          ("ciudad de buenos aires", "Ciudad"), ("credicoop", "Credicoop"), ("santander", "Santander"),
                          ("bbva", "BBVA"), ("macro", "Macro"), ("industrial and commercial", "ICBC"), ("supervielle", "Supervielle"),
                          ("brubank", "Brubank"), ("comafi", "Comafi"), ("hipotecario", "Hipotecario"), ("patagonia", "Patagonia"),
                          ("banco del sol", "Banco del Sol"), ("hsbc", "HSBC"), ("icbc", "ICBC"), ("frances", "BBVA")):
        if clave in k:
            return nombre
    n = re.sub(r"\b(S\.?A\.?U?\.?|Sociedad An[oó]nima|Cooperativo Limitado|Limitado)\b", "", n or "", flags=re.I)
    n = re.sub(r"^\s*Banco\s+(de\s+la\s+|de\s+|del\s+)?", "", n, flags=re.I).strip(" .,")
    return (n.title() if n.isupper() else n)[:28]


def _leer_lineas():
    j = _bajar_json(URL_HIPO)
    vistos, out = set(), []
    for x in j.get("results", []):
        if x.get("denominacion") != "UVA" or x.get("destinoFondos") not in DESTINOS:
            continue
        if str(x.get("territorioValidez", "0")) not in TERRITORIOS:
            continue
        tea = float(x.get("tasaEfectivaAnualMaxima") or 0)
        plazo = int(x.get("plazoMaximoOtorgable") or 0)
        ltv = float(x.get("relacionMontoTasacion") or 0)
        rci = float(x.get("relacionCuotaIngreso") or 25)
        if not (0 < tea < 40 and plazo >= 60 and 10 <= ltv <= 100):
            continue
        l = {"banco": _banco_corto(x.get("descripcionEntidad")), "es_banco": bool(re.search(r"banco|bank|brubank", x.get("descripcionEntidad") or "", re.I)), "entidad": x.get("descripcionEntidad"),
             "linea": (x.get("nombreCorto") or x.get("nombreCompleto") or "").strip(),
             "destino": "2da vivienda" if "adicional" in x.get("destinoFondos", "") else "Vivienda única",
             "beneficiario": x.get("beneficiario") or "", "tea": tea, "tipo_tasa": x.get("tipoTasa") or "",
             "plazo": plazo, "ltv": ltv, "rci": rci, "monto_max": float(x.get("montoMaximoOtorgable") or 0),
             "ingreso_min": float(x.get("ingresoMinimoMensual") or 0), "cft": x.get("costoFinancieroEfectivoTotalMaximo"),
             "fecha": x.get("fechaInformacion") or "", "nota": (x.get("masInformacion") or "")[:600]}
        k = (l["banco"], l["linea"], l["destino"], l["beneficiario"], l["tea"], l["plazo"], l["ltv"])
        if k in vistos:
            continue
        vistos.add(k)
        out.append(l)
    out.sort(key=lambda l: (l["destino"] != "Vivienda única", l["tea"], -l["ltv"]))
    return out


def actualizar(anterior: dict | None) -> dict | None:
    """Devuelve los datos nuevos (con lo anterior como respaldo) o None si no hay nada que guardar."""
    nuevo = dict(anterior or {})
    hace20 = (ahora_local() - timedelta(hours=20)).strftime("%Y-%m-%d %H:%M")
    if nuevo.get("leido", "") > hace20:
        return None
    try:
        nuevo["uva"] = _leer_uva()
    except Exception as e:
        log.info(f"Crédito: no se pudo leer la UVA ({str(e)[:100]})")
    try:
        lin = _leer_lineas()
        if lin:
            nuevo["lineas"] = lin
            nuevo["lineas_leidas"] = ahora_local().strftime("%Y-%m-%d %H:%M")
    except Exception as e:
        log.info(f"Crédito: no se pudieron leer las tasas de los bancos ({str(e)[:100]})")
    if nuevo.get("uva") or nuevo.get("lineas"):
        nuevo["leido"] = ahora_local().strftime("%Y-%m-%d %H:%M")
        return nuevo
    return None


def a_json(d: dict) -> str:
    return json.dumps(d, ensure_ascii=False)
