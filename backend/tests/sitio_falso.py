"""Sitio falso de BBP + IBB para probar el worker sin tocar los sitios reales.

El HTML imita las partes que leen los analizadores (mismas clases y estructura que los sitios reales).
`ESTADO` se puede cambiar entre corridas para simular avisos nuevos, bajas y cambios de precio.
"""
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ESTADO: dict = {
    # BBP: número -> (precio, título, inmobiliaria)
    "bbp": {
        "95001": ("U$S 158.000", "Casa en Venta en Zapiola 1473, Palihue, Bahía Blanca", "INMO UNO"),
        "95002": ("U$S 120.000", "Departamento en Venta en Soler 111, Centro, Bahía Blanca", "INMO DOS"),
        "95003": ("$ 450.000", "Departamento en Alquiler en Caronti 190 2ºE, Centro, Bahía Blanca", "INMO UNO"),
    },
    "bbp_sitemap_extra": set(),   # números que figuran en el sitemap pero cuya ficha da 404
    # IBB: slug -> (operación, precio, título)
    "ibb": {
        "casa-en-venta-3-dormitorios-en-zapiola-1473": ("selling", "USD 99.000", "Casa en Venta"),
        "departamento-en-alquiler-en-soler-111": ("renting", "$ 380.000", "Departamento en Alquiler"),
    },
    "ibb_credito": {"casa-en-venta-3-dormitorios-en-zapiola-1473"},
    "pedidos": [],
}


def ficha_bbp(num: str, precio: str, titulo: str, inmo: str) -> str:
    return f'''<!doctype html><html lang="es"><head><title>{titulo}</title>
<meta property="og:image" content="/fotos/{num}-og.jpg"></head><body>
<div class="propiedad-in-wrapper"><h2 class="propiedad-in-inmo"><a href="/x">{inmo}</a></h2>
<h1 class="propiedad-in-title">{titulo}</h1>
<ul class="propiedad-in-info clearfix"><li><i class="fa fa-tag text-orange"></i> {precio}</li>
<li><i class="fa fa-bed"></i> 3 Dormitorios</li></ul></div>
<div class="swiper-zoom-container"><img class="x" src="/fotos/{num}-1.jpg"></div>
<div class="swiper-zoom-container"><img class="x" src="/fotos/{num}-2.jpg"></div>
<div id="propiedad-in-map" data-lat="-38.7012345" data-lng="-62.2654321"></div>
<hr><h6><strong>Descripción</strong></h6><p>Linda casa con patio, quincho y cochera. Apta crédito. Totalmente amoblada.</p>
<hr><h6><strong>Detalles</strong></h6>
<div class="row"><div class="col-sm-4"> Dormitorios: <strong> 3 Dormitorios </strong></div>
<div class="col-sm-4"> Baños: <strong> 2 </strong></div>
<div class="col-sm-4"> Superficie Cubierta (mts²): <strong> 120 </strong></div>
<div class="col-sm-4"> Superficie Total (mts²): <strong> 300 </strong></div>
<div class="col-sm-4"> Antigüedad: <strong> 10 años </strong></div></div>
<!-- Propiedades Relacionadas --><h3>Propiedades Relacionadas</h3>
<div class="col-sm-4"> Dormitorios: <strong> 1 Dormitorio </strong></div>
<footer></footer></body></html>'''


def listado_ibb(slugs) -> str:
    return "<html><body>" + "".join(f'<a href="/listings/{s}">x</a>' for s in slugs) + "</body></html>"


def ficha_ibb(slug: str, op: str, precio: str, titulo: str) -> str:
    return f'''<!DOCTYPE html><html><body>
<h1 class="fs-32">{titulo}</h1>
<h2 class="text-neutral-1000 fs-24 fw-bold mb-0">{precio}</h2>
<p class="mb-0 text-neutral-1000 fs-lm">Zapiola 1473, palihue, Bahía Blanca (8000), Provincia de Buenos Aires, Argentina</p>
<p class="fs-6 fw-normal text-neutral-1000">{"Venta" if op == "selling" else "Alquiler"}</p>
<p class="fs-24 fw-bold text-neutral-1000">Inmobiliaria IBB Socia</p>
<!-- Main features -->
<div><span class="fw-medium">3 dormitorios</span><span class="fw-medium">2 baños</span>
<span class="fw-medium">150 m² cubierta</span><span class="fw-medium">400 m² totales</span>
<span class="fw-medium">1 estacionamiento</span></div>
<p class="text-secondary fs-ml">Publicado hace 3 días</p>
<div data-description-toggle-target="content">Casa con jardín y pileta.</div>
<div id="map" data-properties="[{{&quot;latitude&quot;:-38.7100001,&quot;longitude&quot;:-62.2500001}}]"></div>
<img src="https://res.cloudinary.com/x/image/upload/t_big/v123/listing-gallery/{slug}-1.jpg">
</body></html>'''


class Manejador(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def responder(self, codigo: int, cuerpo: str, ctype: str = "text/html"):
        b = cuerpo.encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Last-Modified", "Mon, 23 Nov 2026 13:00:00 GMT")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(b)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        ESTADO["pedidos"].append(self.path)
        ruta = self.path.split("?")[0]
        if ruta.startswith("/bbp/sitemap.xml"):
            nums = list(ESTADO["bbp"]) + list(ESTADO["bbp_sitemap_extra"])
            return self.responder(200, "<urlset>" + "".join(
                f"<url><loc>https://x/propiedad/{n}/</loc></url>" for n in nums) + "</urlset>", "application/xml")
        if ruta.startswith("/bbp/propiedad/"):
            num = ruta.strip("/").split("/")[-1]
            if num in ESTADO["bbp"]:
                return self.responder(200, ficha_bbp(num, *ESTADO["bbp"][num]))
            return self.responder(404, "no existe")
        if ruta.startswith("/bbp/fotos/"):
            return self.responder(200, "x", "image/jpeg")
        if ruta.startswith("/ibb/"):
            if "text/html" not in (self.headers.get("Accept") or ""):
                return self.responder(406, "")  # igual que el sitio real
            if ruta == "/ibb/search":
                q = self.path
                if "accepts_credit=true" in q:
                    return self.responder(200, listado_ibb(ESTADO["ibb_credito"]))
                lt = q.split("listing_type=")[1].split("&")[0]
                return self.responder(200, listado_ibb(s for s, v in ESTADO["ibb"].items() if v[0] == lt))
            if ruta.startswith("/ibb/listings/"):
                slug = ruta.split("/listings/")[1]
                if slug in ESTADO["ibb"]:
                    return self.responder(200, ficha_ibb(slug, *ESTADO["ibb"][slug]))
                return self.responder(404, "")
        return self.responder(404, "")


def arrancar() -> tuple[ThreadingHTTPServer, str]:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"
