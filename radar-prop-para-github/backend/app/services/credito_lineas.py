"""Condiciones reales de cada línea de crédito hipotecario UVA y la simulación para una propiedad.

El BCRA (régimen de transparencia) informa por línea: TEA, CFT, plazo máximo, % máximo que financia, relación
cuota/ingreso, monto máximo en pesos e ingreso mínimo. Además, cada banco escribe en "masInformacion" (texto libre)
condiciones que no tienen campo propio, por ejemplo el Nación: "MONTO MAXIMO OTORGABLE 157500 UVAS Y VALOR DE VIVIENDA
DE HASTA 210000 UVAS". Acá se leen las que tienen una forma reconocible; las demás quedan como texto, sin inventar
números. Los montos en UVAs se pasan a pesos con la UVA del día, así el tope sigue al valor actual.
"""
import math
import re

# Valores de relleno que algunos bancos cargan en vez de "sin tope".
_SIN_TOPE = 999_999_999


def _num(s: str) -> float:
    return float(s.replace(".", "").replace(",", "."))


def condiciones(ln: dict) -> dict:
    """Devuelve la línea con los topes leídos del texto del banco (no modifica la original)."""
    d = dict(ln)
    nota = re.sub(r"\s+", " ", str(d.get("nota") or "")).upper()
    mm = d.get("monto_max") or 0
    d["monto_max"] = mm if 0 < mm < _SIN_TOPE else None
    m = re.search(r"MONTO MAXIMO OTORGABLE (\d[\d.]*) UVAS", nota)
    d["monto_max_uva"] = _num(m.group(1)) if m else None
    m = re.search(r"VALOR DE (?:LA )?VIVIENDA SUPERIOR A (\d[\d.]*) UVAS HASTA (\d[\d.]*) UVAS", nota)
    if m:
        d["valor_min_uva"], d["valor_max_uva"] = _num(m.group(1)), _num(m.group(2))
    else:
        m = re.search(r"VALOR DE (?:LA )?VIVIENDA (?:DE )?HASTA (\d[\d.]*) UVAS", nota)
        d["valor_min_uva"], d["valor_max_uva"] = None, (_num(m.group(1)) if m else None)
    m = re.search(r"MONTO MINIMO \$? ?(\d[\d.]*)", nota)
    d["monto_min"] = _num(m.group(1)) if m else None
    im = d.get("ingreso_min") or 0
    m = re.search(r"INGRESO M.NIMO \$? ?(\d[\d.]+)", nota)
    if m:
        im = _num(m.group(1))
    elif im in (999_999, 9_999_999):  # relleno, no es un dato
        im = 0
    d["ingreso_min"] = im or None
    m = re.search(r"\bTNA (\d+(?:,\d+)?) POR CIENTO", nota)
    d["tna"] = _num(m.group(1)) if m else round(12 * ((1 + d["tea"] / 100) ** (1 / 12) - 1) * 100, 2)
    try:
        d["cft"] = float(str(d.get("cft")).replace(",", ".")) if d.get("cft") not in (None, "") else None
    except ValueError:
        d["cft"] = None
    req = []
    if re.search(r"NI EL TITULAR NI EL COTITULAR O CONYUGE PODRAN SER PROPIETARIOS", nota):
        req.append("Ni el titular ni el cotitular o cónyuge pueden tener otra propiedad")
    if re.search(r"NO INCLUYE SEGURO DE INCENDIO", nota):
        req.append("La cuota no incluye seguro de incendio ni IVA")
    elif re.search(r"SEGURO DE INCENDIO", nota):
        req.append("Al pagar se suma el seguro de incendio, que depende de la tasación")
    if re.search(r"SEGURO DE HOGAR", nota):
        req.append("Exige contratar seguro de hogar (y vida o auto)")
    d["requisitos"] = req
    limpia = re.sub(r"\s+", " ", str(d.get("nota") or "")).strip()
    d["nota"] = "" if limpia.upper() in ("", "0", "N/A", "NA", "-") else limpia
    return d


def simular(pp: float | None, ln: dict | None, uva: float | None, anios: int | None = None,
            ltv: float | None = None) -> dict | None:
    """Cuota inicial y condiciones para una vivienda de pp pesos con la línea ln (ya pasada por condiciones())."""
    if not pp or not ln:
        return None
    plazo_max = max(1, math.floor(ln["plazo"] / 12))
    anios = min(anios or 20, plazo_max)
    ltv = min(ltv or ln["ltv"], ln["ltv"])
    motivos: list[str] = []
    califica = True
    if uva and ln.get("valor_max_uva") and pp > ln["valor_max_uva"] * uva:
        califica = False
        vmax = ln["valor_max_uva"]
        motivos.append(f"la vivienda supera el valor máximo de la línea ({fmt_uva(vmax)} UVAs ≈ $ {fmt(vmax * uva)})")
    if uva and ln.get("valor_min_uva") and pp <= ln["valor_min_uva"] * uva:
        califica = False
        motivos.append(f"esta línea es para viviendas de más de {fmt_uva(ln['valor_min_uva'])} UVAs (≈ $ {fmt(ln['valor_min_uva'] * uva)})")
    prestamo = pp * ltv / 100
    tope = None
    topes = [x for x in (ln.get("monto_max"), (ln.get("monto_max_uva") or 0) * (uva or 0)) if x]
    if topes and prestamo > min(topes):
        tope = min(topes)
        prestamo = tope
    if ln.get("monto_min") and prestamo < ln["monto_min"]:
        califica = False
        motivos.append(f"el préstamo queda por debajo del mínimo de la línea ($ {fmt(ln['monto_min'])})")
    n = anios * 12
    i = (1 + ln["tea"] / 100) ** (1 / 12) - 1
    cuota = prestamo * i / (1 - (1 + i) ** -n)
    ingreso = max(cuota / (ln["rci"] / 100), ln.get("ingreso_min") or 0)
    return {"cuota": cuota, "prestamo": prestamo, "anios": anios, "plazo_max": plazo_max, "ltv": round(prestamo / pp * 100),
            "pp": pp, "anticipo": pp - prestamo, "ingreso": ingreso, "tope": tope, "califica": califica, "motivos": motivos,
            "cuota_uva": cuota / uva if uva else None, "uvas": prestamo / uva if uva else None, "total": cuota * n}


def fmt(v: float) -> str:
    return f"{round(v):,}".replace(",", ".")


def fmt_uva(v: float) -> str:
    return fmt(v)
