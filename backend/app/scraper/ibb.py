"""Lectura de IBB (ibb.com.ar). Las funciones de análisis son copia de El Ojo de Dios."""
import re
from datetime import timedelta

from app.scraper.red import Respuesta, ahora_local, bajar, sitio_ibb
from app.scraper.texto import (
    NUM_PAL,
    TIPOS_EQUIV,
    a_numero,
    completar_formato_fichas,
    htmlmod,
    limpiar_html,
    norm,
)
from app.scraper.texto import precio_de_texto as _precio

BUSQUEDAS = {"Venta": "selling", "Alquiler": "renting", "Alquiler temporario": "temporary_renting"}


def bajar_ibb(url: str, timeout: int = 40, reintentos: int = 3) -> Respuesta:
    return bajar(url, timeout=timeout, reintentos=reintentos, html=True)


def enumerar(minimo_venta: int = 300) -> tuple[dict[str, str], set[str]]:
    """Lista completa de avisos por operación (el buscador devuelve todo en una sola página) y el conjunto de
    avisos que el propio sitio marca como aptos crédito."""
    base = sitio_ibb()
    avisos: dict[str, str] = {}
    for op, lt in BUSQUEDAS.items():
        r = bajar_ibb(f"{base}/search?listing_type={lt}&category=&city=&view=list", timeout=120, reintentos=2)
        if r.estado != "ok":
            raise RuntimeError(f"IBB {op}: {r.motivo}")
        for slug in re.findall(r'href="/listings/([^"?#/]+)"', r.html or ""):
            avisos.setdefault(f"{base}/listings/{slug}", op)
    credito: set[str] = set()
    r = bajar_ibb(f"{base}/search?listing_type=selling&category=&city=&accepts_credit=true&view=list", timeout=120,
                  reintentos=2)
    if r.estado == "ok":
        credito = {f"{base}/listings/{s}" for s in re.findall(r'href="/listings/([^"?#/]+)"', r.html or "")}
    if len([1 for v in avisos.values() if v == "Venta"]) < minimo_venta:
        raise RuntimeError(f"IBB devolvió muy pocos avisos ({len(avisos)}); se ignora esta lectura")
    return avisos, credito


def _txt(h, patron):
    m = re.search(patron, h, re.S)
    return " ".join(limpiar_html(m.group(1)).split()) if m else ""


def publicado_aprox(texto):
    """'Publicado hace alrededor de 1 año' → fecha aproximada (YYYY-MM-DD)."""
    t = norm(texto)
    m = re.search(r"(\d+|un|una)\s+(minuto|hora|dia|semana|mes|ano)", t)
    if not m:
        return None
    n = 1 if m.group(1) in ("un", "una") else int(m.group(1))
    dias = {"minuto": 0, "hora": 0, "dia": 1, "semana": 7, "mes": 30, "ano": 365}[m.group(2)] * n
    return (ahora_local() - timedelta(days=dias)).strftime("%Y-%m-%d")


