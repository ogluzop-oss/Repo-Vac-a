"""
Migración 0252 — Escaneo remoto: soporte para solicitudes de FOTO (no solo código escaneado). ADITIVA,
reversible.

Extiende `escaneos_remotos` (migración 0244+0246) con una columna `tipo` ('codigo'|'foto'): la solicitud
"código" ya existía (delegar el escaneo de un código de barras/QR al móvil); "foto" es la misma
infraestructura de difusión-por-tienda/reclamo/expiración, pero el móvil responde con una FOTO en vez de
un valor de texto — primer consumidor: la foto de evidencia obligatoria de Mermas en escritorio
(antes solo se podía adjuntar desde el propio móvil, nunca solicitarla desde el PC).
"""

VERSION = "0252"
DESCRIPCION = "escaneos_remotos: columna tipo ('codigo'/'foto')"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute(
        "ALTER TABLE escaneos_remotos ADD COLUMN IF NOT EXISTS tipo VARCHAR(10) NOT NULL DEFAULT 'codigo'"
    )


def revertir(cur):
    cur.execute("ALTER TABLE escaneos_remotos DROP COLUMN IF EXISTS tipo")
