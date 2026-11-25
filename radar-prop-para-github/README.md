# Radar Prop

Sistema multiusuario de búsqueda de propiedades de Guillermo Badenheuer Inmobiliaria. Es el reemplazo de El Ojo de Dios: base central en la nube, uso desde el celular y la computadora, y varios usuarios a la vez.

**Estado: Fase 2 (usuarios y seguridad) lista. Fase 1 (base y migración) cargada en Supabase.** La app vieja sigue funcionando igual en `Documents\BuscadorPropiedades`.

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
- Documentos: `docs/estado_actual.md`, `docs/mapeo_migracion.md` y `docs/api_fase2.md`.
