"""Quitar acentos rápido. Da exactamente lo mismo que filtrar carácter por carácter las marcas combinantes
(categoría Unicode "Mn") después de normalizar a NFD, pero sin recorrer en Python cada letra de las descripciones:
con 16.000 avisos eso eran millones de llamadas y el servidor tardaba segundos en cargar."""
import re
import unicodedata

_MN_BMP = re.compile("[" + "".join(re.escape(chr(i)) for i in range(0x10000) if unicodedata.category(chr(i)) == "Mn") + "]")
_ASTRAL = re.compile("[\U00010000-\U0010FFFF]")


def sin_marcas(s: str) -> str:
    if s.isascii():
        return s
    s = unicodedata.normalize("NFD", s)
    if _ASTRAL.search(s):  # emojis u otros caracteres raros: camino lento, exacto
        return "".join(c for c in s if unicodedata.category(c) != "Mn")
    return _MN_BMP.sub("", s)
