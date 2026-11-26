"""Devolverle al sistema la memoria que quedó libre después de armar el catálogo.

Python libera los objetos, pero el reservador de memoria de Linux (glibc) se queda con los huecos; en el servidor
gratis (512 MB) eso es lo que lo acercaba al límite. malloc_trim(0) los devuelve. En otros sistemas no hace nada.
"""
import ctypes
import gc
from typing import Any

_trim: Any
try:
    _libc = ctypes.CDLL("libc.so.6")
    _trim = _libc.malloc_trim
    # Máximo 2 zonas de memoria para todos los hilos (por defecto glibc abre hasta 8 por núcleo y la memoria se
    # fragmenta: con 10 usuarios a la vez el proceso pasaba de 220 a 420 MB; así queda en ~280 MB).
    # Es lo mismo que la variable MALLOC_ARENA_MAX=2, pero puesto desde el código. M_ARENA_MAX = -8.
    _libc.mallopt(-8, 2)
except (OSError, AttributeError):
    _trim = None


def liberar_memoria() -> None:
    gc.collect()
    if _trim is not None:
        _trim(0)
