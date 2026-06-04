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

# Todo el árbol assets/ (lang, fuentes, denominaciones, logos, wavs, icono…)
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
hiddenimports += [
    "pymysql", "pymysql.cursors",
    "reportlab.graphics.barcode", "reportlab.graphics.barcode.code128",
    "reportlab.graphics.barcode.eanbc", "reportlab.graphics.barcode.qr",
    "barcode", "barcode.writer", "pyzbar", "pyzbar.pyzbar",
    "PIL._tkinter_finder",
    "pyttsx3.drivers", "pyttsx3.drivers.sapi5",
    "openpyxl", "pandas", "numpy",
]

# Paquetes pesados/con datos que se recogen completos si están instalados.
binaries = []
for paquete in ("prophet", "matplotlib", "cv2", "anthropic", "edge_tts"):
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
