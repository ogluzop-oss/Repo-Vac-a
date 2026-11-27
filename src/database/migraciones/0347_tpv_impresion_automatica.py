"""
Migración 0347 — Impresión automática del ticket de venta en el TPV (petición explícita,
2026-11-16). ADITIVA, idempotente, reversible.

`tpv_imprimir_ticket_auto` (desactivada por defecto): cuando está activa, tras generar el PDF del
ticket de cada venta el TPV también lo envía a la impresora PREDETERMINADA del sistema operativo
(`src.utils.plataforma.imprimir_archivo`, mismo mecanismo ya usado para el vale de devolución).
Por defecto en 0 porque, sin una impresora térmica real configurada como predeterminada, forzar el
envío a imprimir en cada venta puede abrir diálogos inesperados (p. ej. contra impresoras virtuales
tipo "Microsoft Print to PDF") — se activa explícitamente el día que la empresa conecta su
impresora de tickets y la deja como predeterminada de Windows.
"""

VERSION = "0347"
DESCRIPCION = "empresas.tpv_imprimir_ticket_auto — impresión automática del ticket de venta"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute(
        "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS "
        "tpv_imprimir_ticket_auto TINYINT(1) NOT NULL DEFAULT 0")


def revertir(cur):
    cur.execute("ALTER TABLE empresas DROP COLUMN IF EXISTS tpv_imprimir_ticket_auto")
