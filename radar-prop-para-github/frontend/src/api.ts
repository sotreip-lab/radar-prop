/* Cliente de la API. El token de acceso vive solo en memoria (nunca en localStorage); la renovación usa la
   cookie httpOnly. Si un pedido vuelve 401, se renueva una sola vez (aunque haya varios pedidos a la vez) y se
   reintenta, así la sesión se renueva sola sin cortar lo que la persona estaba haciendo. */
export class ApiError extends Error {
  estado: number;
  constructor(estado: number, mensaje: string) {
    super(mensaje);
    this.estado = estado;
  }
}

export type Usuario = {
  id: number; nombre: string; apellido: string; usuario: string; email: string | null; telefono: string | null;
  rol: "admin" | "agente"; activo: boolean; debe_cambiar_password: boolean;
};
type TokenOut = { access_token: string; usuario: Usuario; debe_cambiar_password: boolean };

let token: string | null = null;
let renovando: Promise<TokenOut | null> | null = null;
const oyentes = new Set<(u: TokenOut | null) => void>();

export function alCambiarSesion(f: (u: TokenOut | null) => void) {
  oyentes.add(f);
  return () => oyentes.delete(f);
}
function avisar(t: TokenOut | null) {
  oyentes.forEach((f) => f(t));
}
export function ponerToken(t: TokenOut | null) {
  token = t?.access_token ?? null;
  avisar(t);
}

export function renovar(): Promise<TokenOut | null> {
  if (!renovando) {
    renovando = fetch("/api/auth/refresh", { method: "POST", credentials: "include" })
      .then(async (r) => (r.ok ? ((await r.json()) as TokenOut) : null))
      .catch(() => null)
      .then((t) => {
        token = t?.access_token ?? null;
        return t;
      })
      .finally(() => setTimeout(() => (renovando = null), 0));
  }
  return renovando;
}

// Las pantallas de Mapa de valores y Captación (páginas aparte en un iframe) piden el token por acá.
declare global {
  interface Window { __radarToken?: () => Promise<string | null>; }
}
window.__radarToken = async () => token ?? (await renovar())?.access_token ?? null;

async function mensajeDe(r: Response): Promise<string> {
  try {
    const j = await r.json();
    if (typeof j?.detail === "string") return j.detail;
  } catch { /* sin cuerpo */ }
  if (r.status >= 500) return "El servidor no respondió bien. Probá de nuevo en un momento.";
  return "No se pudo completar. Probá de nuevo.";
}

export async function api<T>(ruta: string, opciones: RequestInit & { json?: unknown } = {}, reintento = true): Promise<T> {
  const headers = new Headers(opciones.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let body = opciones.body;
  if (opciones.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(opciones.json);
  }
  let r: Response;
  try {
    r = await fetch(`/api${ruta}`, { ...opciones, headers, body, credentials: "include" });
  } catch {
    throw new ApiError(0, "Sin conexión. Revisá internet y probá de nuevo.");
  }
  if (r.status === 401 && reintento && !ruta.startsWith("/auth/")) {
    const t = await renovar();
    if (t) return api<T>(ruta, opciones, false);
    avisar(null);
  }
  if (!r.ok) throw new ApiError(r.status, await mensajeDe(r));
  if (r.status === 204) return undefined as T;
  const tipo = r.headers.get("content-type") || "";
  if (tipo.includes("application/json")) return (await r.json()) as T;
  return (await r.blob()) as T;
}

export async function ingresar(usuario: string, password: string) {
  const t = await api<TokenOut>("/auth/login", { method: "POST", json: { usuario, password } });
  ponerToken(t);
  return t;
}

export async function salir() {
  try {
    await api("/auth/logout", { method: "POST" });
  } finally {
    ponerToken(null);
  }
}

export function claveIdempotencia() {
  return crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}
