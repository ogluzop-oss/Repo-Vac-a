"""
Migración 0311 — `empresa_branding.color_terciario`. ADITIVA, idempotente, reversible.

`portal_theming.py` (tema compartido por los portales Empleado/Empresa B2B/Proveedor) solo
personalizaba acento (`color_primario`) y superficie de tarjetas (`color_secundario`), dejando el
fondo general de la interfaz fijo en el literal por defecto (`#0D1117`) — así eran las dos únicas
columnas de color que ya existían en `empresa_branding`. El encargo pide ahora poder teñir también
el fondo general; se añade como una TERCERA columna de color en la MISMA tabla `empresa_branding`
(nunca una tabla de tema paralela — mismo criterio que ya documenta `portal_theming.py` para las
otras dos). Los consumidores de `empresa_branding` fuera de los portales (`aeat/documento.py`,
`saas/facturas.py`) solo leen `nombre_comercial`, nunca colores, así que esta columna no afecta a
ningún documento/PDF generado — es exclusiva de la identidad visual de los 3 portales internos.
"""

VERSION = "0311"
DESCRIPCION = "empresa_branding.color_terciario (fondo general de los portales internos)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("ALTER TABLE empresa_branding ADD COLUMN IF NOT EXISTS "
                "color_terciario VARCHAR(12) DEFAULT NULL")


def revertir(cur):
    cur.execute("ALTER TABLE empresa_branding DROP COLUMN IF EXISTS color_terciario")
