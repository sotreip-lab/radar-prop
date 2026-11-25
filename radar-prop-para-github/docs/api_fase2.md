# API: usuarios, sesiones y seguridad (Fase 2)

Todas las rutas piden sesión, salvo `POST /auth/login` y `GET /health`. Los errores vienen en español y sin datos internos (`{"detail": "..."}`).

## Ingreso y sesión
| Ruta | Qué hace |
|---|---|
| `POST /auth/login` `{usuario, password, dispositivo?}` | Se ingresa con el usuario o el email. Devuelve el token de acceso (15 min) y deja el token de renovación (30 días) en una cookie `rp_refresh` httpOnly, Secure y SameSite=Lax. |
| `POST /auth/refresh` | Renueva el acceso. Cada uso cambia el token de renovación y el anterior deja de servir. |
| `POST /auth/logout` | Cierra la sesión actual. |
| `POST /auth/cambiar-password` `{actual, nueva}` | Mínimo 8 caracteres, con letras y números. Cierra las demás sesiones abiertas. |
| `GET /me` | Mis datos. |
| `GET /me/sesiones` y `DELETE /me/sesiones/{id}` | Mis dispositivos conectados. Puedo cerrar cualquiera. |

**Reglas de seguridad**
- **Bloqueo:** 5 intentos fallidos bloquean el usuario por 15 minutos.
- **Límite por IP:** 20 pedidos por minuto en `/auth/*`.
- **Contraseña temporal:** quien la tenga solo puede usar `/me`, `/auth/cambiar-password` y `/auth/logout` hasta cambiarla.
- **Cortes inmediatos:** un usuario desactivado o una sesión cerrada dejan de funcionar en el próximo pedido.
- **Contraseñas:** se guardan con Argon2id.

## Equipo (solo admin)
| Ruta | Qué hace |
|---|---|
| `GET /admin/usuarios` | Lista. |
| `POST /admin/usuarios` | Alta: nombre, apellido, usuario, email y teléfono (opcionales) y rol. Devuelve **una sola vez** la contraseña temporal, el texto para WhatsApp y el link `wa.me`. |
| `PATCH /admin/usuarios/{id}` | Editar datos y rol. |
| `POST /admin/usuarios/{id}/desactivar` y `/reactivar` | Desactivar cierra todas sus sesiones al instante. |
| `POST /admin/usuarios/{id}/resetear-password` | Genera una temporal nueva y cierra sus sesiones. |
| `GET` y `DELETE /admin/usuarios/{id}/sesiones` | Ver o cerrar todas sus sesiones. |
| `GET /admin/actividad?usuario_id=&q=&antes_de_id=` | Registro de actividad del equipo, de a 100. |

**Validaciones**
- El nombre de usuario es único sin distinguir mayúsculas.
- No se puede desactivar ni pasar a agente al último admin activo.
- Un admin no puede desactivarse a sí mismo.

## Datos personales (ejemplo: selección)
- `GET /selecciones`, `POST /selecciones` `{propiedad_ids}`, `DELETE /selecciones/{id}` y `DELETE /selecciones`.
- `POST /selecciones/importar-ojo-de-dios` `{ids_legado}` sube la selección guardada en el navegador de El Ojo de Dios.

El `user_id` sale siempre de la sesión. Si el navegador manda uno, se ignora.

## Primer administrador
`Crear admin inicial.bat` (o `python scripts/crear_admin_inicial.py`) crea a Bautista con una contraseña temporal, que se muestra una sola vez. Si ya hay un admin, no hace nada.
