"""
Migración 0044 — Índices de rendimiento en `ventas` (B4). ADITIVA e idempotente.

Justificados por EXPLAIN sobre consultas reales:
- idx_v_emp_tienda_fecha (id_empresa, id_tienda, fecha): panel de ventas (ventas_busqueda),
  informes por empresa/fecha (facturas_cliente.ventas_por_cliente) y barrido de
  reconciliación (ventas_sin_integrar). Sustituye el filtrado post-índice sobre idx_v_fecha.
- idx_v_cliente (cliente_id): historial de cliente (clientes.historial_comercial) que hoy
  hace FULL SCAN (type=ALL).
No altera datos ni lógica; solo añade índices (ADD INDEX IF NOT EXISTS).
"""

VERSION = "0044"
DESCRIPCION = "Índices en ventas: (id_empresa,id_tienda,fecha) + (cliente_id)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_IDX = [
    ("idx_v_emp_tienda_fecha", "id_empresa, id_tienda, fecha"),
    ("idx_v_cliente", "cliente_id"),
]


def aplicar(cur):
    for nombre, cols in _IDX:
        cur.execute(f"ALTER TABLE ventas ADD INDEX IF NOT EXISTS {nombre} ({cols})")


def revertir(cur):
    for nombre, _ in _IDX:
        cur.execute(f"ALTER TABLE ventas DROP INDEX IF EXISTS {nombre}")
