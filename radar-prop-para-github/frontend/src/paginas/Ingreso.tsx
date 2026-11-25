import { useState, type FormEvent } from "react";
import { ingresar } from "../api";

export default function Ingreso() {
  const [usuario, setUsuario] = useState("");
  const [clave, setClave] = useState("");
  const [error, setError] = useState("");
  const [cargando, setCargando] = useState(false);
  async function enviar(e: FormEvent) {
    e.preventDefault();
    setError("");
    setCargando(true);
    try {
      await ingresar(usuario.trim(), clave);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCargando(false);
    }
  }
  return (
    <div className="ingreso">
      <form onSubmit={enviar}>
        <div className="logo"><img src="/icono.svg" alt="" /><div><h1>Radar Prop</h1><p>Guillermo Badenheuer Inmobiliaria</p></div></div>
        <label className="campo"><span>Usuario o email</span>
          <input type="text" autoComplete="username" autoCapitalize="none" value={usuario} onChange={(e) => setUsuario(e.target.value)} required /></label>
        <label className="campo"><span>Contraseña</span>
          <input type="password" autoComplete="current-password" value={clave} onChange={(e) => setClave(e.target.value)} required /></label>
        {error && <div className="aviso error" role="alert">{error}</div>}
        <button className="btn" disabled={cargando}>{cargando ? "Ingresando…" : "Ingresar"}</button>
        <p className="chico">¿No tenés usuario o te olvidaste la contraseña? Pedíselo al administrador: la genera desde la pantalla Equipo.</p>
      </form>
    </div>
  );
}
