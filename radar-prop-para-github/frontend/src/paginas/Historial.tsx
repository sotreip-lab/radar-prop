import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useBusqueda } from "../busqueda";
import Detalle from "../componentes/Detalle";
import { fechaHora, fmt, sim } from "../formato";
import { useSesion } from "../sesion";
import { FILTROS_INICIALES, type Filtros, type Zona } from "../tipos";
import { useToast } from "../toast";

type B = { id: number; creada_en: string; texto: string; filtros: Partial<Filtros>; zona: Zona | null; cantidad: number; nuevas: number | null };
type V = { id: number; vista_en: string; tipo: string; barrio: string; direccion: string; moneda: string; precio: number | null; precio_al_ver: number | null; cambio_precio: boolean; baja: boolean; foto: string | null };
type F = { id: number; tipo: string; enlace: string | null; cantidad: number; cliente: string | null; creada_en: string };
type G = { id: number; nombre: string; texto: string; filtros: Partial<Filtros>; zona: Zona | null; creada_en: string };
type A = { id: number; user_id: number | null; accion: string; detalle: Record<string, unknown>; creada_en: string };
type U = { id: number; nombre: string; apellido: string; usuario: string };

const TIPO_FICHA: Record<string, string> = { web: "Ficha web", whatsapp: "WhatsApp", excel: "Excel", panel: "Panel de fichas" };

