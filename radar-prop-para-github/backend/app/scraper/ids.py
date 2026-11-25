"""Identificador real de cada aviso en su plataforma: (plataforma, id_externo).

En El Ojo de Dios el `id` de la tabla props era:
  - BBP: el número de aviso de bahiablancapropiedades.com (url vacía),
  - IBB y ZP: un número inventado desde 1.000.000.000; el aviso real se identifica por su link.
Acá se deriva el id_externo verdadero para que dos avisos de plataformas distintas con el mismo número nunca se
mezclen, y para que el mismo aviso cargado dos veces (por el actualizador o por planilla) no se duplique.
"""
import re
from urllib.parse import urlsplit

SITIO_BBP = "https://www.bahiablancapropiedades.com"
DOMINIOS = (("bahiablancapropiedades.com", "BBP"), ("ibb.com.ar", "IBB"), ("zonaprop.com", "ZP"))
_BBP_RE = re.compile(r"/propiedad/(\d+)")
_ZP_RE = re.compile(r"-(\d{5,})\.html", re.I)
_IBB_RE = re.compile(r"/listings/([^/?#]+)", re.I)


class IdInvalido(ValueError):
    pass


def plataforma_de_url(url: str | None) -> str | None:
    u = (url or "").lower()
    for dominio, plat in DOMINIOS:
        if dominio in u:
            return plat
    return None


def url_normalizada(url: str) -> str:
    p = urlsplit(url.strip())
    host = p.netloc.lower().removeprefix("www.")
    return f"{host}{p.path.rstrip('/')}".lower()


def id_externo(plataforma: str | None, id_viejo: int | None = None, url: str | None = None) -> str:
    """Devuelve el identificador del aviso dentro de su plataforma (siempre texto)."""
    plat = (plataforma or "").strip().upper() or "BBP"  # fuente vacía equivale a BBP
    url = (url or "").strip()
    if plat == "BBP":
        m = _BBP_RE.search(url)
        if m:
            return m.group(1)
        if id_viejo is None or id_viejo <= 0 or id_viejo >= 1_000_000_000:
            raise IdInvalido(f"aviso de BBP sin número válido (id={id_viejo}, url={url!r})")
        return str(int(id_viejo))
    if not url:
        raise IdInvalido(f"aviso de {plat} sin link (id={id_viejo})")
    if plat == "ZP":
        m = _ZP_RE.search(url)
        if m:
            return m.group(1)
    if plat == "IBB":
        m = _IBB_RE.search(url)
        if m:
            return m.group(1).lower()
    return url_normalizada(url)


def url_de(plataforma: str, id_ext: str, url: str | None) -> str:
    if url:
        return url
    if plataforma == "BBP":
        return f"{SITIO_BBP}/propiedad/{id_ext}/"
    return ""
