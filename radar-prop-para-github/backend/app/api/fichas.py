"""Fichas: página para el cliente (con fotos), texto para WhatsApp, Excel por plataforma y "Mandar al panel".

- Cada ficha queda registrada en fichas_generadas (es el historial "Fichas generadas" de cada usuario).
- Doble toque en el celular: con la misma clave de idempotencia se devuelve la ficha ya creada, no una nueva.
- La página para el cliente se abre con un link secreto (no pide usuario): es para mandársela al cliente.
"""
import json
import secrets
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import Actual, usuario_actual
from app.db import get_db
from app.models import Cliente, FichaGenerada
from app.scraper import bbp, ibb
from app.services.auditoria import registrar
from app.services.catalogo import PLAT_NOM, catalogo, ficha_whatsapp
from app.services.fichas_formato import generar_excel, html_ficha_cliente, item_para_panel

router = APIRouter(tags=["fichas"])
publico = APIRouter(tags=["fichas"])  # sin sesión: la página que se le manda al cliente


class FichaIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=40)
    tipo: str = Field("web", pattern="^(web|whatsapp)$")
    cliente: str = Field("", max_length=160)
    cliente_id: int | None = None
    clave_idempotencia: str | None = Field(None, max_length=80)


def _datos_vivos(o: dict, descripcion: str, fotos: list) -> tuple[dict | None, list]:
    """Como datos_para_ficha() de la app vieja: lee el aviso en vivo (precio y fotos del momento); si el sitio no
    responde, usa lo guardado. Si el aviso ya no existe, devuelve None (no se incluye)."""
    d = {**o, "descripcion": descripcion or o.get("descripcion"), "precio": o.get("precio_publicado"),
         "ref": o["id_externo"] if o["fuente"] == "BBP" else o["id"], "_verificada": False}
    try:
        if o["fuente"] == "BBP":
            r = bbp.bajar_ficha(o["id_externo"])
            if r.estado == "baja":
                return None, []
            if r.estado == "ok" and r.html:
                vivo = bbp.analizar_ficha(r.html)
                fotos = bbp.fotos_de_ficha(r.html) or fotos
                d.update({k: vivo[k] for k in ("precio", "moneda", "descripcion", "dormitorios", "banos", "sup_cub", "sup_tot",
                                               "exterior", "estacionamiento", "pago", "antiguedad", "m2_base") if vivo.get(k) is not None})
                d["_verificada"] = True
        elif o["fuente"] == "IBB" and o.get("url"):
            r = ibb.bajar_ibb(o["url"], reintentos=2)
            if r.estado == "baja":
                return None, []
            if r.estado == "ok" and r.html:
                vivo = ibb.analizar(r.html, o["url"], o.get("operacion"), None)
                fotos = ibb.fotos(r.html) or fotos
                d.update({k: vivo[k] for k in ("precio", "moneda", "descripcion") if vivo.get(k)})
                d["_verificada"] = True
    except Exception:
        pass  # sin conexión con el sitio: quedan los datos guardados
    return d, fotos or []


def _armar_html(ids: list[int], cliente: str, db: Session) -> str:
    cat = catalogo()
    extra = {i: (desc, fotos) for i, desc, fotos in db.execute(
        text("SELECT id, descripcion, fotos FROM propiedades WHERE id = ANY(:ids)"), {"ids": ids})}
    trabajos: list = []
    for i in ids:
        o = cat.por_id.get(i)
        if not o or o["estado_aviso"] == "baja":
            trabajos.append(None)
        else:
            desc, fotos = extra.get(i, ("", []))
            trabajos.append((o, desc or "", fotos or []))
    with ThreadPoolExecutor(max_workers=8) as ex:
        datos = list(ex.map(lambda t: _datos_vivos(*t) if t else (None, []), trabajos))
    refs = [(cat.por_id[i]["id_externo"] if i in cat.por_id and cat.por_id[i]["fuente"] == "BBP" else i) for i in ids]
    return html_ficha_cliente(refs, cliente, datos)


@router.post("/fichas")
def crear_ficha(datos: FichaIn, a: Actual = Depends(usuario_actual), db: Session = Depends(get_db)):
    if datos.clave_idempotencia:
        ya = db.scalar(select(FichaGenerada).where(FichaGenerada.clave_idempotencia == datos.clave_idempotencia,
                                                   FichaGenerada.user_id == a.id))
        if ya:
            return _salida(ya)
    cliente = datos.cliente
    if datos.cliente_id:
        c = db.get(Cliente, datos.cliente_id)
        if c:
            cliente = cliente or c.nombre
    cat = catalogo()
    if datos.tipo == "whatsapp":
        textos = [f"*{n}.*\n" + ficha_whatsapp(cat.por_id[i]) for n, i in enumerate(datos.ids, 1) if i in cat.por_id]
        f = FichaGenerada(user_id=a.id, cliente_id=datos.cliente_id, propiedades_ids=datos.ids, tipo="whatsapp",
                          enlace=None, clave_idempotencia=datos.clave_idempotencia)
        db.add(f)
        db.commit()
        return {**_salida(f), "texto": "\n\n".join(textos)}
    html = _armar_html(datos.ids, cliente, db)
    token = secrets.token_urlsafe(18)
    f = FichaGenerada(user_id=a.id, cliente_id=datos.cliente_id, propiedades_ids=datos.ids, tipo="web",
                      enlace=f"/f/{token}", clave_idempotencia=datos.clave_idempotencia)
    db.add(f)
    db.flush()
    db.execute(text("INSERT INTO fichas_html (ficha_id, token, html, cliente) VALUES (:f, :t, :h, :c)"),
               {"f": f.id, "t": token, "h": html, "c": cliente[:160]})
    registrar(db, a.id, "ficha_web", "ficha", f.id, {"propiedades": len(datos.ids), "cliente": cliente[:80]})
    db.commit()
    return _salida(f)


