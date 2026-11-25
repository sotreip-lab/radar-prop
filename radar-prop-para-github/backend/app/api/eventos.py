"""Avisos en vivo (Server-Sent Events): "Base actualizada a las HH:MM" y "Hay X propiedades nuevas".

La conexión dura unos minutos y se corta sola (el navegador se reconecta). Si un proxy no deja pasar SSE, la app
consulta /estado cada 60 segundos: el resultado es el mismo.
"""
import asyncio
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.core.deps import Actual, usuario_actual
from app.services.catalogo import catalogo

router = APIRouter(tags=["estado"])


@router.get("/eventos")
async def eventos(request: Request, a: Actual = Depends(usuario_actual)):
    async def fuente():
        ultima = None
        for _ in range(30):  # ~5 minutos
            if await request.is_disconnected():
                break
            cat = await asyncio.to_thread(catalogo)
            if cat.ultima != ultima:
                ultima = cat.ultima
                yield f"event: base\ndata: {json.dumps({'actualizado': ultima})}\n\n"
            else:
                yield ": sigo\n\n"
            await asyncio.sleep(10)
    return StreamingResponse(fuente(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
