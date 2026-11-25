/* Versión de PC con el diseño de "El Ojo de Dios": encabezado azul con los botones y debajo la pantalla elegida. */
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api, salir } from "../api";
import { useBusqueda } from "../busqueda";
import { horaDe } from "../formato";
import { useEnLinea, useEstado } from "../hooks";
import Compradores from "../paginas/Compradores";
import Credito from "../paginas/Credito";
import Cuenta from "../paginas/Cuenta";
import Equipo from "../paginas/Equipo";
import Historial from "../paginas/Historial";
import Sector from "../paginas/Sector";
import Seleccion from "../paginas/Seleccion";
import { useSesion } from "../sesion";
import { useToast } from "../toast";
import BuscarPC from "./BuscarPC";
import "./clasico.css";

function Ojo() {
  return (
    <svg width="26" height="26" viewBox="0 0 48 48" aria-hidden="true">
      <path d="M3 24 C12 10 36 10 45 24 C36 38 12 38 3 24Z" fill="none" stroke="#f5b301" strokeWidth="3" />
      <circle cx="24" cy="24" r="8" fill="#f5b301" /><circle cx="24" cy="24" r="3.2" fill="#1f4e79" />
    </svg>
  );
}

function Pagina({ children }: { children: React.ReactNode }) {
  return <div className="c-page"><div className="c-pagebox">{children}</div></div>;
}

export default function Escritorio({ notif, pend }: { notif: number; pend: number }) {
  const s = useSesion();
  const est = useEstado();
  const enLinea = useEnLinea();
  const nav = useNavigate();
  const loc = useLocation();
  const toast = useToast();
  const { setFiltros } = useBusqueda();
  const admin = s.usuario?.rol === "admin";
  const e = est.data;
  const st = !enLinea ? "Sin conexión: se muestran los últimos datos cargados."
    : est.isError ? "No pude consultar el servidor. Puede estar despertándose (tarda hasta un minuto la primera vez del día)."
      : e ? `${e.activas.toLocaleString("es-AR")} activas${e.bajas ? ` · ${e.bajas.toLocaleString("es-AR")} bajas` : ""} · Revisado: ${e.actualizado ? horaDe(e.actualizado) : "nunca"} · se actualiza solo varias veces por día`
        : "Cargando…";
  const ir = (a: string) => nav(a);
  async function excel() {
    toast("Armando el Excel con los datos de este momento…");
    try {
      const b = await api<Blob>("/excel?fuente=BBP");
      const a = document.createElement("a");
      a.href = URL.createObjectURL(b);
      a.download = `Fichas_Venta_Bahia_Blanca_Propiedades_${new Date().toISOString().slice(0, 10)}.xlsx`;
      a.click();
    } catch (err) { toast((err as Error).message); }
  }
  const en = (a: string) => (loc.pathname === a ? { background: "rgba(255,255,255,.3)" } : undefined);
  return (
    <div className="clasico">
      <header>
        <h1 style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }} onClick={() => ir("/")}><Ojo />Radar Prop</h1>
        <div className="c-st">{st}</div>
        <button className="c-nuevas" title="Ver lo publicado en las últimas 24 horas"
          onClick={() => { setFiltros((f) => ({ ...f, nuevas_horas: 24, orden: "detectada", orden_dir: -1 })); ir("/"); }}>
          {e ? e.nuevas_24h : 0} nuevas en 24 h</button>
        <button onClick={() => window.open("/mapa-de-valores", "_blank")} title="Precio por m² por barrio según las propiedades que se dieron de baja (probables ventas)">Mapa de valores</button>
        <button onClick={() => window.open("/captacion", "_blank")} title="Dueños directos y señales para captar propiedades">Captación</button>
        <button style={en("/compradores")} className={notif ? "c-alerta" : ""} onClick={() => ir("/compradores")} title="Pedidos de tus compradores: te avisa cuando entra una propiedad que encaja">
          {notif ? `Compradores · ${notif} nueva${notif === 1 ? "" : "s"}` : "Compradores"}</button>
        <button style={en("/credito")} onClick={() => ir("/credito")} title="Simulador de crédito hipotecario UVA con las tasas del BCRA">Crédito UVA</button>
        <button style={en("/historial")} onClick={() => ir("/historial")} title="Tus búsquedas, propiedades vistas y fichas generadas">Historial</button>
        <button onClick={excel} title="Descarga el Excel de fichas con los datos de este momento">Excel actualizado</button>
        {admin && <button style={en("/equipo")} className={pend ? "c-alerta" : ""} onClick={() => ir("/equipo")} title="Usuarios del equipo y pedidos de acceso">{pend ? `Equipo · ${pend} pedido${pend === 1 ? "" : "s"}` : "Equipo"}</button>}
        <button style={en("/cuenta")} onClick={() => ir("/cuenta")} title="Tus datos, contraseña y sesiones">{s.usuario?.nombre || "Mi cuenta"}</button>
        <button onClick={() => salir()} title="Cerrar sesión en esta computadora">Salir</button>
      </header>
      <Routes>
        <Route path="/" element={<BuscarPC />} />
        <Route path="/mapa" element={<BuscarPC />} />
        <Route path="/seleccion" element={<Pagina><Seleccion /></Pagina>} />
        <Route path="/historial" element={<Pagina><Historial /></Pagina>} />
        <Route path="/compradores" element={<Pagina><Compradores /></Pagina>} />
        <Route path="/credito" element={<Pagina><Credito pc /></Pagina>} />
        <Route path="/mapa-de-valores" element={<Pagina><Sector cual="mercado" /></Pagina>} />
        <Route path="/captacion" element={<Pagina><Sector cual="captacion" /></Pagina>} />
        <Route path="/equipo" element={admin ? <Pagina><Equipo /></Pagina> : <Navigate to="/" />} />
        <Route path="/cuenta" element={<Pagina><Cuenta /></Pagina>} />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </div>
  );
}
