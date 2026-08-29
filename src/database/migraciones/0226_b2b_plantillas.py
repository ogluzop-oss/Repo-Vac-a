"""
Migración 0226 — Plantillas de aprovisionamiento recurrente (Smart Suppliers B2B · Fase 3).

Permite a una empresa guardar el carrito B2B actual como plantilla nombrada y reenviar sus líneas al
carrito con un clic. Sin precio propio: se re-resuelve al enviar (ver b2b_catalogo.precio_para_cantidad,
migración 0228) para no reintroducir precios obsoletos. ADITIVA, idempotente, reversible.
"""

VERSION = "0226"
DESCRIPCION = "Plantillas de aprovisionamiento B2B (cabecera + líneas)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("b2b_plantillas", """
        id           BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
        id_empresa   CHAR(36)     NOT NULL,
        nombre       VARCHAR(160) NOT NULL,
        creado_en    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_b2b_plant_emp (id_empresa)"""),
    ("b2b_plantilla_lineas", """
        id              BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
        id_plantilla    BIGINT       NOT NULL,
        id_suministrador BIGINT      NOT NULL,
        codigo          VARCHAR(50)  NOT NULL,
        nombre          VARCHAR(255) NOT NULL,
        unidad_medida   VARCHAR(20)  NOT NULL,
        cantidad        INT          NOT NULL DEFAULT 1,
        INDEX idx_b2b_plant_lin_plantilla (id_plantilla)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) "
                    "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
