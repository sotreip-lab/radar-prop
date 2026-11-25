"""Lectura de planillas .xlsx sin dependencias (copia de leer_xlsx de El Ojo de Dios)."""
import io
import os
import re
import xml.etree.ElementTree as ET
import zipfile


def leer_xlsx(data):
    """Lector mínimo de .xlsx (stdlib). Devuelve lista de (hoja, filas[list[str]], links[list[str]])."""
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
          "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
          "pr": "http://schemas.openxmlformats.org/package/2006/relationships"}
    z = zipfile.ZipFile(io.BytesIO(data))
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in root.findall("m:si", ns):
            shared.append("".join(t.text or "" for t in si.iter(f"{{{ns['m']}}}t")))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    rmap = {r.get("Id"): r.get("Target") for r in rels.findall("pr:Relationship", ns)}
    salida = []
    for sh in wb.find("m:sheets", ns).findall("m:sheet", ns):
        nombre = sh.get("name")
        target = rmap.get(sh.get(f"{{{ns['r']}}}id"), "")
        path = target.lstrip("/") if target.startswith("/xl/") else "xl/" + target.replace("xl/", "")
        if path not in z.namelist():
            continue
        root = ET.fromstring(z.read(path))
        links, hl_rid = [], {}
        relpath = os.path.dirname(path) + "/_rels/" + os.path.basename(path) + ".rels"
        if relpath in z.namelist():
            rr = ET.fromstring(z.read(relpath))
            rels_h = {r.get("Id"): r.get("Target") for r in rr.findall("pr:Relationship", ns)
                      if "hyperlink" in (r.get("Type") or "")}
            links = list(rels_h.values())
            hls = root.find("m:hyperlinks", ns)
            for h in (hls.findall("m:hyperlink", ns) if hls is not None else []):
                tg = rels_h.get(h.get(f"{{{ns['r']}}}id"))
                if tg and h.get("ref"):
                    hl_rid[h.get("ref").split(":")[0]] = tg

        def col_idx(ref):
            m = re.match(r"([A-Z]+)", ref or "")
            if not m:
                return None
            n = 0
            for ch in m.group(1):
                n = n * 26 + ord(ch) - 64
            return n - 1
        filas = []
        for row in root.iter(f"{{{ns['m']}}}row"):
            vals = []
            for c in row.findall("m:c", ns):
                t = c.get("t")
                v = c.find("m:v", ns)
                if t == "s" and v is not None:
                    val = shared[int(v.text)]
                elif t == "inlineStr":
                    val = "".join(x.text or "" for x in c.iter(f"{{{ns['m']}}}t"))
                else:
                    val = v.text if v is not None else ""
                ref = c.get("r")
                if ref in hl_rid and not str(val).lower().startswith("http"):
                    val = hl_rid[ref]  # celda con hipervínculo ("Ver propiedad") → la dirección real
                ci = col_idx(ref)
                if ci is not None:
                    while len(vals) < ci:
                        vals.append("")  # celdas vacías que Excel no guarda
                vals.append(val)
            filas.append(vals)
        salida.append((nombre, filas, links))
    return salida
