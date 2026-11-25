import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { useEffect, useRef, useState } from "react";
import { useBusqueda } from "../busqueda";
import { fmt, sim } from "../formato";
import type { Zona } from "../tipos";

export type Punto = [number, number, number, string, string, number | null, string | null, number];
const COLOR: Record<string, string> = { Verde: "#2e9e4f", Violeta: "#7c4dba", Amarillo: "#d99a00", Rojo: "#d24b43", "": "#23385d" };
const ZCOL: Record<string, string> = { dentro: "#16a34a", cerca: "#f59e0b" };

function zonaDeLimites(b: L.LatLngBounds): Zona {
  const [s, w, n, e] = [b.getSouth(), b.getWest(), b.getNorth(), b.getEast()];
  return { type: "Polygon", coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] };
}

/** Mapa con los resultados. Con muchos puntos y poco zoom se agrupan (círculo con la cantidad). */
export default function MapaResultados({ puntos, sinUbic, ocultas, abrir, marcar, pc = false }: {
  puntos: Punto[]; sinUbic: number; ocultas: number; abrir: (id: number) => void; marcar: (id: number) => void;
  /** true = herramientas con el diseño de la PC (El Ojo de Dios) */ pc?: boolean;
}) {
  const div = useRef<HTMLDivElement>(null);
  const mapa = useRef<L.Map | null>(null);
  const capa = useRef<L.LayerGroup | null>(null);
  const zonaCapa = useRef<L.Rectangle | null>(null);
  const [dibujando, setDibujando] = useState(false);
  const esquina = useRef<L.LatLng | null>(null);
  const guia = useRef<L.Rectangle | null>(null);
  const { zona, setZona, filtros, cambiar } = useBusqueda();
  const [zoom, setZoom] = useState(13);
  const ajustado = useRef(false);
  const abrirRef = useRef(abrir);
  const marcarRef = useRef(marcar);
  abrirRef.current = abrir;
  marcarRef.current = marcar;

  useEffect(() => {
    if (!div.current || mapa.current) return;
    const m = L.map(div.current, { preferCanvas: true, zoomControl: true }).setView([-38.7183, -62.2663], 13);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(m);
    capa.current = L.layerGroup().addTo(m);
    m.on("zoomend", () => setZoom(m.getZoom()));
    mapa.current = m;
    setTimeout(() => m.invalidateSize(), 60);
    return () => { m.remove(); mapa.current = null; };
  }, []);

  // dibujar zona: dos toques (sirve en celular y en PC) o arrastrar con el mouse
  useEffect(() => {
    const m = mapa.current;
    if (!m) return;
    if (!dibujando) {
      m.dragging.enable();
      return;
    }
    m.dragging.disable();
    esquina.current = null;
    const fin = (b: L.LatLngBounds) => {
      guia.current?.remove();
      guia.current = null;
      setDibujando(false);
      if (Math.abs(b.getNorth() - b.getSouth()) < 1e-4 || Math.abs(b.getEast() - b.getWest()) < 1e-4) return;
      setZona(zonaDeLimites(b));
    };
    const abajo = (e: L.LeafletMouseEvent) => {
      if (!esquina.current) {
        esquina.current = e.latlng;
        guia.current = L.rectangle(L.latLngBounds(e.latlng, e.latlng), { color: "#16a34a", weight: 3, dashArray: "6,6", fillOpacity: 0.08 }).addTo(m);
      } else {
        fin(L.latLngBounds(esquina.current, e.latlng));
      }
    };
    const mover = (e: L.LeafletMouseEvent) => { if (esquina.current && guia.current) guia.current.setBounds(L.latLngBounds(esquina.current, e.latlng)); };
    const arriba = (e: L.LeafletMouseEvent) => {
      if (esquina.current && e.latlng.distanceTo(esquina.current) > 30) fin(L.latLngBounds(esquina.current, e.latlng));
    };
    m.on("mousedown", abajo);
    m.on("mousemove", mover);
    m.on("mouseup", arriba);
    return () => { m.off("mousedown", abajo); m.off("mousemove", mover); m.off("mouseup", arriba); m.dragging.enable(); };
  }, [dibujando, setZona]);

  useEffect(() => {
    const m = mapa.current;
    if (!m) return;
    zonaCapa.current?.remove();
    zonaCapa.current = null;
    if (zona) {
      const c = zona.coordinates[0];
      const lats = c.map((p) => p[1]), lngs = c.map((p) => p[0]);
      zonaCapa.current = L.rectangle([[Math.min(...lats), Math.min(...lngs)], [Math.max(...lats), Math.max(...lngs)]],
        { color: "#16a34a", weight: 3, fillColor: "#16a34a", fillOpacity: 0.07, interactive: false }).addTo(m);
    }
  }, [zona]);

  useEffect(() => {
    const m = mapa.current, c = capa.current;
    if (!m || !c) return;
    c.clearLayers();
    const agrupar = puntos.length > 1500 && zoom < 14;
    if (agrupar) {
      const t = zoom <= 11 ? 0.04 : zoom <= 12 ? 0.02 : 0.01;
      const celdas = new Map<string, { lat: number; lng: number; n: number }>();
      for (const p of puntos) {
        const k = `${Math.floor(p[1] / t)}|${Math.floor(p[2] / t)}`;
        const g = celdas.get(k) || { lat: 0, lng: 0, n: 0 };
        g.lat += p[1]; g.lng += p[2]; g.n++;
        celdas.set(k, g);
      }
      celdas.forEach((g) => {
        const r = Math.min(26, 10 + Math.sqrt(g.n));
        L.marker([g.lat / g.n, g.lng / g.n], {
          icon: L.divIcon({ className: "", html: `<div style="width:${r * 2}px;height:${r * 2}px;border-radius:50%;background:rgba(20,36,63,.85);color:#fff;display:grid;place-items:center;font:600 12px Archivo Variable,sans-serif;border:2px solid #f2b705">${g.n}</div>`, iconSize: [r * 2, r * 2] }),
        }).on("click", () => m.setView([g.lat / g.n, g.lng / g.n], Math.min(zoom + 2, 16))).addTo(c);
      });
    } else {
      for (const p of puntos) {
        const [id, lat, lng, color, z, precio, moneda, sel] = p;
        const col = zona ? ZCOL[z] || "#94a3b8" : COLOR[color] || COLOR[""];
        const mk = L.circleMarker([lat, lng], { radius: sel ? 8 : 6, weight: sel ? 3 : 1.5, color: sel ? "#f2b705" : "#fff", fillColor: col, fillOpacity: 0.95 });
        mk.bindPopup(() => {
          const d = document.createElement("div");
          d.innerHTML = `<b>${precio ? `${sim(moneda)} ${fmt(precio)}` : "Consultar"}</b>${color ? ` · ${color}` : ""}${z === "dentro" ? " · en la zona" : z === "cerca" ? " · cerca de la zona" : ""}<br>`;
          const ver = document.createElement("button");
          ver.className = pc ? "c-btn" : "btn chico"; ver.textContent = "Ver detalle"; ver.onclick = () => { m.closePopup(); abrirRef.current(id); };
          const mar = document.createElement("button");
          mar.className = pc ? "c-btn c-sec" : "btn sec chico"; mar.style.marginLeft = "6px"; mar.textContent = sel ? "Desmarcar" : "Marcar"; mar.onclick = () => { m.closePopup(); marcarRef.current(id); };
          d.append(ver, mar);
          return d;
        });
        mk.addTo(c);
      }
    }
    if (!ajustado.current && puntos.length) {
      ajustado.current = true;
      // se centra en la mediana (algún aviso con la ubicación mal cargada no aleja todo el mapa)
      const med = (a: number[]) => a.sort((x, y) => x - y)[a.length >> 1];
      if (!zona) m.setView([med(puntos.map((p) => p[1])), med(puntos.map((p) => p[2]))], puntos.length > 300 ? 13 : 14);
    }
  }, [puntos, zoom, zona, pc]);

  const dentro = puntos.filter((p) => p[4] === "dentro").length, cerca = puntos.filter((p) => p[4] === "cerca").length;
  if (pc) {
    return (
      <div>
        <div className="c-maptools">
          <button type="button" className={`c-btn c-mdibujar${dibujando ? " c-on" : ""}`} title="Tocá el botón y arrastrá el mouse sobre el mapa para dibujar el cuadrado" onClick={() => setDibujando(!dibujando)}>▭ Dibujar cuadrado</button>
          <button type="button" className="c-btn c-sec" title="Usa como zona lo que se ve ahora en el mapa" onClick={() => mapa.current && setZona(zonaDeLimites(mapa.current.getBounds()))}>Usar lo que se ve</button>
          <button type="button" className="c-btn c-sec" onClick={() => setZona(null)}>Borrar zona</button>
          <label className="c-f" style={{ margin: 0 }}>Cercanías</label>
          <select style={{ width: "auto" }} value={filtros.margen} onChange={(e) => cambiar("margen", +e.target.value)}>
            <option value={0}>Solo adentro</option><option value={200}>+ 200 m</option><option value={300}>+ 300 m</option><option value={500}>+ 500 m</option><option value={1000}>+ 1 km</option>
          </select>
          <label className="c-chk" style={{ margin: 0 }}><input type="checkbox" checked={filtros.sin_ubic} onChange={(e) => cambiar("sin_ubic", e.target.checked)} /> Incluir avisos sin ubicación</label>
          <span className="c-mute">
            {dibujando ? "Arrastrá el mouse sobre el mapa (o tocá dos esquinas)."
              : zona ? `${dentro} adentro · ${cerca} cerca${ocultas ? ` · ${ocultas} sin ubicación no se muestran` : ""}`
                : `${puntos.length.toLocaleString("es-AR")} en el mapa${sinUbic ? ` · ${sinUbic.toLocaleString("es-AR")} sin ubicación` : ""}`}
          </span>
        </div>
        {zona && <div className="c-mute" style={{ margin: "-2px 0 8px", fontSize: 12.5 }}>
          <span className="c-dot" style={{ background: "#16a34a" }} /><b>Adentro del cuadrado</b> &nbsp; <span className="c-dot" style={{ background: "#f59e0b" }} /><b>Cerca</b> (dentro del margen de cercanía) &nbsp;·&nbsp; Los filtros de la izquierda (precio, dormitorios, etc.) también se aplican.</div>}
        <div ref={div} className="c-map" style={dibujando ? { cursor: "crosshair" } : undefined} role="application" aria-label="Mapa de resultados" />
      </div>
    );
  }
  return (
    <div className={dibujando ? "dibujando" : ""}>
      <div className="mapa-herr">
        <button type="button" className={`btn chico${dibujando ? "" : " sec"}`} onClick={() => setDibujando(!dibujando)}>
          {dibujando ? "Tocá la otra esquina…" : "Dibujar zona"}</button>
        <button type="button" className="btn sec chico" onClick={() => mapa.current && setZona(zonaDeLimites(mapa.current.getBounds()))}>Usar lo que se ve</button>
        {zona && <button type="button" className="btn sec chico" onClick={() => setZona(null)}>Quitar zona</button>}
        <span className="suave chico">
          {dibujando ? "Tocá una esquina y después la opuesta (en la PC también podés arrastrar)."
            : zona ? `${dentro} adentro · ${cerca} cerca${sinUbic ? ` · ${sinUbic} sin ubicación` : ""}${ocultas ? ` · ${ocultas} sin ubicación no se muestran` : ""}`
              : `${puntos.length.toLocaleString("es-AR")} en el mapa${sinUbic ? ` · ${sinUbic.toLocaleString("es-AR")} sin ubicación` : ""}`}
        </span>
      </div>
      <div ref={div} className="mapa" role="application" aria-label="Mapa de resultados" />
    </div>
  );
}
