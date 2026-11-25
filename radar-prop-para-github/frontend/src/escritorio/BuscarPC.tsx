/* Pantalla de búsqueda en la PC: el mismo diseño de "El Ojo de Dios" (panel a la izquierda, tabla con semáforo,
   detalle desplegable en la fila, barra de selección y mapa), con los datos y la selección de Radar Prop. */
import { useInfiniteQuery, useMutation, useQuery } from "@tanstack/react-query";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { api, claveIdempotencia } from "../api";
import { useBusqueda } from "../busqueda";
import MapaResultados, { type Punto } from "../componentes/MapaResultados";
import { bandas } from "../componentes/PanelFiltros";
import SimCredito from "../componentes/SimCredito";
import { copiar, fmt, fmtK, norm, PLAT_CORTO, PLAT_NOM, sim } from "../formato";
import { useDemorado, useEstado, useSeleccion } from "../hooks";
import { cuerpo, exportarCSV } from "../paginas/Buscar";
import { FILTROS_INICIALES, type Filtros, type Item, type Resultado, type Zona } from "../tipos";
import { useToast } from "../toast";

type Opciones = { operaciones: [string, number][]; ciudades: [string, number][]; tipos: [string, number][]; barrios: [string, number][] };
type SiNo = "" | "si" | "no";

function Seg<T extends string>({ valor, opciones, cambiar, estilo }: { valor: T; opciones: [T, string][]; cambiar: (v: T) => void; estilo?: React.CSSProperties }) {
  return (
    <div className="c-seg" style={estilo}>
      {opciones.map(([v, t]) => <span key={v} className={valor === v ? "c-on" : ""} onClick={() => cambiar(v)}>{t}</span>)}
    </div>
  );
}

function Num({ valor, cambiar, ph, min, max, clase }: { valor: number | null; cambiar: (v: number) => void; ph?: string; min?: number; max?: number; clase?: string }) {
  return <input type="number" className={clase} min={min} max={max} value={valor || ""} placeholder={ph} onChange={(e) => cambiar(+e.target.value || 0)} />;
}

const SINO: [SiNo, string][] = [["", "Indistinto"], ["si", "Sí"], ["no", "No"]];
const ANTIG: [string, string][] = [["", "Todas"], ["0-7", "Menos de 7 días"], ["0-30", "Menos de 30 días"], ["30-180", "1 a 6 meses"], ["180-365", "6 a 12 meses"], ["365-99999", "Más de 1 año"]];

function Rango({ f }: { f: Filtros }) {
  const S = sim(f.mon);
  if (!f.b) return <div className="c-rango">Escribí un presupuesto para ver el semáforo. Sin presupuesto podés usar precio mínimo / máximo.</div>;
  const { loV, hiV, topV } = bandas(f.b, f.mon);
  return (
    <div className="c-rango">
      <span className="c-dot" style={{ background: "var(--verde)" }} />Verde: {S} {fmt(loV)} a {fmt(hiV)}{f.mon === "ARS" ? " (±5%)" : ""}<br />
      {topV > hiV ? <><span className="c-dot" style={{ background: "var(--violeta)" }} />Violeta: {S} {fmt(hiV + 1)} a {fmt(topV)}<br /></> : <><span className="c-mute">Violeta: no aplica (7% &lt; USD 5.000)</span><br /></>}
      <span className="c-dot" style={{ background: "var(--amarillo)" }} />Amarillo: hasta {S} {fmt(f.b * 1.15)}, más baratas desde {fmt(f.b * (1 - f.pct_abajo / 100))}, o falta un dato
      {f.rojas && <><br /><span className="c-dot" style={{ background: "var(--rojo)" }} />Rojo: hasta {S} {fmt(f.b * 1.3)}</>}
    </div>
  );
}

