import { useState, type FormEvent } from "react";
import { api, ingresar } from "../api";

type Pedido = { nombre: string; apellido: string; usuario: string; email: string; telefono: string; password: string; repetir: string };
const VACIO: Pedido = { nombre: "", apellido: "", usuario: "", email: "", telefono: "", password: "", repetir: "" };

function Logo() {
  return <div className="logo"><img src="/icono.svg" alt="" /><div><h1>Radar Prop</h1><p>Guillermo Badenheuer Inmobiliaria</p></div></div>;
}

function SolicitarAcceso({ volver }: { volver: (usuario?: string) => void }) {
  const [p, setP] = useState<Pedido>(VACIO);
  const [error, setError] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [enviado, setEnviado] = useState(false);
  const set = (k: keyof Pedido, v: string) => setP((x) => ({ ...x, [k]: v }));
  async function enviar(e: FormEvent) {
    e.preventDefault();
    setError("");
    if (p.password !== p.repetir) return setError("Las dos contraseñas no coinciden.");
    setEnviando(true);
    try {
      await api("/auth/solicitar-acceso", { method: "POST", json: { nombre: p.nombre.trim(), apellido: p.apellido.trim(), usuario: p.usuario.trim(),
        email: p.email.trim() || null, telefono: p.telefono.trim() || null, password: p.password } });
      setEnviado(true);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setEnviando(false);
    }
  }
  if (enviado) {
    return (
      <div className="ingreso"><div className="tarjeta-ingreso">
        <Logo />
        <h2 style={{ margin: 0 }}>Solicitud enviada</h2>
        <p>El administrador tiene que aprobarla. Cuando lo haga, vas a poder ingresar con el usuario <b>{p.usuario.trim()}</b> y la contraseña que elegiste.</p>
        <button className="btn" onClick={() => volver(p.usuario.trim())}>Volver al ingreso</button>
      </div></div>
    );
  }
  return (
    <div className="ingreso">
      <form onSubmit={enviar}>
        <Logo />
        <h2 style={{ margin: 0 }}>Pedir acceso</h2>
        <p className="chico">Completá tus datos. El administrador revisa el pedido y te habilita.</p>
        <div className="dos-col">
          <label className="campo"><span>Nombre</span><input type="text" autoComplete="given-name" value={p.nombre} onChange={(e) => set("nombre", e.target.value)} required /></label>
          <label className="campo"><span>Apellido</span><input type="text" autoComplete="family-name" value={p.apellido} onChange={(e) => set("apellido", e.target.value)} /></label>
        </div>
        <label className="campo"><span>Usuario para ingresar</span>
          <input type="text" autoComplete="username" autoCapitalize="none" value={p.usuario} onChange={(e) => set("usuario", e.target.value)}
            required minLength={3} pattern="[A-Za-z0-9._\-]+" title="Solo letras, números, punto, guion o guion bajo, sin espacios" /></label>
        <label className="campo"><span>Teléfono (opcional)</span><input type="tel" autoComplete="tel" value={p.telefono} onChange={(e) => set("telefono", e.target.value)} /></label>
        <label className="campo"><span>Email (opcional)</span><input type="email" autoComplete="email" value={p.email} onChange={(e) => set("email", e.target.value)} /></label>
        <label className="campo"><span>Contraseña</span><input type="password" autoComplete="new-password" value={p.password} onChange={(e) => set("password", e.target.value)} required /></label>
        <label className="campo"><span>Repetí la contraseña</span><input type="password" autoComplete="new-password" value={p.repetir} onChange={(e) => set("repetir", e.target.value)} required /></label>
        <p className="chico">Mínimo 8 caracteres, con letras y números.</p>
        {error && <div className="aviso error" role="alert">{error}</div>}
        <button className="btn" disabled={enviando}>{enviando ? "Enviando…" : "Enviar solicitud"}</button>
        <button type="button" className="btn sec" onClick={() => volver()}>Ya tengo usuario</button>
      </form>
    </div>
  );
}

export default function Ingreso() {
  const [usuario, setUsuario] = useState("");
  const [clave, setClave] = useState("");
  const [error, setError] = useState("");
  const [cargando, setCargando] = useState(false);
  const [pidiendo, setPidiendo] = useState(false);
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
  if (pidiendo) return <SolicitarAcceso volver={(u) => { setPidiendo(false); if (u) setUsuario(u); }} />;
  return (
    <div className="ingreso">
      <form onSubmit={enviar}>
        <Logo />
        <label className="campo"><span>Usuario o email</span>
          <input type="text" autoComplete="username" autoCapitalize="none" value={usuario} onChange={(e) => setUsuario(e.target.value)} required /></label>
        <label className="campo"><span>Contraseña</span>
          <input type="password" autoComplete="current-password" value={clave} onChange={(e) => setClave(e.target.value)} required /></label>
        {error && <div className="aviso error" role="alert">{error}</div>}
        <button className="btn" disabled={cargando}>{cargando ? "Ingresando…" : "Ingresar"}</button>
        <button type="button" className="btn sec" onClick={() => setPidiendo(true)}>Pedir acceso</button>
        <p className="chico">¿Te olvidaste la contraseña? Pedile al administrador que te genere una nueva desde Equipo.</p>
      </form>
    </div>
  );
}
