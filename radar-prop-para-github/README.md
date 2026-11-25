# Radar Prop

Sistema multiusuario de búsqueda de propiedades de Guillermo Badenheuer Inmobiliaria. Es el reemplazo de El Ojo de Dios: base central en la nube, uso desde el celular y la computadora, y varios usuarios a la vez.

**Estado: Fases 1 a 4 listas.** La app vieja sigue funcionando igual en `Documents\BuscadorPropiedades`.

## Usar la app

Entrá a **https://radar-prop.netlify.app** con tu usuario y contraseña (te los da el administrador desde la pantalla Equipo). La primera vez te pide cambiar la contraseña.

**Instalarla con ícono propio**
- **Android (Chrome):** menú ⋮ → *Instalar aplicación* (o *Agregar a la pantalla principal*).
- **iPhone (Safari):** botón Compartir → *Agregar a inicio*.
- **Windows (Chrome o Edge):** el ícono de instalar en la barra de direcciones (o menú → *Instalar Radar Prop*).

**Qué hay en cada sección**
- **Buscar**: los mismos filtros y el mismo semáforo que El Ojo de Dios (Verde ±USD 5.000, Violeta hasta +7%, Amarillo hasta +15%), pestañas por plataforma y buscador en toda la base.
- **Mapa**: los resultados en el mapa; "Dibujar zona" (dos toques) o "Usar lo que se ve" para filtrar por zona.
- **Selección**: lo que marcaste. Desde acá salen la ficha para el cliente (link con fotos), el texto para WhatsApp y el envío al panel.
- **Historial**: tus búsquedas (con "Repetir búsqueda" y cuántas nuevas hay desde entonces), las propiedades que viste y las fichas que mandaste.
- **Más**: Compradores y alertas, Crédito UVA, Mapa de valores, Captación, Excel por plataforma, Equipo (admin) y Mi cuenta.

**Pasar tu selección de El Ojo de Dios**: en El Ojo de Dios tocá *Pasar mi selección a Radar Prop* (copia un código) y pegalo en Radar Prop → Mi cuenta → *Importar mi selección*.

**Si algo falla**: si la app dice que no puede consultar el servidor, esperá un minuto (se está despertando). Más detalles en `docs/deploy.md`.

## Pasar los datos a Supabase (Fase 1)

1. Abrí la carpeta `Documents\radar-prop` y hacé doble clic en **Cargar en Supabase.bat**.
2. La primera vez te pide la **cadena de conexión** de Supabase:
   - En el panel del proyecto, tocá el botón **Connect** (arriba).
   - Entrá a la pestaña **Connection string** y elegí **Session pooler**.
   - Copiá la cadena que empieza con `postgresql://postgres.<tu-proyecto>:` y pegala con clic derecho.
3. Después te pide la **contraseña de la base de datos**. Es la que pusiste al crear el proyecto; mientras la escribís no se ve. Si no la recordás, se cambia en Supabase, en *Project Settings → Database → Reset database password*.
4. Esperá 1 o 2 minutos. Al final aparece la tabla de conteos y **LISTO: los conteos coinciden**.

La contraseña queda guardada solo en tu PC, en `radar-prop\.env`. No se sube a ningún lado y no hace falta mandarla por chat. El script se puede volver a correr cuando quieras: actualiza los datos sin duplicar nada.

Si algo falla, el detalle queda en `radar-prop\cargar_supabase.log`, sin la contraseña.

## Crear tu usuario de administrador (una sola vez)

Hacé doble clic en **Crear admin inicial.bat**. Muestra tu usuario (`bautista`) y una **contraseña temporal**: anotala, porque no se vuelve a mostrar. Cuando la app esté publicada, al primer ingreso te va a pedir cambiarla. A los demás usuarios los creás vos desde la app, en la pantalla **Equipo**.

## Para desarrolladores

- `backend/`: FastAPI, SQLAlchemy 2, Alembic y PostGIS.
  - Migraciones: `alembic upgrade head`, con `DATABASE_URL` definida.
- `scripts/migrar_sqlite_a_postgres.py`: migración desde `propiedades.db`. Es idempotente y verifica los conteos.
- Tests: `TEST_DATABASE_URL=postgresql+psycopg://... pytest`, con una base Postgres + PostGIS real.
  - Para validar contra los datos reales: `RADAR_SQLITE_REAL=.../propiedades.db RADAR_PG_REAL=... pytest tests/test_muestra_real.py`.
- Linters: `ruff check . ../scripts` y `mypy app ../scripts/migrar_sqlite_a_postgres.py`.
- `docker-compose.yml`: base PostGIS local más la API (`/health`).
- Documentos: `docs/estado_actual.md`, `docs/mapeo_migracion.md`, `docs/api_fase2.md`, `docs/worker.md`, `docs/deploy.md` y `docs/costos.md`.
- App web: `frontend/` (React + Vite + PWA). `npm run dev` (usa la API en el puerto 8000), `npm run lint`, `npm run typecheck`, `npm run test:e2e` (Playwright, celular 390×844 y PC 1440×900).
