"""Crea el esquema de Radar Prop en Supabase y pasa los datos de El Ojo de Dios.
Se corre desde la PC (con "Cargar en Supabase.bat"), que es donde están propiedades.db y la conexión a internet.

- La primera vez pide la cadena de conexión de Supabase y la contraseña de la base (la contraseña no se ve
  al escribirla) y las guarda en radar-prop/.env, que queda solo en esta PC.
- Deja todo lo que pasa en cargar_supabase.log, sin la contraseña.
"""
import getpass
import os
import re
import sys
import traceback
from datetime import datetime
from urllib.parse import quote

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(RAIZ, "backend")
OJO = os.path.join(os.path.dirname(RAIZ), "BuscadorPropiedades")
ENV = os.path.join(RAIZ, ".env")
LOG = os.path.join(RAIZ, "cargar_supabase.log")
sys.path.insert(0, BACKEND)
sys.path.insert(0, os.path.join(RAIZ, "scripts"))


def log(msg):
    linea = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(linea)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(linea + "\n")


def oculta(url: str) -> str:
    return re.sub(r"(://[^:/@]+:)[^@]*@", r"\1****@", url)


def leer_env() -> dict:
    d = {}
    if os.path.exists(ENV):
        for linea in open(ENV, encoding="utf-8"):
            linea = linea.strip()
            if linea and not linea.startswith("#") and "=" in linea:
                k, v = linea.split("=", 1)
                d[k.strip()] = v.strip().strip('"').strip("'")
    return d


def pedir_url() -> str:
    print("\nEn Supabase: botón 'Connect' (arriba) > pestaña 'Connection string' > 'Session pooler'.")
    print("Copiá la cadena que empieza con postgresql://postgres.<tu-proyecto>:... y pegala acá.")
    url = input("\nCadena de conexión: ").strip()
    if "[YOUR-PASSWORD]" in url or "[YOUR_PASSWORD]" in url:
        clave = getpass.getpass("Contraseña de la base de datos (no se ve al escribir): ")
        url = re.sub(r"\[YOUR[-_]PASSWORD\]", quote(clave, safe=""), url)
    if not url.startswith(("postgresql://", "postgres://")):
        raise SystemExit("Eso no parece una cadena de conexión de Postgres. Volvé a abrir el .bat y probá de nuevo.")
    with open(ENV, "a", encoding="utf-8") as f:
        f.write(f"DATABASE_URL={url}\n")
    log("Cadena de conexión guardada en .env (solo en esta PC)")
    return url


def pedir_clave() -> str:
    """Ventanita para que la persona escriba la contraseña (no se ve en pantalla ni queda en el registro)."""
    try:
        import tkinter as tk
        from tkinter import simpledialog
        raiz = tk.Tk()
        raiz.withdraw()
        raiz.attributes("-topmost", True)
        clave = simpledialog.askstring("Radar Prop - Supabase",
                                       "Pegá la contraseña de la base de datos de Supabase\n"
                                       "(la que generaste con Reset password):", show="*", parent=raiz)
        raiz.destroy()
    except Exception:
        clave = getpass.getpass("Contraseña de la base de datos de Supabase (no se ve al escribir): ")
    if not clave:
        raise SystemExit("No se escribió la contraseña. Volvé a abrir el .bat cuando la tengas.")
    return clave


def guardar_url(url: str):
    lineas = [ln for ln in open(ENV, encoding="utf-8")] if os.path.exists(ENV) else []
    lineas = [ln for ln in lineas if not ln.strip().startswith("DATABASE_URL=")]
    lineas.append(f"DATABASE_URL={url}\n")
    with open(ENV, "w", encoding="utf-8") as f:
        f.writelines(lineas)


def borrar_url():
    if os.path.exists(ENV):
        lineas = [ln for ln in open(ENV, encoding="utf-8") if not ln.strip().startswith("DATABASE_URL=")]
        with open(ENV, "w", encoding="utf-8") as f:
            f.writelines(lineas)


def main():
    log("=== Carga en Supabase ===")
    plantilla = os.path.join(RAIZ, "supabase_conexion.txt")  # cadena de Supabase SIN contraseña (no es secreta)
    from alembic.config import main as alembic_main
    from sqlalchemy import text

    from app.db_util import engine_para, normalizar_url

    verificar = True
    for intento in range(3):
        env = leer_env()
        if not env.get("DATABASE_URL") and os.path.exists(plantilla):
            url = open(plantilla, encoding="utf-8").read().strip()
        else:
            url = env.get("DATABASE_URL") or pedir_url()
        if re.search(r"\[YOUR[-_]PASSWORD\]", url):
            url = re.sub(r"\[YOUR[-_]PASSWORD\]", quote(pedir_clave(), safe=""), url)
            guardar_url(url)
            log("Contraseña guardada en .env (solo en esta PC)")
        url = normalizar_url(url, "pg8000")
        os.environ["DATABASE_URL"] = url
        log(f"Base destino: {oculta(url)}")
        # prueba de conexión (con certificado verificado; si Windows no lo reconoce, se reintenta sin verificar)
        try:
            try:
                with engine_para(url).connect() as c:
                    c.execute(text("SELECT 1"))
            except Exception as e:
                if "CERTIFICATE" in str(e).upper() or "SSL" in str(e).upper():
                    log("Aviso: Windows no reconoció el certificado de Supabase; la conexión sigue cifrada pero sin verificarlo")
                    verificar = False
                    os.environ["RADAR_SSL_SIN_VERIFICAR"] = "1"
                    with engine_para(url, verificar_certificado=False).connect() as c:
                        c.execute(text("SELECT 1"))
                else:
                    raise
            break
        except Exception as e:
            if "password authentication failed" in str(e).lower():
                borrar_url()
                log("La contraseña no es correcta. Se borró la guardada; probá de nuevo.")
                if intento == 2:
                    raise SystemExit("Tres intentos con contraseña incorrecta. Revisala en Supabase y volvé a abrir el .bat.") from e
                continue
            raise
    log("Conexión OK")

    # 2) esquema
    cwd = os.getcwd()
    os.chdir(BACKEND)
    try:
        alembic_main(argv=["-c", os.path.join(BACKEND, "alembic.ini"), "upgrade", "head"])
    finally:
        os.chdir(cwd)
    log("Esquema creado / actualizado")

    # 3) datos
    from migrar_sqlite_a_postgres import imprimir, migrar
    db = os.path.join(OJO, "propiedades.db")
    cap = os.path.join(OJO, "modulos", "datos", "captacion.db")
    if not os.path.exists(db):
        raise SystemExit(f"No encontré {db}")
    log("Pasando las propiedades (tarda 1 o 2 minutos)...")
    r = migrar(db, url, cap if os.path.exists(cap) else None, silencioso=True, verificar_certificado=verificar)
    imprimir(r)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(repr(r) + "\n")
    log("LISTO: los conteos coinciden" if r["ok"] else "ATENCIÓN: hay diferencias en los conteos")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        log("ERROR:\n" + traceback.format_exc().replace(os.environ.get("DATABASE_URL", "\0"), "****"))
        sys.exit(1)
