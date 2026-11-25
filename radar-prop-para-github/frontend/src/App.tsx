import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { api } from "./api";
import { IcoBuscar, IcoCaptar, IcoCredito, IcoEquipo, IcoHist, IcoMapa, IcoMas, IcoPersonas, IcoSel, IcoValores } from "./componentes/Iconos";
import { horaDe } from "./formato";
import { useEnLinea, useEstado, useSeleccion } from "./hooks";
import Buscar from "./paginas/Buscar";
import CambiarClave from "./paginas/CambiarClave";
import Compradores from "./paginas/Compradores";
import Credito from "./paginas/Credito";
import Cuenta from "./paginas/Cuenta";
import Equipo from "./paginas/Equipo";
import Historial from "./paginas/Historial";
import Ingreso from "./paginas/Ingreso";
import Mas from "./paginas/Mas";
import Sector from "./paginas/Sector";
import Seleccion from "./paginas/Seleccion";
import { useSesion } from "./sesion";

type Notif = { total: number; compradores: { cliente_id: number; nombre: string; cantidad: number }[] };

function Avisos() {
  // Propiedades nuevas para mis compradores: globo en el menú y notificación del navegador si la persona la aceptó.
  const q = useQuery({ queryKey: ["notificaciones"], queryFn: () => api<Notif>("/notificaciones"), refetchInterval: 120_000 });
  const antes = useRef<number | null>(null);
  useEffect(() => {
    const t = q.data?.total ?? 0;
    if (antes.current !== null && t > antes.current && "Notification" in window && Notification.permission === "granted") {
      const c = q.data!.compradores[0];
      new Notification("Radar Prop", { body: `${t - antes.current} propiedad(es) nueva(s) para ${c?.nombre || "tus compradores"}`, icon: "/icono-192.png" });
    }
    if (q.data) antes.current = t;
  }, [q.data]);
  return q.data?.total ?? 0;
}

export default function App() {
  const s = useSesion();
  if (s.estado === "cargando") return <div className="ingreso"><div className="esqueleto" style={{ width: 200, height: 20 }} /></div>;
  if (s.estado === "fuera") return <Ingreso />;
  if (s.debeCambiar) return <CambiarClave obligatorio />;
  return <Dentro />;
}

function Dentro() {
  const s = useSesion();
  const est = useEstado();
  const enLinea = useEnLinea();
  const sel = useSeleccion();
  const notif = Avisos();
  const admin = s.usuario?.rol === "admin";
  const act = est.data?.actualizado;
  const enlaces = [
    { a: "/", t: "Buscar", i: <IcoBuscar />, fin: true },
    { a: "/mapa", t: "Mapa", i: <IcoMapa /> },
    { a: "/seleccion", t: "Selección", i: <IcoSel />, n: sel.lista.length },
    { a: "/historial", t: "Historial", i: <IcoHist /> },
  ];
  return (
    <div className="app">
      <header className="barra">
        <div className="marca"><img src="/icono.svg" alt="" />Radar Prop</div>
        <div className="estado">
          {act ? <>Última actualización: <b>{horaDe(act)}</b></> : "Cargando…"}
          {est.data ? <div>{est.data.nuevas_24h} nuevas en 24 h</div> : null}
        </div>
      </header>
      <nav className="nav-lado" aria-label="Secciones">
        {enlaces.map((e) => (
          <NavLink key={e.a} to={e.a} end={e.fin} className={({ isActive }) => (isActive ? "activo" : "")}>
            {e.i}{e.t}{e.n ? <span className="globo">{e.n}</span> : null}
          </NavLink>
        ))}
        <hr />
        <NavLink to="/compradores" className={({ isActive }) => (isActive ? "activo" : "")}><IcoPersonas />Compradores{notif ? <span className="globo">{notif}</span> : null}</NavLink>
        <NavLink to="/credito" className={({ isActive }) => (isActive ? "activo" : "")}><IcoCredito />Crédito UVA</NavLink>
        <NavLink to="/mapa-de-valores" className={({ isActive }) => (isActive ? "activo" : "")}><IcoValores />Mapa de valores</NavLink>
        <NavLink to="/captacion" className={({ isActive }) => (isActive ? "activo" : "")}><IcoCaptar />Captación</NavLink>
        <hr />
        {admin && <NavLink to="/equipo" className={({ isActive }) => (isActive ? "activo" : "")}><IcoEquipo />Equipo</NavLink>}
        <NavLink to="/cuenta" className={({ isActive }) => (isActive ? "activo" : "")}><IcoEquipo />Mi cuenta</NavLink>
      </nav>
      <main className="contenido">
        {!enLinea && <div className="aviso sin-red" role="alert">Sin conexión — mostrando datos de las {act ? horaDe(act).slice(6) : "última vez"}.</div>}
        {est.isError && enLinea && <div className="aviso error">No pude consultar el servidor. Puede estar despertándose (tarda hasta un minuto la primera vez del día).</div>}
        <Routes>
          <Route path="/" element={<Buscar />} />
          <Route path="/mapa" element={<Buscar soloMapa />} />
          <Route path="/seleccion" element={<Seleccion />} />
          <Route path="/historial" element={<Historial />} />
          <Route path="/compradores" element={<Compradores />} />
          <Route path="/credito" element={<Credito />} />
          <Route path="/mapa-de-valores" element={<Sector cual="mercado" />} />
          <Route path="/captacion" element={<Sector cual="captacion" />} />
          <Route path="/equipo" element={admin ? <Equipo /> : <Navigate to="/" />} />
          <Route path="/cuenta" element={<Cuenta />} />
          <Route path="/mas" element={<Mas notif={notif} />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </main>
      <nav className="nav-abajo" aria-label="Secciones">
        {enlaces.map((e) => (
          <NavLink key={e.a} to={e.a} end={e.fin} className={({ isActive }) => (isActive ? "activo" : "")}>
            {e.i}<span>{e.t}</span>{e.n ? <span className="globo">{e.n}</span> : null}
          </NavLink>
        ))}
        <NavLink to="/mas" className={({ isActive }) => (isActive ? "activo" : "")}><IcoMas /><span>Más</span>{notif ? <span className="globo">{notif}</span> : null}</NavLink>
      </nav>
    </div>
  );
}
