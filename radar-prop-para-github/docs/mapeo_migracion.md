# Mapeo de la migración: El Ojo de Dios (SQLite) → Radar Prop (PostgreSQL)

Script: `scripts/migrar_sqlite_a_postgres.py`. Ninguna columna se descarta: lo que no tiene lugar propio va a `datos_extra` (JSONB).

## props → propiedades

| Columna vieja | Columna nueva | Transformación |
|---|---|---|
| `id` | `id_legado` | Se conserva tal cual, como clave única. Sirve para importar selecciones y fichas viejas. |
| `fuente` | `plataforma` | Si está vacía, `BBP`. |
| `id` + `url` | `id_externo` | BBP: número del aviso. ZP: número del link (`-60773311.html`). IBB: *slug* del link (`/listings/<slug>`). Con `plataforma` forma la clave única. |
| `url` | `url` | En BBP, que no la guardaba, se arma `https://www.bahiablancapropiedades.com/propiedad/{id}/`. |
| `titulo`, `tipo`, `operacion`, `direccion`, `barrio`, `ciudad`, `inmobiliaria`, `moneda` | mismo nombre | Sin cambios. |
| `precio`, `precio_anterior` | mismo nombre | Numérico exacto (`NUMERIC`). |
| — | `precio_ars` | Igual a `precio` solo si `moneda = ARS`. No se convierte con el dólar, para no inventar un dato. |
| `dormitorios`, `banos` | mismo nombre | Sin cambios. |
| `sup_cub` / `sup_tot` / `m2_base` | `m2_cubiertos` / `m2_totales` / `m2_base` | Sin cambios. |
| `estado` | `estado_inmueble` | Ejemplos: "Excelente", "Muy Bueno". |
| `antiguedad`, `patio`, `cochera`, `pileta`, `parrilla`, `amoblado`, `apto_credito`, `pago`, `exterior`, `estacionamiento`, `expensas` | mismo nombre | Texto tal cual, para no perder matices como "Sí (desc.)", "No informado" o "No figura". |
| `detalles` | `detalles` | JSON en texto → JSONB. Si no es JSON válido, el texto va a `datos_extra.detalles_texto`. |
| `descripcion` | `descripcion` | Sin cambios. |
| `lat`, `lng` | `lat`, `lng` | Siempre se guardan tal cual vinieron. |
| `lat`, `lng` | `ubicacion` (geography Point 4326) y `ubicacion_valida` | Solo si es creíble: no (0,0) y no un punto genérico repetido en más de 12 avisos. Los genéricos llevan `datos_extra.coordenada_generica = true`. Datos actuales: 11.645 con punto en el mapa. |
| `detectada_desde` / `detectada` | `publicada_desde` / `publicada_hasta` | Ventana exacta: "2026-11-24 10:00 a 10:15". |
| `pub_txt` | `pub_txt` | Texto del sitio (IBB). |
| `pub_aprox` | `pub_aprox` | Aproximada (BBP: fecha de las fotos). |
| — | `fecha_publicacion` | Solo para ordenar: `publicada_hasta`, o si no hay, `pub_aprox`. Nunca reemplaza a la ventana en pantalla. |
| `alta` | `primera_vez_vista` | Sin cambios. |
| `ultima_verif` | `ultima_vez_vista` + `ultima_verif_origen` | "2026-11-21 (planilla)" → fecha + origen "planilla". |
| `estado_aviso` | `estado` | activo → activa, baja → baja, pendiente → pendiente. |
| `fecha_baja` | `fecha_baja` + `fecha_baja_origen` | Igual que `ultima_verif`. |
| `cambio_precio` | `cambio_precio` | Texto → fecha y hora. |
| `intentos` | `intentos` | Sin cambios. |
| `ia_json`, `ia_resumen`, `ia_fecha`, `ia_intentos` | mismo nombre | Hoy están todas vacías: la IA nunca corrió. |
| `dorm_fuente` | `datos_extra.dorm_fuente` | Valores: "ficha" o "descripción". |
| cualquier columna futura | `datos_extra.<nombre>` | Automático. |

Columnas nuevas sin dato de origen: `ambientes`, `fotos`, `grupo_duplicado_id`. Quedan vacías hasta que las complete el worker.

## historial → historial_precios
`id` → `propiedad_id`, buscado por `id_legado`. `fecha` → `fecha`. `moneda` → `moneda`. `antes` → `precio_anterior`. `despues` → `precio`. Es única por (propiedad, fecha, antes, después).

## meta → meta
`k` → `clave`, `v` → `valor`, sin cambios. Incluye el JSON de `dolar` tal cual. Se agrega `migrado_desde_ojo_de_dios` con la fecha de la migración.

## pedidos → clientes
- `id` → `id_legado`.
- De `datos` (JSON):
  - `nombre` → `nombre`;
  - `telefono` → `telefono`;
  - `presu` → `presupuesto`;
  - `moneda` → `moneda`;
  - `texto` (o `obs`) → `pedido`;
  - el JSON completo, más `visto_hasta`, → `filtros`.
- `activo` → `activo`.
- `creado` → `creado_en`.
- `asignado_a` queda vacío. Las alertas (`alertas`) se crean recién cuando cada cliente tenga un agente asignado, en la Fase 2.

## modulos/datos/captacion.db → captacion_duenos / captacion_seguimiento
- `duenos` → `captacion_duenos`. Se renombran `dorm` → `dormitorios` y `alta` → `creado_en`, y `id` pasa a `id_legado`.
- `seguimiento` → `captacion_seguimiento`. `prop_id` → `propiedad_id`, usando el id nuevo. `dueno_id` → `dueno_id`, también con el id nuevo.

## localStorage de cada navegador (no está en la base)
- `bp_sel`: lista de ids viejos. En la Fase 4 se agrega el botón "Importar mis datos de El Ojo de Dios", que los convierte con `id_legado`.
- `bp_ped_n`: es solo un contador. No se migra.
