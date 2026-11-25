# Estado actual de "El Ojo de Dios" (antes de migrar a Radar Prop)

Relevado el 25/11/2026 a las 08:50 sobre la carpeta `C:\Users\juanb\Documents\BuscadorPropiedades`
(copia de `propiedades.db` + `-wal`, con checkpoint hecho sobre la copia, nunca sobre el original).

## 1. Archivos

| Archivo | Qué hace |
|---|---|
| `app.py` (131 KB, ~2.560 líneas) | Todo el backend. Solo biblioteca estándar de Python. Servidor `ThreadingHTTPServer` en `127.0.0.1:8765` con clase `Handler`. También es el actualizador (scraper BBP + IBB), el importador de planillas, el generador de Excel, la IA, las fichas y el puente con el panel. |
| `ui.html` (94 KB) | Toda la interfaz en un solo archivo (HTML + CSS + JS). Se lee del disco en cada pedido. Carga todas las propiedades en el navegador (`DATA`) y filtra ahí. |
| `static/` | Leaflet 1.x (`leaflet.js`, `leaflet.css`, imágenes), `d3-delaunay.min.js` (mapa de valores) y `zp_import.xlsx` (planilla de ZonaProp importada). |
| `modulos/` | Sectores aparte, cargados por `cargar_modulos()`. Si uno falla, la app sigue. Ver punto 6. |
| `modulos/datos/` | Datos propios de los sectores: `captacion.db`, `credito.json`, `zonas_barrios.json`, `zonas_cpu.json`. |
| `propiedades.db` (+ `-wal`, `-shm`) | SQLite en modo WAL. Base principal. |
| `config.json` | Configuración. Tiene `panel_token` (43 caracteres) y `ia_api_key` (hoy **vacía**). No debe subirse a ningún repositorio. |
| `actualizaciones.log` | Registro de cada corrida: 373 corridas desde el 21/11 a las 02:54. |
| `Fichas_Venta_*.xlsx` (3) | Excel por plataforma, regenerados al final de cada actualización. |
| `Iniciar Buscador.bat`, `INSTALAR.bat`, `instalar.ps1`, `Reiniciar app.bat`, `reiniciar.ps1`, `python_path.txt` | Instalación y arranque en Windows. |
| `Programar actualizacion diaria.bat` | Crea 2 tareas de Windows: `--vigilar` cada 15 min y `--actualizar completa` todos los días a las 07:00. |
| `panel-badenheuer-ojo.zip` | Código del panel de fichas (Netlify) con el puente `/api/ojo/*` agregado. |
| `*.mp4` (9) | Videos de presentación. No son parte del sistema. |

## 2. Base de datos (`propiedades.db`)

### Tabla `props`: 16.228 filas
**El documento dice ~11.900, pero la base real tiene 16.228.**

| Plataforma | Activas | Bajas | Total |
|---|---|---|---|
| BBP | 11.832 | 146 | 11.978 |
| IBB | 2.372 | 15 | 2.387 |
| ZP | 1.863 | 0 | 1.863 |

- Operaciones: Venta 13.574, Alquiler 2.544, Alquiler por día 47, Alquiler temporario 5, Fideicomiso 56, Sin operación 1 y 1 vacía.
- Ciudades: Bahía Blanca 13.347, Monte Hermoso 1.624, Sierra de la Ventana 200, Pehuen Co 167, Punta Alta 113, otras.

Columnas reales (50), todas a migrar:

```
id INTEGER PK, titulo, tipo, operacion, direccion, barrio, ciudad, inmobiliaria, moneda, precio REAL,
dormitorios INT, dorm_fuente, banos INT, sup_cub REAL, sup_tot REAL, antiguedad, estado,
patio, cochera, apto_credito, pileta, parrilla, detalles (JSON en texto), descripcion,
estado_aviso (activo/baja/pendiente), alta, ultima_verif, precio_anterior REAL, cambio_precio, intentos INT,
detectada, detectada_desde, fecha_baja, ia_json, ia_resumen, ia_fecha, ia_intentos INT,
exterior, estacionamiento, pago, expensas, m2_base REAL, lat REAL, lng REAL,
fuente (BBP/IBB/ZP, default BBP), url, pub_txt, pub_aprox, amoblado
```

Índices: `estado_aviso`, `fuente`, `url`, `detectada`.

Cómo se maneja hoy la publicación y la ubicación:

| Dato | Cobertura |
|---|---|
| `detectada` / `detectada_desde` (ventana exacta, avisos vistos aparecer) | 132 |
| `pub_txt` (texto del sitio, IBB) | 2.387 |
| `pub_aprox` (BBP: fecha `Last-Modified` de las 2 primeras fotos) | 14.321 |
| Coordenadas | 13.950, pero hay coordenadas basura: 390 en (0,0) y ~900 repetidas en un mismo punto genérico del portal |

