"""
Resolución de rutas de recursos y datos, compatible con PyInstaller.

En desarrollo, los recursos (assets/, src/database/) y los datos de salida
(documentos/) viven bajo la raíz del proyecto. Al empaquetar con PyInstaller
(`sys.frozen`), los recursos se extraen a `sys._MEIPASS`.

`preparar_entorno()` (llamado al inicio de main.py) deja el entorno coherente
para el ejecutable:
  • fija el directorio de trabajo en la base de recursos, de modo que TODAS las
    rutas a `documentos/` —tanto las relativas a os.getcwd() como las relativas a
    __file__— apunten al MISMO sitio persistente (sin refactorizar decenas de
    archivos);
  • carga el `.env` situado junto al ejecutable;
  • garantiza que exista la carpeta `documentos/`.

También expone `ruta_recurso()` / `ruta_datos()` para código nuevo que quiera ser
explícito.
"""

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
# raíz del proyecto en desarrollo (src/utils -> raíz)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_THIS_DIR))


def es_frozen() -> bool:
    """True si la app corre como ejecutable PyInstaller."""
    return bool(getattr(sys, "frozen", False))


def dir_recursos() -> str:
    """Carpeta base de recursos de solo lectura (assets, SQL…)."""
    if es_frozen():
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return _PROJECT_ROOT


def dir_ejecutable() -> str:
    """Carpeta donde está el .exe (o la raíz del proyecto en desarrollo)."""
    if es_frozen():
        return os.path.dirname(sys.executable)
    return _PROJECT_ROOT


def ruta_recurso(*partes) -> str:
    """Ruta a un recurso empaquetado (p. ej. ruta_recurso('assets', 'lang'))."""
    return os.path.join(dir_recursos(), *partes)


def ruta_datos(*partes) -> str:
    """Ruta a datos de salida en tiempo de ejecución (bajo documentos/)."""
    return os.path.join(dir_recursos(), "documentos", *partes)


def preparar_entorno():
    """Prepara el entorno para ejecución empaquetada. Inocuo en desarrollo."""
    base = dir_recursos()
    try:
        # Unifica el destino de documentos/: con el cwd en `base`, las rutas
        # basadas en os.getcwd() y las basadas en __file__ (que resuelven a
        # `_MEIPASS`) coinciden en el mismo directorio persistente (onedir).
        if es_frozen():
            os.chdir(base)
        # Carga .env junto al ejecutable (la app también lo carga vía conexion.py).
        try:
            from dotenv import load_dotenv
            for cand in (os.path.join(dir_ejecutable(), ".env"),
                         os.path.join(base, ".env")):
                if os.path.exists(cand):
                    load_dotenv(cand)
                    break
        except Exception:
            pass
        # Garantiza la carpeta de salidas.
        os.makedirs(os.path.join(base, "documentos"), exist_ok=True)
    except Exception:
        # Nunca debe impedir el arranque de la app.
        pass
