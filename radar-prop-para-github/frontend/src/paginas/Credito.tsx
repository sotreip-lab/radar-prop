import { useState } from "react";
import SimCredito from "../componentes/SimCredito";
import { useCredito } from "../hooks";

export default function Credito({ pc = false }: { pc?: boolean }) {
  const c = useCredito();
  const [precio, setPrecio] = useState(100000);
  const [mon, setMon] = useState<"USD" | "ARS">("USD");
  if (c.isLoading) return <div className="esqueleto" style={{ height: 120 }} />;
  if (c.isError) return <div className="aviso error">{(c.error as Error).message}</div>;
  if (!c.data?.lineas.length) return <div className="vacio"><h3>Todavía no hay tasas del BCRA cargadas</h3>Se actualizan solas una vez por día.</div>;
  const dolar = c.data.dolar?.valor || 0;
  const pp = mon === "ARS" ? precio : precio * dolar;
  return (
    <div style={{ display: "grid", gap: 14, maxWidth: 980 }}>
      <h2 style={{ margin: 0 }}>Simulador de crédito hipotecario UVA</h2>
      <p className="suave" style={{ margin: 0 }}>Cargá el valor de la propiedad y elegí la línea. Las líneas que no sirven para ese valor aparecen aparte, con el motivo.</p>
      <div className="tarjeta grid-form">
        <label className="campo"><span>Valor de la propiedad</span><input type="number" value={precio || ""} onChange={(e) => setPrecio(+e.target.value || 0)} /></label>
        <label className="campo"><span>Moneda</span><select value={mon} onChange={(e) => setMon(e.target.value as "USD" | "ARS")}><option value="USD">USD</option><option value="ARS">Pesos</option></select></label>
      </div>
      {pp > 0 && <div className={pc ? "c-neg-box c-cred-box" : "tarjeta"}><SimCredito pc={pc} precioPesos={pp} moneda={mon} mostrarTitulo={false} /></div>}
    </div>
  );
}
