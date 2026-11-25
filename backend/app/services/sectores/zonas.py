"""Mapas oficiales del Municipio de Bahía Blanca (datos.bahia.gob.ar): barrios y zonas del CPU.
Vienen ya procesados de El Ojo de Dios (app/datos/zonas_*.json). Clases copiadas de modulos/zonas.py."""
import json
import os

CAPAS: dict = {}
ESTADO: dict = {}
DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "datos")


def cargar(capa):
    if capa not in CAPAS:
        with open(os.path.join(DIR, f"zonas_{capa}.json"), encoding="utf-8") as f:
            CAPAS[capa] = json.load(f)
        ESTADO[capa] = f"{len(CAPAS[capa])} polígonos"
    return CAPAS[capa]


class Indice:
    """Ubica un punto dentro de los polígonos de una capa."""

    def __init__(self, feats):
        self.items = []
        for f in feats:
            for anillo in f["p"]:
                la = [x[0] for x in anillo]
                ln = [x[1] for x in anillo]
                self.items.append((min(la), max(la), min(ln), max(ln), anillo, f["n"]))

    def donde(self, lat, lng):
        """Si el punto cae en dos zonas superpuestas (un barrio dentro de otro), gana la más chica."""
        mejor, area = "", 1e9
        for a, b, c, d, anillo, n in self.items:
            if a <= lat <= b and c <= lng <= d:
                ar = (b - a) * (d - c)
                if ar < area and _dentro(lat, lng, anillo):
                    mejor, area = n, ar
        return mejor


def _dentro(y, x, anillo):
    dentro = False
    j = len(anillo) - 1
    for i in range(len(anillo)):
        yi, xi = anillo[i]
        yj, xj = anillo[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            dentro = not dentro
        j = i
    return dentro


def para_mapa(capa):
    """Polígonos agrupados por nombre, listos para dibujar."""
    g = {}
    for f in cargar(capa):
        g.setdefault(f["n"], []).extend(f["p"])
    caja = lambda ps: (max(x[0] for r in ps for x in r) - min(x[0] for r in ps for x in r)) * (max(x[1] for r in ps for x in r) - min(x[1] for r in ps for x in r))
    # primero las zonas grandes, así las chicas (un barrio dentro de otro) quedan arriba y se pueden tocar
    return sorted(({"n": n, "p": p} for n, p in g.items()), key=lambda f: -caja(f["p"]))
