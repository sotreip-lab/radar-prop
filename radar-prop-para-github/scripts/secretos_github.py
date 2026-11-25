"""Muestra, solo en esta PC, los dos valores que hay que pegar como secretos en GitHub.

- DATABASE_URL: la conexión a Supabase que ya está guardada en radar-prop/.env.
- BACKUP_CLAVE: la clave de los respaldos. Se genera una sola vez y queda en .env.
  Sin ella no se pueden abrir los respaldos: no la borres.

Nada de esto se sube al repositorio ni pasa por el chat.
"""
import os
import re
import secrets
import string
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = os.path.join(RAIZ, ".env")


def leer_env() -> dict:
    d = {}
    if os.path.exists(ENV):
        for linea in open(ENV, encoding="utf-8"):
            if "=" in linea and not linea.strip().startswith("#"):
                k, v = linea.split("=", 1)
                d[k.strip()] = v.strip().strip('"').strip("'")
    return d


def url_sin_driver(url: str) -> str:
    return re.sub(r"^postgres(ql)?(\+\w+)?://", "postgresql://", url.strip())


def clave_respaldo(env: dict) -> str:
    if len(env.get("BACKUP_CLAVE", "")) >= 20:
        return env["BACKUP_CLAVE"]
    clave = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(40))
    with open(ENV, "a", encoding="utf-8") as f:
        f.write(f"\nBACKUP_CLAVE={clave}\n")
    return clave


def mostrar(valores: list[tuple[str, str]]):
    import tkinter as tk

    v = tk.Tk()
    v.title("Radar Prop - Secretos para GitHub")
    v.attributes("-topmost", True)
    tk.Label(v, justify="left", font=("Segoe UI", 10), text=(
        "En GitHub: Settings → Secrets and variables → Actions → New repository secret.\n"
        "Creá estos dos secretos: en Name va el nombre en negrita y en Secret el valor (botón Copiar).")
    ).pack(padx=14, pady=(12, 6), anchor="w")
    for nombre, valor in valores:
        marco = tk.Frame(v)
        marco.pack(fill="x", padx=14, pady=4)
        tk.Label(marco, text=nombre, font=("Segoe UI", 10, "bold"), width=14, anchor="w").pack(side="left")
        e = tk.Entry(marco, width=60, show="•")
        e.insert(0, valor)
        e.configure(state="readonly")
        e.pack(side="left", padx=6)

        def copiar(x=valor, b=None):
            v.clipboard_clear()
            v.clipboard_append(x)
        tk.Button(marco, text="Copiar", command=copiar).pack(side="left")
    tk.Label(v, fg="#a33", font=("Segoe UI", 9), text=(
        "BACKUP_CLAVE quedó guardada en radar-prop\\.env. Sin ella no se pueden abrir los respaldos.")
    ).pack(padx=14, pady=(6, 4), anchor="w")
    tk.Button(v, text="Listo", width=12, command=v.destroy).pack(pady=(4, 12))
    v.mainloop()


def main() -> int:
    env = leer_env()
    url = os.environ.get("DATABASE_URL") or env.get("DATABASE_URL")
    if not url:
        print("No encuentro la conexión a Supabase. Corré primero 'Cargar en Supabase.bat'.")
        return 1
    valores = [("DATABASE_URL", url_sin_driver(url)), ("BACKUP_CLAVE", clave_respaldo(env))]
    try:
        mostrar(valores)
    except Exception:
        for n, val in valores:  # sin ventana: se muestra en la consola
            print(f"{n}: {val}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
