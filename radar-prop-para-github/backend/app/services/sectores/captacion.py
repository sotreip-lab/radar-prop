"""Sector CAPTACIÓN: señales para conseguir propiedades nuevas (copia de modulos/captacion.py de El Ojo de Dios).

  - cansadas: más de un año publicadas o con dos o más bajas de precio,
  - bajas largas: se dieron de baja después de 6 meses o más (¿se vendió o se le venció el contrato?),
  - varias inmobiliarias: la misma propiedad publicada por 2 o más inmobiliarias (no tiene exclusividad),
  - cambió de inmobiliaria: se bajó de una y apareció en otra.
Los dueños directos y el seguimiento viven en la base central (captacion_duenos, captacion_seguimiento).
"""
import re

from app.scraper.red import ahora_local
from app.services.sectores import comun

ESTADOS = ("por_contactar", "contactado", "captada", "descartada")


def _dias(a, b=None):
    try:
        b = b or ahora_local().strftime("%Y-%m-%d")
        return (comun.dia(b[:10]) - comun.dia(a[:10])).days
    except Exception:
        return None


def _ficha(r, barrios, valida, dolar):
    usd = comun.precio_usd(r, dolar)
    m2 = comun.m2_de(r)
    ini = r["detectada"] or r["pub_aprox"]
    return {"id": r["id"], "tipo": r["tipo"], "g": comun.grupo_tipo(r["tipo"]), "op": r["operacion"],
            "dir": r["direccion"] or "", "b": barrios.de(r, valida), "c": r["ciudad"] or "", "inm": r["inmobiliaria"] or "",
            "moneda": r["moneda"], "precio": r["precio"], "usd": round(usd) if usd else None, "m2": round(m2) if m2 else None,
            "um2": round(usd / m2) if usd and m2 and m2 >= 15 else None, "dorm": r["dormitorios"],
            "f": r["fuente"] or "BBP", "url": r["url"],
            "dias": _dias(ini) if ini else None, "baja": (r["fecha_baja"] or "")[:10],
            "est": r["estado_aviso"]}


