import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { useBusqueda } from "../busqueda";
import { fmt, norm, sim } from "../formato";
import type { Filtros } from "../tipos";
import { IcoCerrar } from "./Iconos";

type Opciones = { operaciones: [string, number][]; ciudades: [string, number][]; tipos: [string, number][]; barrios: [string, number][] };

function Seg<T extends string>({ valor, opciones, cambiar, etiqueta }: { valor: T; opciones: [T, string][]; cambiar: (v: T) => void; etiqueta: string }) {
  return (
    <div className="seg" role="group" aria-label={etiqueta}>
      {opciones.map(([v, t]) => (
        <button key={v} type="button" aria-pressed={valor === v} onClick={() => cambiar(v)}>{t}</button>
      ))}
    </div>
  );
}

function Num({ etiqueta, valor, cambiar, ph }: { etiqueta: string; valor: number | null; cambiar: (v: number) => void; ph?: string }) {
  return (
    <label className="campo"><span>{etiqueta}</span>
      <input type="number" inputMode="numeric" min={0} value={valor || ""} placeholder={ph} onChange={(e) => cambiar(+e.target.value || 0)} />
    </label>
  );
}

export function bandas(b: number, mon: string) {
  return mon === "ARS" ? { loV: b * 0.95, hiV: b * 1.05, topV: b * 1.07 } : { loV: b - 5000, hiV: b + 5000, topV: Math.max(b * 1.07, b + 5000) };
}

export function RangoSemaforo({ f }: { f: Filtros }) {
  const S = sim(f.mon);
  if (!f.b) return <div className="rango">Escribí un presupuesto para ver el semáforo. Sin presupuesto podés usar precio mínimo y máximo.</div>;
  const { loV, hiV, topV } = bandas(f.b, f.mon);
  return (
    <div className="rango">
      <div><span className="punto" style={{ background: "var(--verde)" }} />Verde: {S} {fmt(loV)} a {fmt(hiV)}{f.mon === "ARS" ? " (±5%)" : ""}</div>
      {topV > hiV ? <div><span className="punto" style={{ background: "var(--violeta)" }} />Violeta: {S} {fmt(hiV + 1)} a {fmt(topV)}</div>
        : <div>Violeta: no aplica (7% es menos que USD 5.000)</div>}
      <div><span className="punto" style={{ background: "var(--amarillo)" }} />Amarillo: hasta {S} {fmt(f.b * 1.15)}, más baratas desde {fmt(f.b * (1 - f.pct_abajo / 100))}, o falta un dato</div>
      {f.rojas && <div><span className="punto" style={{ background: "var(--rojo)" }} />Rojo: hasta {S} {fmt(f.b * 1.3)}</div>}
    </div>
  );
}

const SINO: ["" | "si" | "no", string][] = [["", "Indistinto"], ["si", "Sí"], ["no", "No"]];

