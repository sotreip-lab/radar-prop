/* Filtros y zona compartidos entre Buscar, Mapa y Selección. Se recuerdan en esta pestaña del navegador. */
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { FILTROS_INICIALES, type Filtros, type Zona } from "./tipos";

type B = {
  filtros: Filtros; zona: Zona | null;
  setFiltros: (f: Filtros | ((f: Filtros) => Filtros)) => void; setZona: (z: Zona | null) => void;
  cambiar: <K extends keyof Filtros>(k: K, v: Filtros[K]) => void; reiniciar: () => void;
};
const Ctx = createContext<B | null>(null);

function leer(): { filtros: Filtros; zona: Zona | null } {
  try {
    const j = JSON.parse(sessionStorage.getItem("rp_busqueda") || "null");
    if (j) return { filtros: { ...FILTROS_INICIALES, ...j.filtros }, zona: j.zona ?? null };
  } catch { /* nada guardado */ }
  return { filtros: FILTROS_INICIALES, zona: null };
}

export function BusquedaProvider({ children }: { children: ReactNode }) {
  const inicial = leer();
  const [filtros, setFiltros] = useState<Filtros>(inicial.filtros);
  const [zona, setZona] = useState<Zona | null>(inicial.zona);
  useEffect(() => {
    try { sessionStorage.setItem("rp_busqueda", JSON.stringify({ filtros, zona })); } catch { /* sin almacenamiento */ }
  }, [filtros, zona]);
  const cambiar = <K extends keyof Filtros>(k: K, v: Filtros[K]) => setFiltros((f) => ({ ...f, [k]: v }));
  const reiniciar = () => { setFiltros({ ...FILTROS_INICIALES, oper: filtros.oper, mon: filtros.mon, ciudad: filtros.ciudad }); setZona(null); };
  return <Ctx.Provider value={{ filtros, zona, setFiltros, setZona, cambiar, reiniciar }}>{children}</Ctx.Provider>;
}

export function useBusqueda() {
  const c = useContext(Ctx);
  if (!c) throw new Error("falta BusquedaProvider");
  return c;
}
