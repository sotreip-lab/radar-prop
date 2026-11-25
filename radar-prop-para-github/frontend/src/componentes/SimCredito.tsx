import { useEffect, useMemo, useState } from "react";
import { lineaSugerida, pct, prestamoPorIngreso, simular, textoCliente } from "../credito";
import { copiar, fmt } from "../formato";
import { useCredito } from "../hooks";
import { useToast } from "../toast";

/** Simulador de crédito UVA para una propiedad (o un valor cargado a mano). Usa las condiciones reales de cada línea
    publicadas por el BCRA: tasas, plazo, % que financia, topes, valor máximo de la vivienda e ingreso mínimo. */
export default function SimCredito({ precioPesos, moneda, titulo, direccion, aptoCredito, mostrarTitulo = true, pc = false }: {
  precioPesos: number; moneda?: string | null; titulo?: string; direccion?: string | null; aptoCredito?: string | null; mostrarTitulo?: boolean;
  /** true = con el estilo de la PC (El Ojo de Dios) */ pc?: boolean;
}) {
  const k = (n: string) => n.split(" ").map((x) => (pc ? "c-" : "") + x).join(" ");
  const c = useCredito();
  const toast = useToast();
  const lineas = useMemo(() => c.data?.lineas || [], [c.data]);
  const uva = c.data?.uva?.valor;
  const dolar = c.data?.dolar?.valor || 0;
  const [idx, setIdx] = useState(-1);
  const [anios, setAnios] = useState(20);
  const [ltv, setLtv] = useState(0);
  const [ingreso, setIngreso] = useState(0);
  useEffect(() => { if (lineas.length) setIdx(lineaSugerida(precioPesos, lineas, uva, c.data?.plazo_anios || 20)); }, [lineas, precioPesos, uva, c.data?.plazo_anios]);
  const evals = useMemo(() => lineas.map((l) => simular(precioPesos, l, uva, anios)), [lineas, precioPesos, uva, anios]);
  if (!c.data || !lineas.length || idx < 0 || !precioPesos) return null;
  const l = lineas[Math.min(idx, lineas.length - 1)];
  const r = simular(precioPesos, l, uva, anios, ltv || l.ltv);
  const S = (v: number) => (moneda === "USD" && dolar ? <>$ {fmt(v)} <span className={pc ? "c-mute" : "suave"}>(USD {fmt(v / dolar)})</span></> : <>$ {fmt(v)}</>);
  const apto = aptoCredito === undefined || /^Sí/.test(aptoCredito || "");
  const opcion = (i: number) => {
    const x = lineas[i];
    return <option key={i} value={i}>{x.banco} · {x.linea} · TEA {String(x.tea).replace(".", ",")}% · {x.beneficiario}{evals[i].califica ? "" : " (no califica)"}</option>;
  };
  const califican = lineas.map((_, i) => i).filter((i) => evals[i].califica).sort((a, b) => lineas[a].tea - lineas[b].tea);
  const noCalifican = lineas.map((_, i) => i).filter((i) => !evals[i].califica).sort((a, b) => lineas[a].tea - lineas[b].tea);
  const porIngreso = ingreso ? prestamoPorIngreso(ingreso, l, r.anios) : null;
  return (
    <div className={k("cred-sim")}>
      {mostrarTitulo && <div className={k("cred-tit")}>Crédito hipotecario UVA {!apto && <span className={k("cred-aviso")}>· el aviso no dice que sea apto crédito</span>}</div>}
      <div className={k("cred-ctrl")}>
        <select aria-label="Línea de crédito" value={idx} onChange={(e) => setIdx(+e.target.value)}>
          {califican.length > 0 && <optgroup label={`Califican para esta propiedad (${califican.length})`}>{califican.map(opcion)}</optgroup>}
          {noCalifican.length > 0 && <optgroup label={`No califican (${noCalifican.length})`}>{noCalifican.map(opcion)}</optgroup>}
        </select>
        <span className={k("cred-par")}><select aria-label="Plazo en años" value={anios} onChange={(e) => setAnios(+e.target.value)}>
          {[5, 10, 15, 20, 25, 30].map((a) => <option key={a} value={a} disabled={a > r.plazoMax}>{a}</option>)}
        </select> años</span>
        <span className={k("cred-par")}>financia <input aria-label="Porcentaje que financia" type="number" min={10} max={l.ltv} step={5} value={ltv || ""} placeholder={`${l.ltv}`} onChange={(e) => setLtv(+e.target.value || 0)} />%</span>
        <span className={k("cred-par")}>ingreso del hogar $ <input aria-label="Ingreso del hogar" className={k("cred-ing")} type="number" min={0} step={50000} value={ingreso || ""} placeholder="opcional" onChange={(e) => setIngreso(+e.target.value || 0)} /></span>
      </div>
      <div className={k(`cred-estado ${r.califica ? "ok" : "no"}`)}>
        {r.califica ? <>Califica para esta línea</> : <>No califica: {r.motivos.join("; ")}</>}
      </div>
      <div className={k("cred-grid")}>
        <div><span className={pc ? "c-mute" : "suave"}>Cuota inicial</span><b>$ {fmt(r.cuota)}/mes</b>{r.cuotaUva ? <small>{r.cuotaUva.toFixed(1).replace(".", ",")} UVAs fijas</small> : null}</div>
        <div><span className={pc ? "c-mute" : "suave"}>Préstamo ({r.ltv}%)</span><b>{S(r.prestamo)}</b>{r.uvas ? <small>{fmt(r.uvas)} UVAs</small> : null}</div>
        <div><span className={pc ? "c-mute" : "suave"}>Anticipo que necesita</span><b>{S(r.anticipo)}</b><small>más gastos de escritura</small></div>
        <div><span className={pc ? "c-mute" : "suave"}>Ingreso mínimo del hogar</span><b>$ {fmt(r.ingreso)}/mes</b><small>{l.ingreso_min && r.ingreso <= l.ingreso_min + 1 ? "mínimo que pide el banco" : `la cuota no puede pasar el ${l.rci}% del ingreso`}</small></div>
      </div>
      {porIngreso && (
        <div className={k(`cred-estado ${ingreso >= r.ingreso ? "ok" : "no"}`)}>
          {ingreso >= r.ingreso
            ? <>Con $ {fmt(ingreso)} de ingreso le alcanza para esta cuota.</>
            : <>Con $ {fmt(ingreso)} de ingreso puede pagar hasta $ {fmt(porIngreso.cuotaMax)}/mes: el préstamo llega a ≈ $ {fmt(Math.min(porIngreso.prestamo, r.prestamo))}{dolar ? ` (USD ${fmt(Math.min(porIngreso.prestamo, r.prestamo) / dolar)})` : ""}{l.ingreso_min && ingreso < l.ingreso_min ? `, y el banco pide un ingreso de al menos $ ${fmt(l.ingreso_min)}` : ""}.</>}
        </div>
      )}
      <div className={k("cred-datos")}>
        TNA {pct(l.tna)} · TEA {pct(l.tea)} · CFTEA {pct(l.cft)} · plazo hasta {r.plazoMax} años · financia hasta {l.ltv}% · cuota hasta el {l.rci}% del ingreso
        {l.monto_max_uva && uva ? <> · préstamo máximo {fmt(l.monto_max_uva)} UVAs (≈ $ {fmt(l.monto_max_uva * uva)})</> : l.monto_max ? <> · préstamo máximo $ {fmt(l.monto_max)}</> : null}
        {l.valor_max_uva && uva ? <> · vivienda de hasta {fmt(l.valor_max_uva)} UVAs (≈ $ {fmt(l.valor_max_uva * uva)}{dolar ? ` · USD ${fmt((l.valor_max_uva * uva) / dolar)}` : ""})</> : null}
        {l.monto_min ? <> · préstamo mínimo $ {fmt(l.monto_min)}</> : null}
      </div>
      {r.tope ? <div className={k("cred-aviso")}>El préstamo llega al tope de la línea: el resto va al anticipo.</div> : null}
      {l.requisitos?.length ? <ul className={k("cred-req")}>{l.requisitos.map((x) => <li key={x}>{x}</li>)}</ul> : null}
      {l.nota ? <div className={k("cred-nota")}>Texto del banco: {l.nota}</div> : null}
      <div className={k("cred-pie")}>
        <button type="button" className={k("btn sec chico")} onClick={() => copiar(textoCliente({ titulo, direccion }, l, r, uva, dolar)).then(() => toast("Simulación copiada"))}>Copiar simulación para el cliente</button>
        <span className={pc ? "c-mute" : "suave"}>Datos del BCRA (régimen de transparencia{c.data.lineas_leidas ? `, leídos ${c.data.lineas_leidas}` : ""}) · UVA $ {fmt(uva)}{c.data.uva?.fecha ? ` (${c.data.uva.fecha.split("-").reverse().join("/")})` : ""} · dólar {c.data.dolar?.tipo || ""} $ {fmt(dolar)}. La cuota es la inicial y se ajusta por UVA. No incluye seguros ni gastos de escritura; el banco confirma el monto al evaluar al cliente.</span>
      </div>
    </div>
  );
}