def _salida(f: FichaGenerada) -> dict:
    return {"id": f.id, "tipo": f.tipo, "enlace": f.enlace, "propiedades_ids": f.propiedades_ids,
            "creada_en": f.creada_en.isoformat() if f.creada_en else None}


@publico.get("/f/{token}", response_class=HTMLResponse)
def ver_ficha(token: str, db: Session = Depends(get_db)):
    if len(token) > 60:
        raise HTTPException(404, "No encontré esa ficha.")
    h = db.scalar(text("SELECT html FROM fichas_html WHERE token = :t"), {"t": token})
    if not h:
        return HTMLResponse("<h2 style='font-family:sans-serif'>Esta ficha no existe o se borró.</h2>", status_code=404)
    return HTMLResponse(h, headers={"Cache-Control": "private, max-age=300", "X-Robots-Tag": "noindex"})


# ------------------------------------------------------------------ Excel por plataforma
def filas_excel(fuente: str) -> tuple[list[dict], list[dict], str]:
    cat = catalogo()
    venta = [{**o, "precio": o["precio_publicado"]} for o in cat.data if o["fuente"] == fuente and o["operacion"] == "Venta"]
    def num(o):
        return int(o["id_externo"]) if str(o["id_externo"]).isdigit() else o["id"]
    activas = sorted((o for o in venta if o["estado_aviso"] == "activo"), key=num, reverse=True)
    bajas = sorted((o for o in venta if o["estado_aviso"] == "baja"), key=lambda o: (o["fecha_baja"] or "", num(o)), reverse=True)
    return activas, bajas, cat.inicio


@router.get("/excel")
def excel(fuente: str = Query("BBP", pattern="^(BBP|IBB|ZP)$"), a: Actual = Depends(usuario_actual),
          db: Session = Depends(get_db)):
    activas, bajas, inicio = filas_excel(fuente)
    data = generar_excel(fuente, activas, bajas, inicio)
    db.add(FichaGenerada(user_id=a.id, propiedades_ids=[], tipo="excel", enlace=f"excel:{fuente}"))
    db.commit()
    nombre = {"BBP": "Fichas_Venta_Bahia_Blanca_Propiedades", "IBB": "Fichas_Venta_IBB", "ZP": "Fichas_Venta_Zonaprop"}[fuente]
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}_{date.today()}.xlsx"'})


# ------------------------------------------------------------------ panel de fichas (Netlify)
def _panel(ruta: str, cuerpo: dict | None = None) -> dict:
    if not settings.panel_token:
        raise HTTPException(503, "Falta configurar la clave del panel de fichas (PANEL_TOKEN en el servidor).")
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(settings.panel_url.rstrip("/") + ruta, data=datos, method="POST" if datos else "GET",
                                 headers={"x-ojo-token": settings.panel_token, "content-type": "application/json",
                                          "User-Agent": "RadarProp"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise HTTPException(502, f"El panel de fichas respondió {e.code}.") from None
    except Exception:
        raise HTTPException(502, "No pude conectar con el panel de fichas.") from None


@router.get("/panel/clientes")
def panel_clientes(a: Actual = Depends(usuario_actual)):
    return _panel("/api/ojo/clientes")


class PanelIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=40)
    cliente_panel: str = Field("", max_length=80)
    etiqueta: str = Field("", max_length=160)
    cliente_id: int | None = None
    clave_idempotencia: str | None = Field(None, max_length=80)


@router.post("/panel/enviar")
def panel_enviar(datos: PanelIn, a: Actual = Depends(usuario_actual), db: Session = Depends(get_db)):
    if datos.clave_idempotencia:
        ya = db.scalar(select(FichaGenerada).where(FichaGenerada.clave_idempotencia == datos.clave_idempotencia,
                                                   FichaGenerada.user_id == a.id))
        if ya:
            return {"ok": True, "repetido": True, **_salida(ya)}
    cat = catalogo()
    extra = {i: (desc, fotos) for i, desc, fotos in db.execute(
        text("SELECT id, descripcion, fotos FROM propiedades WHERE id = ANY(:ids)"), {"ids": datos.ids})}
    trabajos = [(cat.por_id[i], *(extra.get(i) or ("", []))) for i in datos.ids
                if i in cat.por_id and cat.por_id[i]["estado_aviso"] == "activo"]
    with ThreadPoolExecutor(max_workers=8) as ex:
        leidos = list(ex.map(lambda t: _datos_vivos(t[0], t[1] or "", t[2] or []), trabajos))
    items = [item_para_panel(d, fotos) for d, fotos in leidos if d]
    if not items:
        raise HTTPException(409, "Ninguna de las seleccionadas sigue publicada.")
    r = _panel("/api/ojo/borrador", {"clientId": datos.cliente_panel, "label": datos.etiqueta, "items": items})
    f = FichaGenerada(user_id=a.id, cliente_id=datos.cliente_id, propiedades_ids=datos.ids, tipo="panel",
                      enlace=settings.panel_url.rstrip("/") + settings.panel_ruta, clave_idempotencia=datos.clave_idempotencia)
    db.add(f)
    registrar(db, a.id, "mandar_al_panel", "ficha", None, {"enviadas": len(items), "borrador": r.get("id")})
    db.commit()
    return {"ok": True, "enviadas": len(items), "no_disponibles": len(datos.ids) - len(items), "panel": f.enlace, **_salida(f)}


__all__ = ["router", "publico", "PLAT_NOM"]
