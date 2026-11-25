"""Textos legibles para el historial ("Casa · 3+ dorm · hasta USD 160.000 · zona dibujada")."""


def _miles(n) -> str:
    return f"{round(float(n)):,}".replace(",", ".")


def resumen_filtros(f: dict, con_zona: bool = False) -> str:
    if f.get("qg"):
        return f"Búsqueda en toda la base: «{f['qg']}»"
    p: list[str] = [f.get("oper") or "Venta"]
    if f.get("tipos"):
        p.append(", ".join(f["tipos"][:4]) + ("…" if len(f["tipos"]) > 4 else ""))
    if f.get("dorm") not in (None, ""):
        d = f["dorm"]
        p.append("monoambiente" if d == "0" else f"{d}+ dorm" if (d == "5" or f.get("dorm_modo") == "min") else f"{d} dorm")
    s = "$" if f.get("mon") == "ARS" else "USD"
    if f.get("b"):
        p.append(f"presupuesto {s} {_miles(f['b'])}")
    else:
        if f.get("pmin"):
            p.append(f"desde {s} {_miles(f['pmin'])}")
        if f.get("pmax"):
            p.append(f"hasta {s} {_miles(f['pmax'])}")
    if f.get("ciudad"):
        p.append(f["ciudad"])
    if f.get("barrios"):
        p.append(", ".join(f["barrios"][:3]) + ("…" if len(f["barrios"]) > 3 else ""))
    for k, t in (("patio", "patio"), ("cochera", "cochera"), ("pileta", "pileta"), ("balcon", "balcón"), ("parrilla", "parrilla")):
        if f.get(k) == "si":
            p.append(f"con {t}")
        elif f.get(k) == "no":
            p.append(f"sin {t}")
    if f.get("amoblado") == "si":
        p.append("amoblado")
    elif f.get("amoblado") == "no":
        p.append("sin amoblar")
    if f.get("credito"):
        p.append("apto crédito")
    if f.get("kw"):
        p.append(f"«{f['kw']}»")
    if f.get("nuevas_horas"):
        p.append(f"nuevas ({f['nuevas_horas']} h)")
    if f.get("plataforma") and f["plataforma"] != "todas":
        p.append(f["plataforma"])
    if con_zona:
        p.append("zona dibujada")
    return " · ".join(p)
