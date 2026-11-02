"""
Migración 0321 — Cross-docking inteligente Producción -> Logística -> Reparto (petición explícita:
automatizar el flujo de salida desde fabricación hasta el envío/recepción en cualquier centro).
ADITIVA, idempotente, reversible.

Auditoría previa (sin infraestructura previa de "mercancía lista para expedir enlazada a una ruta
de reparto concreta"): existían por separado (a) la producción (`ordenes_fabricacion`, sin ningún
campo de centro destino), (b) el cross-dock YA EXISTENTE (`services/expediciones.py`), que solo
empareja recepciones con DEMANDA DE VENTA pendiente, nunca con una ruta/camión, y (c) las rutas de
reparto (`transporte_rutas`/`transporte_paradas`), sin ninguna columna de centro destino estructurado
(solo texto libre `cliente`/`direccion`) ni ningún enlace hacia `documentos_logisticos`. Esta
migración añade EXCLUSIVAMENTE las columnas de enlace que faltaban — ninguna tabla nueva, ningún
motor de stock paralelo (reutiliza `kardex`/`stock_almacen` tal cual).

`centros_trabajo.id_centro` es VARCHAR(36) (UUID), de ahí que las nuevas columnas de centro sean
VARCHAR(36) y no INT.
"""

VERSION = "0321"
DESCRIPCION = "Cross-docking a rutas de reparto: enlaces centro/ruta en documentos_logisticos, transporte_paradas y ordenes_fabricacion"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    # Parada de reparto -> centro registrado (tienda/almacén/fábrica/oficina/otro) al que se dirige.
    cur.execute("ALTER TABLE transporte_paradas ADD COLUMN IF NOT EXISTS id_centro_destino "
               "VARCHAR(36) NULL")
    cur.execute("ALTER TABLE transporte_paradas ADD COLUMN IF NOT EXISTS id_almacen_destino "
               "INT NULL")

    # Documento logístico -> centros origen/destino estructurados + enlace a la ruta/parada que lo
    # recogió (cross-docking) + flag de validación para el cierre de un solo clic.
    cur.execute("ALTER TABLE documentos_logisticos ADD COLUMN IF NOT EXISTS id_centro_origen "
               "VARCHAR(36) NULL")
    cur.execute("ALTER TABLE documentos_logisticos ADD COLUMN IF NOT EXISTS id_centro_destino "
               "VARCHAR(36) NULL")
    cur.execute("ALTER TABLE documentos_logisticos ADD COLUMN IF NOT EXISTS id_ruta BIGINT NULL")
    cur.execute("ALTER TABLE documentos_logisticos ADD COLUMN IF NOT EXISTS id_parada BIGINT NULL")
    cur.execute("ALTER TABLE documentos_logisticos ADD COLUMN IF NOT EXISTS validado "
               "TINYINT(1) NOT NULL DEFAULT 0")
    cur.execute("ALTER TABLE documentos_logisticos ADD COLUMN IF NOT EXISTS id_almacen_origen "
               "INT NULL")

    # Orden de fabricación -> centro destino elegido al registrar producción (antes solo existía
    # `id_almacen`, sin ningún concepto de "a qué centro va esta producción").
    cur.execute("ALTER TABLE ordenes_fabricacion ADD COLUMN IF NOT EXISTS id_centro_destino "
               "VARCHAR(36) NULL")


def revertir(cur):
    cur.execute("ALTER TABLE ordenes_fabricacion DROP COLUMN IF EXISTS id_centro_destino")
    cur.execute("ALTER TABLE documentos_logisticos DROP COLUMN IF EXISTS id_almacen_origen")
    cur.execute("ALTER TABLE documentos_logisticos DROP COLUMN IF EXISTS validado")
    cur.execute("ALTER TABLE documentos_logisticos DROP COLUMN IF EXISTS id_parada")
    cur.execute("ALTER TABLE documentos_logisticos DROP COLUMN IF EXISTS id_ruta")
    cur.execute("ALTER TABLE documentos_logisticos DROP COLUMN IF EXISTS id_centro_destino")
    cur.execute("ALTER TABLE documentos_logisticos DROP COLUMN IF EXISTS id_centro_origen")
    cur.execute("ALTER TABLE transporte_paradas DROP COLUMN IF EXISTS id_almacen_destino")
    cur.execute("ALTER TABLE transporte_paradas DROP COLUMN IF EXISTS id_centro_destino")
