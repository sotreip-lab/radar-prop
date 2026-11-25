import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useBusqueda } from "../busqueda";
import Detalle from "../componentes/Detalle";
import { IcoFiltros } from "../componentes/Iconos";
import MapaResultados, { type Punto } from "../componentes/MapaResultados";
import PanelFiltros, { bandas } from "../componentes/PanelFiltros";
import Tarjeta from "../componentes/Tarjeta";
import { copiar, COLOR, fmt, PLAT_NOM, sim } from "../formato";
import { useDemorado, useSeleccion } from "../hooks";
import { FILTROS_INICIALES, type Filtros, type Item, type Resultado, type Zona } from "../tipos";
import { useToast } from "../toast";

const ORDENES: [string, string][] = [["", "Semáforo"], ["precio", "Precio"], ["dif", "Diferencia con el presupuesto"], ["usdm2", "Precio por m²"],
  ["detectada", "Fecha de publicación"], ["vsb", "m² contra el barrio"], ["dormitorios", "Dormitorios"], ["sup_cub", "m² cubiertos"]];

function cuerpo(filtros: Filtros, zona: Zona | null, extra: object = {}) {
  return { filtros, zona, ...extra };
}

async function exportarCSV(filtros: Filtros, zona: Zona | null, total: number, toast: (t: string) => void) {
  // Mismo formato de "Exportar" de El Ojo de Dios (separado por ; para Excel en español)
  toast(`Armando la planilla con ${total} propiedades…`);
  const filas: Item[] = [];
  for (let off = 0; off < Math.min(total, 3000); off += 100) {
    const r = await api<Resultado>("/propiedades/buscar", { method: "POST", json: cuerpo(filtros, zona, { offset: off, limite: 100 }) });
    filas.push(...r.items);
  }
  const b = filtros.b, MON = filtros.mon, S = sim(MON);
  const H = ["Semáforo", "Tipo", "Dormitorios", "Zona/Barrio", "Dirección", `Precio ${S}`, `Dif. vs presupuesto ${S}`, "% vs presupuesto", "m² cubiertos", "m² totales",
    `${S}/m² cub.`, `${S}/m² tot.`, "Apto crédito", "Espacio exterior", "Estacionamiento", "Amoblado", "Antigüedad propiedad", "Fuente", "Link", "Estado del link", "Observaciones", "Publicada"];
  const q = (v: unknown) => { const s = v == null ? "" : String(v); return /[;"\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  const num = (v: number | null) => (v == null ? "" : String(Math.round(v * 100) / 100).replace(".", ","));
  const out: unknown[][] = [];
  if (b) { const { loV, hiV, topV } = bandas(b, MON); out.push([`Presupuesto ${S} ${fmt(b)} — Verde entre ${S} ${fmt(loV)} y ${S} ${fmt(hiV)}${topV > hiV ? ` — Violeta hasta ${S} ${fmt(topV)}` : ""} — Amarillo = falta un dato, más barata que el Verde, o hasta +15%`]); }
  out.push(H);
  for (const o of filas) {
    const p = o.moneda === MON && o.precio ? o.precio : null;
    out.push([o.color, o.tipo, o.dormitorios == null ? "no informado" : o.dormitorios === 0 ? "Monoambiente" : o.dormitorios, o.barrio || "no informado", o.direccion,
      p == null ? "no informado" : Math.round(p), p != null && b ? Math.round(p - b) : "", p != null && b ? num((p / b - 1) * 100) + "%" : "", num(o.sup_cub), num(o.sup_tot),
      p && o.sup_cub ? Math.round(p / o.sup_cub) : "", p && o.sup_tot ? Math.round(p / o.sup_tot) : "", o.pago, o.exterior, o.estacionamiento, o.amoblado || "No figura",
      o.antiguedad || "no informado", o.plataformas.map((x) => PLAT_NOM[x.fuente] || x.fuente).join(" + ") + (o.inmobiliaria ? " – " + o.inmobiliaria : ""),
      o.plataformas.map((x) => x.url).join(" | "), o.estado_aviso === "baja" ? "Caído" : "Activo", o.obs, o.pub_titulo]);
  }
  const csv = "﻿" + out.map((f) => f.map(q).join(";")).join("\r\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  a.download = `Asesoria_${b || "sin-presupuesto"}_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  toast(`Exportadas ${filas.length} propiedades`);
}

export default function Buscar({ soloMapa = false }: { soloMapa?: boolean }) {
  const { filtros, zona, cambiar } = useBusqueda();
  const f = useDemorado(filtros, 300);
  const z = useDemorado(zona, 100);
  const [panel, setPanel] = useState(false);
  const [verMapa, setVerMapa] = useState(() => localStorage.getItem("rp_ver_mapa") === "1");
  const [abierto, setAbierto] = useState<number | null>(null);
  const [qg, setQg] = useState(filtros.qg);
  const sel = useSeleccion();
  const toast = useToast();
  const mostrarMapa = soloMapa || verMapa;
  useEffect(() => { localStorage.setItem("rp_ver_mapa", verMapa ? "1" : "0"); }, [verMapa]);
  useEffect(() => { const t = setTimeout(() => cambiar("qg", qg), 250); return () => clearTimeout(t); }, [qg]); // eslint-disable-line react-hooks/exhaustive-deps

  const lista = useInfiniteQuery({
    queryKey: ["buscar", f, z],
    queryFn: ({ pageParam }) => api<Resultado>("/propiedades/buscar", { method: "POST", json: cuerpo(f, z, { offset: pageParam, limite: 50 }) }),
    initialPageParam: 0,
    getNextPageParam: (u) => (u.offset + u.items.length < u.total ? u.offset + u.items.length : undefined),
    enabled: !soloMapa,
    placeholderData: (prev) => prev,
  });
  const mapa = useQuery({
    queryKey: ["mapa", f, z],
    queryFn: () => api<{ puntos: Punto[]; sin_ubicacion: number; sin_ubic_ocultas: number }>("/propiedades/mapa", { method: "POST", json: cuerpo(f, z) }),
    enabled: mostrarMapa,
    placeholderData: (prev) => prev,
  });
  // "Mi historial": la búsqueda se guarda sola cuando la persona deja de tocar los filtros
  const fh = useDemorado(JSON.stringify([filtros, zona]), 2500);
  useEffect(() => {
    const [ff, zz] = JSON.parse(fh);
    if (JSON.stringify([{ ...ff, orden: "", orden_dir: 1 }, zz]) === JSON.stringify([FILTROS_INICIALES, null])) return; // sin filtros: no es una búsqueda
    api("/propiedades/buscar", { method: "POST", json: cuerpo(ff, zz, { limite: 1, registrar: true }) }).catch(() => {});
  }, [fh]);

  const primera = lista.data?.pages[0];
  const items = useMemo(() => lista.data?.pages.flatMap((p) => p.items) || [], [lista.data]);
  const colores = primera?.colores || {};
  const totalColor = Object.values(colores).reduce((a, b) => a + b, 0);
  const plats = primera?.plataformas || {};
  const totPlats = Object.values(plats).reduce((a, b) => a + b, 0);

  return (
    <div className={`buscar${verMapa && !soloMapa ? " con-mapa" : ""}`}>
      <PanelFiltros abierto={panel} cerrar={() => setPanel(false)} />
      <section aria-label="Resultados" style={{ minWidth: 0 }}>
        <div className="buscador-global">
          <input type="search" placeholder="Buscar en toda la base: dirección, número de aviso o link" value={qg} onChange={(e) => setQg(e.target.value)} aria-label="Buscar en toda la base" />
          <button className="btn sec solo-movil" onClick={() => setPanel(true)} aria-label="Abrir filtros"><IcoFiltros className="ico" />Filtros</button>
        </div>
        {filtros.qg && <div className="aviso" style={{ marginTop: 8 }}>Búsqueda en toda la base: se ignoran los filtros. <button className="lnk" onClick={() => setQg("")}>Volver a los filtros</button></div>}

        {!soloMapa && (
          <>
            <div className="resumen-res" style={{ marginTop: 10 }}>
              <span className="total num">{lista.isLoading ? "Buscando…" : `${(primera?.total ?? 0).toLocaleString("es-AR")} propiedades`}</span>
              {filtros.b > 0 && totalColor > 0 && (
                <div className="semaforo-barra" role="img" aria-label={Object.entries(colores).map(([k, n]) => `${k} ${n}`).join(", ")}>
                  {Object.entries(colores).map(([k, n]) => (n ? <span key={k} style={{ width: `${(n / totalColor) * 100}%`, background: COLOR[k] }} /> : null))}
                </div>
              )}
              {filtros.b > 0 && <div className="leyenda-sem">{Object.entries(colores).filter(([k, n]) => n || k !== "Rojo").map(([k, n]) => <span key={k}><span className="punto" style={{ background: COLOR[k] }} />{k} {n}</span>)}</div>}
            </div>
            <div className="plats" role="tablist" aria-label="Plataformas">
              {(["todas", "BBP", "IBB", "ZP"] as const).map((p) => (
                <button key={p} role="tab" className="chip" aria-pressed={filtros.plataforma === p} aria-selected={filtros.plataforma === p} onClick={() => cambiar("plataforma", p)}>
                  {p === "todas" ? "Todas" : PLAT_NOM[p]}<small>{p === "todas" ? totPlats - (primera?.dups || 0) : plats[p] || 0}</small>
                </button>
              ))}
            </div>
            <div className="fila-flex" style={{ marginBottom: 10 }}>
              <label className="campo" style={{ minWidth: 200 }}><span>Ordenar por</span>
                <select value={filtros.orden} onChange={(e) => cambiar("orden", e.target.value)}>{ORDENES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></label>
              {filtros.orden && <div className="seg" style={{ alignSelf: "end" }}><button aria-pressed={filtros.orden_dir > 0} onClick={() => cambiar("orden_dir", 1)}>Menor a mayor</button><button aria-pressed={filtros.orden_dir < 0} onClick={() => cambiar("orden_dir", -1)}>Mayor a menor</button></div>}
              <div className="botones" style={{ alignSelf: "end", marginLeft: "auto" }}>
                <button className="btn sec chico solo-pc" onClick={() => setVerMapa(!verMapa)}>{verMapa ? "Ocultar mapa" : "Ver mapa al lado"}</button>
                <button className="btn sec chico" onClick={() => exportarCSV(f, z, primera?.total || 0, toast).catch((e) => toast(e.message))} disabled={!primera?.total}>Exportar</button>
                <button className="btn sec chico" disabled={!items.length} onClick={() => copiar(items.slice(0, 50).map((x) => x.ficha + "\n" + x.url).join("\n\n")).then(() => toast(`${Math.min(50, items.length)} fichas copiadas`))}>Copiar fichas</button>
              </div>
            </div>
            {lista.isError && <div className="aviso error">{(lista.error as Error).message} <button className="lnk" onClick={() => lista.refetch()}>Reintentar</button></div>}
            {lista.isLoading && <div className="lista">{[1, 2, 3, 4].map((i) => <div key={i} className="esqueleto" style={{ height: 110 }} />)}</div>}
            {primera && !items.length && (
              <div className="vacio"><h3>No hay propiedades con esos filtros</h3>Probá ampliar barrios, elegir dormitorios "O más" o tildar "Incluir los que no informan un dato".</div>
            )}
            <div className="lista">
              {items.map((it) => (
                <Tarjeta key={it.id} it={it} marcada={sel.ids.has(it.id)} conDif={filtros.b > 0} abrir={() => setAbierto(it.id)} marcar={() => sel.alternar(it.id)} />
              ))}
            </div>
            {lista.hasNextPage && (
              <div className="vacio"><button className="btn sec" onClick={() => lista.fetchNextPage()} disabled={lista.isFetchingNextPage}>
                {lista.isFetchingNextPage ? "Cargando…" : `Mostrar más (${(primera!.total - items.length).toLocaleString("es-AR")} restantes)`}</button></div>
            )}
          </>
        )}
        {soloMapa && (
          <div style={{ marginTop: 10 }}>
            {mapa.isError && <div className="aviso error">{(mapa.error as Error).message}</div>}
            <MapaResultados puntos={mapa.data?.puntos || []} sinUbic={mapa.data?.sin_ubicacion || 0} ocultas={mapa.data?.sin_ubic_ocultas || 0} abrir={setAbierto} marcar={sel.alternar} />
          </div>
        )}
      </section>
      {verMapa && !soloMapa && (
        <section className="solo-pc" aria-label="Mapa">
          <MapaResultados puntos={mapa.data?.puntos || []} sinUbic={mapa.data?.sin_ubicacion || 0} ocultas={mapa.data?.sin_ubic_ocultas || 0} abrir={setAbierto} marcar={sel.alternar} />
        </section>
      )}
      {sel.lista.length > 0 && (
        <div className="barra-sel" role="region" aria-label="Selección">
          <b>{sel.lista.length} marcada{sel.lista.length === 1 ? "" : "s"}</b>
          <Link className="btn chico" to="/seleccion">Armar ficha</Link>
          <button className="btn sec chico" onClick={() => cambiar("solo_seleccion", !filtros.solo_seleccion)}>{filtros.solo_seleccion ? "Ver todos" : "Ver solo marcadas"}</button>
          <button className="btn sec chico" onClick={() => sel.vaciar.mutate()}>Desmarcar todas</button>
        </div>
      )}
      {abierto != null && <Detalle id={abierto} cerrar={() => setAbierto(null)} />}
    </div>
  );
}
