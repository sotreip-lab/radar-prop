export const fmt = (n: number | null | undefined) => (n == null ? "" : Math.round(n).toLocaleString("es-AR"));
export const sim = (m: string | null | undefined) => (m === "ARS" ? "$" : "USD");
export const precioTxt = (precio: number | null | undefined, moneda: string | null | undefined) =>
  precio ? `${sim(moneda)} ${fmt(precio)}` : "Consultar";
export const fmtK = (n: number) => (n >= 1e6 ? (n / 1e6).toFixed(2).replace(".", ",") + " M" : fmt(n));
export const norm = (s: string | null | undefined) => (s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
export const COLOR: Record<string, string> = { Verde: "var(--verde)", Violeta: "var(--violeta)", Amarillo: "var(--amarillo)", Rojo: "var(--rojo)", "": "var(--tinta-2)" };
export const PLAT_NOM: Record<string, string> = { BBP: "Bahía Blanca Propiedades", IBB: "IBB", ZP: "ZonaProp" };
export const PLAT_CORTO: Record<string, string> = { BBP: "BBP", IBB: "IBB", ZP: "ZONAPROP" };
export function horaDe(t: string | null | undefined) {
  if (!t) return "";
  return `${t.slice(8, 10)}/${t.slice(5, 7)} ${t.slice(11, 16)}`;
}
export function fechaHora(iso: string) {
  const d = new Date(iso);
  return d.toLocaleString("es-AR", { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" });
}
export function copiar(texto: string) {
  if (navigator.clipboard?.writeText) return navigator.clipboard.writeText(texto);
  const a = document.createElement("textarea");
  a.value = texto;
  document.body.appendChild(a);
  a.select();
  document.execCommand("copy");
  a.remove();
  return Promise.resolve();
}
