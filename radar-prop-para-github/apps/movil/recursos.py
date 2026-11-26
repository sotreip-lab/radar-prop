"""Íconos y pantalla de inicio de la app de Android, generados desde el ícono de la web (frontend/public/icono-512.png).
Se corre en GitHub Actions después de `npx cap add android` (la carpeta android/ no se guarda en el repositorio)."""
import os
import re

from PIL import Image

AZUL = (0x14, 0x24, 0x3F, 255)
RES = "android/app/src/main/res"
ico = Image.open(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "public", "icono-512.png")).convert("RGBA")

for d, s in [("mdpi", 48), ("hdpi", 72), ("xhdpi", 96), ("xxhdpi", 144), ("xxxhdpi", 192)]:
    p = f"{RES}/mipmap-{d}"
    icono = ico.resize((s, s), Image.LANCZOS)
    icono.save(f"{p}/ic_launcher.png")
    icono.save(f"{p}/ic_launcher_round.png")
    # ícono adaptable (Android 8+): 108dp con el dibujo en el centro (zona segura de 66dp)
    f = round(s * 108 / 48)
    lienzo = Image.new("RGBA", (f, f), (0, 0, 0, 0))
    adentro = ico.resize((round(f * 0.62),) * 2, Image.LANCZOS)
    lienzo.paste(adentro, ((f - adentro.width) // 2,) * 2, adentro)
    lienzo.save(f"{p}/ic_launcher_foreground.png")

with open(f"{RES}/values/ic_launcher_background.xml", "w", encoding="utf-8") as fh:
    fh.write('<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <color name="ic_launcher_background">#14243F</color>\n</resources>\n')

# pantalla de inicio: fondo azul con el ícono (reemplaza el logo de Capacitor)
for raiz, _, archivos in os.walk(RES):
    if "splash.png" in archivos:
        ruta = os.path.join(raiz, "splash.png")
        w, h = Image.open(ruta).size
        fondo = Image.new("RGBA", (w, h), AZUL)
        lado = round(min(w, h) * 0.28)
        logo = ico.resize((lado, lado), Image.LANCZOS)
        fondo.paste(logo, ((w - lado) // 2, (h - lado) // 2), logo)
        fondo.convert("RGB").save(ruta)

# número de versión = número de corrida de GitHub Actions (cada APK nueva se instala encima de la anterior)
v = os.environ.get("VERSION_CODE", "1")
g = "android/app/build.gradle"
txt = open(g, encoding="utf-8").read()
txt = re.sub(r"versionCode \d+", f"versionCode {v}", txt)
txt = re.sub(r'versionName "[^"]*"', f'versionName "2.0.{v}"', txt)
open(g, "w", encoding="utf-8").write(txt)
print("recursos listos, versión", v)
