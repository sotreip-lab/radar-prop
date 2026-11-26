"""Sector MAPA DE VALORES: precio por m² por barrio según las propiedades en venta que se dieron de baja
de los portales (probables ventas), comparado con lo que se publica hoy.

Una baja NO siempre es una venta. Antes de contarla como "cierre probable" se descarta si:
  - la misma propiedad sigue publicada en otro portal o por otra inmobiliaria (no se vendió: la sacó una sola),
  - volvió a publicarse después (cambió de inmobiliaria o renovó el aviso),
  - se bajó a los pocos días de publicarse (error, duplicado o aviso de prueba),
  - la fecha de baja es desconocida (vino así en una planilla vieja),
  - en Captación la marcaste como "No se vendió".
Y queda "en observación" mientras no pasen N días desde la baja (config: mercado_espera_dias, 21 por defecto),
porque en ese tiempo todavía puede reaparecer.
Si en Captación la marcás como "Se vendió", cuenta como cierre confirmado."""
import re

from app.scraper.red import ahora_local
from app.services.sectores import comun, zonas

VENDIDA_RE = re.compile(r"\b(vendid[oa]|reservad[oa]|señad[oa])\b", re.I)


def _dias(a, b):
    try:
        return (comun.dia(b[:10]) - comun.dia(a[:10])).days
    except Exception:
        return None


def calcular(filas, dolar, marcas, inicio_base, espera=21):
    """filas: propiedades con los nombres de columna de El Ojo de Dios (ver api/sectores.filas_legado).
    marcas: {id: 'vendida' | 'no_vendida'} hechas en Captación."""
    hoy = ahora_local().strftime("%Y-%m-%d")
    valida = comun.coords_validas(filas)
    barrios = comun.Barrios(filas, valida)
    idx_b = zonas.Indice(zonas.cargar("barrios"))
    idx_c = zonas.Indice(zonas.cargar("cpu"))
    # barrio escrito en el aviso -> barrio oficial (para los avisos sin ubicación en el mapa)
    clave_b = lambda n: re.sub(r"^(villa|v|barrio|b|bo|bº)\s+", "", re.sub(r"[^a-z0-9 ]", " ", comun.norm(n)).strip()).replace(" ", "")
    oficiales = {clave_b(f["n"]): f["n"] for f in zonas.cargar("barrios")}

    # 1) puntos para dibujar los sectores de cada barrio (Bahía Blanca, todas las operaciones)
    celdas = {}
    for r in filas:
        if (r["ciudad"] or "") != "Bahía Blanca" or not valida(r) or not (r["barrio"] or "").strip():
            continue
        k = (round(r["lat"], 4), round(r["lng"], 4))
        celdas.setdefault(k, []).append(barrios.de(r))
    puntos = [[k[0], k[1], max(set(v), key=v.count)] for k, v in celdas.items()]
    puntos = _suavizar(puntos)

    # 2) índice de lo que sigue publicado, por dirección
    venta = [r for r in filas if r["operacion"] == "Venta"]
    activos_dir = {}
    for r in venta:
        if r["estado_aviso"] == "activo":
            k = comun.clave_direccion(r["direccion"])
            if k:
                activos_dir.setdefault((k, comun.grupo_tipo(r["tipo"])), []).append(r)

    def misma(a, b):
        ma, mb = comun.m2_de(a), comun.m2_de(b)
        if ma and mb:
            return abs(ma - mb) / max(ma, mb) <= 0.12
        return a["dormitorios"] is not None and a["dormitorios"] == b["dormitorios"]

    regs = []
    for r in venta:
        g = comun.grupo_tipo(r["tipo"])
        usd = comun.precio_usd(r, dolar)
        m2 = comun.m2_de(r)
        um2 = None
        if usd and m2:
            minimo = 50 if g in ("Terreno", "Quinta / Campo") else 15
            lim = (2, 4000) if g in ("Terreno", "Quinta / Campo") else (150, 9000)
            v = usd / m2
            if m2 >= minimo and lim[0] <= v <= lim[1]:
                um2 = round(v)
        inicio = r["detectada"] or r["pub_aprox"] or (r["alta"] or "")
        reg = {"id": r["id"], "g": g, "tipo": r["tipo"], "b": barrios.de(r, valida), "c": r["ciudad"] or "",
               "usd": round(usd) if usd else None, "m2": round(m2) if m2 else None, "um2": um2,
               "dorm": r["dormitorios"], "dir": r["direccion"] or "", "inm": r["inmobiliaria"] or "",
               "f": r["fuente"] or "BBP", "url": r["url"],
               "lat": r["lat"] if valida(r) else None, "lng": r["lng"] if valida(r) else None}
        if not usd and r["precio"]:
            reg["pf"] = True  # precio de relleno (111.111.111, etc.): no entra en la comparativa
        if reg["lat"] is not None and (r["ciudad"] or "") == "Bahía Blanca":
            reg["zb"] = idx_b.donde(reg["lat"], reg["lng"])
            reg["zc"] = idx_c.donde(reg["lat"], reg["lng"])
        if not reg.get("zb") and reg["b"]:
            reg["zb"] = oficiales.get(clave_b(reg["b"]), "")
        if r["estado_aviso"] == "activo":
            reg["est"] = "pub"
            reg["fecha"] = (inicio or "")[:10]
            regs.append(reg)
            continue
        fb = r["fecha_baja"] or ""
        reg["fecha"] = fb[:10]
        ini_real = r["detectada"] or r["pub_aprox"]  # "alta" es solo cuando la app la vio por primera vez
        reg["dias_pub"] = _dias(ini_real, fb) if ini_real else None
        if r["id"] in marcas:
            reg["est"], reg["motivo"] = (("cierre", "confirmada en Captación") if marcas[r["id"]] == "vendida"
                                         else ("desc", "marcada en Captación como no vendida"))
            regs.append(reg)
            continue
        motivo = ""
        k = comun.clave_direccion(r["direccion"])
        otros = [x for x in activos_dir.get((k, g), []) if x["id"] != r["id"] and misma(r, x)] if k else []
        if "planilla" in fb:
            motivo = "fecha de baja desconocida (vino en una planilla vieja)"
        elif otros:
            nuevo = [x for x in otros if (x["detectada"] or "") > fb]
            x = (nuevo or otros)[0]
            motivo = (f"volvió a publicarse ({x['inmobiliaria'] or x['fuente']})" if nuevo
                      else f"sigue publicada ({x['inmobiliaria'] or x['fuente']})")
            reg["otro_url"] = x["url"]
        elif reg["dias_pub"] is not None and reg["dias_pub"] < 5:
            motivo = f"se bajó a los {reg['dias_pub']} días de publicarse"
        if motivo:
            reg["est"], reg["motivo"] = "desc", motivo
        elif VENDIDA_RE.search((r["titulo"] or "") + " " + (r["descripcion"] or "")[:400]):
            reg["est"], reg["motivo"] = "cierre", "el aviso decía vendida / reservada"
        elif (_dias(fb, hoy) or 0) < espera:
            reg["est"], reg["motivo"] = "obs", f"bajó hace {_dias(fb, hoy)} días: espero {espera} por si reaparece"
        else:
            reg["est"], reg["motivo"] = "cierre", f"no reapareció en {_dias(fb, hoy)} días"
        regs.append(reg)

    return {"puntos": puntos, "regs": regs, "capas_estado": dict(zonas.ESTADO),
            "capas_n": {"barrios": len(zonas.cargar("barrios")), "cpu": len(zonas.cargar("cpu"))}, "dolar": dolar, "espera": espera,
            "inicio_base": inicio_base, "generado": ahora_local().strftime("%Y-%m-%d %H:%M")}


