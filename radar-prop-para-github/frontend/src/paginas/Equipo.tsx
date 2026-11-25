import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type Usuario } from "../api";
import { copiar, fechaHora } from "../formato";
import { useToast } from "../toast";

type U = Usuario & { creado_en: string; ultimo_ingreso: string | null; solicitud_pendiente?: boolean };
type Creado = { usuario: U; password_temporal: string; texto_whatsapp: string; link_whatsapp: string | null };
type Form = { nombre: string; apellido: string; usuario: string; email: string; telefono: string; rol: "admin" | "agente" };

function ClaveTemporal({ c, cerrar }: { c: Creado; cerrar: () => void }) {
  const toast = useToast();
  return (
    <div className="modal" role="dialog" aria-modal="true"><div className="caja">
      <h2>Contraseña temporal de {c.usuario.nombre}</h2>
      <p>Se muestra <b>una sola vez</b>. Al primer ingreso le va a pedir que la cambie.</p>
      <div className="clave-temporal">{c.password_temporal}</div>
      <p className="suave chico">Usuario: <b>{c.usuario.usuario}</b></p>
      <div className="botones">
        <button className="btn sec" onClick={() => copiar(c.password_temporal).then(() => toast("Contraseña copiada"))}>Copiar contraseña</button>
        {c.link_whatsapp && <a className="btn sec" href={c.link_whatsapp} target="_blank" rel="noreferrer">Mandar por WhatsApp</a>}
        <button className="btn" onClick={cerrar}>Listo, ya la pasé</button>
      </div>
    </div></div>
  );
}

function Editor({ u, cerrar, creado }: { u: U | null; cerrar: () => void; creado: (c: Creado) => void }) {
  const [f, setF] = useState<Form>({ nombre: u?.nombre || "", apellido: u?.apellido || "", usuario: u?.usuario || "", email: u?.email || "", telefono: u?.telefono || "", rol: u?.rol || "agente" });
  const [error, setError] = useState("");
  const qc = useQueryClient();
  const g = useMutation({
    mutationFn: (): Promise<U | Creado> => (u ? api<U>(`/admin/usuarios/${u.id}`, { method: "PATCH", json: { ...f, email: f.email || null, telefono: f.telefono || null } })
      : api<Creado>("/admin/usuarios", { method: "POST", json: { ...f, email: f.email || null, telefono: f.telefono || null } })),
    onSuccess: (r) => { qc.invalidateQueries({ queryKey: ["usuarios"] }); cerrar(); if (!u) creado(r as unknown as Creado); },
    onError: (e) => setError((e as Error).message),
  });
  const set = (k: keyof Form, v: string) => setF((x) => ({ ...x, [k]: v }));
  return (
    <div className="modal" role="dialog" aria-modal="true"><div className="caja">
      <h2>{u ? `Editar a ${u.nombre}` : "Nuevo usuario"}</h2>
      <div className="grid-form">
        <label className="campo"><span>Nombre</span><input type="text" value={f.nombre} onChange={(e) => set("nombre", e.target.value)} /></label>
        <label className="campo"><span>Apellido</span><input type="text" value={f.apellido} onChange={(e) => set("apellido", e.target.value)} /></label>
        <label className="campo"><span>Usuario (para ingresar)</span><input type="text" autoCapitalize="none" value={f.usuario} onChange={(e) => set("usuario", e.target.value)} /></label>
        <label className="campo"><span>Email (opcional)</span><input type="email" value={f.email} onChange={(e) => set("email", e.target.value)} /></label>
        <label className="campo"><span>Teléfono (opcional, para WhatsApp)</span><input type="tel" value={f.telefono} onChange={(e) => set("telefono", e.target.value)} /></label>
        <label className="campo"><span>Rol</span><select value={f.rol} onChange={(e) => set("rol", e.target.value)}><option value="agente">Agente</option><option value="admin">Administrador</option></select></label>
      </div>
      {error && <div className="aviso error" role="alert">{error}</div>}
      <div className="botones"><button className="btn sec" onClick={cerrar}>Cancelar</button><button className="btn" disabled={g.isPending} onClick={() => g.mutate()}>{u ? "Guardar" : "Crear usuario"}</button></div>
    </div></div>
  );
}

