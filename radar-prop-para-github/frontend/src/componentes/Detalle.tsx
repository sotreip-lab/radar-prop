import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { copiar, fmt, PLAT_CORTO, PLAT_NOM, sim } from "../formato";
import { useCredito, useSeleccion } from "../hooks";
import type { Linea } from "../tipos";
import { useToast } from "../toast";
import { IcoCerrar } from "./Iconos";

type D = Record<string, unknown> & {
  id: number; fuente: string; url: string; titulo: string; tipo: string | null; operacion: string; direccion: string | null; barrio: string | null;
  ciudad: string | null; inmobiliaria: string | null; moneda: string | null; precio: number | null; precio_publicado: number | null;
  dormitorios: number | null; banos: number | null; sup_cub: number | null; sup_tot: number | null; m2_base: number | null;
  exterior: string | null; estacionamiento: string | null; amoblado: string | null; pago: string | null; antiguedad: string | null;
  estado: string | null; pileta: string | null; parrilla: string | null; apto_credito: string | null; descripcion: string; fotos: string[];
  pub_titulo: string; ultima_verif: string; fecha_baja: string | null; estado_aviso: string; ficha: string; negociar: [string, string][];
  otro_precio: { id: number; fuente: string; inmobiliaria: string | null; precio: number; moneda: string; url: string }[] | null;
  margen: string; alertas_ia: string[]; ia_resumen: string | null; credito_posible: boolean; id_externo: string; lat: number | null; lng: number | null;
  precio_falso: number | null;
};

export function calcCuota(precioPesos: number, l: Linea, anios: number, ltv: number, uva?: number) {
  anios = Math.min(anios, Math.floor(l.plazo / 12));
  ltv = Math.min(ltv || l.ltv, l.ltv);
  let prestamo = (precioPesos * ltv) / 100;
  if (l.monto_max && prestamo > l.monto_max) prestamo = l.monto_max;
  const n = anios * 12, i = Math.pow(1 + l.tea / 100, 1 / 12) - 1, cuota = (prestamo * i) / (1 - Math.pow(1 + i, -n));
  return {
    cuota, prestamo, anios, ltv: Math.round((prestamo / precioPesos) * 100), anticipo: precioPesos - prestamo,
    ingreso: Math.max(cuota / (l.rci / 100), l.ingreso_min || 0), cuotaUva: uva ? cuota / uva : null, uvas: uva ? prestamo / uva : null,
  };
}