def _suavizar(puntos, k=15, vueltas=3):
    """Los portales cargan el barrio a mano y se mezclan (una casa de Universitario marcada como Centro).
    Cada punto toma el barrio que tiene la mayoría de sus vecinos más cercanos: quedan zonas continuas."""
    T = 0.004
    for _ in range(vueltas):
        grilla = {}
        for i, p in enumerate(puntos):
            grilla.setdefault((int(p[0] / T), int(p[1] / T)), []).append(i)
        nuevo = []
        for p in puntos:
            gi, gj = int(p[0] / T), int(p[1] / T)
            cand = [puntos[i] for a in (-1, 0, 1) for b in (-1, 0, 1) for i in grilla.get((gi + a, gj + b), ())]
            x0, y0 = p[0], p[1]
            dist = [(q[0] - x0) ** 2 + ((q[1] - y0) * 0.78) ** 2 for q in cand]
            # mismo orden que ordenar cand por distancia (orden estable), pero sin llamar a una función por cada par
            cerca = [cand[i] for i in sorted(range(len(cand)), key=dist.__getitem__)[:k]]
            votos = {}
            for j, q in enumerate(cerca):
                votos[q[2]] = votos.get(q[2], 0) + (1.5 if j == 0 else 1)
            nuevo.append([p[0], p[1], max(votos.items(), key=lambda x: x[1])[0]])
        puntos = nuevo
    return puntos