### Cómo se identifican hoy los avisos (importante para la clave nueva)
- **BBP**: `id` = número de aviso del sitio (de 140 a 95.448). `url` está vacía y se arma como `https://www.bahiablancapropiedades.com/propiedad/{id}/`.
- **IBB y ZP**: `id` es un número **sintético** desde `ID_EXTERNO_BASE = 1.000.000.000`, correlativo por orden de alta (IBB y ZP comparten la numeración). La identidad real es la `url`, que es única (4.250 urls, 4.250 distintas).
  - IBB no tiene número: el identificador es el *slug* del link (por ejemplo `departamento-en-venta-1-dormitorio-en-casanova-230-840ccfad-...`). **Riesgo:** si la inmobiliaria edita el título, el slug puede cambiar.
  - ZP tiene número en el link (`/propiedades/-60773311.html` → `60773311`).
- Hoy no hay choques porque los ids sintéticos están por encima de 1.000 millones. Igual, en la base nueva la clave pasa a ser `(plataforma, id_externo)`. Como la selección guardada en los navegadores y las fichas usan el `id` viejo, conviene conservarlo como `id_legado`.

### Tabla `historial`: 52 filas
`(id, fecha, moneda, antes, despues)`. Solo guarda cambios de precio, cargados por el trigger `tr_hist` (`AFTER UPDATE OF precio`, misma moneda, diferencia mayor a 0,5). Se sembró una vez desde `precio_anterior`.

### Tabla `meta`: 10 claves
`inicio_base`, `version_lector`, `ultima_completa`, `import_ZP`, `historial_sembrado`, `dolar` (JSON: valor, tipo Bolsa, fecha, leído), `ibb_ultima_revision`, `ultima_revision_sitemap`, `ultima_actualizacion`, `excel_generado`.

### Tabla `pedidos`: 0 filas
`(id, datos JSON, creado, visto_hasta, activo)`. Son los compradores y alertas.
**Ojo: viven en la base, no en el navegador.**

### Otras bases
`modulos/datos/captacion.db` tiene las tablas `duenos` y `seguimiento`, con 0 filas las dos.

## 3. Actualizador (scraper)

- **BBP**: lee el sitemap (`bajar_sitemap`) para detectar altas y bajas, busca ids nuevos por encima del último (`buscar_ids_nuevas`) y abre cada ficha (`bajar_ficha` → `analizar_ficha`). Corre en 8 hilos con 3 reintentos.
  - Una respuesta 404/410, o una página sin `propiedad-in-title`, cuenta como baja.
  - Reactiva las bajas que vuelven a aparecer.
  - Reverifica 400 fichas por ronda en forma rotativa, y todas una vez por día.
  - Corta si hay 40 fallos seguidos.
- **IBB**: `ibb_enumerar` recorre el buscador completo (venta, alquiler y temporario) y lee las fichas nuevas o las posibles bajas (`ibb_analizar`). Reverifica 150 por ronda y tiene un mínimo de 300 avisos para no marcar bajas masivas si el sitio falla.
- **ZonaProp**: solo por planilla (`importar_bytes` → `importar_externo`). No hay lectura automática.
- **Dólar**: dolarapi.com, cotización Bolsa (MEP), cada 6 h.
- **Lock**: archivo `actualizando.lock` (se descarta si tiene más de 3 h). Se usa porque hoy corren a la vez el `vigilante` de la app abierta (cada 10 min) y la tarea de Windows (cada 15 min).
- Una ronda rápida tarda unos 2 minutos y lee unas 590 fichas. Hoy a las 08:48: 2 nuevas, 1 baja.

## 4. Funciones de la app (ui.html + app.py)

**Búsqueda y filtros**
- Presupuesto en USD o $.
- Operación, tipo (con equivalencias), ciudad, barrio, dormitorios (exacto o mínimo), baños, superficie mínima.
- Patio, cochera, pileta, balcón, parrilla, amoblado, apto crédito, a estrenar.
- Palabras clave, plataforma, inmobiliarias excluidas, solo nuevas, mostrar bajas, solo bajaron de precio.
- Margen de negociación, antigüedad de publicación (días), precio por m² máximo, bajó al menos un %, cuota máxima de crédito.
- Buscador global (ID, link o texto).

**Semáforo** (función `bandas`)
- USD:
  - Verde: presupuesto ± USD 5.000.
  - Violeta: hasta el mayor entre +7% y +5.000.
  - Amarillo: hasta +15%, más baratas desde −X% configurable, o falta un dato.
  - Rojo (opcional): hasta +30%.
