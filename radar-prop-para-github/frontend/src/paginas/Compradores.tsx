import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, ApiError } from "../api";
import Detalle from "../componentes/Detalle";
import Tarjeta from "../componentes/Tarjeta";
import { fmt, sim } from "../formato";
import { useSeleccion } from "../hooks";
import { useSesion } from "../sesion";
import type { Item } from "../tipos";
import { useToast } from "../toast";

type Datos = {
  nombre: string; telefono: string; operacion: string; ciudad: string; tipos: string[]; presu: number | null; moneda: "USD" | "ARS";
  dorm: number | null; barrios: string[]; patio: "" | "si"; cochera: "" | "si"; credito: "" | "si"; amoblado: "" | "si" | "no"; obs: string; texto: string;
};
type Cliente = { id: number; version: number; datos: Datos; asignado_a: number | null; asignado_nombre: string | null; coinciden: number; ids: number[]; nuevas: number[]; es_mia: boolean };
const VACIO: Datos = { nombre: "", telefono: "", operacion: "Venta", ciudad: "Bahía Blanca", tipos: [], presu: null, moneda: "USD", dorm: null, barrios: [], patio: "", cochera: "", credito: "", amoblado: "", obs: "", texto: "" };

/** parsearPedido() de El Ojo de Dios: lee el pedido pegado de WhatsApp ("Inmueble: casa", "Presupuesto: USD 150.000"…). */
export function parsearPedido(t: string): Datos {
  const d: Datos = { ...VACIO };
  const lin = t.split(/\n/).map((l) => l.replace(/[*_]/g, "").trim()).filter(Boolean);
  const get = (re: RegExp) => { for (const l of lin) { const m = l.match(re); if (m) return m[1].trim(); } return ""; };
  d.nombre = get(/^nombre\s*:?\s*(.+)$/i);
  d.telefono = get(/^(?:tel[eé]fono|cel(?:ular)?|whatsapp)\s*:?\s*(.+)$/i);
  const inm = get(/^inmueble\s*:?\s*(.+)$/i);
  d.tipos = inm ? inm.split(/[,/]| o | y /i).map((x) => x.trim()).filter(Boolean).map((x) => (/depto|dpto/i.test(x) ? "Departamento" : x)) : [];
  const ub = get(/^ubicaci[oó]n\s*:?\s*(.+)$/i);
  d.barrios = ub && !/indistint|cualquier|todo/i.test(ub) ? ub.split(/[,/]| o | y /i).map((x) => x.trim()).filter(Boolean) : [];
  const dn = get(/^dormitorios?\s*:?\s*(.+)$/i).match(/\d/);
  d.dorm = dn ? +dn[0] : null;
  d.patio = /patio|jard|parque/i.test(get(/^espacio exterior\s*:?\s*(.+)$/i)) ? "si" : "";
  const est = get(/^(?:estacionamiento|cochera)\s*:?\s*(.+)$/i);
  d.cochera = /^s[ií]|cochera|garage/i.test(est) && !/^no|indist/i.test(est) ? "si" : "";
  d.credito = /cr[eé]dito/i.test(get(/^pago\s*:?\s*(.+)$/i)) ? "si" : "";
  const pr = get(/^presupuesto(?: m[aá]ximo)?\s*:?\s*(.+)$/i);
  d.moneda = /\$|ars|pesos/i.test(pr) && !/us|u\$s|usd|d[oó]lar/i.test(pr) ? "ARS" : "USD";
  const num = pr.replace(/[^\d.,kKmM]/g, "");
  let v = parseFloat(num.replace(/\./g, "").replace(",", ".")) || 0;
  if (/k/i.test(num) && v < 10000) v *= 1000;
  if (/m/i.test(pr.replace(/[^a-z]/gi, "").slice(-1)) && v < 1000) v *= 1e6;
  d.presu = v || null;
  const op = get(/^operaci[oó]n\s*:?\s*(.+)$/i);
  d.operacion = /alquil/i.test(op + " " + t.slice(0, 80)) && !/venta|compra/i.test(op) ? "Alquiler" : "Venta";
  const amo = get(/^amoblado\s*:?\s*(.+)$/i);
  d.amoblado = amo ? (/^no/i.test(amo) ? "no" : "si") : "";
  d.obs = [get(/^inversi[oó]n o vivienda\s*:?\s*(.+)$/i), get(/^observaci[oó]n(?:es)?\s*:?\s*(.+)$/i)].filter(Boolean).join(" · ");
  d.texto = t;
  return d;
}