export default function PanelFiltros({ abierto, cerrar }: { abierto: boolean; cerrar: () => void }) {
  const { filtros: f, cambiar, setFiltros, reiniciar, zona, setZona } = useBusqueda();
  const [qBarrio, setQBarrio] = useState("");
  const [todosTipos, setTodosTipos] = useState(false);
  const [mas, setMas] = useState(false);
  const op = useQuery({
    queryKey: ["opciones", f.oper, f.ciudad],
    queryFn: () => api<Opciones>(`/propiedades/opciones?operacion=${encodeURIComponent(f.oper)}&ciudad=${encodeURIComponent(f.ciudad)}`),
    staleTime: 300_000,
  });
  const S = sim(f.mon);
  const alternar = (k: "tipos" | "barrios", v: string) =>
    setFiltros((x) => ({ ...x, [k]: x[k].includes(v) ? x[k].filter((y) => y !== v) : [...x[k], v] }));
  const tipos = op.data?.tipos || [];
  const tiposVis = todosTipos ? tipos : tipos.filter(([k], i) => i < 8 || f.tipos.includes(k));
  const barrios = (op.data?.barrios || []).filter(([k]) => !qBarrio || norm(k).includes(norm(qBarrio)));
  const cambiarOper = (v: string) =>
    setFiltros((x) => ({ ...x, oper: v, tipos: [], barrios: [], mon: /alquiler/i.test(v) ? "ARS" : "USD" }));

  return (
    <>
      {abierto && <div className="velo-filtros" onClick={cerrar} />}
      <aside className={`panel-filtros${abierto ? " abierto" : ""}`} aria-label="Filtros">
        <div className="fila-flex">
          <h3 className="crece">Filtros</h3>
          <button className="lnk" type="button" onClick={reiniciar}>Limpiar</button>
          <button className="btn sec chico solo-movil" type="button" onClick={cerrar} aria-label="Cerrar filtros"><IcoCerrar className="ico" /></button>
        </div>

        <label className="campo"><span>Operación</span>
          <select value={f.oper} onChange={(e) => cambiarOper(e.target.value)}>
            {(op.data?.operaciones || [[f.oper, 0]]).map(([k, n]) => <option key={k} value={k}>{k}{n ? ` (${n.toLocaleString("es-AR")})` : ""}</option>)}
          </select></label>
        <label className="campo"><span>Ciudad</span>
          <select value={f.ciudad} onChange={(e) => setFiltros((x) => ({ ...x, ciudad: e.target.value, barrios: [] }))}>
            <option value="">Todas</option>
            {(op.data?.ciudades || []).map(([k, n]) => <option key={k} value={k}>{k} ({n.toLocaleString("es-AR")})</option>)}
          </select></label>

        <div className="campo"><span>Moneda</span>
          <Seg etiqueta="Moneda" valor={f.mon} opciones={[["USD", "Dólares"], ["ARS", "Pesos"]]} cambiar={(v) => cambiar("mon", v)} /></div>
        <Num etiqueta={`Presupuesto ${f.mon === "ARS" ? "en pesos ($)" : "USD"}`} valor={f.b} cambiar={(v) => cambiar("b", v)} ph={f.mon === "ARS" ? "650000" : "160000"} />
        <RangoSemaforo f={f} />

        <div className="campo"><span>Tipo</span>
          <div className="chips">
            {tiposVis.map(([k, n]) => (
              <button type="button" key={k} className="chip" aria-pressed={f.tipos.includes(k)} onClick={() => alternar("tipos", k)}>{k}<small>{n}</small></button>
            ))}
            {tipos.length > 8 && <button type="button" className="chip" onClick={() => setTodosTipos(!todosTipos)}>{todosTipos ? "Ver menos" : `Ver todos (${tipos.length})`}</button>}
          </div></div>

        <div className="campo"><span>Dormitorios</span>
          <Seg etiqueta="Dormitorios" valor={f.dorm} cambiar={(v) => cambiar("dorm", v)}
            opciones={[["", "Todos"], ["0", "Mono"], ["1", "1"], ["2", "2"], ["3", "3"], ["4", "4"], ["5", "5+"]]} />
          <Seg etiqueta="Dormitorios exactos o mínimo" valor={f.dorm_modo} cambiar={(v) => cambiar("dorm_modo", v)} opciones={[["exacto", "Exactos"], ["min", "O más"]]} />
        </div>

        <div className="campo"><span>Barrios {f.barrios.length ? `(${f.barrios.length})` : ""}</span>
          <input type="search" placeholder="Buscar barrio" value={qBarrio} onChange={(e) => setQBarrio(e.target.value)} />
          <div className="barrios-lista">
            {barrios.map(([k, n]) => (
              <label key={k} className="check"><input type="checkbox" checked={f.barrios.includes(k)} onChange={() => alternar("barrios", k)} />{k} <span className="suave">({n})</span></label>
            ))}
            {!barrios.length && <div className="suave">Sin barrios</div>}
          </div>
          {f.barrios.length > 0 && <button type="button" className="lnk" onClick={() => cambiar("barrios", [])}>Todos los barrios</button>}
          <label className="check"><input type="checkbox" checked={f.sin_barrio} onChange={(e) => cambiar("sin_barrio", e.target.checked)} />Incluir avisos sin barrio</label>
        </div>

        {(["patio", "cochera", "pileta", "balcon", "parrilla"] as const).map((k) => (
          <div key={k} className="campo"><span>{{ patio: "Patio", cochera: "Cochera", pileta: "Pileta", balcon: "Balcón o terraza", parrilla: "Parrilla o quincho" }[k]}</span>
            <Seg etiqueta={k} valor={f[k]} opciones={SINO} cambiar={(v) => cambiar(k, v)} /></div>
        ))}
        <div className="campo"><span>Amoblado</span>
          <Seg etiqueta="Amoblado" valor={f.amoblado} opciones={[["", "Indistinto"], ["si", "Amoblado"], ["no", "Sin amoblar"]]} cambiar={(v) => cambiar("amoblado", v)} /></div>
        <label className="check"><input type="checkbox" checked={f.credito === "si"} onChange={(e) => cambiar("credito", e.target.checked ? "si" : "")} />Apto crédito</label>
        <label className="check"><input type="checkbox" checked={f.estrenar} onChange={(e) => cambiar("estrenar", e.target.checked)} />A estrenar o en construcción</label>
        <label className="check"><input type="checkbox" checked={f.sin_dato} onChange={(e) => cambiar("sin_dato", e.target.checked)} />Incluir los que no informan un dato (salen en Amarillo)</label>

        <label className="campo"><span>Palabras clave (en título y descripción)</span>
          <input type="search" value={f.kw} onChange={(e) => cambiar("kw", e.target.value)} placeholder="pileta, a refaccionar…" /></label>
        <label className="campo"><span>Publicadas en las últimas</span>
          <select value={f.nuevas_horas} onChange={(e) => cambiar("nuevas_horas", +e.target.value)}>
            <option value={0}>Cualquier fecha</option><option value={24}>24 horas</option><option value={72}>3 días</option>
            <option value={168}>7 días</option><option value={720}>30 días</option>
          </select></label>

        <button type="button" className="btn sec" onClick={() => setMas(!mas)} aria-expanded={mas}>{mas ? "Menos filtros" : "Más filtros"}</button>
        {mas && (
          <>
            <div className="fila2">
              <Num etiqueta={`Precio mín. ${S}`} valor={f.pmin} cambiar={(v) => cambiar("pmin", v)} />
              <Num etiqueta={`Precio máx. ${S}`} valor={f.pmax} cambiar={(v) => cambiar("pmax", v)} />
            </div>
            <div className="fila2">
              <Num etiqueta="Baños (mínimo)" valor={f.banos} cambiar={(v) => cambiar("banos", v)} />
              <Num etiqueta="m² cubiertos (mínimo)" valor={f.supmin} cambiar={(v) => cambiar("supmin", v)} />
            </div>
            <Num etiqueta={`Precio por m² hasta ${S}`} valor={f.m2max} cambiar={(v) => cambiar("m2max", v)} />
            <div className="fila2">
              <Num etiqueta="Más baratas hasta (−%)" valor={f.pct_abajo} cambiar={(v) => cambiar("pct_abajo", v)} />
              <Num etiqueta="Cuota de crédito hasta $" valor={f.cuota_max} cambiar={(v) => cambiar("cuota_max", v)} />
            </div>
            <label className="check"><input type="checkbox" checked={f.rojas} onChange={(e) => cambiar("rojas", e.target.checked)} />Mostrar en Rojo hasta +30%</label>
            <div className="campo"><span>Días publicada (solo las que tienen fecha conocida)</span>
              <div className="fila2">
                <Num etiqueta="Desde" valor={f.dmin} cambiar={(v) => cambiar("dmin", v || null)} />
                <Num etiqueta="Hasta" valor={f.dmax} cambiar={(v) => cambiar("dmax", v || null)} />
              </div></div>
            <Num etiqueta="Bajó de precio al menos (%)" valor={f.bajo_min} cambiar={(v) => cambiar("bajo_min", v)} />
            <label className="check"><input type="checkbox" checked={f.bajo_precio} onChange={(e) => cambiar("bajo_precio", e.target.checked)} />Solo las que bajaron de precio</label>
            <label className="check"><input type="checkbox" checked={f.margen_neg} onChange={(e) => cambiar("margen_neg", e.target.checked)} />Solo con margen de negociación</label>
            <label className="check"><input type="checkbox" checked={!f.excl} onChange={(e) => cambiar("excl", !e.target.checked)} />Incluir inmobiliarias excluidas (Re/Max, Maidana…)</label>
            <label className="check"><input type="checkbox" checked={f.bajas} onChange={(e) => cambiar("bajas", e.target.checked)} />Mostrar también las dadas de baja</label>
            {zona && (
              <>
                <Num etiqueta="Mostrar también hasta X metros de la zona" valor={f.margen} cambiar={(v) => cambiar("margen", v)} />
                <label className="check"><input type="checkbox" checked={f.sin_ubic} onChange={(e) => cambiar("sin_ubic", e.target.checked)} />Incluir avisos sin ubicación en el mapa</label>
              </>
            )}
          </>
        )}
        {zona && <div className="aviso">Hay una zona dibujada en el mapa. <button type="button" className="lnk" onClick={() => setZona(null)}>Quitar zona</button></div>}
        <button type="button" className="btn listo solo-movil" onClick={cerrar}>Ver resultados</button>
      </aside>
    </>
  );
}
