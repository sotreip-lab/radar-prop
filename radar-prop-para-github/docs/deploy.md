# Cómo está publicado Radar Prop (todo gratis)

| Pieza | Dónde | Plan |
|---|---|---|
| Base de datos | Supabase (`rsqomnnxdzdcjfagamby`) | Free: 500 MB (hoy usa ~70 MB) |
| Worker (lee los sitios cada 15 min) y respaldo diario | GitHub Actions, repositorio público `sotreip-lab/radar-prop` | Gratis en repositorios públicos |
| API | Render, servicio `radar-prop-api` (`render.yaml`) | Free: se duerme tras 15 min sin uso; el primer pedido tarda hasta 1 minuto en despertarlo |
| App web (PWA) | Netlify, sitio `radar-prop` → https://radar-prop.netlify.app | Free |

Netlify reenvía `/api/*` y `/f/*` a Render (`frontend/public/_redirects`), así la app y la API quedan en el mismo dominio y la cookie de sesión funciona.

## Variables de entorno
**Render (API):** `DATABASE_URL` (secreto, la de Supabase "Session pooler"), `JWT_SECRET` (la genera Render), `COOKIE_PATH=/api/auth`, `COOKIE_SECURE=true`, `FRONTEND_ORIGIN` y `APP_URL` (la dirección de Netlify), `DB_POOL_SIZE=3`, `DB_MAX_OVERFLOW=2`. Opcionales: `PANEL_TOKEN`, `PANEL_URL`, `PANEL_RUTA` (puente con el panel de fichas).

**GitHub (Settings → Secrets → Actions):** `DATABASE_URL` y `BACKUP_CLAVE`.

Ninguna clave está en el código. `Secretos para GitHub.bat` muestra en la PC los dos valores para pegar.

## Actualizar
- **API**: cada cambio en `radar-prop-para-github/backend` en GitHub se publica solo en Render. Al arrancar corre `alembic upgrade head` (las migraciones de la base se aplican solas).
- **App**: `cd frontend && npm run build` y publicar la carpeta `dist` en Netlify (`netlify deploy --prod --dir dist`).
- **Worker**: toma el código nuevo en la próxima corrida.

## Restaurar un respaldo
1. GitHub → Actions → Respaldo diario → la corrida del día → Artifacts → descargar `radar-prop-AAAA-MM-DD.dump.gpg` (viene en un .zip).
2. `gpg -d -o radar.dump radar-prop-AAAA-MM-DD.dump.gpg` (pide `BACKUP_CLAVE`).
3. En una base de prueba con PostGIS: `pg_restore --no-owner -d "postgresql://..." radar.dump`.
Probado el 25/11/2026: se restauraron las 16.228 propiedades.

**Prueba automática:** GitHub → Actions → "Prueba de restauración" corre sola el día 1 de cada mes (y se puede lanzar
a mano). Baja el último respaldo, lo descifra, lo restaura en una base de prueba vacía y compara cuántas filas tiene
cada tabla contra la base real. 26/11/2026: aprobada (16.280 propiedades restauradas).

## Prueba de uso simultáneo (Fase 5)
GitHub → Actions → "Prueba de carga" → Run workflow (minutos y usuarios a elección). Crea usuarios `carga01…carga10`
con una contraseña al azar, buscan / abren propiedades / miran el mapa / guardan historial / generan fichas cada 1 a 4
segundos, con el actualizador corriendo a la vez, y al final se borran con todo lo que generaron.

Resultados del 26/11/2026 contra producción (Render gratis, 0,1 CPU):

| Corrida | Errores 5xx | Búsqueda mediana | Búsqueda p95 |
|---|---|---|---|
| 10 usuarios, antes de los arreglos | 10 de 10 ingresos (el servidor se quedaba sin memoria) | – | – |
| 10 usuarios, con memoria arreglada | 0 de 436 | 4,6 s | 9,5 s |
| 10 usuarios, con búsqueda optimizada | 0 de 564 | 2,1 s | 8,2 s |

La meta de p95 < 1 s no se alcanza en el plan gratis: el procesador es 1/10 de uno común. Con Render Starter
(USD 7/mes, 0,5 CPU) la misma búsqueda debería quedar entre 0,2 y 0,5 s.

## Si algo falla
- **La app dice que no puede consultar el servidor**: Render se está despertando; esperá un minuto.
- **No se actualizan las propiedades**: GitHub → Actions → "Actualizar propiedades": la última corrida tiene el detalle. También queda en la tabla `corridas_actualizacion`.
- **Supabase pausó el proyecto** (pasa si nadie lo usa 7 días; con el worker cada 15 min no debería pasar): entrar al panel de Supabase y tocar "Restore".
