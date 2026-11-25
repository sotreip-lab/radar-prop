"""Descargas de los sitios. Solo biblioteca estándar, con reintentos y sin claves.

Los sitios se pueden cambiar con variables de entorno (solo para pruebas con un sitio falso):
RADAR_SITIO_BBP, RADAR_SITIO_IBB.
"""
import email.utils
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
ZONA = ZoneInfo("America/Argentina/Buenos_Aires")


def sitio_bbp() -> str:
    return os.environ.get("RADAR_SITIO_BBP", "https://www.bahiablancapropiedades.com").rstrip("/")


def sitio_ibb() -> str:
    return os.environ.get("RADAR_SITIO_IBB", "https://ibb.com.ar").rstrip("/")


def ahora_local() -> datetime:
    """Hora de Bahía Blanca sin zona (igual que las fechas que ya están en la base): el servidor de GitHub
    está en UTC y sin esto las ventanas de publicación quedarían corridas 3 horas."""
    return datetime.now(ZONA).replace(tzinfo=None, microsecond=0)


@dataclass
class Respuesta:
    estado: str             # ok | baja | error
    html: str | None
    motivo: str = ""


def bajar(url: str, timeout: int = 25, reintentos: int = 3, html: bool = False) -> Respuesta:
    """404/410 = baja (el aviso no existe más). Otros errores se reintentan con espera creciente."""
    cab = {"User-Agent": UA, "Accept-Language": "es-AR,es"}
    if html:  # IBB responde 406 si no se pide HTML explícitamente
        cab["Accept"] = "text/html,application/xhtml+xml"
    motivo = ""
    for intento in range(reintentos):
        try:
            req = urllib.request.Request(url, headers=cab)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return Respuesta("ok", r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return Respuesta("baja", None, f"HTTP {e.code}")
            motivo = f"HTTP {e.code}"
        except Exception as e:  # red, tiempo agotado
            motivo = str(e)[:120]
        if intento < reintentos - 1:
            time.sleep(1.5 * (intento + 1))
    return Respuesta("error", None, motivo)


def fecha_ultima_modificacion(url: str) -> datetime | None:
    """Cabecera Last-Modified de una foto, en hora de Bahía Blanca (BBP no informa la fecha de publicación)."""
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            lm = r.headers.get("Last-Modified")
        if lm:
            return email.utils.parsedate_to_datetime(lm).astimezone(ZONA).replace(tzinfo=None)
    except Exception:
        return None
    return None
