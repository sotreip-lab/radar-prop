"""Crea el PRIMER administrador (Bautista). Después, todos los usuarios se crean desde la app (pantalla Equipo).

    python scripts/crear_admin_inicial.py [usuario] [nombre] [apellido]
    python scripts/crear_admin_inicial.py --nueva-clave [usuario]   (si no anotaste la temporal)

- Si ya hay un administrador, no hace nada (para eso está la pantalla Equipo).
- Genera una contraseña temporal que se muestra UNA vez; al primer ingreso la app obliga a cambiarla.
- Usa DATABASE_URL (variable de entorno o el .env de radar-prop).
"""
import os
import secrets
import string
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "backend"))

from argon2 import PasswordHasher  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db_util import engine_para, normalizar_url  # noqa: E402
from app.models import Actividad, Usuario  # noqa: E402


def leer_url() -> str:
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    env = os.path.join(RAIZ, ".env")
    if os.path.exists(env):
        for linea in open(env, encoding="utf-8"):
            if linea.strip().startswith("DATABASE_URL="):
                return linea.split("=", 1)[1].strip()
    raise SystemExit("Falta DATABASE_URL (corré primero 'Cargar en Supabase.bat').")


def temporal() -> str:
    letras = "".join(c for c in string.ascii_letters if c not in "OolIL")
    while True:
        c = "".join(secrets.choice(letras + "23456789") for _ in range(10))
        if any(x.isdigit() for x in c) and any(x.isalpha() for x in c):
            return c


def crear(url: str, usuario: str, nombre: str, apellido: str, verificar_certificado: bool = True) -> str | None:
    eng = engine_para(url, verificar_certificado=verificar_certificado)
    with Session(eng) as db:
        if db.scalar(select(Usuario.id).where(Usuario.rol == "admin").limit(1)):
            return None
        if db.scalar(select(Usuario.id).where(func.lower(Usuario.usuario) == usuario.lower())):
            raise SystemExit(f"Ya existe el usuario {usuario}.")
        clave = temporal()
        u = Usuario(nombre=nombre, apellido=apellido, usuario=usuario, rol="admin",
                    hash_password=PasswordHasher().hash(clave), debe_cambiar_password=True, activo=True)
        db.add(u)
        db.flush()
        db.add(Actividad(user_id=u.id, accion="crear_admin_inicial", entidad="usuario", entidad_id=str(u.id), detalle={}))
        db.commit()
    eng.dispose()
    return clave


def nueva_clave(url: str, usuario: str, verificar_certificado: bool = True) -> str:
    """Genera otra contraseña temporal para un admin y cierra sus sesiones (solo desde la PC que tiene el .env)."""
    from sqlalchemy import update

    from app.models import Sesion
    eng = engine_para(url, verificar_certificado=verificar_certificado)
    with Session(eng) as db:
        u = db.scalar(select(Usuario).where(func.lower(Usuario.usuario) == usuario.lower(), Usuario.rol == "admin"))
        if not u:
            raise SystemExit(f"No hay un administrador con el usuario {usuario}.")
        clave = temporal()
        u.hash_password = PasswordHasher().hash(clave)
        u.debe_cambiar_password = True
        u.intentos_fallidos = 0
        u.bloqueado_hasta = None
        u.activo = True
        db.execute(update(Sesion).where(Sesion.user_id == u.id).values(revocada=True))
        db.add(Actividad(user_id=u.id, accion="nueva_clave_admin_desde_pc", entidad="usuario", entidad_id=str(u.id), detalle={}))
        db.commit()
    eng.dispose()
    return clave


def mostrar(usuario: str, clave: str):
    """Ventana que queda abierta hasta que la cierres, con botón para copiar la contraseña."""
    print(f"\nUsuario: {usuario}\nContraseña temporal: {clave}\n")
    try:
        import tkinter as tk
        v = tk.Tk()
        v.title("Radar Prop - tu usuario de administrador")
        v.attributes("-topmost", True)
        v.resizable(False, False)
        f = ("Segoe UI", 12)
        tk.Label(v, text="Anotá estos datos. La contraseña no se vuelve a mostrar.", font=("Segoe UI", 11, "bold"),
                 padx=20, pady=10).pack()
        for etiqueta, valor in (("Usuario", usuario), ("Contraseña temporal", clave)):
            fila = tk.Frame(v, padx=20, pady=4)
            fila.pack(fill="x")
            tk.Label(fila, text=etiqueta + ":", width=20, anchor="w", font=f).pack(side="left")
            e = tk.Entry(fila, font=("Consolas", 14), width=16, justify="center")
            e.insert(0, valor)
            e.configure(state="readonly")
            e.pack(side="left")

        def copiar():
            v.clipboard_clear()
            v.clipboard_append(clave)
            b.configure(text="Copiada ✓")
        b = tk.Button(v, text="Copiar contraseña", font=f, command=copiar, padx=10)
        b.pack(pady=8)
        tk.Label(v, text="Al primer ingreso a la app te va a pedir que la cambies por una tuya.", font=("Segoe UI", 10),
                 padx=20, pady=8).pack()
        tk.Button(v, text="Ya la anoté, cerrar", font=f, command=v.destroy, padx=10).pack(pady=(0, 14))
        v.mainloop()
    except Exception:
        input("Anotala y apretá Enter para cerrar...")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--nueva-clave":
        usuario = sys.argv[2] if len(sys.argv) > 2 else "bautista"
        url = normalizar_url(leer_url(), "pg8000" if os.name == "nt" else "psycopg")
        try:
            clave = nueva_clave(url, usuario)
        except Exception as e:
            if "CERTIFICATE" in str(e).upper() or "SSL" in str(e).upper():
                clave = nueva_clave(url, usuario, verificar_certificado=False)
            else:
                raise
        mostrar(usuario, clave)
        return
    usuario = sys.argv[1] if len(sys.argv) > 1 else "bautista"
    nombre = sys.argv[2] if len(sys.argv) > 2 else "Bautista"
    apellido = sys.argv[3] if len(sys.argv) > 3 else "Thiessen"
    url = normalizar_url(leer_url(), "pg8000" if os.name == "nt" else "psycopg")
    try:
        clave = crear(url, usuario, nombre, apellido)
    except Exception as e:
        if "CERTIFICATE" in str(e).upper() or "SSL" in str(e).upper():
            clave = crear(url, usuario, nombre, apellido, verificar_certificado=False)
        else:
            raise
    if clave is None:
        print("Ya hay un administrador. Los demás usuarios se crean desde la app, en la pantalla Equipo.")
        return
    print("\nADMINISTRADOR CREADO")
    mostrar(usuario, clave)


if __name__ == "__main__":
    main()
