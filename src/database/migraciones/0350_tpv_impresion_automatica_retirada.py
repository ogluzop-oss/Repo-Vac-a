"""
Migración 0350 — retira `empresas.tpv_imprimir_ticket_auto` (añadida en la migración 0347).
ADITIVA en el sentido de "revierte limpiamente una migración anterior", idempotente, reversible.

Petición explícita, 2026-11-16 (mismo día, pasos posteriores de la misma conversación): la
impresión automática del ticket de venta deja de ser una opción configurable con casilla en
Configuración → Gestión caja — pasa a estar SIEMPRE activa por defecto para cualquier empresa
(mismo mecanismo de envío a la impresora predeterminada, `utils.plataforma.imprimir_archivo`,
ahora incondicional en `gui.tpv`). Sin ningún interruptor que desactivarla, la columna que
guardaba ese on/off deja de tener sentido — se retira en vez de dejarla huérfana en el esquema.
"""

VERSION = "0350"
DESCRIPCION = "retira empresas.tpv_imprimir_ticket_auto (impresión automática pasa a ser siempre activa, no configurable)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("ALTER TABLE empresas DROP COLUMN IF EXISTS tpv_imprimir_ticket_auto")


def revertir(cur):
    cur.execute(
        "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS "
        "tpv_imprimir_ticket_auto TINYINT(1) NOT NULL DEFAULT 0")