def senales(filas, hist, dolar):
    """filas: con los nombres de columna de El Ojo de Dios; hist: {id: [(antes, después)]}."""
    valida = comun.coords_validas(filas)
    barrios = comun.Barrios(filas, valida)
    ventas = [r for r in filas if r["operacion"] == "Venta" and not comun.es_propia(r["inmobiliaria"])]

    # medianas de USD/m² publicadas por barrio y tipo (para la comparativa)
    gr = {}
    for r in ventas:
        if r["estado_aviso"] == "activo":
            usd, m2 = comun.precio_usd(r, dolar), comun.m2_de(r)
            if usd and m2 and m2 >= 15:
                gr.setdefault((barrios.de(r, valida), comun.grupo_tipo(r["tipo"])), []).append(usd / m2)
    MED = {k: (comun.mediana(v), len(v)) for k, v in gr.items() if len(v) >= 4}

    def con_mercado(f):
        m = MED.get((f["b"], f["g"]))
        if m and f["um2"]:
            f["vs"] = round((f["um2"] / m[0] - 1) * 100)
            f["med"], f["med_n"] = round(m[0]), m[1]
        return f

    out = {"cansadas": [], "bajas_largas": [], "multi": [], "cambio": []}
    por_dir = {}
    for r in ventas:
        k = comun.clave_direccion(r["direccion"])
        if k:
            por_dir.setdefault((k, comun.grupo_tipo(r["tipo"])), []).append(r)

    for r in ventas:
        f = None
        if r["estado_aviso"] == "activo":
            h = hist.get(r["id"], [])
            bajas = sum(1 for a, d in h if d < a)
            maxp = max([r["precio"] or 0] + [a for a, _ in h])
            pct = (1 - r["precio"] / maxp) * 100 if r["precio"] and maxp > r["precio"] else 0
            ini = r["detectada"] or r["pub_aprox"]
            dias = _dias(ini) if ini else None
            motivos = []
            if dias is not None and dias >= 365:
                motivos.append(f"{dias // 30} meses publicada")
            if bajas >= 2:
                motivos.append(f"bajó {bajas} veces")
            if pct >= 8:
                motivos.append(f"−{pct:.0f}% desde su precio más alto")
            if motivos:
                f = con_mercado(_ficha(r, barrios, valida, dolar))
                f["motivo"] = " · ".join(motivos)
                f["peso"] = (dias or 0) / 30 + bajas * 6 + pct
                out["cansadas"].append(f)
        else:
            ini = r["detectada"] or r["pub_aprox"]
            dp = _dias(ini, r["fecha_baja"]) if ini and r["fecha_baja"] and "planilla" not in r["fecha_baja"] else None
            k = comun.clave_direccion(r["direccion"])
            sigue = [x for x in por_dir.get((k, comun.grupo_tipo(r["tipo"])), []) if x["estado_aviso"] == "activo"] if k else []
            if dp is not None and dp >= 180 and not sigue:
                f = con_mercado(_ficha(r, barrios, valida, dolar))
                f["motivo"] = f"estuvo {dp // 30} meses publicada y se dio de baja: ¿se vendió o se venció el contrato?"
                f["peso"] = dp / 30
                out["bajas_largas"].append(f)

    for (k, g), grupo in por_dir.items():
        act = [x for x in grupo if x["estado_aviso"] == "activo"]
        if len({comun.inm_clave(x["inmobiliaria"]) for x in act if x["inmobiliaria"]}) >= 2:
            edificio = len(act) > 6  # muchas unidades en la misma dirección: exige coincidencia exacta
            padre = list(range(len(act)))

            def raiz(i):
                while padre[i] != i:
                    padre[i] = padre[padre[i]]
                    i = padre[i]
                return i
            for i in range(len(act)):
                for j in range(i + 1, len(act)):
                    a, b = act[i], act[j]
                    if comun.inm_clave(a["inmobiliaria"]) == comun.inm_clave(b["inmobiliaria"]):
                        continue
                    ma, mb = comun.m2_de(a), comun.m2_de(b)
                    pa, pb = comun.precio_usd(a, dolar), comun.precio_usd(b, dolar)
                    precio_ok = pa and pb and abs(pa - pb) / max(pa, pb) <= (0.12 if edificio else 0.2)
                    dorm_ok = a["dormitorios"] is None or b["dormitorios"] is None or a["dormitorios"] == b["dormitorios"]
                    if ma and mb:
                        igual = abs(ma - mb) / max(ma, mb) <= (0.02 if edificio else 0.06) and dorm_ok and precio_ok
                    else:
                        igual = (not edificio and a["dormitorios"] is not None and a["dormitorios"] == b["dormitorios"]
                                 and pa and pb and abs(pa - pb) / max(pa, pb) <= 0.1)
                    if igual:
                        padre[raiz(i)] = raiz(j)
            grupos = {}
            for i in range(len(act)):
                grupos.setdefault(raiz(i), []).append(act[i])
            for pares in grupos.values():
                n_inm = len({comun.inm_clave(x["inmobiliaria"]) for x in pares if x["inmobiliaria"]})
                if n_inm < 2:
                    continue
                f = con_mercado(_ficha(pares[0], barrios, valida, dolar))
                f["otras"] = [{"inm": x["inmobiliaria"], "precio": x["precio"], "moneda": x["moneda"],
                               "url": x["url"], "f": x["fuente"]} for x in pares]
                f["n_inm"] = n_inm
                f["emprend"] = n_inm >= 5
                f["motivo"] = (f"la venden {n_inm} inmobiliarias: parece un emprendimiento o desarrollo" if n_inm >= 5
                               else f"la publican {n_inm} inmobiliarias: no tiene exclusividad")
                f["peso"] = 10 - n_inm if n_inm < 5 else 0
                out["multi"].append(f)
        bajas = [x for x in grupo if x["estado_aviso"] == "baja" and x["fecha_baja"] and "planilla" not in x["fecha_baja"]]
        for b in bajas:
            nuevas = [x for x in act if comun.inm_clave(x["inmobiliaria"]) != comun.inm_clave(b["inmobiliaria"])
                      and comun.m2_de(x) and comun.m2_de(b) and abs(comun.m2_de(x) - comun.m2_de(b)) / max(comun.m2_de(x), comun.m2_de(b)) <= 0.06
                      and (x["detectada"] or "") >= b["fecha_baja"][:10]]
            if nuevas:
                x = nuevas[0]
                f = con_mercado(_ficha(x, barrios, valida, dolar))
                f["antes"] = {"inm": b["inmobiliaria"], "precio": b["precio"], "moneda": b["moneda"], "baja": b["fecha_baja"][:10],
                              "url": b["url"]}
                f["motivo"] = f"se bajó de {b['inmobiliaria'] or b['fuente']} y apareció en {x['inmobiliaria'] or x['fuente']}"
                f["peso"] = 1
                out["cambio"].append(f)
    for k in out:
        out[k].sort(key=lambda f: -f.get("peso", 0))
    return out, MED


