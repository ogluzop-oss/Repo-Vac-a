"""
Migracion 0104 — Enriquecimiento de Compras (Módulo 3). ADITIVA, idempotente, reversible.
Auditoría: planificación/sugerencias (reabastecimiento), recepción parcial/múltiple, consolidación
(crear_pedido_desde_propuestas), contratos (acuerdos marco del M2), incidencias/costes/facturas ya
existen. Se añade SOLO lo ausente:
  · pedidos recurrentes (programación de pedidos periódicos),
  · órdenes abiertas / blanket orders (con consumos/call-offs).
La comparativa de proveedores y la aprobación multinivel NO requieren tablas: se calculan/gestionan
reutilizando datos existentes (precios negociados, evaluaciones) y el Workflow existente.
"""

VERSION = "0104"
DESCRIPCION = "Compras: pedidos recurrentes + órdenes abiertas (blanket)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("compras_pedidos_recurrentes", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        id_proveedor INT NOT NULL,
        nombre VARCHAR(160) DEFAULT NULL,
        frecuencia_dias INT NOT NULL DEFAULT 30,
        proximo DATE DEFAULT NULL,
        lineas_json TEXT DEFAULT NULL,
        id_almacen INT DEFAULT NULL,
        activo TINYINT NOT NULL DEFAULT 1,
        ultimo_generado DATE DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_precur (id_empresa, activo, proximo)"""),
    ("compras_ordenes_abiertas", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        id_proveedor INT NOT NULL,
        referencia VARCHAR(80) DEFAULT NULL,
        codigo_articulo VARCHAR(64) DEFAULT NULL,
        cantidad_total DECIMAL(14,3) NOT NULL DEFAULT 0,
        cantidad_consumida DECIMAL(14,3) NOT NULL DEFAULT 0,
        precio DECIMAL(12,4) DEFAULT 0,
        fecha_inicio DATE DEFAULT NULL,
        fecha_fin DATE DEFAULT NULL,
        estado VARCHAR(20) NOT NULL DEFAULT 'abierta',
        id_acuerdo INT DEFAULT NULL,
        creada DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_ordab (id_empresa, id_proveedor, estado)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
