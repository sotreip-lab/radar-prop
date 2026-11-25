import { Link } from "react-router-dom";
import { IcoCaptar, IcoCredito, IcoEquipo, IcoExcel, IcoPersonas, IcoValores } from "../componentes/Iconos";
import { useSesion } from "../sesion";
import { useToast } from "../toast";
import { api } from "../api";

async function bajarExcel(fuente: string, toast: (t: string) => void) {
  toast("Armando el Excel con los datos de este momento…");
  try {
    const b = await api<Blob>(`/excel?fuente=${fuente}`);
    const a = document.createElement("a");
    a.href = URL.createObjectURL(b);
    a.download = `Fichas_Venta_${fuente}_${new Date().toISOString().slice(0, 10)}.xlsx`;
    a.click();
  } catch (e) {
    toast((e as Error).message);
  }
}

export default function Mas({ notif }: { notif: number }) {
  const s = useSesion();
  const toast = useToast();
  return (
    <div style={{ display: "grid", gap: 14 }}>
      <div className="filas">
        <Link to="/compradores" className="fila-flex" style={{ textDecoration: "none", color: "inherit" }}><IcoPersonas className="ico" /><span className="crece">Compradores y alertas</span>{notif ? <span className="tag nueva">{notif} nuevas</span> : null}</Link>
        <Link to="/credito" className="fila-flex" style={{ textDecoration: "none", color: "inherit" }}><IcoCredito className="ico" /><span className="crece">Crédito UVA</span></Link>
        <Link to="/mapa-de-valores" className="fila-flex" style={{ textDecoration: "none", color: "inherit" }}><IcoValores className="ico" /><span className="crece">Mapa de valores (m² por zona)</span></Link>
        <Link to="/captacion" className="fila-flex" style={{ textDecoration: "none", color: "inherit" }}><IcoCaptar className="ico" /><span className="crece">Captación</span></Link>
        {s.usuario?.rol === "admin" && <Link to="/equipo" className="fila-flex" style={{ textDecoration: "none", color: "inherit" }}><IcoEquipo className="ico" /><span className="crece">Equipo</span></Link>}
        <Link to="/cuenta" className="fila-flex" style={{ textDecoration: "none", color: "inherit" }}><IcoEquipo className="ico" /><span className="crece">Mi cuenta</span></Link>
      </div>
      <div className="tarjeta" style={{ display: "grid", gap: 8 }}>
        <h3 style={{ margin: 0 }}>Excel de fichas en venta</h3>
        <div className="botones" style={{ justifyContent: "flex-start" }}>
          {[["BBP", "Bahía Blanca Propiedades"], ["IBB", "IBB"], ["ZP", "ZonaProp"]].map(([f, n]) => (
            <button key={f} className="btn sec" onClick={() => bajarExcel(f, toast)}><IcoExcel className="ico" />{n}</button>))}
        </div>
      </div>
    </div>
  );
}