export default function Equipo() {
  const q = useQuery({ queryKey: ["usuarios"], queryFn: () => api<U[]>("/admin/usuarios") });
  const [editar, setEditar] = useState<U | null | "nuevo">(null);
  const [clave, setClave] = useState<Creado | null>(null);
  const qc = useQueryClient();
  const toast = useToast();
  const accion = useMutation({
    mutationFn: ({ u, a }: { u: U; a: "desactivar" | "reactivar" | "resetear-password" | "cerrar" | "aprobar" | "rechazar" }) =>
      a === "cerrar" ? api(`/admin/usuarios/${u.id}/sesiones`, { method: "DELETE" }) : api<U | Creado>(`/admin/usuarios/${u.id}/${a}`, { method: "POST" }),
    onSuccess: (r, v) => {
      qc.invalidateQueries({ queryKey: ["usuarios"] });
      qc.invalidateQueries({ queryKey: ["solicitudes"] });
      if (v.a === "resetear-password") setClave(r as Creado);
      else toast({ cerrar: "Se cerraron sus sesiones", desactivar: `${v.u.nombre} ya no puede entrar`, reactivar: `${v.u.nombre} puede volver a entrar`,
        aprobar: `Listo: ${v.u.nombre} ya puede ingresar`, rechazar: `Solicitud de ${v.u.nombre} rechazada` }[v.a]);
    },
    onError: (e) => toast((e as Error).message),
  });
  const pendientes = q.data?.filter((u) => u.solicitud_pendiente) ?? [];
  const resto = q.data?.filter((u) => !u.solicitud_pendiente) ?? [];
  return (
    <div style={{ display: "grid", gap: 12 }}>
      <div className="fila-flex"><h2 className="crece" style={{ margin: 0 }}>Equipo</h2><button className="btn" onClick={() => setEditar("nuevo")}>Nuevo usuario</button></div>
      <p className="suave" style={{ margin: 0 }}>Los usuarios no se borran: se desactivan, y su historial queda.</p>
      {q.isLoading && <div className="esqueleto" style={{ height: 80 }} />}
      {q.isError && <div className="aviso error">{(q.error as Error).message}</div>}
      {pendientes.length > 0 && (
        <section className="solicitudes" aria-label="Solicitudes de acceso">
          <h3>{pendientes.length === 1 ? "1 persona pide acceso" : `${pendientes.length} personas piden acceso`}</h3>
          {pendientes.map((u) => (
            <div key={u.id} className="fila-flex">
              <div className="crece">
                <b>{u.nombre} {u.apellido}</b> <span className="suave">({u.usuario})</span>
                <div className="suave chico">{[u.telefono, u.email].filter(Boolean).join(" · ") || "Sin teléfono ni email"} · pidió el {fechaHora(u.creado_en)}</div>
              </div>
              <button className="btn sec chico" onClick={() => confirm(`¿Rechazar el pedido de ${u.nombre}? Se borra la solicitud.`) && accion.mutate({ u, a: "rechazar" })}>Rechazar</button>
              <button className="btn chico" onClick={() => accion.mutate({ u, a: "aprobar" })}>Aprobar</button>
            </div>
          ))}
        </section>
      )}
      <div className="filas">
        {resto.map((u) => (
          <div key={u.id} className="fila-flex" style={u.activo ? undefined : { opacity: 0.6 }}>
            <div className="crece">
              <b>{u.nombre} {u.apellido}</b> <span className="suave">({u.usuario})</span> · {u.rol === "admin" ? "Administrador" : "Agente"}{!u.activo && " · desactivado"}
              <div className="suave chico">{u.ultimo_ingreso ? `Último ingreso ${fechaHora(u.ultimo_ingreso)}` : "Nunca ingresó"}{u.debe_cambiar_password ? " · tiene contraseña temporal" : ""}</div>
            </div>
            <button className="btn sec chico" onClick={() => setEditar(u)}>Editar</button>
            <button className="btn sec chico" onClick={() => confirm(`¿Generar una contraseña temporal nueva para ${u.nombre}? Se cierran sus sesiones.`) && accion.mutate({ u, a: "resetear-password" })}>Resetear contraseña</button>
            <button className="btn sec chico" onClick={() => accion.mutate({ u, a: "cerrar" })}>Cerrar sesiones</button>
            {u.activo ? <button className="btn sec chico" onClick={() => confirm(`¿Desactivar a ${u.nombre}? No va a poder entrar.`) && accion.mutate({ u, a: "desactivar" })}>Desactivar</button>
              : <button className="btn sec chico" onClick={() => accion.mutate({ u, a: "reactivar" })}>Reactivar</button>}
          </div>
        ))}
      </div>
      {editar && <Editor u={editar === "nuevo" ? null : editar} cerrar={() => setEditar(null)} creado={setClave} />}
      {clave && <ClaveTemporal c={clave} cerrar={() => setClave(null)} />}
    </div>
  );
}