function Credito({ d }: { d: D }) {
  const c = useCredito();
  const lineas = useMemo(() => c.data?.lineas || [], [c.data]);
  const def = c.data?.linea_defecto;
  const [idx, setIdx] = useState(-1);
  const [anios, setAnios] = useState(20);
  const [ltv, setLtv] = useState(0);
  useEffect(() => { if (def && idx < 0) { setIdx(Math.max(0, lineas.findIndex((l) => l.banco === def.banco && l.linea === def.linea && l.tea === def.tea))); setAnios(c.data?.plazo_anios || 20); } }, [def, lineas, idx, c.data]);
  if (!c.data || !lineas.length || idx < 0) return null;
  const dolar = c.data.dolar?.valor || 0;
  const pp = d.moneda === "ARS" ? ((d.precio || 0) >= 15e6 ? d.precio : null) : d.precio && dolar ? d.precio * dolar : null;
  if (!pp) return null;
  const l = lineas[idx];
  const r = calcCuota(pp, l, anios, ltv || l.ltv, c.data.uva?.valor);
  const S = (v: number) => (d.moneda === "USD" && dolar ? `$ ${fmt(v)} (USD ${fmt(v / dolar)})` : `$ ${fmt(v)}`);
  const apto = /^Sí/.test(d.apto_credito || "");
  return (
    <section className="det-sec">
      <h3>Crédito hipotecario UVA {!apto && <span className="chico" style={{ color: "var(--amarillo)" }}>· el aviso no dice que sea apto crédito</span>}</h3>
      <div className="grid-form">
        <label className="campo"><span>Línea</span>
          <select value={idx} onChange={(e) => setIdx(+e.target.value)}>
            {lineas.map((x, i) => <option key={i} value={i}>{x.banco} · {x.linea} · TEA {String(x.tea).replace(".", ",")}% · {x.beneficiario}</option>)}
          </select></label>
        <label className="campo"><span>Plazo</span>
          <select value={anios} onChange={(e) => setAnios(+e.target.value)}>
            {[10, 15, 20, 25, 30].map((a) => <option key={a} value={a} disabled={a > Math.floor(l.plazo / 12)}>{a} años</option>)}
          </select></label>
        <label className="campo"><span>Financia (%) — máximo {l.ltv}</span>
          <input type="number" min={10} max={100} step={5} value={ltv || ""} placeholder={`${l.ltv}`} onChange={(e) => setLtv(+e.target.value || 0)} /></label>
      </div>
      <div className="cred-grid">
        <div><span className="suave chico">Cuota inicial</span><b className="num">$ {fmt(r.cuota)}/mes</b>{r.cuotaUva ? <small>{r.cuotaUva.toFixed(1).replace(".", ",")} UVAs fijas</small> : null}</div>
        <div><span className="suave chico">Préstamo ({r.ltv}%)</span><b className="num">{S(r.prestamo)}</b></div>
        <div><span className="suave chico">Anticipo que necesita</span><b className="num">{S(r.anticipo)}</b><small>más gastos de escritura</small></div>
        <div><span className="suave chico">Ingreso mínimo del hogar</span><b className="num">$ {fmt(r.ingreso)}/mes</b><small>la cuota no puede pasar el {l.rci}% del ingreso</small></div>
      </div>
      {l.monto_max && r.prestamo >= l.monto_max - 1 ? <p style={{ color: "var(--amarillo)" }}>Tope de la línea: $ {fmt(l.monto_max)}. El resto va al anticipo.</p> : null}
      <p className="suave chico">Tasas del BCRA (régimen de transparencia{c.data.lineas_leidas ? `, leídas ${c.data.lineas_leidas}` : ""}) · UVA $ {fmt(c.data.uva?.valor)} · dólar {c.data.dolar?.tipo || ""} $ {fmt(dolar)}. La cuota es la inicial: en pesos se ajusta por UVA. Es una estimación: el banco define el monto al evaluar al cliente. No incluye gastos de escritura ni seguros.</p>
    </section>
  );
}

