import { useMutation, useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api, claveIdempotencia } from "../api";
import Detalle from "../componentes/Detalle";
import Tarjeta from "../componentes/Tarjeta";
import { copiar } from "../formato";
import { useSeleccion } from "../hooks";
import type { Item } from "../tipos";
import { useToast } from "../toast";

type Cliente = { id: number; datos: { nombre: string } };
type PanelCli = { id: string; name: string; estado?: string };

function PanelModal({ ids, cliente, cerrar }: { ids: number[]; cliente: string; cerrar: () => void }) {
  const q = useQuery({ queryKey: ["panel-clientes"], queryFn: () => api<{ clients: PanelCli[] }>("/panel/clientes"), retry: false });
  const [cli, setCli] = useState("");
  const [etiqueta, setEtiqueta] = useState(`${cliente ? cliente + " · " : ""}${ids.length} propiedad${ids.length === 1 ? "" : "es"} (Radar Prop)`);
  const clave = useRef(claveIdempotencia());
  const enviar = useMutation({
    mutationFn: () => api<{ enviadas: number; no_disponibles: number; panel: string }>("/panel/enviar", { method: "POST", json: { ids, cliente_panel: cli, etiqueta, clave_idempotencia: clave.current } }),
  });
  return (
    <div className="modal" role="dialog" aria-modal="true"><div className="caja">
      <h2>Mandar al panel de fichas</h2>
      {q.isLoading && <p>Cargando clientes del panel…</p>}
      {q.isError && <div className="aviso error">No pude conectar con el panel: {(q.error as Error).message}</div>}
      {q.data && <label className="campo"><span>Cliente en el panel</span>
        <select value={cli} onChange={(e) => setCli(e.target.value)}>
          <option value="">Sin cliente (lo elijo en el panel)</option>
          {q.data.clients.filter((c) => c.estado !== "archivado").map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select></label>}
      <label className="campo"><span>Nombre del borrador</span><input type="text" value={etiqueta} onChange={(e) => setEtiqueta(e.target.value)} /></label>
      {enviar.isPending && <p>Leyendo {ids.length} propiedades en vivo (fotos y precio del momento) y mandándolas…</p>}
      {enviar.isError && <div className="aviso error">No se pudo: {(enviar.error as Error).message}</div>}
      {enviar.data && <div className="aviso">Listo: {enviar.data.enviadas} en el borrador.{enviar.data.no_disponibles ? ` ${enviar.data.no_disponibles} ya no están publicadas y no se mandaron.` : ""} <a href={enviar.data.panel} target="_blank" rel="noreferrer">Abrir el panel</a></div>}
      <div className="botones">
        <button className="btn sec" onClick={cerrar}>Cerrar</button>
        <button className="btn" disabled={!q.data || enviar.isPending || !!enviar.data} onClick={() => enviar.mutate()}>Mandar</button>
      </div>
    </div></div>
  );
}

export default function Seleccion() {
  const sel = useSeleccion();
  const toast = useToast();
  const [cliente, setCliente] = useState("");
  const [clienteId, setClienteId] = useState<number | "">("");
  const [abierto, setAbierto] = useState<number | null>(null);
  const [panel, setPanel] = useState(false);
  const clave = useRef(claveIdempotencia());
  const items = useQuery({
    queryKey: ["lote", sel.lista],
    queryFn: () => api<Item[]>("/propiedades/lote", { method: "POST", json: { ids: sel.lista } }),
    enabled: sel.lista.length > 0,
  });
  const compradores = useQuery({ queryKey: ["clientes"], queryFn: () => api<Cliente[]>("/clientes") });
  const ficha = useMutation({
    mutationFn: (tipo: "web" | "whatsapp") => api<{ enlace: string; texto?: string }>("/fichas", { method: "POST",
      json: { ids: sel.lista.slice(0, 40), tipo, cliente, cliente_id: clienteId || null, clave_idempotencia: `${clave.current}-${tipo}` } }),
  });
  const ids = sel.lista;
  if (sel.cargando) return <div className="esqueleto" style={{ height: 120 }} />;
  if (!ids.length) {
    return <div className="vacio"><h3>Todavía no marcaste propiedades</h3>Marcalas desde Buscar o el Mapa y acá armás la ficha para el cliente, el texto para WhatsApp o el borrador del panel.</div>;
  }
  async function web() {
    // la ventana se abre antes de esperar al servidor (si no, el celular la bloquea)
    const v = window.open("", "_blank");
    try {
      const r = await ficha.mutateAsync("web");
      const url = `${location.origin}${r.enlace}`;
      if (v) v.location.href = url; else location.href = url;
      copiar(url);
      toast("Ficha lista. El link quedó copiado para mandárselo al cliente.");
      clave.current = claveIdempotencia();
    } catch (e) {
      v?.close();
      toast((e as Error).message);
    }
  }
  async function whatsapp(enviar: boolean) {
    try {
      const r = await ficha.mutateAsync("whatsapp");
      await copiar(r.texto || "");
      if (enviar) window.open(`https://wa.me/?text=${encodeURIComponent((r.texto || "").slice(0, 6000))}`, "_blank");
      toast(`${ids.length} fichas copiadas: pegalas en WhatsApp`);
      clave.current = claveIdempotencia();
    } catch (e) {
      toast((e as Error).message);
    }
  }
  return (
    <div style={{ display: "grid", gap: 14 }}>
      <div className="tarjeta" style={{ display: "grid", gap: 10 }}>
        <h3 style={{ margin: 0 }}>{ids.length} propiedad{ids.length === 1 ? "" : "es"} marcada{ids.length === 1 ? "" : "s"}</h3>
        <div className="grid-form">
          <label className="campo"><span>Para el cliente (opcional)</span><input type="text" value={cliente} onChange={(e) => setCliente(e.target.value)} placeholder="Nombre que aparece en la ficha" /></label>
          <label className="campo"><span>Comprador cargado (opcional)</span>
            <select value={clienteId} onChange={(e) => { const v = e.target.value ? +e.target.value : ""; setClienteId(v); const c = compradores.data?.find((x) => x.id === v); if (c && !cliente) setCliente(c.datos.nombre); }}>
              <option value="">Ninguno</option>{compradores.data?.map((c) => <option key={c.id} value={c.id}>{c.datos.nombre}</option>)}
            </select></label>
        </div>
        {ids.length > 40 && <div className="aviso error">Máximo 40 propiedades por ficha: se usan las primeras 40.</div>}
        <div className="botones" style={{ justifyContent: "flex-start" }}>
          <button className="btn" onClick={web} disabled={ficha.isPending}>{ficha.isPending ? "Armando con los datos del momento…" : "Ficha para el cliente (con fotos)"}</button>
          <button className="btn sec" onClick={() => whatsapp(false)}>Copiar para WhatsApp</button>
          <button className="btn sec" onClick={() => whatsapp(true)}>Mandar por WhatsApp</button>
          <button className="btn sec" onClick={() => setPanel(true)}>Mandar al panel</button>
          <button className="btn sec" onClick={() => sel.vaciar.mutate()}>Desmarcar todas</button>
        </div>
      </div>
      {items.isLoading && <div className="esqueleto" style={{ height: 110 }} />}
      <div className="lista">
        {items.data?.map((it) => <Tarjeta key={it.id} it={it} marcada conDif={false} abrir={() => setAbierto(it.id)} marcar={() => sel.alternar(it.id)} />)}
      </div>
      {panel && <PanelModal ids={ids.slice(0, 40)} cliente={cliente} cerrar={() => setPanel(false)} />}
      {abierto != null && <Detalle id={abierto} cerrar={() => setAbierto(null)} />}
    </div>
  );
}
