"""
Migración 0214 — Retirada de "Pedir a Central": elimina las tablas de solicitudes de traspaso al almacén
central (migr 0182), ya sin uso tras retirar el módulo (GUI `pedido_central_gui` + servicio
`logistica/solicitudes`). No la usa ningún otro flujo. Mismo criterio que 0207 (desmontaje).

Irreversible (elimina datos): requiere backup. Idempotente (DROP IF EXISTS).
"""

VERSION = "0214"
DESCRIPCION = "Eliminar solicitudes_traspaso (+_items): 'Pedir a Central' retirado (duplicaba Reabastecimiento)"
REVERSIBLE = False
REQUIERE_BACKUP = True

# Orden: primero la hija (FK), luego la cabecera.
_TABLAS = ["solicitudes_traspaso_items", "solicitudes_traspaso"]


def aplicar(cur):
    for nombre in _TABLAS:
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")


def revertir(cur):
    # Irreversible: las tablas y sus datos se eliminan (el módulo ya no existe).
    pass