export default function Detalle({ id, cerrar }: { id: number; cerrar: () => void }) {
  const q = useQuery({ queryKey: ["propiedad", id], queryFn: () => api<D>(`/propiedades/${id}`) });
  const sel = useSeleccion();
  const toast = useToast();
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && cerrar();
    document.addEventListener("keydown", esc);
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", esc); document.body.style.overflow = ""; };
  }, [cerrar]);
  const d = q.data;
  const marcada = sel.ids.has(id);
  const kv: [string, unknown][] = d ? [
    ["Operación", d.operacion], ["Dormitorios", d.dormitorios === 0 ? "Monoambiente" : d.dormitorios], ["Baños", d.banos],
    ["m² cubiertos", d.sup_cub ? fmt(d.sup_cub) : null], ["m² totales", d.sup_tot ? fmt(d.sup_tot) : null],
    ["Espacio exterior", d.exterior], ["Estacionamiento", d.estacionamiento], ["Pileta", d.pileta], ["Parrilla o quincho", d.parrilla],
    ["Amoblado", d.amoblado || "No figura"], ["Pago", d.pago], ["Antigüedad", d.antiguedad], ["Estado", d.estado],
    ["Publicación", d.pub_titulo], ["Última verificación", d.ultima_verif], ["Dada de baja", d.fecha_baja || "—"],
    ["Referencia", d.fuente === "BBP" ? `Aviso ${d.id_externo}` : `${PLAT_NOM[d.fuente] || d.fuente} · ${d.id}`],
  ] : [];
  return (
    <div className="hoja" role="dialog" aria-modal="true" aria-label="Detalle de la propiedad">
      <div className="velo" onClick={cerrar} />
      <div className="caja">
        <div className="cab">
          <button className="btn sec chico" onClick={cerrar} aria-label="Cerrar"><IcoCerrar className="ico" /></button>
          <h2>{d ? [d.tipo, d.barrio || d.ciudad].filter(Boolean).join(" en ") : "Cargando…"}</h2>
          {d && <b className="num">{d.precio ? `${sim(d.moneda)} ${fmt(d.precio)}` : d.precio_falso ? "Precio no real" : "Consultar"}</b>}
        </div>
        {q.isLoading && <div style={{ padding: 16 }}><div className="esqueleto" style={{ height: 220 }} /></div>}
        {q.isError && <div className="det-sec"><div className="aviso error">{(q.error as Error).message} <button className="lnk" onClick={() => q.refetch()}>Reintentar</button></div></div>}
        {d && (
          <>
            {d.fotos?.length ? <div className="galeria">{d.fotos.map((u) => <img key={u} src={u} alt="" loading="lazy" />)}</div> : null}
            <section className="det-sec fila-flex">
              <span className={`ptag ${d.fuente}`}>{PLAT_CORTO[d.fuente] || d.fuente}</span>
              <span className="crece">{d.direccion}{d.ciudad ? `, ${d.ciudad}` : ""} · {d.inmobiliaria || "inmobiliaria sin verificar"}</span>
              <a className="btn sec chico" href={d.url} target="_blank" rel="noreferrer">Ver aviso</a>
              {d.lat && <a className="btn sec chico" href={`https://www.google.com/maps?q=${d.lat},${d.lng}`} target="_blank" rel="noreferrer">Ubicación</a>}
              <button className={`btn chico${marcada ? " sec" : ""}`} onClick={() => sel.alternar(id)}>{marcada ? "Quitar de la selección" : "Marcar"}</button>
            </section>
            {d.estado_aviso === "baja" && <div className="det-sec"><div className="aviso error">Esta publicación se dio de baja.</div></div>}
            {(d.negociar.length > 0 || d.otro_precio) && (
              <section className="det-sec">
                <h3>Para negociar y asesorar{d.margen ? ` · margen de negociación ${d.margen === "alto" ? "ALTO" : "medio"}` : ""}</h3>
                <ul className="negociar">
                  {d.negociar.map(([k, v]) => <li key={k}><b>{k}:</b> {v}</li>)}
                  {d.otro_precio && <li><b>Misma propiedad, otro precio:</b> {d.otro_precio.map((x) => (
                    <span key={x.id}> <a href={x.url} target="_blank" rel="noreferrer">{PLAT_CORTO[x.fuente]}</a> {x.inmobiliaria}: {sim(x.moneda)} {fmt(x.precio)}
                      {d.precio ? ` (${x.precio < d.precio ? "−" : "+"}${Math.abs((x.precio / d.precio - 1) * 100).toFixed(1).replace(".", ",")}%)` : ""};</span>))}
                    <span className="suave"> (posible: misma dirección, tipo y dormitorios)</span></li>}
                </ul>
              </section>
            )}
            {d.credito_posible && <Credito d={d} />}
            <section className="det-sec">
              <h3>Ficha para WhatsApp</h3>
              <div className="ficha-wa">{d.ficha}</div>
              <div className="botones" style={{ marginTop: 8 }}>
                <button className="btn sec chico" onClick={() => copiar(d.ficha + "\n" + d.url).then(() => toast("Ficha copiada: pegala en WhatsApp"))}>Copiar ficha</button>
                <a className="btn chico" href={`https://wa.me/?text=${encodeURIComponent(d.ficha + "\n" + d.url)}`} target="_blank" rel="noreferrer">Mandar por WhatsApp</a>
              </div>
            </section>
            <section className="det-sec"><div className="kv">{kv.filter(([, v]) => v != null && v !== "").map(([k, v]) => <div key={k}><span>{k}</span>{String(v)}</div>)}</div></section>
            {d.ia_resumen && <section className="det-sec"><b>Análisis IA:</b> {d.ia_resumen}{d.alertas_ia?.length ? <><br /><b>Alertas:</b> {d.alertas_ia.join(" · ")}</> : null}</section>}
            <section className="det-sec"><h3>{d.titulo}</h3><div className="desc">{d.descripcion}</div>
              <p className="suave chico">* = dato leído de la descripción (no figura en los campos de la ficha).</p></section>
          </>
        )}
      </div>
    </div>
  );
}
