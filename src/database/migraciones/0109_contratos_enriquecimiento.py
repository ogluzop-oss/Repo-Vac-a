"""
Migracion 0109 — Enriquecimiento de Contratos (Módulo 9). ADITIVA, idempotente, reversible.
Auditoría: contratos laborales (`rrhh_contratos`, con renovaciones/modificaciones/anexos) y contratos
de servicio con cliente + SLA (`contratos_servicio`, usados por SAT) YA existen. Se añade lo ausente:
un REPOSITORIO CENTRAL de contratos para los tipos no cubiertos (proveedor, alquiler, seguro,
licencia, servicio general), obligaciones/hitos y cláusulas GENÉRICAS (aplicables a cualquier
contrato por origen_tipo+origen_id) y alertas de vencimiento/renovación. No reescribe los existentes:
los referencia. No duplica.
"""

VERSION = "0109"
DESCRIPCION = "Contratos: repositorio central + obligaciones/cláusulas genéricas + alertas vencimiento"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("contratos", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        codigo VARCHAR(60) DEFAULT NULL,
        tipo VARCHAR(30) NOT NULL DEFAULT 'servicio',
        contraparte VARCHAR(160) DEFAULT NULL,
        id_referencia VARCHAR(64) DEFAULT NULL,
        fecha_inicio DATE DEFAULT NULL,
        fecha_fin DATE DEFAULT NULL,
        valor DECIMAL(14,2) DEFAULT 0,
        moneda VARCHAR(8) DEFAULT 'EUR',
        auto_renovacion TINYINT NOT NULL DEFAULT 0,
        preaviso_dias INT NOT NULL DEFAULT 30,
        estado VARCHAR(20) NOT NULL DEFAULT 'VIGENTE',
        doc_ruta VARCHAR(255) DEFAULT NULL,
        observaciones TEXT DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        actualizado DATETIME DEFAULT NULL,
        INDEX idx_contrato (id_empresa, tipo, estado, fecha_fin)"""),
    ("contrato_obligaciones", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        origen_tipo VARCHAR(30) NOT NULL DEFAULT 'contratos',
        origen_id INT NOT NULL,
        descripcion VARCHAR(255) NOT NULL,
        tipo VARCHAR(20) NOT NULL DEFAULT 'hito',
        fecha_limite DATE DEFAULT NULL,
        cumplida TINYINT NOT NULL DEFAULT 0,
        fecha_cumplida DATETIME DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_oblig (id_empresa, origen_tipo, origen_id, cumplida)"""),
    ("contrato_clausulas", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) DEFAULT NULL,
        origen_tipo VARCHAR(30) NOT NULL DEFAULT 'contratos',
        origen_id INT NOT NULL,
        titulo VARCHAR(160) NOT NULL,
        texto TEXT DEFAULT NULL,
        creado DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_clausula (origen_tipo, origen_id)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
