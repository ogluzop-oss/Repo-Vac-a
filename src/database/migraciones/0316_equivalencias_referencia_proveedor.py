"""
Migración 0316 — `equivalencias_referencia_proveedor`. ADITIVA, idempotente, reversible.

Tabla de equivalencia/mapeo REFERENCIA DEL PROVEEDOR -> ARTÍCULO INTERNO (petición explícita:
"una tabla de equivalencia/mapeo referencia de proveedor <-> EAN interno, soportando un número
ilimitado de referencias de proveedor por EAN interno"). No existía ningún mecanismo de este
tipo en el ERP (confirmado por auditoría: `proveedor_precios_negociados.codigo_articulo` y
`b2b_catalogo.codigo` usan ya el código interno/del proveedor respectivamente, pero NINGUNA tabla
los relaciona entre sí) — se crea desde cero, sin tocar ninguna tabla existente.

Diseño:
- `(id_empresa, id_proveedor, referencia_proveedor)` es ÚNICO: una misma referencia de un mismo
  proveedor solo puede apuntar a UN artículo interno a la vez (si cambia, se reemplaza la fila,
  nunca se duplica).
- `codigo_articulo` NO es único: múltiples referencias (incluso de proveedores distintos) pueden
  apuntar al MISMO artículo interno — "un número ilimitado de referencias de proveedor por EAN
  interno", exactamente como se pidió.
- `estado` ('activa'/'deshecha') en vez de borrado físico — mecanismo de seguridad REVERSIBLE
  ("deshacer cualquier equivalencia/mapeo en cualquier etapa del proceso", petición explícita):
  deshacer una equivalencia nunca borra el historial, solo la desactiva (`deshacer_equivalencia`,
  ver `src/db/equivalencias_proveedor.py`), y puede reactivarse.
- `id_proveedor` es NULLable a propósito: admite tanto proveedores del directorio clásico
  (`proveedores.id`) como suministradores de Smart Suppliers B2B (`suministradores.id`) sin
  forzar una FK a una tabla concreta (dos universos de proveedor distintos y ya establecidos en
  el ERP, ver auditoría) — el campo `origen_proveedor` ('clasico'/'b2b') distingue cuál aplica.
"""

VERSION = "0316"
DESCRIPCION = "equivalencias_referencia_proveedor (mapeo ref. proveedor -> EAN interno, reversible)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS equivalencias_referencia_proveedor (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            id_empresa VARCHAR(64) NOT NULL,
            id_proveedor BIGINT NULL,
            origen_proveedor VARCHAR(10) NOT NULL DEFAULT 'clasico',
            nombre_proveedor VARCHAR(150) NULL,
            referencia_proveedor VARCHAR(100) NOT NULL,
            codigo_articulo VARCHAR(64) NOT NULL,
            estado VARCHAR(10) NOT NULL DEFAULT 'activa',
            creado_por VARCHAR(100) NULL,
            fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
            fecha_actualizacion DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_equiv_ref (id_empresa, id_proveedor, referencia_proveedor),
            KEY idx_equiv_articulo (id_empresa, codigo_articulo),
            KEY idx_equiv_estado (id_empresa, estado)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS equivalencias_referencia_proveedor")
