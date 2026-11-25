/* Simulación de crédito hipotecario UVA con las condiciones reales de cada línea (misma cuenta que el servidor:
   backend/app/services/credito_lineas.py). Los topes en UVAs se pasan a pesos con la UVA del día. */
import { fmt } from "./formato";
import type { Linea } from "./tipos";

export type Sim = {
  cuota: number; prestamo: number; anios: number; plazoMax: number; ltv: number; pp: number; anticipo: number; ingreso: number;
  tope: number | null; califica: boolean; motivos: string[]; cuotaUva: number | null; uvas: number | null;
};

export function simular(pp: number, l: Linea, uva: number | undefined, anios: number, ltv?: number): Sim {
  const plazoMax = Math.max(1, Math.floor(l.plazo / 12));
  anios = Math.min(anios || 20, plazoMax);
  ltv = Math.min(ltv || l.ltv, l.ltv);
  const motivos: string[] = [];
  let califica = true;
  if (uva && l.valor_max_uva && pp > l.valor_max_uva * uva) {
    califica = false;
    motivos.push(`la vivienda supera el valor máximo de la línea (${fmt(l.valor_max_uva)} UVAs ≈ $ ${fmt(l.valor_max_uva * uva)})`);
  }
  if (uva && l.valor_min_uva && pp <= l.valor_min_uva * uva) {
    califica = false;
    motivos.push(`esta línea es para viviendas de más de ${fmt(l.valor_min_uva)} UVAs (≈ $ ${fmt(l.valor_min_uva * uva)})`);
  }
  let prestamo = (pp * ltv) / 100;
  let tope: number | null = null;
  const topes = [l.monto_max || 0, (l.monto_max_uva || 0) * (uva || 0)].filter((x) => x > 0);
  if (topes.length && prestamo > Math.min(...topes)) {
    tope = Math.min(...topes);
    prestamo = tope;
  }
  if (l.monto_min && prestamo < l.monto_min) {
    califica = false;
    motivos.push(`el préstamo queda por debajo del mínimo de la línea ($ ${fmt(l.monto_min)})`);
  }
  const n = anios * 12, i = Math.pow(1 + l.tea / 100, 1 / 12) - 1, cuota = (prestamo * i) / (1 - Math.pow(1 + i, -n));
  return {
    cuota, prestamo, anios, plazoMax, ltv: Math.round((prestamo / pp) * 100), pp, anticipo: pp - prestamo,
    ingreso: Math.max(cuota / (l.rci / 100), l.ingreso_min || 0), tope, califica, motivos,
    cuotaUva: uva ? cuota / uva : null, uvas: uva ? prestamo / uva : null,
  };
}

/** Préstamo máximo que permite un ingreso dado (la cuota no puede pasar el % de la línea). */
export function prestamoPorIngreso(ingreso: number, l: Linea, anios: number) {
  const n = Math.min(anios, Math.floor(l.plazo / 12)) * 12, i = Math.pow(1 + l.tea / 100, 1 / 12) - 1;
  const cuotaMax = ingreso * (l.rci / 100);
  return { cuotaMax, prestamo: (cuotaMax * (1 - Math.pow(1 + i, -n))) / i };
}

const GENERAL = /todos|sueldo|dependencia|cuenta/i;
export function esGeneral(l: Linea) {
  return l.es_banco !== false && GENERAL.test(l.beneficiario) && !/públic/i.test(l.beneficiario) && !/p[uú]blico/i.test(l.linea) && l.ltv <= 80;
}

/** Línea sugerida: la más barata de uso general para la que la propiedad califica. */
export function lineaSugerida(pp: number, lineas: Linea[], uva?: number, anios = 20) {
  const orden = [...lineas.map((l, i) => ({ l, i }))].sort((a, b) => a.l.tea - b.l.tea);
  const ok = (x: { l: Linea }) => simular(pp, x.l, uva, anios).califica;
  return (orden.find((x) => esGeneral(x.l) && ok(x)) || orden.find(ok) || orden[0])?.i ?? 0;
}

export const pct = (v: number | null | undefined) => (v == null ? "s/d" : `${v.toFixed(2).replace(".", ",")}%`);

export function textoCliente(o: { titulo?: string; direccion?: string | null }, l: Linea, r: Sim, uva: number | undefined, dolar: number) {
  const usd = (v: number) => (dolar ? ` (USD ${fmt(v / dolar)})` : "");
  return [
    `*Simulación de crédito hipotecario UVA*${o.direccion ? `\n${o.titulo ? o.titulo + " · " : ""}${o.direccion}` : ""}`,
    `Banco: ${l.banco} · ${l.linea} (${l.beneficiario})`,
    `Valor de la propiedad: $ ${fmt(r.pp)}${usd(r.pp)}`,
    `Préstamo: $ ${fmt(r.prestamo)}${usd(r.prestamo)} (${r.ltv}% del valor)${r.uvas ? ` · ${fmt(r.uvas)} UVAs` : ""}`,
    `Anticipo: $ ${fmt(r.anticipo)}${usd(r.anticipo)} + gastos de escritura`,
    `Plazo: ${r.anios} años · TNA ${pct(l.tna)} · TEA ${pct(l.tea)} · CFTEA ${pct(l.cft)}`,
    `Primera cuota: $ ${fmt(r.cuota)} por mes${r.cuotaUva ? ` (${r.cuotaUva.toFixed(1).replace(".", ",")} UVAs, se ajusta por UVA)` : ""}`,
    `Ingreso mínimo del hogar: $ ${fmt(r.ingreso)} por mes`,
    `Datos del BCRA, UVA $ ${fmt(uva)}. Es una estimación: el banco confirma el monto al evaluar el pedido.`,
  ].join("\n");
}