function Panel({ mapa, cliente, setCliente }: { mapa: () => void; cliente: string; setCliente: (v: string) => void }) {
  const { filtros: f, cambiar, setFiltros, zona, setZona } = useBusqueda();
  const [qBarrio, setQBarrio] = useState("");
  const [verTipos, setVerTipos] = useState(false);
  const op = useQuery({
    queryKey: ["opciones", f.oper, f.ciudad],
    queryFn: () => api<Opciones>(`/propiedades/opciones?operacion=${encodeURIComponent(f.oper)}&ciudad=${encodeURIComponent(f.ciudad)}`),
    staleTime: 300_000,
  });
  const S = sim(f.mon);
  const tipos = op.data?.tipos || [];
  const visTipos = verTipos ? tipos : tipos.filter(([k], i) => i < 8 || f.tipos.includes(k));
  const q = norm(qBarrio);
  const barrios = (op.data?.barrios || []).filter(([k]) => !/^\d/.test(k) && (!q || norm(k).includes(q))).sort((a, b) => a[0].localeCompare(b[0]));
  const antig = ANTIG.find(([v]) => v === `${f.dmin ?? ""}-${f.dmax ?? ""}` || (v === "365-99999" && f.dmin === 365 && f.dmax == null))?.[0] ?? (f.dmin == null && f.dmax == null ? "" : "x");
  const alternar = (k: "tipos" | "barrios", v: string) => cambiar(k, f[k].includes(v) ? f[k].filter((x) => x !== v) : [...f[k], v]);
  const limpiar = () => setFiltros({ ...FILTROS_INICIALES, oper: f.oper, ciudad: f.ciudad, mon: /alquiler/i.test(f.oper) ? "ARS" : "USD", plataforma: f.plataforma });
  return (
    <aside>
      <h3>Pedido del cliente</h3>
      <label className="c-f">Cliente (para la planilla)</label>
      <input type="text" placeholder="Ej: Rosa María" value={cliente} onChange={(e) => setCliente(e.target.value)} />
      <Seg valor={f.mon} opciones={[["USD", "Dólares (USD)"], ["ARS", "Pesos ($)"]]} cambiar={(v) => cambiar("mon", v)} estilo={{ marginTop: 6 }} />
      <label className="c-f">Presupuesto {f.mon === "ARS" ? "en pesos ($)" : "USD"}</label>
      <Num clase="c-big" valor={f.b} cambiar={(v) => cambiar("b", v)} ph={f.mon === "ARS" ? "650000" : "160000"} />
      <Rango f={f} />
      <div className="c-row2" style={{ marginTop: 6 }}>
        <div><label className="c-f">Más baratas hasta −%</label><input type="number" min={0} max={90} value={f.pct_abajo} onChange={(e) => cambiar("pct_abajo", +e.target.value || 0)} /></div>
        <div><label className="c-f">Mostrar rojas (+15%)</label><select value={f.rojas ? "1" : "0"} onChange={(e) => cambiar("rojas", e.target.value === "1")}><option value="0">No</option><option value="1">Sí, hasta +30%</option></select></div>
      </div>
      <div className="c-row2">
        <div><label className="c-f">Precio mín. {S}</label><Num valor={f.pmin} cambiar={(v) => cambiar("pmin", v)} /></div>
        <div><label className="c-f">Precio máx. {S}</label><Num valor={f.pmax} cambiar={(v) => cambiar("pmax", v)} /></div>
      </div>

      <h3>Qué busca</h3>
      <div className="c-row2">
        <div><label className="c-f">Operación</label>
          <select value={f.oper} onChange={(e) => setFiltros((x) => ({ ...x, oper: e.target.value, tipos: [], barrios: [], mon: /alquiler/i.test(e.target.value) ? "ARS" : "USD" }))}>
            {(op.data?.operaciones || [[f.oper, 0]]).map(([k, n]) => <option key={k} value={k}>{k}{n ? ` (${n})` : ""}</option>)}
          </select></div>
        <div><label className="c-f">Ciudad</label>
          <select value={f.ciudad} onChange={(e) => setFiltros((x) => ({ ...x, ciudad: e.target.value, barrios: [] }))}>
            <option value="">Todas</option>
            {(op.data?.ciudades || [[f.ciudad, 0]]).filter(([k]) => k).map(([k, n]) => <option key={k} value={k}>{k}{n ? ` (${n})` : ""}</option>)}
          </select></div>
      </div>
      <label className="c-f">Tipo</label>
      <div className="c-chips">
        {visTipos.map(([k, n]) => <span key={k} className={`c-chip${f.tipos.includes(k) ? " c-on" : ""}`} onClick={() => alternar("tipos", k)}>{k}<small>{n}</small></span>)}
        {tipos.length > 8 && <span className="c-chip c-more" onClick={() => setVerTipos(!verTipos)}>{verTipos ? "Ver menos" : `Ver todos (${tipos.length})`}</span>}
      </div>
      <label className="c-f">Dormitorios</label>
      <Seg valor={f.dorm} opciones={[["", "Todos"], ["0", "Mono"], ["1", "1"], ["2", "2"], ["3", "3"], ["4", "4"], ["5", "5+"]]} cambiar={(v) => cambiar("dorm", v)} />
      <Seg valor={f.dorm_modo} opciones={[["exacto", "Exacto"], ["min", "O más"]]} cambiar={(v) => cambiar("dorm_modo", v)} estilo={{ marginTop: 4 }} />
      <div className="c-row2">
        <div><label className="c-f">Baños mín.</label><Num valor={f.banos} cambiar={(v) => cambiar("banos", v)} min={0} /></div>
        <div><label className="c-f">m² cub. mín.</label><Num valor={f.supmin} cambiar={(v) => cambiar("supmin", v)} min={0} /></div>
      </div>
      <label className="c-f">Patio</label><Seg valor={f.patio} opciones={SINO} cambiar={(v) => cambiar("patio", v)} />
      <label className="c-f">Cochera</label><Seg valor={f.cochera} opciones={SINO} cambiar={(v) => cambiar("cochera", v)} />
      <label className="c-f">Balcón / terraza</label><Seg valor={f.balcon} opciones={SINO} cambiar={(v) => cambiar("balcon", v)} />
      <label className="c-f">Quincho / parrilla</label><Seg valor={f.parrilla} opciones={SINO} cambiar={(v) => cambiar("parrilla", v)} />
      <label className="c-f">Pileta</label><Seg valor={f.pileta} opciones={SINO} cambiar={(v) => cambiar("pileta", v)} />
      <label className="c-f">Amoblado</label><Seg valor={f.amoblado} opciones={SINO} cambiar={(v) => cambiar("amoblado", v)} />
      <label className="c-f">Apto crédito</label><Seg valor={f.credito} opciones={[["", "No lo pidió"], ["si", "Lo necesita"]]} cambiar={(v) => cambiar("credito", v)} />
      <label className="c-f" title="Cuota inicial estimada con la línea de crédito más barata para la que califica cada propiedad (BCRA), a 20 años">Cuota del crédito hasta ($ por mes)</label>
      <Num valor={f.cuota_max} cambiar={(v) => cambiar("cuota_max", v)} min={0} ph="ej. 900000" />
      <label className="c-chk"><input type="checkbox" checked={f.estrenar} onChange={(e) => cambiar("estrenar", e.target.checked)} /> Solo a estrenar / en construcción</label>

      <h3>Zona</h3>
      <button className="c-btn" style={{ width: "100%", marginBottom: 6 }} onClick={mapa}>▭ Dibujar zona en el mapa</button>
      <div className="c-zona-activa" style={{ display: zona ? "block" : "none" }}>Zona del mapa activa · <a href="#" onClick={(e) => { e.preventDefault(); setZona(null); }}>quitar</a></div>
      <label className="c-f">o por barrio (opcional: si no tildás ninguno, entran todos)</label>
      <input type="text" placeholder="Filtrar barrios…" value={qBarrio} onChange={(e) => setQBarrio(e.target.value)} />
      <div className="c-barrios">
        {barrios.length ? barrios.map(([k, n]) => (
          <label key={k} className="c-chk"><input type="checkbox" checked={f.barrios.includes(k)} onChange={() => alternar("barrios", k)} /> {k} <span className="c-mute">({n})</span></label>
        )) : <div className="c-mute">Sin barrios</div>}
      </div>
      <div style={{ display: "flex", gap: 6, marginTop: 4 }}><span className="c-chip" onClick={() => cambiar("barrios", [])}>Ninguno = todos</span></div>
      <label className="c-chk"><input type="checkbox" checked={f.sin_barrio} onChange={(e) => cambiar("sin_barrio", e.target.checked)} /> Incluir avisos sin barrio informado</label>

      <h3>Otros</h3>
      <label className="c-f">Palabra clave (título, dirección, descripción)</label>
      <input type="text" placeholder="Ej: quincho, esquina, Alem" value={f.kw} onChange={(e) => cambiar("kw", e.target.value)} />
      <label className="c-chk"><input type="checkbox" checked={f.sin_dato} onChange={(e) => cambiar("sin_dato", e.target.checked)} /> <span>Incluir los que <b>no informan</b> un dato pedido (van en Amarillo). Recomendado: así no se pierde ninguna.</span></label>
      <label className="c-chk"><input type="checkbox" checked={f.excl} onChange={(e) => cambiar("excl", e.target.checked)} /> <span>Excluir RE/MAX, Grupo Maidana y Gastón Etherra</span></label>
      <label className="c-chk"><input type="checkbox" checked={f.bajas} onChange={(e) => cambiar("bajas", e.target.checked)} /> Mostrar avisos dados de baja</label>
      <label className="c-f">Publicadas en las últimas</label>
      <select value={f.nuevas_horas || ""} onChange={(e) => cambiar("nuevas_horas", +e.target.value || 0)}>
        <option value="">Cualquier fecha</option><option value="1">1 hora</option><option value="3">3 horas</option><option value="6">6 horas</option><option value="12">12 horas</option>
        <option value="24">24 horas</option><option value="72">3 días</option><option value="168">7 días</option><option value="720">30 días</option>
      </select>
      <label className="c-f">Antigüedad de la publicación</label>
      <Seg valor={antig} opciones={ANTIG} estilo={{ flexWrap: "wrap" }} cambiar={(v) => { const [a, b] = v ? v.split("-") : ["", ""]; setFiltros((x) => ({ ...x, dmin: a === "" ? null : +a, dmax: b === "" || b === "99999" ? null : +b })); }} />
      <div className="c-row2">
        <div><label className="c-f">Publicada hace más de (días)</label><input type="number" min={0} value={f.dmin ?? ""} onChange={(e) => cambiar("dmin", e.target.value === "" ? null : +e.target.value)} /></div>
        <div><label className="c-f">y menos de (días)</label><input type="number" min={0} value={f.dmax ?? ""} onChange={(e) => cambiar("dmax", e.target.value === "" ? null : +e.target.value)} /></div>
      </div>
      <div className="c-row2">
        <div><label className="c-f">Precio por m² hasta {S}</label><Num valor={f.m2max} cambiar={(v) => cambiar("m2max", v)} min={0} /></div>
        <div><label className="c-f">Bajó al menos (%)</label><Num valor={f.bajo_min} cambiar={(v) => cambiar("bajo_min", v)} min={0} max={90} /></div>
      </div>
      <label className="c-chk"><input type="checkbox" checked={f.bajo_precio} onChange={(e) => cambiar("bajo_precio", e.target.checked)} /> Solo las que bajaron de precio</label>
      <label className="c-chk"><input type="checkbox" checked={f.margen_neg} onChange={(e) => cambiar("margen_neg", e.target.checked)} /> <span>Solo con <b>margen para negociar</b> (más de 6 meses publicada, bajó de precio o la publican más barata en otro lado)</span></label>
      <div style={{ marginTop: 12 }}><button className="c-btn c-sec" style={{ width: "100%" }} onClick={limpiar}>Limpiar filtros</button></div>
    </aside>
  );
}

