"""Lectura de fichas de Bahía Blanca Propiedades (bahiablancapropiedades.com).

analizar_ficha y fotos_de_ficha son copia de El Ojo de Dios; lo de red es nuevo (sitio configurable para pruebas).
"""
import re

from app.scraper.red import Respuesta, bajar, sitio_bbp
from app.scraper.texto import (
    NUM_PAL,
    a_numero,
    completar_formato_fichas,
    es_si,
    htmlmod,
    limpiar_html,
    norm,
    partir_titulo,
)

DET_RE = re.compile(r'<div class="col-sm-\d+">\s*([^<:]+?)\s*:\s*<strong>\s*([^<]*?)\s*</strong>', re.S)


def analizar_ficha(h):
    """Devuelve dict con todos los campos analizados de una ficha de BBP."""
    h = re.sub(r"<!--.*?-->", "", h, flags=re.S)  # el sitio deja bloques de ejemplo comentados (1 dorm, cochera, patio)
    d = {}
    m = re.search(r'class="propiedad-in-title"[^>]*>(.*?)</h1>', h, re.S)
    d["titulo"] = limpiar_html(m.group(1)) if m else ""
    # ubicación en el mapa (0 = el aviso no tiene mapa)
    d["lat"] = d["lng"] = 0.0
    m = re.search(r'id="propiedad-in-map"[^>]*>', h)
    if m:
        la = re.search(r'data-lat="(-?\d+\.\d+)"', m.group(0))
        ln = re.search(r'data-lng="(-?\d+\.\d+)"', m.group(0))
        if la and ln and abs(float(la.group(1))) > 1 and abs(float(ln.group(1))) > 1:
            d["lat"], d["lng"] = float(la.group(1)), float(ln.group(1))
    m = re.search(r'class="propiedad-in-inmo"[^>]*>(.*?)</h2>', h, re.S)
    d["inmobiliaria"] = limpiar_html(m.group(1)).title() if m else ""

    # precio: primer <li> de la lista de info
    moneda, precio = "", None
    m = re.search(r'<ul class="propiedad-in-info[^"]*">(.*?)</ul>', h, re.S)
    if m:
        for li in re.findall(r"<li>(.*?)</li>", m.group(1), re.S):
            t = limpiar_html(li)
            mm = re.search(r"(U\$S|U\$D|USD|US\$|\$)\s*([\d.,]+)", t, re.I)
            if mm and "fa-tag" in li:
                moneda = "ARS" if mm.group(1) == "$" else "USD"
                precio = a_numero(mm.group(2))
                break
    d["moneda"], d["precio"] = moneda, precio

    m = re.search(r"<strong>\s*Descripci[oó]n\s*</strong>\s*</h6>\s*<p[^>]*>(.*?)</p>", h, re.S)
    desc = limpiar_html(m.group(1)) if m else ""
    d["descripcion"] = desc

    det = {}
    # solo el bloque "Detalles" de ESTA propiedad (la página trae más abajo propiedades relacionadas)
    i0 = h.find("Detalles</strong>")
    zona = h[i0:] if i0 >= 0 else h
    for corte in ("Compart", "Propiedades Relacionadas", "propiedades-relacionadas", "<footer"):
        j = zona.find(corte)
        if j > 0:
            zona = zona[:j]
    for k, v in DET_RE.findall(zona):
        det.setdefault(limpiar_html(k), limpiar_html(v))
    d["detalles"] = det

    tipo, op, direc, barrio, ciudad = partir_titulo(d["titulo"])
    d.update(tipo=tipo, operacion=op, direccion=direc, barrio=barrio, ciudad=ciudad)

    dn = norm(desc)
    detn = {norm(k): v for k, v in det.items()}

    def det_get(*claves):
        for k, v in detn.items():
            if any(c in k for c in claves):
                return v
        return None

    # dormitorios
    dorm, fuente = None, ""
    v = det_get("dormitorio")
    if v:
        if "mono" in norm(v):
            dorm = 0
        else:
            n = a_numero(v)
            dorm = int(n) if n is not None else None
        fuente = "ficha" if dorm is not None else ""
    if dorm is None:
        if re.search(r"monoambiente", dn) or "monoambiente" in norm(tipo):
            dorm, fuente = 0, "descripción"
        else:
            mm = re.search(r"\b(\d|un|uno|una|dos|tres|cuatro|cinco|seis|siete|ocho)\s+(dormitorios?|habitaciones?|dorm\b|dorms?\b)", dn)
            if mm:
                w = mm.group(1)
                dorm = int(w) if w.isdigit() else NUM_PAL.get(w)
                fuente = "descripción"
    d["dormitorios"], d["dorm_fuente"] = dorm, fuente

    v = det_get("bano")
    d["banos"] = int(a_numero(v)) if v and a_numero(v) is not None else None
    v = det_get("superficie cubierta")
    d["sup_cub"] = a_numero(v) if v else None
    v = det_get("superficie total")
    d["sup_tot"] = a_numero(v) if v else None
    d["antiguedad"] = det_get("antiguedad") or ""
    d["estado"] = det_get("estado") or ""

    def caracteristica(claves_det, patron_si, patron_no=None):
        v = det_get(*claves_det)
        if v is not None:
            return "Sí" if es_si(v) else ("No" if norm(v).startswith("no") else v)
        if patron_no and re.search(patron_no, dn):
            return "No (desc.)"
        if re.search(patron_si, dn):
            return "Sí (desc.)"
        return "No informado"

    d["patio"] = caracteristica(["patio", "jardin"], r"\b(patio|jardin)", r"\bsin (patio|jardin)")
    d["cochera"] = caracteristica(["cochera", "garage", "garaje"], r"\b(cochera|garage|garaje)", r"\bsin (cochera|garage|garaje)")
    d["pileta"] = caracteristica(["pileta", "piscina"], r"\b(pileta|piscina)")
    d["parrilla"] = caracteristica(["parrilla", "quincho"], r"\b(parrilla|quincho)")

    v = det_get("apto para credito", "apto credito")
    if v is not None:
        d["apto_credito"] = "Sí" if es_si(v) else "No"
    elif re.search(r"\bno\s+(es\s+)?apt[oa]\s+(para\s+|a\s+)?(el\s+)?credito", dn):
        d["apto_credito"] = "No (desc.)"
    elif re.search(r"\bapt[oa]\s+(para\s+|a\s+)?(el\s+)?credito|acepta\s+credito", dn):
        d["apto_credito"] = "Sí (desc.)"
    else:
        d["apto_credito"] = "No confirmado"
    completar_formato_fichas(d, detn, dn)
    return d