function Formulario({ inicial, cerrar }: { inicial: Cliente | null; cerrar: () => void }) {
  const [d, setD] = useState<Datos>(inicial ? { ...VACIO, ...inicial.datos } : VACIO);
  const [asig, setAsig] = useState<number | "">(inicial?.asignado_a ?? "");
  const [error, setError] = useState("");
  const equipo = useQuery({ queryKey: ["equipo-nombres"], queryFn: () => api<{ id: number; nombre: string }[]>("/equipo/nombres") });
  const qc = useQueryClient();
  const toast = useToast();
  const set = <K extends keyof Datos>(k: K, v: Datos[K]) => setD((x) => ({ ...x, [k]: v }));
  const guardar = useMutation({
    mutationFn: () => api(inicial ? `/clientes/${inicial.id}` : "/clientes", { method: inicial ? "PUT" : "POST", json: { datos: d, asignado_a: asig || null, version: inicial?.version } }),
    onSuccess: () => { toast("Comprador guardado"); qc.invalidateQueries({ queryKey: ["clientes"] }); qc.invalidateQueries({ queryKey: ["notificaciones"] }); cerrar(); },
    onError: (e) => { setError((e as Error).message); if (e instanceof ApiError && e.estado === 409) qc.invalidateQueries({ queryKey: ["clientes"] }); },
  });
  const lista = (v: string) => v.split(",").map((x) => x.trim()).filter(Boolean);
  return (
    <div className="modal" role="dialog" aria-modal="true"><div className="caja">
      <h2>{inicial ? "Editar comprador" : "Nuevo comprador"}</h2>
      <label className="campo"><span>Pegá el pedido de WhatsApp (se completa solo)</span>
        <textarea value={d.texto} onChange={(e) => { const p = parsearPedido(e.target.value); setD((x) => ({ ...p, nombre: p.nombre || x.nombre, telefono: p.telefono || x.telefono })); }} placeholder={"Nombre: Juan\nInmueble: casa\nUbicación: Palihue, Centro\nDormitorios: 3\nPresupuesto: USD 150.000"} /></label>
      <div className="grid-form">
        <label className="campo"><span>Nombre</span><input type="text" value={d.nombre} onChange={(e) => set("nombre", e.target.value)} required /></label>
        <label className="campo"><span>Teléfono</span><input type="tel" value={d.telefono} onChange={(e) => set("telefono", e.target.value)} /></label>
        <label className="campo"><span>Operación</span><select value={d.operacion} onChange={(e) => set("operacion", e.target.value)}><option>Venta</option><option>Alquiler</option></select></label>
        <label className="campo"><span>Tipos (separados por coma)</span><input type="text" value={d.tipos.join(", ")} onChange={(e) => set("tipos", lista(e.target.value))} /></label>
        <label className="campo"><span>Presupuesto</span><input type="number" value={d.presu ?? ""} onChange={(e) => set("presu", +e.target.value || null)} /></label>
        <label className="campo"><span>Moneda</span><select value={d.moneda} onChange={(e) => set("moneda", e.target.value as "USD" | "ARS")}><option value="USD">USD</option><option value="ARS">Pesos</option></select></label>
        <label className="campo"><span>Dormitorios (mínimo)</span><input type="number" value={d.dorm ?? ""} onChange={(e) => set("dorm", e.target.value === "" ? null : +e.target.value)} /></label>
        <label className="campo"><span>Barrios (separados por coma)</span><input type="text" value={d.barrios.join(", ")} onChange={(e) => set("barrios", lista(e.target.value))} /></label>
        <label className="campo"><span>Patio</span><select value={d.patio} onChange={(e) => set("patio", e.target.value as "" | "si")}><option value="">Indistinto</option><option value="si">Sí</option></select></label>
        <label className="campo"><span>Cochera</span><select value={d.cochera} onChange={(e) => set("cochera", e.target.value as "" | "si")}><option value="">Indistinto</option><option value="si">Sí</option></select></label>
        <label className="campo"><span>Apto crédito</span><select value={d.credito} onChange={(e) => set("credito", e.target.value as "" | "si")}><option value="">Indistinto</option><option value="si">Sí</option></select></label>
        <label className="campo"><span>Amoblado</span><select value={d.amoblado} onChange={(e) => set("amoblado", e.target.value as "" | "si" | "no")}><option value="">Indistinto</option><option value="si">Sí</option><option value="no">No</option></select></label>
        <label className="campo"><span>Avisarle a</span><select value={asig} onChange={(e) => setAsig(e.target.value ? +e.target.value : "")}><option value="">A mí</option>{equipo.data?.map((u) => <option key={u.id} value={u.id}>{u.nombre}</option>)}</select></label>
      </div>
      <label className="campo"><span>Observaciones</span><input type="text" value={d.obs} onChange={(e) => set("obs", e.target.value)} /></label>
      {error && <div className="aviso error" role="alert">{error}</div>}
      <div className="botones"><button className="btn sec" onClick={cerrar}>Cancelar</button><button className="btn" disabled={!d.nombre.trim() || guardar.isPending} onClick={() => guardar.mutate()}>Guardar</button></div>
    </div></div>
  );
}

