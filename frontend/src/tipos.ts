export type Filtros = {
  mon: "USD" | "ARS"; b: number; pct_abajo: number; rojas: boolean; pmin: number; pmax: number;
  oper: string; ciudad: string; tipos: string[]; barrios: string[]; sin_barrio: boolean;
  dorm: "" | "0" | "1" | "2" | "3" | "4" | "5"; dorm_modo: "exacto" | "min"; banos: number; supmin: number;
  patio: "" | "si" | "no"; cochera: "" | "si" | "no"; pileta: "" | "si" | "no"; balcon: "" | "si" | "no"; parrilla: "" | "si" | "no";
  amoblado: "" | "si" | "no"; credito: "" | "si" | "si_nc"; estrenar: boolean; kw: string; nuevas_horas: number; margen: number;
  sin_dato: boolean; sin_ubic: boolean; excl: boolean; bajas: boolean; bajo_precio: boolean; margen_neg: boolean;
  dmin: number | null; dmax: number | null; m2max: number; bajo_min: number; cuota_max: number;
  plataforma: "todas" | "BBP" | "IBB" | "ZP"; qg: string; solo_seleccion: boolean; orden: string; orden_dir: number;
};

export const FILTROS_INICIALES: Filtros = {
  mon: "USD", b: 0, pct_abajo: 15, rojas: false, pmin: 0, pmax: 0, oper: "Venta", ciudad: "Bahía Blanca", tipos: [], barrios: [],
  sin_barrio: true, dorm: "", dorm_modo: "exacto", banos: 0, supmin: 0, patio: "", cochera: "", pileta: "", balcon: "", parrilla: "",
  amoblado: "", credito: "", estrenar: false, kw: "", nuevas_horas: 0, margen: 300, sin_dato: true, sin_ubic: false, excl: true,
  bajas: false, bajo_precio: false, margen_neg: false, dmin: null, dmax: null, m2max: 0, bajo_min: 0, cuota_max: 0,
  plataforma: "todas", qg: "", solo_seleccion: false, orden: "", orden_dir: 1,
};

export type Zona = { type: "Polygon"; coordinates: number[][][] };

export type Item = {
  id: number; fuente: string; plataformas: { fuente: string; url: string; id: number }[]; url: string; color: string; zona: string | null;
  dif: number | null; obs: string; usdm2: number | null; tipo: string | null; operacion: string | null; dormitorios: number | null;
  dorm_fuente: string | null; barrio: string | null; direccion: string | null; ciudad: string | null; moneda: string | null;
  precio: number | null; precio_falso: number | null; sup_cub: number | null; sup_tot: number | null; m2_base: number | null;
  exterior: string | null; estacionamiento: string | null; amoblado: string | null; pago: string | null; antiguedad: string | null;
  inmobiliaria: string | null; foto: string | null; lat: number | null; lng: number | null; estado_aviso: string;
  pub_corta: string; pub_titulo: string; nueva: boolean; bajo: boolean;
  otro_precio: { id: number; fuente: string; inmobiliaria: string | null; precio: number; moneda: string; url: string }[] | null;
  vsb: { pct: number; med: number; n: number; nivel: string; donde: string } | null;
  renta: { pct: number; alq: number; n: number; nivel: string; dolar: number } | null;
  cuota: { cuota: number; prestamo: number; anios: number; ltv: number; ingreso: number; banco: string } | null;
  dias: number | null; bajas: number; baja_pct: number; margen: string; seleccionada: boolean; ficha: string;
};

export type Resultado = {
  total: number; offset: number; items: Item[]; plataformas: Record<string, number>; dups: number;
  colores: Record<string, number>; sin_ubic_ocultas: number; actualizado: string; resumen: string;
};

export type Linea = {
  banco: string; linea: string; tea: number; beneficiario: string; rci: number; ltv: number; plazo: number; destino?: string; es_banco?: boolean;
  monto_max: number | null; monto_max_uva?: number | null; valor_max_uva?: number | null; valor_min_uva?: number | null; monto_min?: number | null;
  ingreso_min?: number | null; tna?: number; cft?: number | null; requisitos?: string[]; nota?: string;
};
export type Credito = { uva: { valor: number; fecha: string } | null; lineas: Linea[]; plazo_anios: number; dolar: { valor?: number; tipo?: string }; linea_defecto: Linea | null; lineas_leidas: string };

export type Estado = {
  actualizado: string; activas: number; bajas: number; nuevas_24h: number; dolar: { valor?: number; tipo?: string };
  ultima_corrida: { fin: string | null; estado: string | null } | null;
};
