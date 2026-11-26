"""Prueba de carga de la Fase 5: 10 usuarios a la vez durante 5 minutos, buscando, abriendo propiedades,
mirando el mapa, guardando búsquedas en el historial y generando fichas.

Crea 10 usuarios de prueba (carga01 … carga10) con una contraseña al azar que nadie ve, corre la prueba y al final
los borra junto con todo lo que generaron. Criterio para aprobar: 0 errores 5xx y búsquedas con p95 < 1 s.

Uso:  DATABASE_URL=... python carga/prueba_carga.py --url https://radar-prop.netlify.app/api --minutos 5
"""
import argparse
import asyncio
import json
import os
import random
import re
import secrets
import statistics
import sys
import time
from collections import Counter, defaultdict

import httpx
import psycopg
from argon2 import PasswordHasher

PREFIJO = "carga"
TIPOS = ["Casa", "Departamento", "Terreno", "Local", "PH", "Cochera"]


def url_pg() -> str:
    return re.sub(r"^postgres(ql)?(\+\w+)?://", "postgresql://", os.environ["DATABASE_URL"].strip())


def crear_usuarios(n: int) -> tuple[list[int], str]:
    clave = secrets.token_urlsafe(24)
    h = PasswordHasher().hash(clave)
    ids = []
    with psycopg.connect(url_pg()) as c:
        borrar_usuarios(c)  # por si quedaron de una corrida cortada
        for i in range(1, n + 1):
            ids.append(c.execute(
                "INSERT INTO usuarios (nombre, apellido, usuario, rol, hash_password, debe_cambiar_password, activo, "
                "solicitud_pendiente, intentos_fallidos) VALUES ('Prueba de carga', %s, %s, 'agente', %s, false, true, "
                "false, 0) RETURNING id", (f"{i:02d}", f"{PREFIJO}{i:02d}", h)).fetchone()[0])
    return ids, clave


def borrar_usuarios(c: psycopg.Connection) -> int:
    ids = [r[0] for r in c.execute("SELECT id FROM usuarios WHERE usuario ~ %s", (f"^{PREFIJO}[0-9]{{2}}$",))]
    if not ids:
        return 0
    refs = c.execute("""
        SELECT tc.table_name, kcu.column_name, col.is_nullable
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = tc.constraint_name
        JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name
        JOIN information_schema.columns col ON col.table_name = tc.table_name AND col.column_name = kcu.column_name
        WHERE tc.constraint_type = 'FOREIGN KEY' AND ccu.table_name = 'usuarios' AND tc.table_name <> 'usuarios'
    """).fetchall()
    # Primero lo que depende de otras tablas del usuario (p. ej. fichas → clientes): se repite hasta que no falle.
    pendientes = list(refs)
    for _ in range(5):
        quedan = []
        for tabla, col, nulo in pendientes:
            try:
                with c.transaction():
                    if nulo == "YES" and col != "user_id":
                        c.execute(f'UPDATE "{tabla}" SET "{col}" = NULL WHERE "{col}" = ANY(%s)', (ids,))
                    else:
                        c.execute(f'DELETE FROM "{tabla}" WHERE "{col}" = ANY(%s)', (ids,))
            except psycopg.errors.ForeignKeyViolation:
                quedan.append((tabla, col, nulo))
        pendientes = quedan
        if not pendientes:
            break
    c.execute("DELETE FROM usuarios WHERE id = ANY(%s)", (ids,))
    c.commit()
    return len(ids)


class Medidor:
    def __init__(self):
        self.tiempos: dict[str, list[float]] = defaultdict(list)
        self.codigos: dict[str, Counter] = defaultdict(Counter)
        self.errores: list[str] = []

    def anotar(self, accion: str, seg: float, codigo: int, detalle: str = ""):
        self.tiempos[accion].append(seg)
        self.codigos[accion][codigo] += 1
        if codigo >= 500 or codigo == 0:
            self.errores.append(f"{accion}: {codigo} {detalle[:200]}")


def p(valores: list[float], q: float) -> float:
    if not valores:
        return 0.0
    v = sorted(valores)
    return v[min(len(v) - 1, int(round(q * (len(v) - 1))))]


async def pedir(cli: httpx.AsyncClient, m: Medidor, accion: str, metodo: str, ruta: str, **kw):
    t = time.perf_counter()
    try:
        r = await cli.request(metodo, ruta, **kw)
        m.anotar(accion, time.perf_counter() - t, r.status_code, r.text if r.status_code >= 400 else "")
        return r
    except httpx.HTTPError as e:
        m.anotar(accion, time.perf_counter() - t, 0, repr(e))
        return None


def filtros_al_azar() -> dict:
    f: dict = {"oper": random.choice(["Venta"] * 4 + ["Alquiler"])}
    if random.random() < 0.7:
        f["tipos"] = random.sample(TIPOS, random.randint(1, 2))
    if f["oper"] == "Venta" and random.random() < 0.6:
        f["b"] = random.choice([60000, 85000, 110000, 140000, 180000, 250000])
    if random.random() < 0.3:
        f["dorm"] = random.choice(["1", "2", "3"])
    if random.random() < 0.15:
        f["credito"] = "si"
    if random.random() < 0.15:
        f["orden"] = random.choice(["precio", "usdm2", "detectada"])
    return f