def analizar(h, url, operacion=None, credito=None):
    h = re.sub(r"<!--(?!\s*Main features).*?-->", "", h, flags=re.S)
    d = {"url": url}
    d["titulo"] = _txt(h, r"<h1[^>]*>(.*?)</h1>")
    precio_txt = _txt(h, r'<h2[^>]*class="[^"]*fs-24[^"]*fw-bold[^"]*"[^>]*>(.*?)</h2>')
    mon, precio = _precio(precio_txt)
    d["moneda"], d["precio"] = mon, precio
    # dirección: "Calle 123, Barrio, Ciudad (8000), Provincia de Buenos Aires, Argentina"
    dir_full = _txt(h, r'<p[^>]*class="[^"]*mb-0 text-neutral-1000 fs-lm[^"]*"[^>]*>(.*?)</p>')
    partes = [p.strip() for p in dir_full.split(",") if p.strip()]
    partes = [p for p in partes if not re.match(r"(?i)^(provincia de|argentina$)", p)]
    ciudad = re.sub(r"\s*\(\d+\)\s*$", "", partes[-1]).strip() if partes else ""
    direccion = partes[0] if len(partes) >= 2 else (partes[0] if partes else "")
    barrio = ", ".join(partes[1:-1]) if len(partes) >= 3 else ""
    if norm(ciudad) == "bahia blanca":
        ciudad = "Bahía Blanca"
    d.update(direccion=direccion, barrio=barrio[:1].upper() + barrio[1:] if barrio else "", ciudad=ciudad)
    # tipo y operación
    m = re.match(r"(.*?)\s+en\s+(Venta|Alquiler)", d["titulo"], re.I)
    tipo = m.group(1).strip() if m else ""
    d["tipo"] = TIPOS_EQUIV.get(norm(tipo), tipo)
    op_txt = _txt(h, r'<p[^>]*class="[^"]*fs-6 fw-normal text-neutral-1000[^"]*"[^>]*>(.*?)</p>')
    d["operacion"] = operacion or ("Venta" if "venta" in norm(op_txt) else ("Alquiler" if "alquiler" in norm(op_txt) else op_txt))
    d["inmobiliaria"] = _txt(h, r'<p[^>]*class="[^"]*fs-24 fw-bold text-neutral-1000[^"]*"[^>]*>(.*?)</p>')
    # características principales
    i0 = h.find("Main features")
    zona = h[i0:i0 + 6000] if i0 >= 0 else ""
    j = zona.find("Publicado")
    if j > 0:
        zona = zona[:j]
    feats = [limpiar_html(x) for x in re.findall(r'<span class="fw-medium">(.*?)</span>', zona, re.S)]
    detn = {}
    dorm = banos = sup_cub = sup_tot = None
    antig = ""
    for f in feats:
        fn = norm(f)
        n = a_numero(f)
        if "dormitorio" in fn and n is not None:
            dorm = int(n)
        elif "monoambiente" in fn:
            dorm = 0
        elif re.search(r"\bbanos?\b", fn) and "suite" not in fn and n is not None:
            banos = int(n)
        elif "superficie cubierta" in fn or ("cubierta" in fn and "m" in fn):
            sup_cub = n
        elif "totales" in fn or "superficie total" in fn:
            sup_tot = n
        elif "estacionamiento" in fn and n:
            detn["cochera"] = "Sí"
        elif "antiguedad" in fn:
            antig = f"{int(n)} años" if n is not None else f
        elif "estrenar" in fn:
            antig = "A estrenar"
    d["detalles"] = {"caracteristicas": feats}
    m = re.search(r'data-description-toggle-target="content"[^>]*>(.*?)</div>', h, re.S)
    desc = limpiar_html(m.group(1)) if m else ""
    d["descripcion"] = desc
    dn = norm(desc)
    if dorm is None:
        mm = re.search(r"\b(\d|un|uno|una|dos|tres|cuatro|cinco|seis)\s+(dormitorios?|habitaciones?)", dn)
        if mm:
            w = mm.group(1)
            dorm = int(w) if w.isdigit() else NUM_PAL.get(w)
            d["dorm_fuente"] = "descripción"
    d["dormitorios"] = dorm
    d.setdefault("dorm_fuente", "ficha" if dorm is not None else "")
    d["banos"], d["sup_cub"], d["sup_tot"] = banos, sup_cub, sup_tot
    d["antiguedad"] = antig
    d["estado"] = ""
    # características por descripción (mismas reglas que Bahía Blanca Propiedades)
    def car(clave_det, patron_si, patron_no=None):
        if detn.get(clave_det) == "Sí":
            return "Sí"
        if patron_no and re.search(patron_no, dn):
            return "No (desc.)"
        return "Sí (desc.)" if re.search(patron_si, dn) else "No informado"
    d["patio"] = car("patio", r"\b(patio|jardin)", r"\bsin (patio|jardin)")
    d["cochera"] = car("cochera", r"\b(cochera|garage|garaje)", r"\bsin (cochera|garage|garaje)")
    d["pileta"] = car("pileta", r"\b(pileta|piscina)")
    d["parrilla"] = car("parrilla", r"\b(parrilla|quincho)")
    if credito is not None and url in credito:
        d["apto_credito"] = "Sí"  # filtro oficial del sitio
    elif re.search(r"\bno\s+(es\s+)?apt[oa]\s+(para\s+|a\s+)?(el\s+)?credito", dn):
        d["apto_credito"] = "No (desc.)"
    elif re.search(r"\bapt[oa]\s+(para\s+|a\s+)?(el\s+)?credito|acepta\s+credito", dn):
        d["apto_credito"] = "Sí (desc.)"
    else:
        d["apto_credito"] = "No confirmado"
    completar_formato_fichas(d, detn, dn)
    # ubicación
    d["lat"] = d["lng"] = 0.0
    m = re.search(r'<div id="map"[^>]*data-properties="([^"]*)"', h)
    if m:
        props = htmlmod.unescape(m.group(1))
        la = re.search(r'"latitude"\s*:\s*(-?\d+\.\d+)', props)
        ln = re.search(r'"longitude"\s*:\s*(-?\d+\.\d+)', props)
        if la and ln and abs(float(la.group(1))) > 1:
            d["lat"], d["lng"] = float(la.group(1)), float(ln.group(1))
    pub = _txt(h, r'<p[^>]*class="[^"]*text-secondary fs-ml[^"]*"[^>]*>(.*?)</p>')
    d["pub_txt"] = pub
    d["pub_aprox"] = publicado_aprox(pub)
    return d


def fotos(h):
    urls, vistos = [], set()
    for u in re.findall(r'(https://res\.cloudinary\.com/[^"\'\s)]*listing-gallery[^"\'\s)]*)', h):
        u = htmlmod.unescape(u)
        clave = u.rsplit("/", 1)[-1]
        if clave in vistos:
            continue
        vistos.add(clave)
        urls.append(re.sub(r"/upload/[^/]+/(v\d+/)", r"/upload/c_fill,f_auto,g_center,h_900,q_auto,w_1600/\1", u))
    return urls[:12]