type D = Record<string, unknown> & {
  id: number; titulo: string; operacion: string; ciudad: string | null; banos: number | null; estado: string | null; pileta: string | null; parrilla: string | null;
  amoblado: string | null; pub_titulo: string; ultima_verif: string; fecha_baja: string | null; ficha: string; descripcion: string; ia_resumen: string | null;
  alertas_ia: string[]; negociar: [string, string][]; margen: string; credito_posible: boolean; moneda: string | null; precio: number | null;
  direccion: string | null; apto_credito: string | null; estado_aviso: string; id_externo: string; fuente: string;
};

function DetalleFila({ id, dolar, toast }: { id: number; dolar: number; toast: (t: string) => void }) {
  const q = useQuery({ queryKey: ["propiedad", id], queryFn: () => api<D>(`/propiedades/${id}`) });
  const d = q.data;
  if (!d) return <tr className="c-det"><td colSpan={20}>{q.isError ? (q.error as Error).message : "Cargando…"}</td></tr>;
  const pp = d.moneda === "ARS" ? ((d.precio || 0) >= 15e6 ? d.precio : null) : d.precio && dolar ? d.precio * dolar : null;
  const kv: [string, unknown][] = [["Título", d.titulo], ["Operación", d.operacion], ["Ciudad", d.ciudad], ["Baños", d.banos], ["Estado", d.estado], ["Pileta", d.pileta],
    ["Parrilla/quincho", d.parrilla], ["Amoblado", d.amoblado || "No figura"], ["Publicación", d.pub_titulo], ["Última verificación", d.ultima_verif],
    ["Dada de baja", d.fecha_baja || "—"], ["ID", d.fuente === "BBP" ? d.id_externo : d.id]];
  const m = d.margen === "alto" ? <> · <b>margen de negociación ALTO</b></> : d.margen === "medio" ? " · margen de negociación medio" : "";
  return (
    <tr className="c-det"><td colSpan={20}>
      {d.estado_aviso === "activo" && d.negociar?.length > 0 && (
        <div className="c-neg-box"><div style={{ fontWeight: 700, marginBottom: 2 }}>Para negociar y asesorar{m}</div>
          {d.negociar.map(([k, v]) => <div key={k}><b>{k}:</b> {v}</div>)}</div>
      )}
      {d.credito_posible && pp ? (
        <div className="c-neg-box c-cred-box" onClick={(e) => e.stopPropagation()}>
          <SimCredito pc precioPesos={pp} moneda={d.moneda} titulo={d.titulo} direccion={d.direccion} aptoCredito={d.apto_credito} />
        </div>
      ) : null}
      <div style={{ display: "flex", gap: 14, alignItems: "flex-start", marginBottom: 8 }}>
        <div className="c-ficha">{d.ficha}</div>
        <button className="c-btn" onClick={(e) => { e.stopPropagation(); copiar(d.ficha).then(() => toast("Ficha copiada")); }}>Copiar ficha WhatsApp</button>
      </div>
      <div className="c-grid">{kv.map(([k, v]) => <div key={k}><span className="c-mute">{k}:</span> {String(v ?? "")}</div>)}</div>
      {d.ia_resumen && <div className="c-ia"><b>Análisis IA:</b> {d.ia_resumen}{d.alertas_ia.length ? <><br /><b>Alertas:</b> {d.alertas_ia.join(" · ")}</> : null}</div>}
      <pre>{d.descripcion}</pre>
      <div className="c-mute" style={{ marginTop: 6 }}>* = dato leído de la descripción · <sup>IA</sup> = dato analizado por IA (no figura en los campos oficiales de la ficha).</div>
    </td></tr>
  );
}