async def usuario(n: int, base: str, clave: str, fin: float, m: Medidor, fichas: bool):
    async with httpx.AsyncClient(base_url=base, timeout=60, http2=False) as cli:
        r = await pedir(cli, m, "login", "POST", "/auth/login", json={"usuario": f"{PREFIJO}{n:02d}", "password": clave})
        if not r or r.status_code != 200:
            m.errores.append(f"carga{n:02d} no pudo entrar ({r.status_code if r else 'sin respuesta'})")
            return
        cli.headers["Authorization"] = "Bearer " + r.json()["access_token"]
        ids: list[int] = []
        await asyncio.sleep(random.random() * 3)
        while time.time() < fin:
            x = random.random()
            if x < 0.55 or not ids:
                cuerpo = {"filtros": filtros_al_azar(), "limite": 50, "registrar": random.random() < 0.4}
                r = await pedir(cli, m, "buscar", "POST", "/propiedades/buscar", json=cuerpo)
                if r is not None and r.status_code == 200:
                    ids = [i["id"] for i in r.json()["items"]] or ids
            elif x < 0.72:
                await pedir(cli, m, "detalle", "GET", f"/propiedades/{random.choice(ids)}")
            elif x < 0.80:
                await pedir(cli, m, "mapa", "POST", "/propiedades/mapa", json={"filtros": filtros_al_azar()})
            elif x < 0.86:
                await pedir(cli, m, "estado", "GET", "/estado")
            elif x < 0.92:
                await pedir(cli, m, "historial", "GET", "/historial/busquedas")
            elif fichas:
                elegidas = random.sample(ids, min(len(ids), random.randint(1, 3)))
                await pedir(cli, m, "ficha", "POST", "/fichas", json={
                    "ids": elegidas, "tipo": random.choice(["web", "whatsapp"]), "cliente": "Prueba de carga",
                    "clave_idempotencia": secrets.token_hex(8)})
            await asyncio.sleep(random.uniform(1, 4))  # lo que tarda una persona en mirar y volver a tocar


async def esperar_servidor(base: str):
    async with httpx.AsyncClient(base_url=base, timeout=90) as cli:
        for _ in range(20):
            try:
                if (await cli.get("/health")).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(5)
    raise SystemExit("El servidor no respondió /health")


async def principal(a):
    print(f"Despertando {a.url} …", flush=True)
    await esperar_servidor(a.url)
    ids, clave = crear_usuarios(a.usuarios)
    print(f"{len(ids)} usuarios de prueba creados. Corriendo {a.minutos} min…", flush=True)
    m = Medidor()
    try:
        # calentar: la primera búsqueda arma el catálogo en memoria (no cuenta para la medición)
        calent = Medidor()
        await usuario(1, a.url, clave, time.time() + 1, calent, False)
        inicio = time.time()
        fin = inicio + a.minutos * 60
        await asyncio.gather(*[usuario(i, a.url, clave, fin, m, not a.sin_fichas) for i in range(1, a.usuarios + 1)])
        dur = time.time() - inicio
    finally:
        with psycopg.connect(url_pg()) as c:
            print(f"Limpieza: {borrar_usuarios(c)} usuarios de prueba borrados con sus datos.", flush=True)

    total = sum(len(v) for v in m.tiempos.values())
    n5xx = sum(n for cod in m.codigos.values() for k, n in cod.items() if k >= 500 or k == 0)
    p95_buscar = p(m.tiempos["buscar"], 0.95)
    filas = []
    for acc in sorted(m.tiempos):
        t = m.tiempos[acc]
        filas.append(f"| {acc} | {len(t)} | {statistics.median(t) * 1000:.0f} ms | {p(t, 0.95) * 1000:.0f} ms | "
                     f"{max(t) * 1000:.0f} ms | {dict(sorted(m.codigos[acc].items()))} |")
    ok = n5xx == 0 and p95_buscar < 1.0 and m.tiempos["buscar"]
    informe = "\n".join([
        f"## Prueba de carga — {'APROBADA ✅' if ok else 'NO APROBADA ❌'}",
        "",
        f"- {a.usuarios} usuarios a la vez durante {dur / 60:.1f} min contra `{a.url}`",
        f"- {total} pedidos ({total / dur:.1f} por segundo)",
        f"- Errores 5xx o sin respuesta: **{n5xx}** (meta: 0)",
        f"- Búsqueda p95: **{p95_buscar * 1000:.0f} ms** (meta: menos de 1.000 ms)",
        "",
        "| Acción | Pedidos | Mediana | p95 | Máximo | Códigos |",
        "|---|---|---|---|---|---|",
        *filas,
        "",
        *(["### Errores (primeros 20)", "", *[f"- {e}" for e in m.errores[:20]]] if m.errores else []),
    ])
    print(informe)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(informe + "\n")
    with open("resultado_carga.json", "w", encoding="utf-8") as f:
        json.dump({"aprobada": bool(ok), "p95_buscar_ms": round(p95_buscar * 1000), "errores_5xx": n5xx,
                   "pedidos": total, "minutos": round(dur / 60, 2), "errores": m.errores[:50]}, f, ensure_ascii=False)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="https://radar-prop.netlify.app/api")
    ap.add_argument("--minutos", type=float, default=5)
    ap.add_argument("--usuarios", type=int, default=10)
    ap.add_argument("--sin-fichas", action="store_true")
    asyncio.run(principal(ap.parse_args()))
