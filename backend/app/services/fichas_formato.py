"""Fichas para el cliente (página con fotos), Excel por plataforma y puente con el panel de fichas.

html_ficha_cliente, generar_excel, item_para_panel y tachar_telefonos son copia de El Ojo de Dios (app.py):
mismo formato. Cambia de dónde salen los datos: de la base central, con lectura en vivo del aviso al armar la ficha.
"""
import html as htmlmod
import io
import re
import urllib.parse
import zipfile

from app.scraper.red import ahora_local
from app.scraper.texto import detectar_amoblado
from app.services.catalogo import PLAT_NOM

WHATSAPP_INMO = "5492915122322"


TEL_RE = re.compile(r"(?<![\d$])(?<!\d[.,])\+?\(?\d[\d \-()]{5,}\d(?!\d|[.,]\d)")
def tachar_telefonos(texto):
    esc = htmlmod.escape(texto or "")
    def rep(m):
        dig = re.sub(r"\D", "", m.group(0))
        despues = esc[m.end():m.end() + 8].lower()
        if 7 <= len(dig) <= 13 and not re.match(r"\s*(m2|m²|mts|metros|m\b)", despues):
            return f"<s>{m.group(0)}</s>"
        return m.group(0)
    return TEL_RE.sub(rep, esc)


