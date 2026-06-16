# -*- mode: python ; coding: utf-8 -*-
# ============================================================
# PyInstaller spec — Smart Manager AI  (build onedir para Windows)
#
#   pip install -r requirements-dev.txt
#   pyinstaller SmartManagerAI.spec --noconfirm
#
# Resultado: dist/SmartManagerAI/SmartManagerAI.exe (+ carpeta _internal).
# Distribuye la carpeta dist/SmartManagerAI/ completa. Coloca el .env junto al
# .exe (las salidas se guardan en _internal/documentos/, persistentes).
# ============================================================
import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_all

ROOT = os.path.abspath(os.getcwd())

# ── Recursos a empaquetar (solo lectura) ────────────────────
datas = []

# Todo el árbol assets/ (lang, fuentes, currencies, logos, wavs, icono…)
# excepto cachés de Python.
for base, _dirs, files in os.walk(os.path.join(ROOT, "assets")):
    if "__pycache__" in base:
        continue
    for f in files:
        if f.endswith((".pyc", ".pyo")):
            continue
        ruta = os.path.join(base, f)
        destino = os.path.relpath(base, ROOT)  # mantiene la jerarquía assets/...
        datas.append((ruta, destino))

# SQL de arranque y datos de ejemplo.
for f in os.listdir(os.path.join(ROOT, "src", "database")):
    if f.endswith(".sql"):
        datas.append((os.path.join(ROOT, "src", "database", f), os.path.join("src", "database")))

# Esquemas XSD/WSDL de Verifactu (C3.3.1.1) — generación y validación de registros.
_esq = os.path.join(ROOT, "src", "services", "fiscal", "esquemas")
for f in os.listdir(_esq):
    if f.endswith((".xsd", ".wsdl")):
        datas.append((os.path.join(_esq, f), os.path.join("src", "services", "fiscal", "esquemas")))

# Datos de paquetes de terceros que los necesitan en runtime.
for paquete in ("edge_tts",):
    try:
        datas += collect_data_files(paquete)
    except Exception:
        pass

# ── Imports que PyInstaller no detecta por análisis estático ─
hiddenimports = []
hiddenimports += collect_submodules("src")
hiddenimports += collect_submodules("assets")
# Migraciones (C4): sus módulos empiezan por dígito (0001_*, 0002_…) y
# collect_submodules los omite. Se añaden por glob para garantizar su
# empaquetado en el .exe (presente y futuras migraciones).
import glob as _glob
hiddenimports.append("src.database.migraciones")
for _mig in _glob.glob(os.path.join(ROOT, "src", "database", "migraciones", "*.py")):
    _nm = os.path.splitext(os.path.basename(_mig))[0]
    if _nm not in ("__init__", "_init_"):
        hiddenimports.append("src.database.migraciones." + _nm)
# unidecode carga submódulos de datos perezosamente (unidecode.x0XX) → recogerlos.
try:
    hiddenimports += collect_submodules("unidecode")
except Exception:
    pass
hiddenimports += [
    "pymysql", "pymysql.cursors",
    "dbutils", "dbutils.pooled_db",  # pool de conexiones (A2)
    "reportlab.graphics.barcode", "reportlab.graphics.barcode.code128",
    "reportlab.graphics.barcode.eanbc", "reportlab.graphics.barcode.qr",
    "barcode", "barcode.writer", "pyzbar", "pyzbar.pyzbar",
    "PIL._tkinter_finder",
    "pyttsx3.drivers", "pyttsx3.drivers.sapi5",
    "openpyxl", "pandas", "numpy",
    "jwt",  # PyJWT (tokens de la futura API; import perezoso en seguridad/tokens)
]

# Paquetes pesados/con datos que se recogen completos si están instalados.
# `cryptography` se incluye entero para garantizar el binario Rust (_rust) que usa
# la firma 3DES de Redsys (se importa de forma perezosa y podría no detectarse).
binaries = []
for paquete in ("prophet", "matplotlib", "cv2", "anthropic", "edge_tts", "cryptography", "argon2"):
    try:
        d, b, h = collect_all(paquete)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

ICONO = os.path.join(ROOT, "assets", "icono.ico")
icono_arg = ICONO if os.path.exists(ICONO) else None

a = Analysis(
    [os.path.join("src", "main.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "PyQt5", "PySide6", "PySide2", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SmartManagerAI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,            # app GUI: sin consola
    disable_windowed_traceback=False,
    icon=icono_arg,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SmartManagerAI",
)
