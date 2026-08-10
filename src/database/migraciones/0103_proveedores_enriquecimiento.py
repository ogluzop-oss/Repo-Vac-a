"""
Migracion 0103 — Enriquecimiento de Proveedores (Módulo 2). ADITIVA, idempotente, reversible.
Auditoría previa: homologaciones/evaluaciones/scoring/incidencias/históricos/auditoría/documentación ya
existen (proveedores.homologacion_estado, proveedores_evaluacion). Se añade SOLO lo que faltaba:
  · certificaciones de proveedor (con validez/caducidad),
  · acuerdos marco (contratos de suministro con renovación),
  · precios negociados por artículo (con vigencia).
La RENOVACIÓN AUTOMÁTICA se resuelve con un job del Scheduler existente (alertas de vencimiento).
Multiempresa por id_empresa. No duplica: reutiliza proveedores/artículos existentes.
"""

VERSION = "0103"
DESCRIPCION = "Proveedores: certificaciones + acuerdos marco + precios negociados"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("proveedor_certificaciones", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        id_proveedor INT NOT NULL,
        tipo VARCHAR(60) NOT NULL,
        numero VARCHAR(80) DEFAULT NULL,
        emisor VARCHAR(120) DEFAULT NULL,
        fecha_emision DATE DEFAULT NULL,
        fecha_caducidad DATE DEFAULT NULL,
        estado VARCHAR(20) NOT NULL DEFAULT 'vigente',
        ref_documento VARCHAR(120) DEFAULT NULL,
        renovacion_auto TINYINT NOT NULL DEFAULT 0,
        creada DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_provcert (id_empresa, id_proveedor, estado, fecha_caducidad)"""),
    ("proveedor_acuerdos_marco", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        id_proveedor INT NOT NULL,
        referencia VARCHAR(80) DEFAULT NULL,
        descripcion VARCHAR(255) DEFAULT NULL,
        fecha_inicio DATE DEFAULT NULL,
        fecha_fin DATE DEFAULT NULL,
        importe_comprometido DECIMAL(14,2) DEFAULT 0,
        condiciones TEXT DEFAULT NULL,
        estado VARCHAR(20) NOT NULL DEFAULT 'vigente',
        renovacion_auto TINYINT NOT NULL DEFAULT 0,
        meses_renovacion INT DEFAULT 12,
        creada DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_provacu (id_empresa, id_proveedor, estado, fecha_fin)"""),
    ("proveedor_precios_negociados", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        id_proveedor INT NOT NULL,
        codigo_articulo VARCHAR(64) DEFAULT NULL,
        precio DECIMAL(12,4) NOT NULL DEFAULT 0,
        divisa VARCHAR(8) DEFAULT 'EUR',
        descuento DECIMAL(6,2) DEFAULT 0,
        cantidad_minima INT DEFAULT 1,
        fecha_inicio DATE DEFAULT NULL,
        fecha_fin DATE DEFAULT NULL,
        id_acuerdo INT DEFAULT NULL,
        creada DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_provprec (id_empresa, id_proveedor, codigo_articulo, fecha_fin)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