def html_ficha_cliente(ids, cliente, datos):
    """datos: lista de (d, fotos) en el mismo orden que ids, ya leídos (en vivo o de la base)."""
    props, no_disp = [], []
    for pid, (d, fotos) in zip(ids, datos, strict=True):
        if not d or d.get("estado_aviso") == "baja":
            no_disp.append(pid)
        else:
            props.append((d, fotos))
    e = htmlmod.escape
    miles = lambda n: f"{n:,.0f}".replace(",", ".")
    hoy = ahora_local().strftime("%d/%m/%Y")
    n_ok = sum(1 for d, _ in props if d.get("_verificada"))
    verif = ("datos verificados hoy" if props and n_ok == len(props)
             else f"{n_ok} de {len(props)} verificadas hoy en el sitio (el resto, con los últimos datos guardados)")

    def precio_txt(d):
        if not d.get("precio"):
            return "Consultar"
        return f"{'$' if d.get('moneda') == 'ARS' else 'U$S'} {miles(d['precio'])}"

    def titulo(d):
        partes = [d.get("tipo") or "Propiedad"]
        if d.get("barrio"):
            partes.append(d["barrio"])
        elif d.get("ciudad"):
            partes.append(d["ciudad"])
        return " · ".join(partes)

    indice = "".join(
        f'<a class="idx" href="#p{i}"><span class="n">{i}</span><span class="t">{e(titulo(d))}</span>'
        f'<span class="d">{e(d.get("direccion") or "")}</span><span class="p">{e(precio_txt(d))}</span></a>'
        for i, (d, _) in enumerate(props, 1))

    tarjetas = []
    for i, (d, fotos) in enumerate(props, 1):
        dorm = d.get("dormitorios")
        specs = [
            ("Dormitorios", "Monoambiente" if dorm == 0 else (str(dorm) if dorm is not None else "")),
            ("Baños", str(d["banos"]) if d.get("banos") else ""),
            ("m² cubiertos", miles(d["sup_cub"]) if d.get("sup_cub") else ""),
            ("m² totales", miles(d["sup_tot"]) if d.get("sup_tot") else ""),
            ("Espacio exterior", d.get("exterior") if d.get("exterior") not in (None, "", "No figura") else ""),
            ("Estacionamiento", "Cochera" if (d.get("estacionamiento") or "").startswith("Sí") else ""),
            ("Amoblado", {"Amoblado": "Sí", "Semi amoblado": "Semi amoblado", "A elección": "Con o sin muebles", "Sin amoblar": "No"}.get(
                detectar_amoblado(d.get("titulo"), d.get("detalles"), d.get("descripcion")) if (d.get("descripcion") or d.get("detalles")) else (d.get("amoblado") or ""), "")),
            ("Forma de pago", d.get("pago") if d.get("pago") == "Apto crédito" else ""),
            ("Antigüedad", d.get("antiguedad") if d.get("antiguedad") not in (None, "", "No figura") else ""),
            ("Estado", d.get("estado") or ""),
            ("Expensas", "Sí" if d.get("expensas") == "Sí" else ""),
        ]
        if d.get("precio") and d.get("m2_base"):
            specs.append(("Precio por m²", f"{'$' if d.get('moneda') == 'ARS' else 'U$S'} {miles(d['precio'] / d['m2_base'])}"))
        spec_html = "".join(f'<div class="sp"><span>{e(k)}</span><b>{e(v)}</b></div>' for k, v in specs if v)
        if fotos:
            galeria = (f'<div class="gal"><img class="main" id="m{i}" src="{e(fotos[0])}" alt="">'
                       + '<div class="thumbs">' + "".join(
                           f'<img src="{e(u)}" alt="" onclick="document.getElementById(\'m{i}\').src=this.src">' for u in fotos)
                       + "</div></div>")
        else:
            galeria = '<div class="gal sinfoto">Sin fotos publicadas</div>'
        msg = (f"Hola! Me interesa coordinar una visita para la propiedad {titulo(d)}, {d.get('direccion') or ''} "
               f"({precio_txt(d)}). Ref. {d['ref']}")
        wa = f"https://wa.me/{WHATSAPP_INMO}?text={urllib.parse.quote(msg)}"
        mapa = ""
        if d.get("lat"):
            mapa = (f'<a class="mapa" target="_blank" href="https://www.google.com/maps?q={d["lat"]},{d["lng"]}">'
                    f'Ver ubicación en el mapa</a>')
        tarjetas.append(f'''
<section class="prop" id="p{i}">
  <div class="cab"><span class="num">{i}</span><div><h2>{e(titulo(d))}</h2><div class="dir">{e(d.get("direccion") or "")}{", " + e(d.get("ciudad")) if d.get("ciudad") else ""}</div></div>
  <div class="precio">{e(precio_txt(d))}</div></div>
  {galeria}
  <div class="specs">{spec_html}</div>
  <div class="desc"><h3>Descripción</h3><p>{tachar_telefonos(d.get("descripcion"))}</p></div>
  <div class="pie">
    <div class="pub">Publicada por <b>{e(d.get("inmobiliaria") or "inmobiliaria colega")}</b> · {("Ref. " + str(d["ref"])) if (d.get("fuente") or "BBP") == "BBP" else "Vía " + e(PLAT_NOM.get(d.get("fuente"), d.get("fuente") or ""))}{" · " + mapa if mapa else ""}</div>
    <a class="wa" target="_blank" href="{e(wa)}">Coordinar visita por WhatsApp</a>
  </div>
</section>''')

    aviso_no = (f'<div class="nodisp">{len(no_disp)} propiedad(es) seleccionada(s) ya no están publicadas y no se incluyeron '
                f'(Ref. {", ".join(map(str, no_disp))}).</div>') if no_disp else ""
    para = f"para {e(cliente)}" if cliente else ""
    return f'''<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Propiedades {para} · Guillermo Badenheuer Inmobiliaria</title>
<style>
:root{{--navy:#13294b;--navy2:#1d3b66;--yel:#f5b301;--ink:#111;--mute:#5b6472;--line:#e4e7ec}}
*{{box-sizing:border-box}} body{{margin:0;font:15px/1.55 "Segoe UI",system-ui,-apple-system,Roboto,Arial,sans-serif;color:var(--ink);background:#f3f4f6}}
.tool{{position:sticky;top:0;z-index:5;background:#fff;border-bottom:1px solid var(--line);padding:8px 18px;display:flex;gap:8px;justify-content:flex-end}}
.tool button{{border:0;border-radius:6px;padding:8px 14px;font:inherit;cursor:pointer;background:var(--navy);color:#fff}} .tool button.s{{background:#fff;color:var(--navy);border:1px solid var(--navy)}}
header{{background:var(--navy);color:#fff;padding:28px 32px 24px;border-bottom:6px solid var(--yel)}}
.marca{{font-weight:800;letter-spacing:2px;font-size:22px}} .marca small{{display:block;font-weight:400;letter-spacing:4px;font-size:12px;color:var(--yel);margin-top:2px}}
header h1{{margin:18px 0 4px;font-size:26px;font-weight:600}} header .sub{{opacity:.85}}
main{{max-width:1000px;margin:0 auto;padding:22px 18px 40px}}
.nota{{background:#fff;border-left:5px solid var(--yel);padding:12px 16px;border-radius:6px;margin-bottom:18px;color:#333}}
.indice{{background:#fff;border-radius:10px;padding:8px;margin-bottom:22px;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
.idx{{display:grid;grid-template-columns:34px 1.2fr 1.4fr auto;gap:10px;align-items:center;padding:9px 10px;border-radius:6px;text-decoration:none;color:inherit}}
.idx:hover{{background:#f5f7fa}} .idx .n{{background:var(--navy);color:#fff;border-radius:50%;width:26px;height:26px;display:grid;place-items:center;font-size:13px;font-weight:700}}
.idx .t{{font-weight:600}} .idx .d{{color:var(--mute)}} .idx .p{{font-weight:700;color:var(--navy)}}
.prop{{background:#fff;border-radius:12px;margin-bottom:26px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08)}}
.cab{{display:flex;gap:14px;align-items:center;padding:18px 20px;border-bottom:1px solid var(--line)}}
.cab .num{{background:var(--yel);color:var(--navy);font-weight:800;border-radius:8px;min-width:38px;height:38px;display:grid;place-items:center;font-size:18px}}
.cab h2{{margin:0;font-size:20px;color:var(--navy)}} .cab .dir{{color:var(--mute)}} .cab>div:nth-child(2){{flex:1}}
.precio{{background:var(--navy);color:#fff;font-weight:800;font-size:20px;padding:8px 14px;border-radius:8px;white-space:nowrap}}
.gal{{background:#0d1b30}} .gal .main{{width:100%;height:460px;object-fit:cover;display:block}}
.thumbs{{display:flex;gap:6px;padding:8px;overflow-x:auto}} .thumbs img{{height:70px;width:105px;object-fit:cover;border-radius:4px;cursor:pointer;opacity:.85}} .thumbs img:hover{{opacity:1}}
.sinfoto{{color:#cfd6e0;padding:40px;text-align:center}}
.specs{{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:10px;padding:18px 20px}}
.sp{{background:#f6f8fb;border-radius:8px;padding:9px 12px}} .sp span{{display:block;font-size:12px;color:var(--mute);text-transform:uppercase;letter-spacing:.5px}} .sp b{{font-size:15px}}
.desc{{padding:0 20px 8px}} .desc h3{{margin:6px 0;color:var(--navy);font-size:16px}} .desc p{{white-space:pre-wrap;margin:0 0 10px;color:#333}} .desc s{{color:#999}}
.pie{{display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between;padding:14px 20px 20px;border-top:1px solid var(--line)}}
.pub{{color:var(--mute);font-size:13.5px}} .mapa{{color:var(--navy2)}}
.wa{{background:#25d366;color:#fff;text-decoration:none;font-weight:700;padding:11px 18px;border-radius:30px}}
.nodisp{{background:#fdecec;border:1px solid #f3b4b4;color:#8a1f1f;padding:10px 14px;border-radius:6px;margin-bottom:16px}}
footer{{text-align:center;color:var(--mute);padding:20px;font-size:13px}} footer b{{color:var(--navy)}}
@media print{{ .tool,.thumbs{{display:none}} body{{background:#fff}} .prop{{box-shadow:none;break-before:page}} .prop:first-of-type{{break-before:auto}} .gal .main{{height:340px}} header{{-webkit-print-color-adjust:exact;print-color-adjust:exact}} .precio,.cab .num,.idx .n,.wa{{-webkit-print-color-adjust:exact;print-color-adjust:exact}} }}
@media(max-width:640px){{ .gal .main{{height:260px}} .idx{{grid-template-columns:30px 1fr auto}} .idx .d{{display:none}} .cab{{flex-wrap:wrap}} }}
</style></head><body>
<div class="tool"><button class="s" onclick="descargar()">Descargar página</button><button onclick="window.print()">Imprimir / Guardar PDF</button></div>
<header><div class="marca">GUILLERMO BADENHEUER<small>INMOBILIARIA</small></div>
<h1>Selección de propiedades {para}</h1><div class="sub">{len(props)} propiedad(es) · {hoy} · {verif}</div></header>
<main>
<div class="nota">Trabajamos en conjunto con inmobiliarias colegas: coordinamos las visitas con ellas, <b>sin doble honorario</b>. Para consultas o visitas escribinos por WhatsApp desde el botón de cada propiedad.</div>
{aviso_no}
<div class="indice">{indice}</div>
{"".join(tarjetas)}
</main>
<footer><b>Guillermo Badenheuer Inmobiliaria</b> · Bahía Blanca · WhatsApp 291 512-2322</footer>
<script>
function descargar(){{const h='<!DOCTYPE html>'+document.documentElement.outerHTML.replace(/<div class="tool">[\\s\\S]*?<\\/div>/,'');
const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([h],{{type:'text/html'}}));a.download='Propiedades{("_" + re.sub(r"[^A-Za-z0-9]+", "_", cliente)) if cliente else ""}_{ahora_local():%Y-%m-%d}.html';a.click()}}
</script></body></html>'''