- Pesos: Verde ±5%, Violeta hasta +7%.

**Secciones y vistas**
- Pestañas por plataforma más "Todas", con etiqueta de plataforma.
- Lista con detalle desplegable.
- Mapa Leaflet con dibujo de zona (`enPoligono`, filtro en el navegador).

**Análisis** (`prepAnalisis`, todo calculado en el navegador)
- m² contra la mediana del barrio.
- Rentabilidad (alquiler contra venta, por tipo y dormitorios).
- Misma propiedad a distinto precio entre inmobiliarias.
- Margen de negociación (días publicada, bajas de precio, % de baja).
- Cuota de crédito UVA (líneas reales del BCRA).

**Selección, fichas y exportación**
- Selección guardada en `localStorage` (`bp_sel`, ids viejos).
- Ficha para el cliente: página `/ficha` con fotos, teléfonos tachados y WhatsApp de la inmobiliaria.
- Texto para WhatsApp (`ficha_whatsapp`).
- Excel por plataforma: 26 columnas, incluidas "Publicada" y "Última verificación".
- "Mandar al panel" (`/api/panel/clientes`, `/api/panel/enviar`) con el token en `config.json`. **El puente nunca se verificó de punta a punta**: el panel respondía "no autorizado".

**Compradores y alertas**
- Tabla `pedidos`, con un contador de vistos en `localStorage` (`bp_ped_n`).
- Avisos en pantalla y notificación del navegador.

**Otras funciones**
- Cargar planilla: xlsx o csv de BBP, IBB, ZP o "formato fichas". Lee los links, no duplica y vigila esas propiedades.
- IA: Claude Haiku analiza cada aviso (`ia_json`, `ia_resumen`). **Nunca corrió: la clave está vacía, y no hay ni un aviso analizado.**
- Amoblado detectado del texto (`detectar_amoblado`).
- Precios de relleno (111.111.111, etc.) excluidos de las comparativas.

**Rutas HTTP**
- GET: `/`, `/ficha`, `/api/excel`, `/static/*`, `/api/props` (todo junto, unos MB), `/api/panel/clientes`, `/api/pedidos`, `/api/status`.
- POST: `/api/actualizar`, `/api/ia`, `/api/panel/enviar`, `/api/pedidos`, `/api/importar`, `/api/reiniciar`.
- Rutas de los sectores aparte: `/mercado`, `/api/mercado`, `/api/mercado/capa`, `/captacion`, `/api/captacion*` y `/api/credito`.

## 5. localStorage (datos que viven en cada navegador)
Solo hay dos claves:
- `bp_sel`: los ids seleccionados.
- `bp_ped_n`: un contador de avisos de compradores.

Los compradores están en la base, no en el navegador.

## 6. Sectores aparte (no figuran en el documento de Radar Prop)

| Sector | Qué hace | Datos |
|---|---|---|
| `credito.py` | UVA y líneas hipotecarias del BCRA (API de transparencia), una vez por día | `credito.json`: 86 líneas de 15 entidades |
| `mercado.py` + `zonas.py` + `mercado.html` | Mapa de valores por m²: cierres probables (bajas filtradas), publicadas hoy y diferencia. Áreas del CPU y barrios oficiales del Municipio | `zonas_cpu.json`: 172 áreas; `zonas_barrios.json` |
| `captacion.py` + `captacion.html` | Dueños directos más señales: cansadas, bajas largas, varias inmobiliarias, cambió de inmobiliaria. Seguimiento por estado | `captacion.db`, vacía |
| `comun.py` | Funciones compartidas: lectura de solo lectura, normalización, precio válido | — |

## 7. Diferencias con el documento de Radar Prop (a decidir antes de la Fase 1)

1. **Cantidad:** hay 16.228 propiedades, no ~11.900.
2. **IA:** existe en el código pero nunca se usó. No hay datos de IA para migrar.
3. **localStorage:** solo tiene la selección y un contador. El botón "Importar mis datos de El Ojo de Dios" sirve para la selección; los compradores se migran desde la base.
4. **Crédito, mapa de valores y captación** no figuran en la sección 7 del documento. Hay que decidir si entran en la Fase 4 o quedan para después.
5. **Puente con el panel:** el código está, pero nunca se probó con éxito. Hay que verificarlo antes de migrarlo.
6. **Sitios desde la nube:** el scraper hoy corre desde una conexión hogareña de Bahía Blanca. Desde un servidor en la nube, BBP o IBB podrían bloquear las IPs. Hay que probarlo al principio, no recién en la Fase 3.
