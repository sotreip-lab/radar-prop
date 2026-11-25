"""Creación de conexiones que sirve tanto en el servidor (psycopg) como en una PC con Windows (pg8000, sin
dependencias compiladas). No depende de la configuración de la app, para poder usarse desde scripts sueltos."""
import ssl

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url


def normalizar_url(url: str, driver: str = "psycopg") -> str:
    """Acepta la URL tal como la copia Supabase (postgresql://...) y le pone el driver."""
    url = url.strip()
    for pref in ("postgres://", "postgresql://"):
        if url.startswith(pref):
            return f"postgresql+{driver}://" + url[len(pref):]
    return url


def engine_para(url: str, verificar_certificado: bool = True, **kw):
    u = make_url(url)
    connect_args = dict(kw.pop("connect_args", {}))
    if u.drivername.endswith("pg8000") and u.host and u.host not in ("localhost", "127.0.0.1"):
        ctx = ssl.create_default_context()
        if not verificar_certificado:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        connect_args["ssl_context"] = ctx
    return create_engine(u, connect_args=connect_args, **kw)
