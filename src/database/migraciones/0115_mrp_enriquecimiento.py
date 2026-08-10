"""
Migracion 0115 — Enriquecimiento de MRP (Módulo 15). ADITIVA, idempotente, reversible.
Auditoría: el MRP ya realiza la explosión de BOM sobre una demanda → necesidades brutas → netas
(descontando stock) → sugerencias de compra/fabricación (`services/mrp/planificador.py`), con BOM
multinivel, centros/capacidad y costes. Se añade lo ausente: PLAN MAESTRO DE PRODUCCIÓN (MPS) que
CONSOLIDA la demanda (pedidos de cliente + previsión) por periodo/artículo y la entrega al
planificador existente. No reimplementa el cálculo de necesidades. No duplica.
"""

VERSION = "0115"
DESCRIPCION = "MRP: Plan Maestro de Producción (MPS) consolidando demanda"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("mrp_plan_maestro", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        periodo VARCHAR(7) NOT NULL,
        articulo VARCHAR(64) NOT NULL,
        demanda_pedidos DECIMAL(14,3) NOT NULL DEFAULT 0,
        demanda_prevision DECIMAL(14,3) NOT NULL DEFAULT 0,
        demanda_total DECIMAL(14,3) NOT NULL DEFAULT 0,
        plan_produccion DECIMAL(14,3) NOT NULL DEFAULT 0,
        estado VARCHAR(20) NOT NULL DEFAULT 'BORRADOR',
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        actualizado DATETIME DEFAULT NULL,
        UNIQUE KEY uq_mps (id_empresa, periodo, articulo)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
