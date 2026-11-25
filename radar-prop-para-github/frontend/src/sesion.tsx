import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { alCambiarSesion, renovar, type Usuario } from "./api";

type Sesion = { estado: "cargando" | "fuera" | "dentro"; usuario: Usuario | null; debeCambiar: boolean };
const Ctx = createContext<Sesion>({ estado: "cargando", usuario: null, debeCambiar: false });

export function SesionProvider({ children }: { children: ReactNode }) {
  const [s, setS] = useState<Sesion>({ estado: "cargando", usuario: null, debeCambiar: false });
  useEffect(() => {
    const quitar = alCambiarSesion((t) =>
      setS(t ? { estado: "dentro", usuario: t.usuario, debeCambiar: t.debe_cambiar_password } : { estado: "fuera", usuario: null, debeCambiar: false }));
    renovar().then((t) =>
      setS(t ? { estado: "dentro", usuario: t.usuario, debeCambiar: t.debe_cambiar_password } : { estado: "fuera", usuario: null, debeCambiar: false }));
    return () => { quitar(); };
  }, []);
  return <Ctx.Provider value={s}>{children}</Ctx.Provider>;
}

export const useSesion = () => useContext(Ctx);
