import { useState, type FormEvent } from "react";
import { api, ponerToken, salir } from "../api";
import { useToast } from "../toast";

export default function CambiarClave({ obligatorio = false }: { obligatorio?: boolean }) {
  const [actual, setActual] = useState("");
  const [nueva, setNueva] = useState("");
  const [repite, setRepite] = useState("");
  const [error, setError] = useState("");
  const toast = useToast();
  async function enviar(e: FormEvent) {
    e.preventDefault();
    setError("");
    if (nueva !== repite) return setError("Las dos contraseñas nuevas no coinciden.");
    try {
      const t = await api<Parameters<typeof ponerToken>[0]>("/auth/cambiar-password", { method: "POST", json: { actual, nueva } });
      ponerToken(t);
      toast("Contraseña cambiada. Se cerraron tus otras sesiones.");
      setActual(""); setNueva(""); setRepite("");
    } catch (err) {
      setError((err as Error).message);
    }
  }
  const form = (
    <form onSubmit={enviar} className={obligatorio ? "" : "tarjeta"} style={{ display: "grid", gap: 12 }}>
      {obligatorio && <div className="logo"><img src="/icono.svg" alt="" /><div><h1>Elegí tu contraseña</h1><p>La que te pasaron es temporal: antes de seguir tenés que cambiarla.</p></div></div>}
      {!obligatorio && <h3 style={{ margin: 0 }}>Cambiar contraseña</h3>}
      <label className="campo"><span>{obligatorio ? "Contraseña temporal" : "Contraseña actual"}</span>
        <input type="password" autoComplete="current-password" value={actual} onChange={(e) => setActual(e.target.value)} required /></label>
      <label className="campo"><span>Contraseña nueva (mínimo 8 caracteres, con letras y números)</span>
        <input type="password" autoComplete="new-password" value={nueva} onChange={(e) => setNueva(e.target.value)} minLength={8} required /></label>
      <label className="campo"><span>Repetí la contraseña nueva</span>
        <input type="password" autoComplete="new-password" value={repite} onChange={(e) => setRepite(e.target.value)} required /></label>
      {error && <div className="aviso error" role="alert">{error}</div>}
      <button className="btn">Guardar contraseña</button>
      {obligatorio && <button type="button" className="lnk" onClick={() => salir()}>Salir</button>}
    </form>
  );
  return obligatorio ? <div className="ingreso">{form}</div> : form;
}
