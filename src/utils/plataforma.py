"""
Capa portable de integración con el sistema operativo (BLOQUE 8 — compatibilidad).

Fuente única de verdad para abrir archivos/carpetas e imprimir, encapsulando las
diferencias entre Windows / macOS (Darwin) / Linux. Sustituye al código disperso
(`os.startfile`, `os.system("start"/"open"/"xdg-open")`, `subprocess.Popen(["open"|"xdg-open"])`)
que solo funcionaba en algunos SO. No contiene lógica de negocio.

Diseño defensivo: nunca lanza por diferencias de plataforma; devuelve bool de éxito y
registra el error. Así una instalación en un SO sin la utilidad correspondiente degrada
con gracia en vez de romper la UI.
"""
from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess

logger = logging.getLogger(__name__)

SISTEMA = platform.system()          # 'Windows' | 'Darwin' | 'Linux' | otros
ES_WINDOWS = SISTEMA == "Windows"
ES_MAC = SISTEMA == "Darwin"
ES_LINUX = SISTEMA == "Linux"


def _abrir_con(args: list[str]) -> bool:
    try:
        subprocess.Popen(args)
        return True
    except Exception as e:  # pragma: no cover - depende del entorno
        logger.error("No se pudo ejecutar %s: %s", args[:1], e)
        return False


def abrir_archivo(ruta: str | os.PathLike) -> bool:
    """Abre `ruta` con la aplicación predeterminada del SO. Portable y degradable."""
    ruta = os.fspath(ruta)
    if not ruta:
        return False
    try:
        if ES_WINDOWS:
            os.startfile(ruta)  # noqa: S606 - Windows API nativa
            return True
        if ES_MAC:
            return _abrir_con(["open", ruta])
        # Linux y resto de POSIX con freedesktop
        if shutil.which("xdg-open"):
            return _abrir_con(["xdg-open", ruta])
        logger.warning("xdg-open no disponible; no se puede abrir %s", ruta)
        return False
    except Exception as e:
        logger.error("abrir_archivo(%s) falló: %s", ruta, e)
        return False


def abrir_carpeta(ruta: str | os.PathLike) -> bool:
    """Abre la carpeta que contiene `ruta` (o `ruta` si ya es carpeta)."""
    ruta = os.fspath(ruta)
    carpeta = ruta if os.path.isdir(ruta) else os.path.dirname(ruta)
    return abrir_archivo(carpeta or ".")


def imprimir_archivo(ruta: str | os.PathLike) -> bool:
    """Envía `ruta` a la impresora predeterminada del SO. Portable y degradable.

    Windows: verbo 'print' de la shell. macOS/Linux: `lpr` (CUPS) si está disponible.
    """
    ruta = os.fspath(ruta)
    if not ruta or not os.path.exists(ruta):
        logger.warning("imprimir_archivo: ruta inexistente %s", ruta)
        return False
    try:
        if ES_WINDOWS:
            os.startfile(ruta, "print")  # noqa: S606 - Windows API nativa
            return True
        if shutil.which("lpr"):  # macOS y Linux con CUPS
            return _abrir_con(["lpr", ruta])
        logger.warning("lpr no disponible; no se puede imprimir %s", ruta)
        return False
    except Exception as e:
        logger.error("imprimir_archivo(%s) falló: %s", ruta, e)
        return False