EXCEL_NOMBRE = "Fichas_Venta_Bahia_Blanca_Propiedades.xlsx"
EXCEL_COLS = ["ID", "Inmueble", "Ciudad", "Barrio", "Dirección", "Dormitorios", "Baños", "Espacio exterior",
              "Estacionamiento", "Pago", "Moneda", "Presupuesto", "Antigüedad", "m² cubiertos", "m² totales",
              "m² (base cálculo)", "Precio por m²", "Estado", "Expensas", "Ficha para WhatsApp", "Título publicación",
              "Link", "Publicada", "Última verificación", "Inmobiliaria", "Amoblado"]
EXCEL_ANCHOS = [8, 13, 16, 16, 24, 11, 8, 26, 15, 28, 8, 12, 16, 11, 11, 13, 12, 13, 9, 45, 50, 14, 22, 20, 26, 14]
_XML_MALO = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
def _col(n):
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _x(v):
    return htmlmod.escape(_XML_MALO.sub("", str(v)), quote=True)


def _hoja(filas_xml, ncols, nfilas, anchos, congelar=True, filtro=True):
    cols = "".join(f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>' for i, w in enumerate(anchos, 1))
    vista = ('<sheetViews><sheetView workbookViewId="0"><pane xSplit="2" ySplit="1" topLeftCell="C2" '
             'activePane="bottomRight" state="frozen"/></sheetView></sheetViews>') if congelar else ""
    af = f'<autoFilter ref="A1:{_col(ncols)}{max(nfilas, 1)}"/>' if filtro else ""
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'{vista}<cols>{cols}</cols><sheetData>{"".join(filas_xml)}</sheetData>{af}</worksheet>')