def fotos_de_ficha(h):
    h = re.sub(r"<!--.*?-->", "", h, flags=re.S)
    urls = re.findall(r'swiper-zoom-container"[^>]*>\s*<img[^>]*?src="([^"]+)"', h)
    if not urls:
        m = re.search(r'property="og:image"\s+content="([^"]+)"', h)
        urls = [m.group(1)] if m else []
    vistos, out = set(), []
    for u in urls:
        u = htmlmod.unescape(u)
        if u.startswith("/"):
            u = sitio_bbp() + u
        if u not in vistos:
            vistos.add(u)
            out.append(u)
    return out[:12]


def bajar_ficha(id_ext: str) -> Respuesta:
    """('ok', html) | ('baja', None) | ('error', motivo). Igual que la app vieja: 3 intentos, 404/410 o
    página sin título = baja."""
    r = bajar(f"{sitio_bbp()}/propiedad/{id_ext}/", reintentos=3)
    if r.estado == "ok" and "propiedad-in-title" not in (r.html or ""):
        return Respuesta("baja", None)
    return r


def ids_del_sitemap(minimo: int = 1000) -> set[str]:
    """Números de todos los avisos activos publicados (una sola descarga)."""
    r = bajar(f"{sitio_bbp()}/sitemap.xml", timeout=90, reintentos=2)
    if r.estado != "ok":
        raise RuntimeError(f"no se pudo leer el sitemap ({r.motivo})")
    ids = set(re.findall(r"/propiedad/(\d+)", r.html or ""))
    if len(ids) < minimo:
        raise RuntimeError(f"sitemap con muy pocos avisos ({len(ids)}), se ignora")
    return ids
