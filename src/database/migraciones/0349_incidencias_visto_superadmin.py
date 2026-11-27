"""
Migración 0349 — columna `visto_superadmin` en `incidencias_internas`. ADITIVA, idempotente,
reversible.

Petición explícita, 2026-11-16: el badge rojo de la tarjeta "Incidencias" del menú principal debe
desaparecer en cuanto el SUPERADMIN abre una incidencia, aunque su `estado` siga en
`pendiente`/`en_proceso` (ese estado es del CICLO DE VIDA de la incidencia, no de si alguien ya la
ha visto). Hasta ahora `tickets.contar_pendientes()` (que alimenta ese badge, ver
`menu_principal._refrescar_badges`) contaba TODAS las filas en esos dos estados sin ningún
concepto de "visto" — por eso el badge, aunque el mecanismo genérico `services.actividad.
marcar_visto` lo pusiera a cero al abrir el MÓDULO, volvía a aparecer en el siguiente refresco
periódico (cada 60s) o al volver al menú: la fuente de verdad (la cuenta cruda en BD) no sabía
nada de "visto". Esta columna es esa fuente de verdad, por incidencia.
"""

VERSION = "0349"
DESCRIPCION = "visto_superadmin en incidencias_internas (badge deja de reaparecer tras abrir la incidencia)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute(
        "ALTER TABLE incidencias_internas ADD COLUMN IF NOT EXISTS visto_superadmin "
        "TINYINT(1) NOT NULL DEFAULT 0")


def revertir(cur):
    cur.execute("ALTER TABLE incidencias_internas DROP COLUMN IF EXISTS visto_superadmin")