def _celda(ref, v, estilo=0):
    st = f' s="{estilo}"' if estilo else ""
    if v is None or v == "":
        return f'<c r="{ref}"{st}/>' if estilo else ""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        n = int(v) if float(v).is_integer() else round(v, 2)
        return f'<c r="{ref}"{st}><v>{n}</v></c>'
    return f'<c r="{ref}" t="inlineStr"{st}><is><t xml:space="preserve">{_x(v)}</t></is></c>'


def _fila(nro, celdas):
    return f'<row r="{nro}">{"".join(celdas)}</row>'


def generar_excel(fuente, activas, bajas, inicio):
    """Arma el .xlsx con el mismo formato del Excel de fichas (solo biblioteca estándar).
    activas / bajas: filas con los nombres de columna de El Ojo de Dios (ver fichas.filas_excel)."""
    def link_de(r):
        return r["url"]

    def publicada(r):
        if r["detectada"] and r["detectada_desde"]:
            return f"{r['detectada_desde'][:16]} a {r['detectada'][11:16]}"
        if r["detectada"]:
            return f"antes de {r['detectada'][:16]}"
        if r["pub_txt"]:
            return f"{r['pub_txt']} (según el sitio)"
        return f"antes de {inicio[:10]}" if inicio else ""

    def fila_prop(i, r):
        n = i + 2
        precio = r["precio"] if r["precio"] else None
        celdas = [
            _celda(f"A{n}", int(r["id_externo"]) if fuente == "BBP" and str(r["id_externo"]).isdigit() else (int(re.search(r"(\d{5,})", r["url"] or "").group(1)) if fuente == "ZP" and re.search(r"(\d{5,})", r["url"] or "") else n - 1)), _celda(f"B{n}", r["tipo"] or "No figura"), _celda(f"C{n}", r["ciudad"] or "No figura"),
            _celda(f"D{n}", r["barrio"] or None), _celda(f"E{n}", r["direccion"] or None),
            _celda(f"F{n}", r["dormitorios"]), _celda(f"G{n}", r["banos"]),
            _celda(f"H{n}", r["exterior"] or "No figura"), _celda(f"I{n}", r["estacionamiento"] or "No figura"),
            _celda(f"J{n}", r["pago"] or "Contado (no figura apto crédito)"), _celda(f"K{n}", r["moneda"] or None),
            _celda(f"L{n}", precio if precio else "Consultar", 3 if precio else 0),
            _celda(f"M{n}", r["antiguedad"] or "No figura"),
            _celda(f"N{n}", r["sup_cub"]), _celda(f"O{n}", r["sup_tot"]), _celda(f"P{n}", r["m2_base"]),
        ]
        pm2 = round(precio / r["m2_base"], 2) if (precio and r["m2_base"]) else ""
        cache = f"<v>{pm2}</v>" if pm2 != "" else "<v></v>"
        tipo_cache = "" if pm2 != "" else ' t="str"'
        celdas.append(f'<c r="Q{n}" s="3"{tipo_cache}><f>IF(AND(ISNUMBER(L{n}),ISNUMBER(P{n}),P{n}&gt;0),L{n}/P{n},"")</f>{cache}</c>')
        url = link_de(r)
        celdas += [
            _celda(f"R{n}", r["estado"] or None), _celda(f"S{n}", r["expensas"] or None),
            _celda(f"T{n}", r["ficha"], 2), _celda(f"U{n}", r["titulo"] or None),
            f'<c r="V{n}" t="str" s="4"><f>HYPERLINK("{_x(url)}","Ver propiedad")</f><v>Ver propiedad</v></c>',
            _celda(f"W{n}", publicada(r)), _celda(f"X{n}", r["ultima_verif"] or None), _celda(f"Y{n}", r["inmobiliaria"] or None),
            _celda(f"Z{n}", r["amoblado"] or "No figura"),
        ]
        return _fila(n, celdas)

    enc = _fila(1, [_celda(f"{_col(i)}1", h, 1) for i, h in enumerate(EXCEL_COLS, 1)])
    hoja1 = _hoja([enc] + [fila_prop(i, r) for i, r in enumerate(activas)], len(EXCEL_COLS), len(activas) + 1, EXCEL_ANCHOS)

    cols_b = ["ID", "Inmueble", "Ciudad", "Barrio", "Dirección", "Moneda", "Último precio", "Dada de baja", "Título publicación", "Link"]
    filas_b = [_fila(1, [_celda(f"{_col(i)}1", h, 1) for i, h in enumerate(cols_b, 1)])]
    for i, r in enumerate(bajas):
        n = i + 2
        filas_b.append(_fila(n, [_celda(f"A{n}", r["id_externo"]), _celda(f"B{n}", r["tipo"]), _celda(f"C{n}", r["ciudad"]),
                                 _celda(f"D{n}", r["barrio"]), _celda(f"E{n}", r["direccion"]), _celda(f"F{n}", r["moneda"]),
                                 _celda(f"G{n}", r["precio"], 3), _celda(f"H{n}", r["fecha_baja"]), _celda(f"I{n}", r["titulo"]),
                                 _celda(f"J{n}", link_de(r))]))
    hoja2 = _hoja(filas_b, len(cols_b), len(bajas) + 1, [8, 13, 16, 16, 24, 8, 12, 20, 50, 45])

    notas = [
        "Cómo se armó",
        f"Generado automáticamente por Radar Prop el {ahora_local():%Y-%m-%d %H:%M:%S}. {len(activas)} propiedades en venta activas, {len(bajas)} dadas de baja (hoja 'Dadas de baja').",
        ("Fuente: cada link de bahiablancapropiedades.com." if fuente == "BBP" else "Fuente: cada link de ibb.com.ar (listado completo del buscador de IBB)." if fuente == "IBB" else "Fuente: planilla de Zonaprop cargada en la app (zonaprop.com.ar).")
        + (" Avisos nuevos y bajas se detectan cada 10-15 minutos; cada ficha se vuelve a leer de forma rotativa (columna 'Última verificación')." if fuente != "ZP" else " Se actualiza cada vez que se carga una planilla nueva de Zonaprop con “Cargar planilla”: lo nuevo se agrega y lo que ya no figura pasa a 'Dadas de baja'."),
        "Precio por m²: Presupuesto ÷ m² (base cálculo). Viviendas usan m² cubiertos; terrenos, locales, campos, etc. usan m² totales. Si falta uno, se usa el otro o los m² escritos en la descripción.",
        "Precio por m² está en la moneda de la columna Moneda (USD o ARS). \"Consultar\" = la publicación no muestra precio.",
        "Pago: \"Apto crédito\" si la ficha o la descripción lo dicen; si no figura, queda como Contado (no figura apto crédito).",
        "Estacionamiento / Espacio exterior: salen de los ítems de la ficha y de palabras clave en la descripción (cochera, garage, patio, jardín, balcón, terraza, quincho, pileta). \"No figura\" = la publicación no lo menciona. Si está activado el análisis con IA, también se completan con lo que la IA lee en la descripción.",
        "Amoblado: sale del título, los ítems y la descripción (amoblado, semi amoblado, sin amoblar). \"Cocina amoblada\" o placares no cuentan como amoblado.",
        "Duplex: se marca cuando el título dice dúplex. Departamento Interno → Interno.",
        "m² menores a 10 se descartaron por ser errores de carga.",
        "Publicada: franja horaria en que el aviso apareció en el sitio (el sitio no informa la fecha original; los avisos que ya estaban al crear la base figuran como \"antes de\").",
        "La columna Ficha para WhatsApp es texto fijo listo para copiar; Precio por m² (col. Q) es fórmula.",
    ]
    hoja3 = _hoja([_fila(i + 1, [_celda(f"A{i + 1}", t, 1 if i == 0 else 0)]) for i, t in enumerate(notas)], 1, len(notas), [140],
                  congelar=False, filtro=False)

    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
              '<numFmts count="1"><numFmt numFmtId="164" formatCode="#,##0"/></numFmts>'
              '<fonts count="3"><font><sz val="11"/><name val="Calibri"/></font>'
              '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>'
              '<font><u/><sz val="11"/><color rgb="FF0563C1"/><name val="Calibri"/></font></fonts>'
              '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
              '<fill><patternFill patternType="solid"><fgColor rgb="FF1F3864"/><bgColor indexed="64"/></patternFill></fill></fills>'
              '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
              '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
              '<cellXfs count="5"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
              '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1">'
              '<alignment vertical="center" wrapText="1"/></xf>'
              '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>'
              '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
              '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
              '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
    hojas = [("Fichas Venta", hoja1), ("Dadas de baja", hoja2), ("Notas", hoja3)]
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
          '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
          + "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                    for i in range(1, len(hojas) + 1)) + '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>')
    wb = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
          + "".join(f'<sheet name="{_x(n)}" sheetId="{i}" r:id="rId{i}"/>' for i, (n, _) in enumerate(hojas, 1))
          + '</sheets><definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0" hidden="1">'
          f"'Fichas Venta'!$A$1:${_col(len(EXCEL_COLS))}${len(activas) + 1}</definedName></definedNames>"
          '<calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>')
    wbrels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
              + "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
                        for i in range(1, len(hojas) + 1))
              + f'<Relationship Id="rId{len(hojas) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
              '</Relationships>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("xl/workbook.xml", wb)
        z.writestr("xl/_rels/workbook.xml.rels", wbrels)
        z.writestr("xl/styles.xml", styles)
        for i, (_, xml) in enumerate(hojas, 1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", xml)
    return buf.getvalue()


def item_para_panel(d, fotos):
    tipo, op = d.get("tipo") or "Propiedad", d.get("operacion") or "Venta"
    lugar = d.get("barrio") or d.get("ciudad") or ""
    feats = [x.strip() for x in (d.get("exterior") or "").split(",") if x.strip() and x.strip() != "No figura"]
    est = d.get("estacionamiento") or ""
    cocheras = None
    if est.startswith("Sí"):
        feats.append("Cochera")
        m = re.search(r"(\d+)", d.get("cochera") or "")
        cocheras = int(m.group(1)) if m else 1
    for k, nom in (("pileta", "Pileta"), ("parrilla", "Quincho / parrilla")):
        if (d.get(k) or "").startswith("Sí") and nom not in feats:
            feats.append(nom)
    if d.get("pago") == "Apto crédito":
        feats.append("Apto crédito")
    if d.get("amoblado") in ("Amoblado", "Semi amoblado"):
        feats.append(d["amoblado"])
    f = {
        "title": (d.get("titulo") or f"{tipo} en {op}{' en ' + lugar if lugar else ''}")[:200],
        "operation": "Alquiler" if "lquiler" in op else "Venta",
        "propertyType": tipo, "currency": "ARS" if d.get("moneda") == "ARS" else "USD", "price": d.get("precio"),
        "expensas": d.get("expensas") or "", "areaTotal": d.get("sup_tot"), "areaCovered": d.get("sup_cub"),
        "ambientes": None, "dormitorios": d.get("dormitorios"), "banos": d.get("banos"), "cocheras": cocheras,
        "antiguedad": d.get("antiguedad") or "",
        "zone": ", ".join(x for x in (d.get("direccion"), d.get("barrio"), d.get("ciudad")) if x),
        "features": feats[:24], "description": d.get("descripcion") or "",
        "publisher": d.get("inmobiliaria") or PLAT_NOM.get(d.get("fuente"), d.get("fuente") or ""),
        "publisherGuess": False, "photos": (fotos or [])[:30],
        "sourceUrl": d.get("url") or "", "note": "", "showOriginal": False,
    }
    return {"url": f["sourceUrl"], "f": f}
