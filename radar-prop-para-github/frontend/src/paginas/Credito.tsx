import { useState } from "react";
import { calcCuota } from "../componentes/Detalle";
import { fmt } from "../formato";
import { useCredito } from "../hooks";

export default function Credito() {
  const c = useCredito();
  const [precio, setPrecio] = useState(100000);
  const [mon, setMon] = useState<"USD" | "ARS">("USD");
  const [idx, setIdx] = useState(0);
  const [anios, setAnios] = useState(20);
  const [ltv, setLtv] = useState(0);
  if (c.isLoading) return <div className="esqueleto" style={{ height: 120 }} />;
  if (c.isError) return <div className="aviso error">{(c.error as Error).message}</div>;
  const lineas = c.data?.lineas || [];
  if (!lineas.length) return <div className="vacio"><h3>Todavía no hay tasas del BCRA cargadas</h3>Se actualizan solas una vez por día.</div>;
  const l = lineas[Math.min(idx, lineas.length - 1)];
  const dolar = c.data?.dolar?.valor || 0;
  const pp = mon === "ARS" ? precio : precio * dolar;
  const r = pp ? calcCuota(pp, l, anios, ltv || l.ltv, c.data?.uva?.valor) : null;
  return (
    <div style={{ display: "grid", gap: 14, maxWidth: 900 }}>
      <h2 style={{ margin: 0 }}>Crédito hipotecario UVA</h2>
      <div className="tarjeta grid-form">
        <label className="campo"><span>Precio de la propiedad</span><input type="number" value={precio || ""} onChange={(e) => setPrecio(+e.target.value || 0)} /></label>
        <label className="campo"><span>Moneda</span><select value={mon} onChange={(e) => setMon(e.target.value as "USD" | "ARS")}><option value="USD">USD</option><option value="ARS">Pesos</option></select></label>
        <label className="campo" style={{ gridColumn: "1 / -1" }}><span>Línea</span>
          <select value={idx} onChange={(e) => setIdx(+e.target.value)}>{lineas.map((x, i) => <option key={i} value={i}>{x.banco} · {x.linea} · TEA {String(x.tea).replace(".", ",")}% · financia hasta {x.ltv}% · {x.beneficiario}</option>)}</select></label>
        <label className="campo"><span>Plazo</span><select value={anios} onChange={(e) => setAnios(+e.target.value)}>{[10, 15, 20, 25, 30].map((a) => <option key={a} value={a} disabled={a > Math.floor(l.plazo / 12)}>{a} años</option>)}</select></label>
        <label className="campo"><span>Financia (%) — máximo {l.ltv}</span><input type="number" value={ltv || ""} placeholder={`${l.ltv}`} onChange={(e) => setLtv(+e.target.value || 0)} /></label>
      </div>
      {r && (
        <div className="cred-grid">
          <div><span className="suave chico">Cuota inicial</span><b className="num">$ {fmt(r.cuota)}/mes</b>{r.cuotaUva ? <small>{r.cuotaUva.toFixed(1).replace(".", ",")} UVAs fijas</small> : null}</div>
          <div><span className="suave chico">Préstamo ({r.ltv}%)</span><b className="num">$ {fmt(r.prestamo)}</b></div>
          <div><span className="suave chico">Anticipo que necesita</span><b className="num">$ {fmt(r.anticipo)}</b><small>más gastos de escritura</small></div>
          <div><span className="suave chico">Ingreso mínimo del hogar</span><b className="num">$ {fmt(r.ingreso)}/mes</b><small>la cuota no puede pasar el {l.rci}% del ingreso</small></div>
        </div>
      )}
      {l.nota && <p className="suave chico">{l.nota}</p>}
      <p className="suave chico">Tasas del BCRA (régimen de transparencia{c.data?.lineas_leidas ? `, leídas ${c.data.lineas_leidas}` : ""}) · UVA $ {fmt(c.data?.uva?.valor)} · dólar {c.data?.dolar?.tipo || ""} $ {fmt(dolar)}. La cuota es la inicial: en pesos se ajusta por UVA. Es una estimación: el banco define el monto al evaluar al cliente.</p>
    </div>
  );
}