function Fila({ it, i, abierta, marcada, alternarAbierta, marcar, conPresu, toast }: {
  it: Item; i: number; abierta: boolean; marcada: boolean; alternarAbierta: () => void; marcar: (v: boolean) => void; conPresu: boolean; toast: (t: string) => void;
}) {
  const S = sim(it.moneda);
  const pub = it.pub_corta.match(/^(≤|≈|antes)\s?(.*)$/);
  return (
    <tr className={`c-r${it.color ? " c-" + it.color : ""}${marcada ? " c-sel" : ""}`} data-i={i} data-id={it.id} onClick={alternarAbierta} aria-expanded={abierta}>
      <td className="c-ck" onClick={(e) => e.stopPropagation()}><input type="checkbox" className="c-ckp" checked={marcada} onChange={(e) => marcar(e.target.checked)} aria-label="Seleccionar" /></td>
      <td className="c-pl">{it.plataformas.map((x) => <span key={x.fuente + x.id} className={`c-ptag c-${x.fuente}`} title={PLAT_NOM[x.fuente] || x.fuente}>{PLAT_CORTO[x.fuente] || x.fuente}</span>)}</td>
      <td>{it.color || "—"}
        {it.estado_aviso === "baja" && <span className="c-tag c-baja">BAJA</span>}
        {it.nueva && <span className="c-tag">NUEVA</span>}
        {it.bajo && <span className="c-tag c-precio">BAJÓ</span>}
        {it.otro_precio?.length ? <span className="c-tag c-otro" title={it.otro_precio.map((x) => `${PLAT_CORTO[x.fuente] || x.fuente} · ${x.inmobiliaria || "s/d"}: ${sim(x.moneda)} ${fmt(x.precio)}`).join("\n")}>OTRO PRECIO</span> : null}
        {it.zona === "dentro" ? <span className="c-tag" style={{ background: "#16a34a" }}>EN ZONA</span> : it.zona === "cerca" ? <span className="c-tag" style={{ background: "#f59e0b" }}>CERCA</span> : null}
      </td>
      <td className="c-pub" title={it.pub_titulo}>
        {pub && pub[1] !== "antes" ? <><span className="c-mute">{pub[1]}</span> {pub[2]}</> : pub ? <span className="c-mute">{it.pub_corta}</span> : it.pub_corta}
        {it.estado_aviso === "activo" && (it.dias != null || it.bajas > 0) && (
          <small className="c-l2" style={it.margen === "alto" ? { color: "#0f766e", fontWeight: 700 } : undefined}>
            {[it.dias != null ? `${it.dias} días` : "", it.bajas ? `bajó ${it.bajas}×${it.baja_pct >= 1 ? ` (−${Math.round(it.baja_pct)}%)` : ""}` : ""].filter(Boolean).join(" · ")}
          </small>
        )}
      </td>
      <td>{it.tipo}</td>
      <td className="c-n">{it.dormitorios == null ? <span className="c-mute">s/d</span> : it.dormitorios === 0 ? "Mono" : it.dormitorios}{it.dorm_fuente === "descripción" ? "*" : it.dorm_fuente === "IA" ? <sup>IA</sup> : ""}</td>
      <td>{it.barrio || <span className="c-mute">s/d</span>}</td>
      <td className="c-dir">{it.direccion}</td>
      <td className="c-n">
        {it.moneda === "ARS" ? "$ " : ""}{fmt(it.precio) || (it.precio_falso ? <span className="c-mute" title={`Publicado como ${fmt(it.precio_falso)}: es un precio de relleno, no se usa en comparativas`}>no real</span> : <span className="c-mute">s/d</span>)}
        {it.cuota && <small className="c-l2 c-cuota" title={`Crédito ${it.cuota.banco} · ${it.cuota.anios} años · financia ${it.cuota.ltv}% ($ ${fmt(it.cuota.prestamo)}) · ingreso mínimo ≈ $ ${fmt(it.cuota.ingreso)}`}>cuota ≈ $ {fmtK(it.cuota.cuota)}/mes</small>}
        {it.renta && <small className="c-l2 c-renta" title={`Alquiler estimado $ ${fmt(it.renta.alq)}/mes (${it.renta.n} alquileres comparables, ${it.renta.nivel})`}>renta ≈ {it.renta.pct.toFixed(1).replace(".", ",")}%</small>}
      </td>
      <td className="c-n">{conPresu && it.dif != null ? `${it.dif > 0 ? "+" : ""}${fmt(it.dif)}` : ""}</td>
      <td className="c-n">{fmt(it.sup_cub) || "–"} / {fmt(it.sup_tot) || "–"}</td>
      <td className="c-n">{fmt(it.usdm2)}{it.vsb && <small className={`c-l2 ${it.vsb.pct > 5 ? "c-caro" : it.vsb.pct < -5 ? "c-barato" : ""}`} title={`Mediana ${S} ${fmt(it.vsb.med)}/m² · ${it.vsb.n} ${it.tipo || ""} en ${it.vsb.donde}`}>{it.vsb.pct > 0 ? "+" : ""}{Math.round(it.vsb.pct)}% {it.vsb.nivel}</small>}</td>
      <td className="c-ext">{it.exterior && it.exterior !== "No figura" ? it.exterior : <span className="c-mute">No figura</span>}</td>
      <td>{(it.estacionamiento || "").startsWith("Sí") ? "Sí" : <span className="c-mute">No figura</span>}</td>
      <td>{!it.amoblado || it.amoblado === "No figura" ? <span className="c-mute">No figura</span> : it.amoblado === "Amoblado" ? <b>Sí</b> : it.amoblado === "Sin amoblar" ? "No" : it.amoblado}</td>
      <td>{it.pago === "Apto crédito" ? <b>Apto crédito</b> : it.pago === "Contado" ? "Contado (no apto)" : "Contado"}</td>
      <td>{it.antiguedad}</td>
      <td>{it.inmobiliaria}</td>
      <td style={{ whiteSpace: "nowrap" }}>
        {it.plataformas.length === 1 ? <a href={it.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>Ver</a>
          : it.plataformas.map((x, k) => <Fragment key={x.fuente + x.id}>{k ? " / " : ""}<a href={x.url} target="_blank" rel="noreferrer" title={`Ver en ${PLAT_NOM[x.fuente] || x.fuente}`} onClick={(e) => e.stopPropagation()}>{PLAT_CORTO[x.fuente] || x.fuente}</a></Fragment>)}
        {" · "}<a href="#" title="Copiar ficha para WhatsApp" onClick={(e) => { e.preventDefault(); e.stopPropagation(); copiar(it.ficha).then(() => toast("Ficha copiada")); }}>Ficha</a>
      </td>
      <td className="c-obs">{it.obs}</td>
    </tr>
  );
}

function PanelModal({ ids, cliente, cerrar }: { ids: number[]; cliente: string; cerrar: () => void }) {
  type PanelCli = { id: string; name: string; estado?: string };
  const q = useQuery({ queryKey: ["panel-clientes"], queryFn: () => api<{ clients: PanelCli[] }>("/panel/clientes"), retry: false });
  const [cli, setCli] = useState("");
  const [lbl, setLbl] = useState(`${cliente ? cliente + " · " : ""}${ids.length} propiedad${ids.length === 1 ? "" : "es"}`);
  const clave = useRef(claveIdempotencia());
  const enviar = useMutation({ mutationFn: () => api<{ enviadas: number; no_disponibles: number; panel: string }>("/panel/enviar", { method: "POST", json: { ids, cliente_panel: cli, etiqueta: lbl, clave_idempotencia: clave.current } }) });
  const msg = q.isError ? `No pude conectar con el panel: ${(q.error as Error).message}` : enviar.isPending ? `Leyendo ${ids.length} propiedades en vivo y mandándolas…`
    : enviar.isError ? `No se pudo: ${(enviar.error as Error).message}` : enviar.data ? `Listo: ${enviar.data.enviadas} en el borrador.${enviar.data.no_disponibles ? ` ${enviar.data.no_disponibles} ya no están publicadas.` : ""}` : "";
  return (
    <div className="c-modal" style={{ display: "flex" }} onClick={cerrar}><div className="c-box" onClick={(e) => e.stopPropagation()}>
      <h2>Mandar al panel de fichas</h2>
      <p>Las propiedades marcadas llegan al panel como <b>borrador</b>, con datos, fotos y link. Abrís el borrador en el panel, revisás y publicás la ficha como siempre.</p>
      <label className="c-f">Cliente</label>
      <select style={{ width: "100%" }} value={cli} onChange={(e) => setCli(e.target.value)}>
        <option value="">{q.isLoading ? "Cargando clientes…" : "Sin cliente (lo elijo en el panel)"}</option>
        {q.data?.clients.filter((c) => c.estado !== "archivado").map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
      </select>
      <label className="c-f">Nombre del borrador</label><input type="text" style={{ width: "100%" }} value={lbl} onChange={(e) => setLbl(e.target.value)} />
      {msg && <div className="c-rango">{msg} {enviar.data && <a href={enviar.data.panel} target="_blank" rel="noreferrer">Abrir el panel</a>}</div>}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 12 }}>
        <button className="c-btn c-sec" onClick={cerrar}>{enviar.data ? "Cerrar" : "Cancelar"}</button>
        <button className="c-btn" disabled={!q.data || enviar.isPending || !!enviar.data} onClick={() => enviar.mutate()}>Mandar</button>
      </div>
    </div></div>
  );
}

