"""Reglas de lectura de texto de los avisos, copiadas tal cual de El Ojo de Dios (app.py).

No cambiar el comportamiento sin cambiar también la app vieja: las dos tienen que dar el mismo resultado
para el mismo aviso. Las pruebas de tests/test_lector.py fijan ese comportamiento.
"""
import html as htmlmod
import re
import unicodedata


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower()


NUM_PAL = {"un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
           "seis": 6, "siete": 7, "ocho": 8}

TITULO_RE = re.compile(r"^(.*?)\s*(en Venta|en Alquiler Temporario|en Alquiler|por D[ií]a|Fideicomiso)\s+(?:en\s+)?(.*)$", re.I)
CIUDADES = ["Bahía Blanca", "Bahia Blanca", "Monte Hermoso", "Punta Alta", "Sierra de la Ventana",
            "Saldungaray", "Tornquist", "Pehuen Co", "Pehuen-Co", "Médanos", "General Cerri", "Ingeniero White",
            "Villa Ventana", "Coronel Dorrego", "Coronel Suárez", "Coronel Pringles", "CABA", "Cabildo",
            "Tres Arroyos", "Carhué", "Mar del Plata"]


def partir_titulo(titulo):
    tipo = operacion = ubic = ""
    m = TITULO_RE.match((titulo or "").strip())
    if m:
        tipo, op, ubic = m.group(1).strip(), m.group(2).lower(), m.group(3).strip()
        if "venta" in op:
            operacion = "Venta"
        elif "temporario" in op:
            operacion = "Alquiler temporario"
        elif "alquiler" in op:
            operacion = "Alquiler"
        elif op.startswith("por d"):
            operacion = "Alquiler por día"
        else:
            operacion = "Fideicomiso"
    else:
        ubic = re.sub(r"^en\s+", "", (titulo or "").strip())
    partes = [p.strip() for p in ubic.split(",") if p.strip()]
    direccion = barrio = ciudad = ""
    if len(partes) >= 3:
        direccion, ciudad, barrio = partes[0], partes[-1], ", ".join(partes[1:-1])
    elif len(partes) == 2:
        direccion, ciudad = partes
    elif len(partes) == 1:
        direccion = partes[0]
    return tipo, operacion, direccion, barrio, ciudad


def ciudad_de_texto(txt):
    for c in CIUDADES:
        if txt and txt.strip().lower().endswith(c.lower()):
            return "Bahía Blanca" if c.lower().startswith("bah") else c
    return ""


def a_numero(s):
    s = (s or "").strip()
    m = re.search(r"[\d.,]+", s)
    if not m:
        return None
    t = m.group(0)
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".")
    elif "." in t and re.fullmatch(r"\d{1,3}(\.\d{3})+", t):
        t = t.replace(".", "")
    elif "," in t:
        t = t.replace(",", ".") if re.fullmatch(r"\d+,\d{1,2}", t) else t.replace(",", "")
    try:
        return float(t)
    except ValueError:
        return None


