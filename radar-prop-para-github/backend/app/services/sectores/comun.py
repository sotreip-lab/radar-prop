"""Herramientas compartidas por los sectores aparte (copia de modulos/comun.py de El Ojo de Dios)."""
import re
from collections import Counter
from functools import lru_cache

from app.core.texto import sin_marcas


@lru_cache(maxsize=1 << 16)  # los mismos barrios, tipos y direcciones se repiten miles de veces
def norm(s):
    return sin_marcas(s or "").lower().strip()


GRUPOS_TIPO = [
    ("Departamento", ("departamento", "semipiso", "piso", "loft", "monoambiente", "interno")),
    ("Casa", ("casa", "chalet", "duplex", "dúplex", "triplex", "cabaña", "casaquinta")),
    ("PH", ("ph",)),
    ("Terreno", ("terreno", "lote")),
    ("Local", ("local", "fondo", "consultorio")),
    ("Oficina", ("oficina",)),
    ("Depósito / Galpón", ("galpon", "galpón", "deposito", "depósito", "frigorifico", "silo")),
    ("Cochera", ("cochera",)),
    ("Quinta / Campo", ("quinta", "campo", "chacra")),
]


@lru_cache(maxsize=4096)
def grupo_tipo(tipo):
    t = norm(tipo)
    if t.startswith("casa con local"):
        return "Local"
    for g, claves in GRUPOS_TIPO:
        if any(t.startswith(norm(c)) for c in claves):
            return g
    return "Otros"


@lru_cache(maxsize=1 << 15)
def clave_direccion(direccion):
    """'Zapiola 1473, Centro' -> 'zapiola1473' (vacío si no tiene número)."""
    d = re.sub(r"[^a-z0-9]", "", norm((direccion or "").split(",")[0]))
    return d if re.search(r"\d", d) and len(d) >= 5 else ""


def m2_de(r):
    """Superficie para el valor por m²: terrenos por superficie total, el resto la base que ya calcula la app."""
    g = grupo_tipo(r["tipo"])
    if g in ("Terreno", "Quinta / Campo"):
        return r["sup_tot"] or r["m2_base"]
    return r["m2_base"]


def precio_valido(precio, moneda="USD", dolar=0, operacion="Venta"):
    """Descarta precios de relleno que ponen las inmobiliarias para no publicar el valor real:
    111.111.111, 11.111.111, 99.999, 123.456.789, 1, etc."""
    if not precio or precio <= 0:
        return False
    d = str(int(round(precio)))
    if len(d) >= 5 and len(set(d)) == 1:
        return False
    if len(d) >= 6 and ("123456789".startswith(d[:6]) or "987654321".startswith(d[:6])):
        return False
    if operacion != "Venta":
        return precio >= (20 if (moneda or "USD") == "USD" else 1000)
    if (moneda or "USD") == "USD":
        return 1000 <= precio <= 20_000_000
    tope = 20_000_000 * (dolar or 2000)
    return 100_000 <= precio <= tope


def precio_usd(r, dolar):
    if not precio_valido(r["precio"], r["moneda"], dolar, r.get("operacion") or "Venta"):
        return None
    if (r["moneda"] or "USD") == "USD":
        return float(r["precio"])
    return float(r["precio"]) / dolar if dolar else None


def coords_validas(filas):
    """Descarta coordenadas genéricas: (0,0) y puntos repetidos en muchos avisos (centro de la ciudad
    o ubicación por defecto del portal)."""
    cuenta = Counter((round(r["lat"], 4), round(r["lng"], 4)) for r in filas if r["lat"] and r["lng"])
    malas = {k for k, n in cuenta.items() if n > 12}
    return lambda r: bool(r["lat"] and r["lng"] and abs(r["lat"]) > 1
                          and (round(r["lat"], 4), round(r["lng"], 4)) not in malas)


class Barrios:
    """Unifica la escritura de los barrios (CENTRO / Centro, Napostá / Naposta) y deduce el barrio
    por cercanía cuando el aviso no lo informa."""

    def __init__(self, filas, valida):
        formas = {}
        for r in filas:
            b = (r["barrio"] or "").strip()
            if b:
                formas.setdefault(norm(b), Counter())[b] += 1
        self.nombre = {k: max(c.items(), key=lambda x: (x[1], any(ch in x[0] for ch in "áéíóúñ"), x[0] != x[0].upper()))[0]
                       for k, c in formas.items()}
        self.puntos = [(r["lat"], r["lng"], norm(r["barrio"])) for r in filas
                       if valida(r) and (r["barrio"] or "").strip() and (r["ciudad"] or "") == "Bahía Blanca"]
        self.grilla = {}
        for p in self.puntos:
            self.grilla.setdefault((int(p[0] / 0.006), int(p[1] / 0.006)), []).append(p)

    def de(self, r, valida=None):
        b = (r["barrio"] or "").strip()
        if b:
            return self.nombre.get(norm(b), b)
        if valida and valida(r) and self.puntos:
            la, ln = r["lat"], r["lng"]
            gi, gj = int(la / 0.006), int(ln / 0.006)
            cand = [p for a in (-1, 0, 1) for b in (-1, 0, 1) for p in self.grilla.get((gi + a, gj + b), ())]
            cerca = sorted(cand, key=lambda p: (p[0] - la) ** 2 + (p[1] - ln) ** 2)[:7]
            if cerca and ((cerca[0][0] - la) ** 2 + (cerca[0][1] - ln) ** 2) ** 0.5 < 0.006:  # ~600 m
                k = Counter(p[2] for p in cerca).most_common(1)[0][0]
                return self.nombre.get(k, k)
        return ""


def mediana(v):
    v = sorted(v)
    if not v:
        return None
    m = len(v) // 2
    return v[m] if len(v) % 2 else (v[m - 1] + v[m]) / 2


def es_propia(inmobiliaria):
    return "badenheuer" in norm(inmobiliaria)


_INM_RUIDO = re.compile(r"\b(inmobiliaria|inmobiliario|inmobiliarios|negocios|servicios|propiedades|estudio|bienes|raices|"
                        r"grupo|desarrollos|operaciones|consultora|asesores|y|e|de|la|las|los|el|del|srl|sa|s\.a\.|sas|bahia|blanca)\b")


def inm_clave(nombre):
    """'Bochile Inmobiliaria' y 'Bochile' -> 'bochile' (para saber si dos avisos son de la misma inmobiliaria)."""
    t = re.sub(r"[^a-z0-9 ]", " ", norm(nombre))
    t = _INM_RUIDO.sub(" ", t).split()
    return " ".join(t[:2]) if t else norm(nombre)


@lru_cache(maxsize=4096)
def dia(f):
    """strptime de 'AAAA-MM-DD', una vez por fecha distinta."""
    from datetime import datetime
    return datetime.strptime(f, "%Y-%m-%d")
