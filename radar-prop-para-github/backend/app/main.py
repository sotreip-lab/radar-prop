"""API de Radar Prop."""
import json
import logging
import os
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api import admin_usuarios, auth, clientes, eventos, fichas, historial, me, propiedades, sectores, selecciones
from app.core.config import settings
from app.db import engine

log = logging.getLogger("radar")
logging.basicConfig(level=logging.INFO, format="%(message)s")

app = FastAPI(title="Radar Prop", version="0.4.0", docs_url="/docs", redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_origin], allow_credentials=True,
                   allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
                   allow_headers=["Authorization", "Content-Type", "Idempotency-Key"])


# Las respuestas grandes (listas, mapa, mapa de valores) viajan comprimidas: pesan entre 5 y 10 veces menos.
app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=5)


@app.on_event("startup")
def precalentar():
    """Carga el catálogo y lo pesado en segundo plano apenas arranca el servidor."""
    import threading

    def tarea():
        try:
            from app.api.sectores import precalentar as sectores
            from app.db import SessionLocal
            from app.services.catalogo import catalogo
            catalogo()
            with SessionLocal() as db:
                sectores(db)
            log.info("precalentado listo")
        except Exception:  # noqa: BLE001
            log.exception("no se pudo precalentar")
    if os.environ.get("PRECALENTAR", "1") == "1":
        threading.Thread(target=tarea, daemon=True).start()


@app.middleware("http")
async def registro(request: Request, call_next):
    # La app web llama a /api/... (Netlify reenvía /api/* a este servidor): se atiende igual que sin el prefijo.
    ruta = request.scope.get("path", "")
    if ruta == "/api" or ruta.startswith("/api/"):
        request.scope["path"] = ruta[4:] or "/"
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    t = time.perf_counter()
    respuesta = await call_next(request)
    respuesta.headers["X-Request-ID"] = rid
    log.info(json.dumps({"rid": rid, "metodo": request.method, "ruta": request.url.path,
                         "estado": respuesta.status_code, "ms": round((time.perf_counter() - t) * 1000, 1)}))
    return respuesta


# ------------------------------------------------------------------ errores: en español y sin datos internos
CAMPOS = {"usuario": "usuario", "password": "contraseña", "nueva": "contraseña nueva", "nombre": "nombre",
          "email": "email", "rol": "rol", "telefono": "teléfono"}


@app.exception_handler(RequestValidationError)
async def validacion(request: Request, exc: RequestValidationError):
    campos = sorted({CAMPOS.get(str(e["loc"][-1]), str(e["loc"][-1])) for e in exc.errors() if e.get("loc")})
    return JSONResponse(status_code=422, content={"detail": "Revisá los datos: " + ", ".join(campos) + "."
                                                  if campos else "Revisá los datos enviados."})


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)


@app.exception_handler(Exception)
async def error_general(request: Request, exc: Exception):
    log.exception("error no controlado en %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Algo salió mal. Probá de nuevo en un momento."})


@app.get("/health", tags=["estado"])
def health():
    estado = {"api": "ok"}
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
            estado["base"] = "ok"
            ult = c.execute(text("SELECT fin, estado FROM corridas_actualizacion ORDER BY id DESC LIMIT 1")).first()
            estado["ultima_corrida"] = {"fin": ult[0].isoformat() if ult and ult[0] else None,
                                        "estado": ult[1] if ult else None}
            estado["ultima_actualizacion_ojo_de_dios"] = c.execute(
                text("SELECT valor FROM meta WHERE clave='ultima_actualizacion'")).scalar()
    except Exception:
        estado["base"] = "sin conexión"
        return JSONResponse(status_code=503, content=estado)
    return estado


app.include_router(auth.router)
app.include_router(me.router)
app.include_router(admin_usuarios.router)
app.include_router(selecciones.router)
app.include_router(propiedades.router)
app.include_router(fichas.router)
app.include_router(fichas.publico)
app.include_router(historial.router)
app.include_router(historial.guardadas)
app.include_router(clientes.router)
app.include_router(sectores.router)
app.include_router(eventos.router)
