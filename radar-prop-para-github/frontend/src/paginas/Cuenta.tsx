import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, salir } from "../api";
import { fechaHora } from "../formato";
import { useSesion } from "../sesion";
import { useToast } from "../toast";
import CambiarClave from "./CambiarClave";

type S = { id: number; dispositivo: string | null; ip: string | null; creada_en: string; ultima_actividad: string; actual: boolean };

function dispositivo(ua: string | null) {
  if (!ua) return "Dispositivo desconocido";
  const so = /iPhone|iPad/.test(ua) ? "iPhone" : /Android/.test(ua) ? "Android" : /Windows/.test(ua) ? "Windows" : /Mac OS/.test(ua) ? "Mac" : "Otro";
  const nav = /Edg\//.test(ua) ? "Edge" : /Chrome\//.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : /Firefox\//.test(ua) ? "Firefox" : "";
  return `${so}${nav ? ` · ${nav}` : ""}`;
}

export default function Cuenta() {
  const s = useSesion();
  const qc = useQueryClient();
  const toast = useToast();
  const [tema, setTema] = useState(localStorage.getItem("rp_tema") || "auto");
  const ses = useQuery({ queryKey: ["mis-sesiones"], queryFn: () => api<S[]>("/me/sesiones") });
  const cerrar = useMutation({ mutationFn: (id: number) => api(`/me/sesiones/${id}`, { method: "DELETE" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["mis-sesiones"] }) });
  function cambiarTema(t: string) {
    setTema(t);
    if (t === "auto") localStorage.removeItem("rp_tema"); else localStorage.setItem("rp_tema", t);
    const oscuro = t === "auto" ? matchMedia("(prefers-color-scheme: dark)").matches : t === "oscuro";
    document.documentElement.dataset.tema = oscuro ? "oscuro" : "claro";
  }
  async function importar() {
    const t = prompt("Pegá acá el código que te da El Ojo de Dios (botón \"Pasar mi selección a Radar Prop\")");
    if (!t) return;
    const ids = t.split(/[^\d]+/).filter(Boolean).map(Number);
    if (!ids.length) return toast("No encontré números de propiedades en ese código");
    const r = await api<{ importadas: number; no_encontradas: number }>("/selecciones/importar-ojo-de-dios", { method: "POST", json: { ids_legado: ids } });
    qc.invalidateQueries({ queryKey: ["seleccion"] });
    toast(`Importadas ${r.importadas}${r.no_encontradas ? ` (${r.no_encontradas} ya no existen)` : ""}`);
  }
  return (
    <div style={{ display: "grid", gap: 14, maxWidth: 720 }}>
      <div className="tarjeta"><h3 style={{ marginTop: 0 }}>{s.usuario?.nombre} {s.usuario?.apellido}</h3>
        <div className="suave">Usuario {s.usuario?.usuario} · {s.usuario?.rol === "admin" ? "Administrador" : "Agente"}</div></div>
      <CambiarClave />
      <div className="tarjeta" style={{ display: "grid", gap: 8 }}>
        <h3 style={{ margin: 0 }}>Dónde tenés la sesión abierta</h3>
        {ses.data?.map((x) => (
          <div key={x.id} className="fila-flex">
            <div className="crece"><b>{dispositivo(x.dispositivo)}</b>{x.actual && " · este dispositivo"}<div className="suave chico">Último uso {fechaHora(x.ultima_actividad)}</div></div>
            {!x.actual && <button className="btn sec chico" onClick={() => cerrar.mutate(x.id)}>Cerrar</button>}
          </div>
        ))}
      </div>
      <div className="tarjeta" style={{ display: "grid", gap: 8 }}>
        <h3 style={{ margin: 0 }}>Apariencia</h3>
        <div className="seg">{[["auto", "Como el teléfono"], ["claro", "Claro"], ["oscuro", "Oscuro"]].map(([v, t]) => <button key={v} aria-pressed={tema === v} onClick={() => cambiarTema(v)}>{t}</button>)}</div>
      </div>
      <div className="tarjeta" style={{ display: "grid", gap: 8 }}>
        <h3 style={{ margin: 0 }}>Importar mis datos de El Ojo de Dios</h3>
        <p className="suave" style={{ margin: 0 }}>Pasa tu selección guardada en El Ojo de Dios a tu cuenta. Los compradores ya están en Radar Prop.</p>
        <div><button className="btn sec" onClick={importar}>Importar mi selección</button></div>
      </div>
      <div><button className="btn sec" onClick={() => salir()}>Cerrar sesión</button></div>
    </div>
  );
}