def limpiar_html(s):
    s = re.sub(r"<br\s*/?>", "\n", s or "", flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = htmlmod.unescape(s)
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*", "\n", s)
    return s.strip()


def es_si(v):
    return norm(v).startswith("si")


# ---- mismas reglas que el Excel "Fichas_Venta_Bahia_Blanca_Propiedades" (hoja Notas)
VIVIENDAS = {"departamento", "casa", "duplex", "triplex", "ph", "semipiso", "piso", "loft", "interno",
             "casa departamento", "casa en planta alta", "cabana", "casaquinta", "monoambiente"}
EXTERIOR_ORDEN = ["Patio", "Jardín/parque", "Terraza/balcón", "Balcón", "Terraza", "Quincho", "Parrilla", "Pileta"]


def completar_formato_fichas(d, detn, dn):
    """Calcula Espacio exterior, Estacionamiento, Pago, Expensas, m² base y normaliza el tipo."""
    titulo_n = norm(d.get("titulo"))
    tipo = d.get("tipo") or ""
    if norm(tipo) == "departamento interno":
        tipo = "Interno"
    if re.search(r"\bduplex\b", titulo_n) and norm(tipo) in ("departamento", "casa", ""):
        tipo = "Duplex"
    d["tipo"] = tipo

    def det_si(*claves):
        return any(any(c in k for c in claves) and es_si(v) for k, v in detn.items())

    def desc_tiene(patron, negacion=None):
        if negacion and re.search(negacion, dn):
            return False
        return bool(re.search(patron, dn))

    ext = set()
    if det_si("patio") or desc_tiene(r"\bpatio", r"\bsin patio"):
        ext.add("Patio")
    if det_si("jardin", "parque") or desc_tiene(r"\bjardin|\bparque (propio|parquizado|verde|arbolado|con)", r"\bsin jardin"):
        ext.add("Jardín/parque")
    balc_det = det_si("balcon")
    terr_det = det_si("terraza")
    if any("balcon" in k and "terraza" in k and es_si(v) for k, v in detn.items()):
        ext.add("Terraza/balcón")
    else:
        if balc_det or desc_tiene(r"\bbalcon"):
            ext.add("Balcón")
        if terr_det or desc_tiene(r"\bterraza"):
            ext.add("Terraza")
    if det_si("quincho") or desc_tiene(r"\bquincho"):
        ext.add("Quincho")
    if det_si("parrilla") or desc_tiene(r"\bparrilla"):
        ext.add("Parrilla")
    if det_si("pileta", "piscina") or desc_tiene(r"\b(pileta|piscina)", r"\bsin (pileta|piscina)"):
        ext.add("Pileta")
    d["exterior"] = ", ".join(x for x in EXTERIOR_ORDEN if x in ext) or "No figura"

    tiene_coch = det_si("cochera", "garage", "garaje") or desc_tiene(r"\b(cochera|garage|garaje)", r"\bsin (cochera|garage|garaje)")
    d["estacionamiento"] = "Sí (cochera)" if tiene_coch else "No figura"

    if d.get("apto_credito") in ("Sí", "Sí (desc.)"):
        d["pago"] = "Apto crédito"
    elif d.get("apto_credito") in ("No", "No (desc.)"):
        d["pago"] = "Contado"
    else:
        d["pago"] = "Contado (no figura apto crédito)"
    d["expensas"] = "Sí" if det_si("expensa") else None

    # m² menores a 10 se descartan (errores de carga)
    for c in ("sup_cub", "sup_tot"):
        if d.get(c) is not None and d[c] < 10:
            d[c] = None
    m2_desc = None
    mm = re.search(r"(\d{2,5}(?:[.,]\d+)?)\s*(m2|m²|mts2|mts²|mts\.? cuadrados|metros cuadrados)", dn)
    if mm:
        m2_desc = a_numero(mm.group(1))
        if m2_desc is not None and m2_desc < 10:
            m2_desc = None
    if norm(tipo) in VIVIENDAS:
        d["m2_base"] = d.get("sup_cub") or d.get("sup_tot") or m2_desc
    else:
        d["m2_base"] = d.get("sup_tot") or d.get("sup_cub") or m2_desc
    if not d.get("antiguedad"):
        d["antiguedad"] = "No figura"
    if d.get("moneda") == "ARS" and not d.get("precio"):
        d["precio"] = None


# ---- amoblado: se deduce del título, los ítems de la ficha y la descripción
_AMO_RUIDO = re.compile(r"(cocina|placard|placares|vestidor|banos?|lavadero|living|alacena|bajo ?mesada|toilette)s?\s+(\w+\s+){0,2}a(mo|mue)blad\w*"
                        r"|a(mo|mue)blamientos?(\s+de)?(\s+\w+){0,2}|muebles?\s+(de|bajo|alto|sobre)\s+(cocina|mesada|bano|lavadero)\w*"
                        r"|a(mo|mue)blad\w*\s+(de\s+)?(cocina|placard|bano)")
_AMO_NO = re.compile(r"\b(sin\s+a(mo|mue)blar|sin\s+muebles|no\s+(se\s+)?(entrega|alquila|incluye|esta)?\s*a(mo|mue)blad\w*|desa(mo|mue)blad\w*)")
_AMO_SEMI = re.compile(r"\b(semi\s*-?\s*a(mo|mue)blad\w*|parcialmente\s+a(mo|mue)blad\w*)")
_AMO_SI = re.compile(r"\b(a(mo|mue)blad[oa]s?|totalmente\s+a(mo|mue)blad\w*|con\s+muebles|full\s+a(mo|mue)blad\w*|furnished)\b")
_AMO_ELEGIR = re.compile(r"\b(con\s+o\s+sin\s+(muebles|a(mo|mue)blar)|a(mo|mue)blad\w*\s+o\s+(sin\s+a(mo|mue)blar|no\b|vacio)|opcional\w*\s+a(mo|mue)blad\w*|a(mo|mue)blad\w*\s+(opcional|a\s+eleccion))")
_AMO_CAMPO = re.compile(r'"a(mo|mue)blad[oa]"\s*:\s*"(si|no)"')


def detectar_amoblado(*textos):
    """Amoblado / Semi amoblado / Sin amoblar / A elección / No figura."""
    t = norm(" ".join(x for x in textos if x))
    campo = _AMO_CAMPO.search(t)
    t = _AMO_CAMPO.sub(" ", t)
    t = _AMO_RUIDO.sub(" ", t)
    if _AMO_SEMI.search(t):
        return "Semi amoblado"
    if _AMO_ELEGIR.search(t):
        return "A elección"
    no = bool(_AMO_NO.search(t))
    t_si = _AMO_NO.sub(" ", t)
    si = bool(_AMO_SI.search(t_si)) or bool(campo and campo.group(2) == "si")
    if campo and campo.group(2) == "no" and not si:
        no = True
    if si and no:
        return "A elección"
    if si:
        return "Amoblado"
    if no:
        return "Sin amoblar"
    return "No figura"


TIPOS_EQUIV = {"lote/terreno": "Terreno", "lote": "Terreno", "local comercial": "Local", "deposito": "Depósito",
               "galpon": "Galpón", "ph": "PH", "duplex": "Duplex", "departamento": "Departamento", "casa": "Casa",
               "oficina": "Oficina", "cochera": "Cochera", "campo": "Campo", "quinta": "Quinta", "fondo de comercio": "Fondo de Comercio"}


def numero_positivo(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) if v > 0 else None
    n = a_numero(str(v))
    return n if n and n > 0 else None


def precio_de_texto(txt, moneda_col=""):
    """'USD 50.000' / 'U$S 50.000' / '$ 450.000' / 50000 → (moneda, precio). USD < 5.000 = 'a consultar'."""
    t = str(txt or "").strip()
    mon = ""
    if re.search(r"u\$s|usd|us\$|u\$d|dolar", t, re.I):
        mon = "USD"
    elif "$" in t or re.search(r"ars|pesos", t, re.I):
        mon = "ARS"
    if moneda_col:
        mc = moneda_col.strip().upper()
        mon = "USD" if mc in ("USD", "U$S", "US$", "DOLARES", "DÓLARES") else ("ARS" if mc in ("ARS", "$", "PESOS") else mon)
    n = numero_positivo(re.sub(r"[^\d.,]", "", t)) if t else None
    if n is not None and mon in ("USD", "") and n < 5000:
        n = None
    if n is not None and mon == "ARS" and n < 1000:
        n = None
    return (mon or ("USD" if n else "")), n