export default function Historial() {
  const s = useSesion();
  const admin = s.usuario?.rol === "admin";
  const [tab, setTab] = useState("busquedas");
  const [q, setQ] = useState("");
  const [desde, setDesde] = useState("");
  const [hasta, setHasta] = useState("");
  const [uid, setUid] = useState<number | "">("");
  const [abierto, setAbierto] = useState<number | null>(null);
  const { setFiltros, setZona } = useBusqueda();
  const nav = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (desde) params.set("desde", `${desde}T00:00:00`);
  if (hasta) params.set("hasta", `${hasta}T23:59:59`);
  if (uid) params.set("usuario_id", String(uid));
  const p = params.toString();
  const usuarios = useQuery({ queryKey: ["usuarios"], queryFn: () => api<U[]>("/admin/usuarios"), enabled: admin });
  const busq = useQuery({ queryKey: ["hist", "busquedas", p], queryFn: () => api<B[]>(`/historial/busquedas?${p}`), enabled: tab === "busquedas" });
  const vistas = useQuery({ queryKey: ["hist", "vistas", p], queryFn: () => api<V[]>(`/historial/vistas?${p}`), enabled: tab === "vistas" });
  const fichas = useQuery({ queryKey: ["hist", "fichas", p], queryFn: () => api<F[]>(`/historial/fichas?${p}`), enabled: tab === "fichas" });
  const guard = useQuery({ queryKey: ["guardadas"], queryFn: () => api<G[]>("/busquedas-guardadas"), enabled: tab === "guardadas" });
  const act = useQuery({ queryKey: ["actividad", uid, q], queryFn: () => api<A[]>(`/admin/actividad?${uid ? `usuario_id=${uid}&` : ""}${q ? `q=${encodeURIComponent(q)}` : ""}`), enabled: tab === "equipo" && admin });
  const guardar = useMutation({
    mutationFn: (b: { nombre: string; filtros: object; zona: Zona | null }) => api("/busquedas-guardadas", { method: "POST", json: b }),
    onSuccess: () => { toast("Búsqueda guardada"); qc.invalidateQueries({ queryKey: ["guardadas"] }); },
  });
  const borrarG = useMutation({ mutationFn: (id: number) => api(`/busquedas-guardadas/${id}`, { method: "DELETE" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["guardadas"] }) });
  const borrarTodo = useMutation({ mutationFn: () => api("/historial", { method: "DELETE" }), onSuccess: () => { toast("Historial borrado"); qc.invalidateQueries({ queryKey: ["hist"] }); } });

  function repetir(f: Partial<Filtros>, z: Zona | null) {
    setFiltros({ ...FILTROS_INICIALES, ...f });
    setZona(z);
    nav("/");
  }
  const tabs: [string, string][] = [["busquedas", "Búsquedas"], ["vistas", "Propiedades vistas"], ["fichas", "Fichas y envíos"], ["guardadas", "Guardadas"]];
  if (admin) tabs.push(["equipo", "Actividad del equipo"]);
  const nombreDe = (id: number | null) => { const u = usuarios.data?.find((y) => y.id === id); return u ? `${u.nombre} ${u.apellido}`.trim() : "—"; };
  const cargando = (x: { isLoading: boolean }) => x.isLoading && <div className="esqueleto" style={{ height: 80 }} />;

  return (
    <div>
      <div className="pestanas" role="tablist">
        {tabs.map(([k, t]) => <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>{t}</button>)}
      </div>
      {tab !== "guardadas" && (
        <div className="fila-flex" style={{ marginBottom: 12, alignItems: "end" }}>
          <label className="campo crece"><span>Buscar</span><input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Casa, Palihue, 3 dorm…" /></label>
          {tab !== "equipo" && <>
            <label className="campo"><span>Desde</span><input type="date" value={desde} onChange={(e) => setDesde(e.target.value)} /></label>
            <label className="campo"><span>Hasta</span><input type="date" value={hasta} onChange={(e) => setHasta(e.target.value)} /></label>
          </>}
          {admin && <label className="campo"><span>Usuario</span>
            <select value={uid} onChange={(e) => setUid(e.target.value ? +e.target.value : "")}>
              <option value="">{tab === "equipo" ? "Todos" : "Yo"}</option>
              {usuarios.data?.map((u) => <option key={u.id} value={u.id}>{u.nombre} {u.apellido}</option>)}
            </select></label>}
        </div>
      )}

      {tab === "busquedas" && <>
        {cargando(busq)}
        {busq.data && !busq.data.length && <div className="vacio"><h3>No hay búsquedas</h3>Las búsquedas se guardan solas cuando dejás de tocar los filtros.</div>}
        <div className="filas">
          {busq.data?.map((b) => (
            <div key={b.id} className="fila-flex">
              <div className="crece"><b>{b.texto}</b><div className="suave chico">{fechaHora(b.creada_en)} · {b.cantidad} resultados{b.nuevas ? <> · <b style={{ color: "var(--verde)" }}>{b.nuevas} nuevas desde entonces</b></> : null}</div></div>
              <button className="btn chico" onClick={() => repetir(b.filtros, b.zona)}>Repetir búsqueda</button>
              <button className="btn sec chico" onClick={() => { const n = prompt("Nombre para esta búsqueda", b.texto.slice(0, 60)); if (n) guardar.mutate({ nombre: n, filtros: b.filtros, zona: b.zona }); }}>Guardar</button>
            </div>
          ))}
        </div>
      </>}

      {tab === "vistas" && <>
        {cargando(vistas)}
        {vistas.data && !vistas.data.length && <div className="vacio"><h3>Todavía no abriste propiedades</h3>Las que abrís en detalle aparecen acá, con su precio de hoy.</div>}
        <div className="filas">
          {vistas.data?.map((v) => (
            <div key={v.id} className="fila-flex" role="button" tabIndex={0} onClick={() => setAbierto(v.id)} style={{ cursor: "pointer" }}>
              {v.foto ? <img src={v.foto} alt="" loading="lazy" style={{ width: 64, height: 48, objectFit: "cover", borderRadius: 6 }} /> : null}
              <div className="crece"><b>{[v.tipo, v.barrio].filter(Boolean).join(" en ")}</b><div className="suave chico">{v.direccion} · vista {fechaHora(v.vista_en)}</div></div>
              <div style={{ textAlign: "right" }}>
                <b className="num">{v.precio ? `${sim(v.moneda)} ${fmt(v.precio)}` : "Consultar"}</b>
                {v.baja && <div className="tag baja">Dada de baja</div>}
                {v.cambio_precio && <div className="chico">antes {sim(v.moneda)} {fmt(v.precio_al_ver)}</div>}
              </div>
            </div>
          ))}
        </div>
      </>}

      {tab === "fichas" && <>
        {cargando(fichas)}
        {fichas.data && !fichas.data.length && <div className="vacio"><h3>No hay fichas</h3>Se registran las fichas web, los textos de WhatsApp, los Excel y los envíos al panel.</div>}
        <div className="filas">
          {fichas.data?.map((f) => (
            <div key={f.id} className="fila-flex">
              <div className="crece"><b>{TIPO_FICHA[f.tipo] || f.tipo}</b>{f.cliente ? ` para ${f.cliente}` : ""}<div className="suave chico">{fechaHora(f.creada_en)}{f.cantidad ? ` · ${f.cantidad} propiedades` : ""}</div></div>
              {f.enlace?.startsWith("/f/") && <a className="btn sec chico" href={f.enlace} target="_blank" rel="noreferrer">Abrir</a>}
              {f.enlace?.startsWith("http") && <a className="btn sec chico" href={f.enlace} target="_blank" rel="noreferrer">Abrir panel</a>}
            </div>
          ))}
        </div>
      </>}

      {tab === "guardadas" && <>
        {cargando(guard)}
        {guard.data && !guard.data.length && <div className="vacio"><h3>No guardaste búsquedas</h3>Desde la pestaña Búsquedas tocá "Guardar" en la que quieras tener a mano.</div>}
        <div className="filas">
          {guard.data?.map((g) => (
            <div key={g.id} className="fila-flex">
              <div className="crece"><b>{g.nombre}</b><div className="suave chico">{g.texto}</div></div>
              <button className="btn chico" onClick={() => repetir(g.filtros, g.zona)}>Buscar</button>
              <button className="btn sec chico" onClick={() => confirm(`¿Borrar "${g.nombre}"?`) && borrarG.mutate(g.id)}>Borrar</button>
            </div>
          ))}
        </div>
      </>}

      {tab === "equipo" && admin && <>
        {cargando(act)}
        <div className="filas">
          {act.data?.map((x) => (
            <div key={x.id}><b>{nombreDe(x.user_id)}</b> · {x.accion.replace(/_/g, " ")} <span className="suave chico">· {fechaHora(x.creada_en)}</span>
              {Object.keys(x.detalle || {}).length ? <div className="suave chico">{Object.entries(x.detalle).map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`).join(" · ")}</div> : null}</div>
          ))}
        </div>
      </>}

      {tab !== "equipo" && !uid && (
        <div style={{ marginTop: 18 }}>
          <button className="btn sec chico" onClick={() => confirm("¿Borrar tu historial de búsquedas y de propiedades vistas? No se puede deshacer.") && borrarTodo.mutate()}>Borrar mi historial</button>
        </div>
      )}
      {abierto != null && <Detalle id={abierto} cerrar={() => setAbierto(null)} />}
    </div>
  );
}
