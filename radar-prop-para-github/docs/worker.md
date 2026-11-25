# Fase 3: el worker (actualización automática, gratis)

## Dónde corre
GitHub Actions, en el repositorio público `sotreip-lab/radar-prop`. En un repositorio público los minutos son gratis. La PC no necesita estar prendida.

| Tarea | Archivo | Cuándo |
|---|---|---|
| Actualizar propiedades | `.github/workflows/actualizar.yml` | Cada 15 minutos. GitHub puede atrasarla unos minutos en horas de mucho uso. |
| Respaldo diario | `.github/workflows/respaldo.yml` | 03:17 (hora de Bahía Blanca). |

Las dos se pueden correr a mano desde la pestaña **Actions** con el botón **Run workflow**.

## Secretos (Settings → Secrets and variables → Actions)
| Nombre | Qué es |
|---|---|
| `DATABASE_URL` | La conexión a Supabase (Session pooler). |
| `BACKUP_CLAVE` | La clave con la que se cifran los respaldos. |

`Secretos para GitHub.bat` los muestra en una ventana, solo en la PC, con botones para copiarlos. Toma la conexión del `.env` y genera `BACKUP_CLAVE` la primera vez. GitHub nunca muestra los secretos en los registros.

## Qué hace cada corrida (`backend/worker/actualizar.py`)
Es la misma lógica que la actualización de El Ojo de Dios. Los lectores de fichas (`backend/app/scraper/texto.py`, `bbp.py` e `ibb.py`) son copia textual de la app vieja. Se comprobó que dan exactamente el mismo resultado para las mismas páginas.

1. **Candado** en la base (`pg_try_advisory_lock`). Si ya hay una corrida activa, la nueva termina sin tocar nada.
2. **Dólar bolsa**, cada 6 horas. Se guarda en `meta.dolar`, con el mismo formato de antes.
3. **Bahía Blanca Propiedades**:
   - Lee el sitemap y procesa, en este orden: los avisos nuevos, los que volvieron a publicarse y las posibles bajas. Una baja se confirma recién después de abrir la ficha y verificar que ya no existe.
   - Lee las fichas pendientes.
   - Si el sitemap falla, busca avisos nuevos por número.
   - Hace una re-lectura rotativa de 300 fichas por corrida, empezando por las verificadas hace más tiempo. Son unas 28.000 lecturas por día, así que cada aviso activo se vuelve a leer unas dos veces por día.
4. **IBB**: lee el listado completo, después los avisos nuevos y las bajas, y re-lee 120 fichas por corrida. Para "apto crédito" usa el filtro oficial del sitio.
5. **Registro**: cada corrida queda en `corridas_actualizacion`, con cantidad de nuevas, actualizadas, bajas, cambios de precio y errores, más el detalle.

### Reglas que se mantienen
- **Fecha de publicación**: es la ventana real "entre la revisión anterior y esta". Nunca se inventa una hora. La ventana avanza solo cuando se terminó de detectar todo lo nuevo; si se cortó, queda más ancha.
- **Cambio de precio**: se guardan el precio anterior, la fecha del cambio y una fila en `historial_precios`.
- **Planilla**: si la ficha no trae tipo, operación, barrio, ciudad o título, queda el dato que ya estaba.
- **Precios**: `precio_ars` solo se completa si el aviso está en pesos. No se convierte con el dólar.
- **Ubicación en el mapa**: solo se usa si es creíble. Se descartan el punto (0,0) y los puntos genéricos repetidos en más de 12 avisos.
- **Fotos**: se guardan en `fotos`. En BBP, la fecha aproximada sale de la fecha de las fotos.

### Límite de tiempo
Cada corrida tiene 11 minutos. Si no le alcanzan, termina con estado `parcial` y lo que falta sigue en la próxima. Lo nuevo siempre va primero.

## Respaldos
- Se hace un `pg_dump` del esquema `public`, con la misma versión de PostgreSQL que la base.
- Antes de cifrarlo, se verifica que tenga al menos 10 tablas con datos.
- Se cifra con AES-256 y queda 30 días en **Actions → Respaldo diario → (la corrida) → Artifacts**.

Para restaurar, primero se descarga el `.zip` del artifact y se descomprime. Después:
```
gpg -d -o radar.dump radar-prop-AAAA-MM-DD.dump.gpg      (pide BACKUP_CLAVE)
pg_restore --no-owner -d "postgresql://..." radar.dump
```

La misma tarea vuelve a activar las tareas programadas una vez por día. Si no, GitHub las apaga cuando el repositorio pasa 60 días sin cambios.

## Pruebas
`backend/tests/test_worker.py` usa un sitio falso (`tests/sitio_falso.py`) y una base PostgreSQL real. Prueba:
- avisos nuevos con su ventana de publicación y la fecha de las fotos;
- cambio de precio con historial;
- bajas confirmadas y avisos que vuelven a publicarse;
- IBB (incluido el 406 si no se pide HTML);
- que un sitio caído no frene al otro;
- el candado;
- el corte por tiempo.