async function todos(f: Filtros, z: Zona | null, total: number) {
  const out: Item[] = [];
  for (let off = 0; off < Math.min(total, 3000); off += 100) {
    const r = await api<Resultado>("/propiedades/buscar", { method: "POST", json: cuerpo(f, z, { offset: off, limite: 100 }) });
    out.push(...r.items);
  }
  return out;
}

const COLS: [string, string][] = [["fuente", "Plataforma"], ["color", "Semáforo"], ["detectada", "Publicada"], ["tipo", "Tipo"], ["dormitorios", "Dorm."], ["barrio", "Barrio"],
  ["direccion", "Dirección"], ["precio", "Precio"], ["dif", "Dif. vs presup."], ["sup_cub", "m² cub/tot"], ["usdm2", "Precio/m²"], ["", "Espacio exterior"], ["", "Estacionam."],
  ["", "Amoblado"], ["", "Pago"], ["antiguedad", "Antigüedad"], ["inmobiliaria", "Inmobiliaria"], ["", "Link"], ["", "Observaciones"]];

export default function BuscarPC() {
  const { filtros, zona, cambiar } = useBusqueda();
  const f = useDemorado(filtros, 200);
  const z = useDemorado(zona, 100);
  const sel = useSeleccion();
  const toast = useToast();
  const est = useEstado();
  const dolar = est.data?.dolar?.valor || 0;
  const [cliente, setClienteE] = useState(() => sessionStorage.getItem("rp_cliente") || "");
  const setCliente = (v: string) => { setClienteE(v); try { sessionStorage.setItem("rp_cliente", v); } catch { /* sin almacenamiento */ } };
  const [qg, setQg] = useState(filtros.qg);
  const [abiertas, setAbiertas] = useState<Set<number>>(new Set());
  const [mapaOn, setMapaOn] = useState(false);
  const [panel, setPanel] = useState(false);
  const mapaRef = useRef<HTMLDivElement>(null);
  useEffect(() => { const t = setTimeout(() => cambiar("qg", qg), 250); return () => clearTimeout(t); }, [qg]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (filtros.qg !== qg && !filtros.qg) setQg(""); }, [filtros.qg]); // eslint-disable-line react-hooks/exhaustive-deps

  const lista = useInfiniteQuery({
    queryKey: ["buscar", f, z, "pc"],
    queryFn: ({ pageParam }) => api<Resultado>("/propiedades/buscar", { method: "POST", json: cuerpo(f, z, { offset: pageParam, limite: 100 }) }),
    initialPageParam: 0,
    getNextPageParam: (u) => (u.offset + u.items.length < u.total ? u.offset + u.items.length : undefined),
    placeholderData: (prev) => prev,
  });
  const mapa = useQuery({
    queryKey: ["mapa", f, z],
    queryFn: () => api<{ puntos: Punto[]; sin_ubicacion: number; sin_ubic_ocultas: number }>("/propiedades/mapa", { method: "POST", json: cuerpo(f, z) }),
    enabled: mapaOn,
    placeholderData: (prev) => prev,
  });
  // la búsqueda queda en "Mi historial" cuando la persona deja de tocar los filtros
  const fh = useDemorado(JSON.stringify([filtros, zona]), 2500);
  useEffect(() => {
    const [ff, zz] = JSON.parse(fh);
    if (JSON.stringify([{ ...ff, orden: "", orden_dir: 1 }, zz]) === JSON.stringify([FILTROS_INICIALES, null])) return;
    api("/propiedades/buscar", { method: "POST", json: cuerpo(ff, zz, { limite: 1, registrar: true }) }).catch(() => {});
  }, [fh]);

  const primera = lista.data?.pages[0];
  const items = useMemo(() => lista.data?.pages.flatMap((p) => p.items) || [], [lista.data]);
  const total = primera?.total ?? 0;
  const plats = primera?.plataformas || {};
  const totPlats = Object.values(plats).reduce((a, b) => a + b, 0);
  const dups = primera?.dups || 0;
  const colores = primera?.colores || {};
  const lote = useQuery({
    queryKey: ["lote", sel.lista],
    queryFn: () => api<Item[]>("/propiedades/lote", { method: "POST", json: { ids: sel.lista } }),
    enabled: sel.lista.length > 0,
  });
  const textoFichas = () => (lote.data || []).map((o, i) => `*${i + 1}.*\n` + o.ficha).join("\n\n");
  const ficha = useMutation({
    mutationFn: (cli: string) => api<{ enlace: string }>("/fichas", { method: "POST", json: { ids: sel.lista.slice(0, 40), tipo: "web", cliente: cli, clave_idempotencia: claveIdempotencia() } }),
  });

  const alternarAbierta = (id: number) => setAbiertas((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const ordenar = (k: string) => {
    if (!k) return;
    if (filtros.orden !== k) { cambiar("orden", k); cambiar("orden_dir", 1); }
    else if (filtros.orden_dir === 1) cambiar("orden_dir", -1);
    else { cambiar("orden", ""); cambiar("orden_dir", 1); }
  };
  async function generarFicha() {
    let cli = cliente.trim();
    if (!cli) cli = prompt("¿Para qué cliente es la ficha? (opcional)") || "";
    if (!sel.lista.length) return toast("No hay propiedades seleccionadas");
    if (sel.lista.length > 40) return toast("Máximo 40 propiedades por ficha");
    toast("Armando la ficha con los datos y fotos del momento…");
    const v = window.open("", "_blank");
    try {
      const r = await ficha.mutateAsync(cli);
      const url = `${location.origin}${r.enlace}`;
      if (v) v.location.href = url; else location.href = url;
      copiar(url);
    } catch (e) { v?.close(); toast((e as Error).message); }
  }
  const abrirMapa = (dibujar = false) => {
    setMapaOn(true);
    setTimeout(() => { mapaRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }); if (dibujar) mapaRef.current?.querySelector<HTMLButtonElement>(".c-mdibujar")?.click(); }, 200);
  };
  const todasVisibles = items.length > 0 && items.every((x) => sel.ids.has(x.id));

  return (
    <main>
      <Panel mapa={() => abrirMapa(true)} cliente={cliente} setCliente={setCliente} />
      <section className="c-res">
        <div className={`c-qbar${qg ? " c-on" : ""}`}>
          <span style={{ fontSize: 17 }}>🔎</span>
          <input value={qg} onChange={(e) => setQg(e.target.value)} onKeyDown={(e) => e.key === "Escape" && setQg("")} autoComplete="off"
            placeholder="Buscar en toda la base: dirección, barrio, inmobiliaria, ID o pegá un link de cualquier plataforma" aria-label="Buscar en toda la base" />
          {qg && <span className="c-x" title="Borrar búsqueda" onClick={() => setQg("")}>✕</span>}
        </div>
        <div className="c-plats">
          {(["todas", "BBP", "IBB", "ZP"] as const).map((p) => {
            const n = p === "todas" ? totPlats - dups : plats[p] || 0;
            return (
              <div key={p} className={`c-plat${filtros.plataforma === p ? " c-on" : ""}`} onClick={() => cambiar("plataforma", p)}>
                {p !== "todas" && <span className={`c-ptag c-${p}`}>{PLAT_CORTO[p]}</span>}{p === "todas" ? "Todas" : PLAT_NOM[p]}
                <span className="c-c">{n.toLocaleString("es-AR")}{p === "todas" && dups ? ` · ${dups} en 2 plataformas` : ""}</span>
              </div>
            );
          })}
        </div>
        <div className="c-bar">
          <span className="c-count">{lista.isLoading ? "Buscando…" : `${total.toLocaleString("es-AR")} propiedades`}
            {filtros.qg && <> <span className="c-tag c-neg">búsqueda en toda la base</span> <a href="#" onClick={(e) => { e.preventDefault(); setQg(""); }}>volver a los filtros</a></>}
            {filtros.solo_seleccion && <> <span className="c-tag c-neg">solo las seleccionadas</span></>}
          </span>
          <span>{filtros.b > 0 && Object.entries(colores).filter(([k, n]) => n || k !== "Rojo").map(([k, n]) => <Fragment key={k}><span className="c-pill" style={{ background: `var(--${k.toLowerCase()})` }}>{k} {n}</span> </Fragment>)}</span>
          <span className="c-sp" />
          <button className={`c-btn c-sec${mapaOn ? " c-on" : ""}`} title="Ver los resultados en el mapa y buscar por zona" onClick={() => setMapaOn(!mapaOn)}>Mapa</button>
          <button className="c-btn c-sec" title="Copia los links de los resultados" onClick={async () => { const t = await todos(f, z, total); copiar(t.map((x) => x.url).join("\n")).then(() => toast(`${t.length} links copiados`)); }}>Copiar links</button>
          <button className="c-btn c-sec" title="Copia las fichas para WhatsApp de los resultados (con su link)" onClick={() => { if (!items.length) return toast("No hay resultados"); const n = Math.min(items.length, 50); copiar(items.slice(0, n).map((x, i) => `*${i + 1}.*\n${x.ficha}\n${x.url}`).join("\n\n")).then(() => toast(`${n} fichas copiadas`)); }}>Copiar fichas WhatsApp</button>
          <button className="c-btn" title="Descarga la planilla con los resultados" onClick={() => exportarCSV(f, z, total, toast).catch((e) => toast(e.message))}>Exportar a Excel</button>
        </div>
        {sel.lista.length > 0 && (
          <div className="c-selbar" style={{ display: "flex" }}>
            <b>{sel.lista.length} seleccionada{sel.lista.length === 1 ? "" : "s"}</b>
            <button className="c-btn c-y" title="Arma una página para el cliente con fotos, datos y botón de WhatsApp" onClick={generarFicha} disabled={ficha.isPending}>Generar ficha para el cliente</button>
            <button className="c-btn" title="Manda las seleccionadas al panel de fichas como borrador" onClick={() => setPanel(true)}>Mandar al panel</button>
            <button className="c-btn c-sec" onClick={() => copiar(textoFichas()).then(() => toast(`${lote.data?.length || 0} fichas copiadas: pegalas en WhatsApp`))}>Copiar fichas WhatsApp</button>
            <button className="c-btn c-sec" onClick={() => { const t = textoFichas(); copiar(t); window.open("https://wa.me/?text=" + encodeURIComponent(t.slice(0, 6000)), "_blank"); }}>Enviar por WhatsApp</button>
            <button className="c-btn c-sec" onClick={() => cambiar("solo_seleccion", !filtros.solo_seleccion)}>{filtros.solo_seleccion ? "Ver todos los resultados" : "Ver solo seleccionadas"}</button>
            <button className="c-btn c-sec" onClick={() => { sel.vaciar.mutate(); cambiar("solo_seleccion", false); }}>Quitar selección</button>
          </div>
        )}
        {mapaOn && (
          <div className="c-mapwrap" ref={mapaRef}>
            <MapaResultados pc puntos={mapa.data?.puntos || []} sinUbic={mapa.data?.sin_ubicacion || 0} ocultas={mapa.data?.sin_ubic_ocultas || 0}
              abrir={(id) => { setAbiertas((s) => new Set(s).add(id)); setTimeout(() => document.querySelector(`[data-id="${id}"]`)?.scrollIntoView({ block: "center" }), 300); }} marcar={sel.alternar} />
          </div>
        )}
        <div className="c-tw"><table>
          <thead><tr>
            <th className="c-ck"><input type="checkbox" title="Marcar todas las que se ven" checked={todasVisibles}
              onChange={(e) => { const ids = items.map((x) => x.id); if (e.target.checked) { sel.agregar.mutate(ids); toast(`${ids.length} marcadas`); } else { ids.forEach((id) => sel.ids.has(id) && sel.quitar.mutate(id)); toast("Desmarcadas"); } }} /></th>
            {COLS.map(([k, t]) => <th key={t} onClick={() => ordenar(k)} style={k ? undefined : { cursor: "default" }}>{t}{filtros.orden === k && k ? (filtros.orden_dir > 0 ? " ▲" : " ▼") : ""}</th>)}
          </tr></thead>
          <tbody>
            {lista.isError && <tr><td colSpan={20} className="c-empty">{(lista.error as Error).message} · <a href="#" onClick={(e) => { e.preventDefault(); lista.refetch(); }}>reintentar</a></td></tr>}
            {primera && !items.length && <tr><td colSpan={20} className="c-empty">No hay propiedades con esos filtros. Probá ampliar barrios, dormitorios "O más" o tildar "Incluir los que no informan un dato".</td></tr>}
            {items.map((it, i) => (
              <Fragment key={it.id}>
                <Fila it={it} i={i} abierta={abiertas.has(it.id)} marcada={sel.ids.has(it.id)} conPresu={filtros.b > 0} toast={toast}
                  alternarAbierta={() => alternarAbierta(it.id)} marcar={(v) => (v ? sel.agregar.mutate([it.id]) : sel.quitar.mutate(it.id))} />
                {abiertas.has(it.id) && <DetalleFila id={it.id} dolar={dolar} toast={toast} />}
              </Fragment>
            ))}
            {lista.hasNextPage && (
              <tr><td colSpan={20} className="c-empty"><button className="c-btn c-sec" disabled={lista.isFetchingNextPage} onClick={() => lista.fetchNextPage()}>
                {lista.isFetchingNextPage ? "Cargando…" : `Mostrar ${Math.min(100, total - items.length)} más (${(total - items.length).toLocaleString("es-AR")} restantes)`}</button></td></tr>
            )}
          </tbody>
        </table></div>
      </section>
      {panel && <PanelModal ids={sel.lista} cliente={cliente} cerrar={() => setPanel(false)} />}
    </main>
  );
}