# ------------------------------------------------------------------ dueños directos
CAMPOS = {"url": ("link", "url", "enlace", "aviso"), "titulo": ("titulo", "título", "title"),
          "tipo": ("tipo", "tipo de propiedad"), "operacion": ("operacion", "operación"),
          "direccion": ("direccion", "dirección", "ubicacion", "ubicación", "calle"), "barrio": ("barrio", "zona"),
          "ciudad": ("ciudad", "localidad"), "moneda": ("moneda",), "precio": ("precio", "valor", "price"),
          "dorm": ("dormitorios", "dorm", "habitaciones", "ambientes"), "m2": ("m2", "m²", "superficie", "sup", "metros", "superficie cubierta"),
          "nombre": ("nombre", "dueño", "dueno", "propietario", "contacto", "vendedor"), "telefono": ("telefono", "teléfono", "celular", "whatsapp", "tel"),
          "notas": ("notas", "observaciones", "comentarios")}


def _num(v):
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    s = re.sub(r"[^\d,.\-]", "", s)
    if s.count(".") > 1 or (s.count(".") == 1 and s.count(",") == 0 and len(s.split(".")[1]) == 3):
        s = s.replace(".", "")
    s = s.replace(",", ".") if s.count(",") == 1 else s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _limpiar(d):
    out = {}
    for k in CAMPOS:
        v = d.get(k)
        if v is None:
            continue
        if k in ("precio", "m2"):
            v = _num(v)
        elif k == "dorm":
            n = _num(v)
            v = int(n) if n is not None else None
        else:
            v = str(v).strip()[:500]
        out[k] = v
    txt = str(d.get("precio_txt") or d.get("precio") or "")
    if not out.get("moneda"):
        out["moneda"] = "ARS" if re.search(r"\$(?!\s*usd)|ars|pesos", txt, re.I) and not re.search(r"u\$s|usd|dolar|dólar", txt, re.I) else "USD"
    if out.get("url") and "mercadolibre" in out["url"]:
        out.setdefault("origen", "MercadoLibre")
    return out


def duenos(MED, filas, act, dolar):
    """filas: dueños directos (dicts con las columnas de la tabla vieja: dorm, m2...); act: propiedades activas."""
    if not filas:
        return []
    por_dir = {}
    for r in act:
        k = comun.clave_direccion(r["direccion"])
        if k:
            por_dir.setdefault(k, []).append(r)
    barr = {comun.norm(b): b for (b, _) in MED}
    for d in filas:
        g = comun.grupo_tipo(d.get("tipo") or d.get("titulo") or "")
        d["g"] = g
        usd = d["precio"] if (d.get("moneda") or "USD") == "USD" else (d["precio"] / dolar if d.get("precio") and dolar else None)
        d["um2"] = round(usd / d["m2"]) if usd and d.get("m2") and d["m2"] >= 15 else None
        b = barr.get(comun.norm(d.get("barrio")), d.get("barrio") or "")
        m = MED.get((b, g))
        if m:
            d["med"], d["med_n"] = round(m[0]), m[1]
            if d["um2"]:
                d["vs"] = round((d["um2"] / m[0] - 1) * 100)
        k = comun.clave_direccion(d.get("direccion"))
        d["en_inmobiliarias"] = [{"inm": r["inmobiliaria"], "precio": r["precio"], "moneda": r["moneda"], "f": r["fuente"],
                                  "url": r["url"]}
                                 for r in por_dir.get(k, []) if comun.grupo_tipo(r["tipo"]) == g] if k else []
    return filas
