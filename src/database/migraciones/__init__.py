"""
Paquete de MIGRACIONES versionadas (C4).

Cada migración es un módulo `NNNN_descripcion.py` con `VERSION`, `DESCRIPCION`,
`aplicar(cur)` y opcional `revertir(cur)`. La lista `MODULOS` mantiene el orden
explícito y GARANTIZA el descubrimiento dentro del `.exe` (donde `pkgutil` no ve
los módulos empaquetados en el archivo PYZ). Al añadir una migración nueva,
inclúyela aquí.
"""

MODULOS = [
    "0001_baseline",
    "0002_fiscal",
]