export default function Compradores() {
  const [soloMios, setSoloMios] = useState(false);
  const [editar, setEditar] = useState<Cliente | null | "nuevo">(null);
  const [ver, setVer] = useState<{ c: Cliente; nuevas: boolean } | null>(null);
  const [abierto, setAbierto] = useState<number | null>(null);
  const qc = useQueryClient();
  const toast = useToast();
  const sel = useSeleccion();
  const s = useSesion();
  const q = useQuery({ queryKey: ["clientes", soloMios], queryFn: () => api<Cliente[]>(`/clientes${soloMios ? "?solo_mios=true" : ""}`) });
  const ids = ver ? (ver.nuevas ? ver.c.nuevas : ver.c.ids) : [];
  const props = useQuery({ queryKey: ["lote", ids], queryFn: () => api<Item[]>("/propiedades/lote", { method: "POST", json: { ids: ids.slice(0, 200) } }), enabled: ids.length > 0 });
  const visto = useMutation({ mutationFn: (id: number) => api(`/clientes/${id}/visto`, { method: "POST" }), onSuccess: () => { qc.invalidateQueries({ queryKey: ["clientes"] }); qc.invalidateQueries({ queryKey: ["notificaciones"] }); } });
  const borrar = useMutation({
    mutationFn: (c: Cliente) => api(`/clientes/${c.id}?version=${c.version}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["clientes"] }),
    onError: (e) => { toast((e as Error).message); qc.invalidateQueries({ queryKey: ["clientes"] }); },
  });
  const pedirAvisos = () => { if ("Notification" in window && Notification.permission === "default") Notification.requestPermission(); };
  const resumen = (d: Datos) => [d.operacion, d.tipos.join("/"), d.dorm != null ? `${d.dorm}+ dorm` : "", d.presu ? `${sim(d.moneda)} ${fmt(d.presu)}` : "", d.barrios.join(", ")].filter(Boolean).join(" · ");

  if (ver) {
    return (
      <div>
        <div className="fila-flex" style={{ marginBottom: 10 }}>
          <button className="btn sec chico" onClick={() => setVer(null)}>Volver</button>
          <h3 className="crece" style={{ margin: 0 }}>{ver.nuevas ? "Nuevas" : "Todas las que encajan"} para {ver.c.datos.nombre} ({ids.length})</h3>
          <button className="btn chico" onClick={() => { sel.agregar.mutate(ids.slice(0, 40)); toast("Marcadas para armar la ficha"); }} disabled={!ids.length}>Marcar todas</button>
          {ver.nuevas && ver.c.es_mia && <button className="btn sec chico" onClick={() => { visto.mutate(ver.c.id); setVer(null); }}>Marcar como vistas</button>}
        </div>
        {props.isLoading && <div className="esqueleto" style={{ height: 100 }} />}
        <div className="lista">{props.data?.map((it) => <Tarjeta key={it.id} it={it} marcada={sel.ids.has(it.id)} conDif={false} abrir={() => setAbierto(it.id)} marcar={() => sel.alternar(it.id)} />)}</div>
        {abierto != null && <Detalle id={abierto} cerrar={() => setAbierto(null)} />}
      </div>
    );
  }
  return (
    <div style={{ display: "grid", gap: 12 }}>
      <div className="fila-flex">
        <h2 className="crece" style={{ margin: 0 }}>Compradores</h2>
        <label className="check"><input type="checkbox" checked={soloMios} onChange={(e) => setSoloMios(e.target.checked)} />Solo los míos</label>
        <button className="btn" onClick={() => { setEditar("nuevo"); pedirAvisos(); }}>Nuevo comprador</button>
      </div>
      <p className="suave" style={{ margin: 0 }}>Cuando entra una propiedad que encaja con un comprador, le aparece un aviso al agente asignado.</p>
      {q.isLoading && <div className="esqueleto" style={{ height: 80 }} />}
      {q.isError && <div className="aviso error">{(q.error as Error).message}</div>}
      {q.data && !q.data.length && <div className="vacio"><h3>No hay compradores cargados</h3>Cargá el pedido de un comprador y la app te avisa cuando aparezca algo para él.</div>}
      <div className="filas">
        {q.data?.map((c) => (
          <div key={c.id} className="fila-flex">
            <div className="crece">
              <b>{c.datos.nombre}</b>{c.datos.telefono ? <span className="suave"> · {c.datos.telefono}</span> : null}
              <div className="suave chico">{resumen(c.datos)}{c.asignado_nombre ? ` · lo sigue ${c.asignado_a === s.usuario?.id ? "vos" : c.asignado_nombre}` : ""}</div>
            </div>
            {c.nuevas.length > 0 && <button className="btn chico" onClick={() => setVer({ c, nuevas: true })}>{c.nuevas.length} nuevas</button>}
            <button className="btn sec chico" onClick={() => setVer({ c, nuevas: false })}>{c.coinciden} encajan</button>
            <button className="btn sec chico" onClick={() => setEditar(c)}>Editar</button>
            <button className="btn sec chico" onClick={() => confirm(`¿Borrar a ${c.datos.nombre}?`) && borrar.mutate(c)}>Borrar</button>
          </div>
        ))}
      </div>
      {editar && <Formulario inicial={editar === "nuevo" ? null : editar} cerrar={() => setEditar(null)} />}
    </div>
  );
}
