"""
Migración 0177 — Videovigilancia: eventos de detección de movimiento. ADITIVA, idempotente, reversible.

`camaras_eventos` registra los eventos (por ahora, movimiento) detectados por análisis OpenCV. AISLAMIENTO
ESTRICTO: cada fila lleva `id_empresa` + `id_centro`; ninguna consulta cruza departamentos ni empresas.
"""

VERSION = "0177"
DESCRIPCION = "Videovigilancia: camaras_eventos (detección de movimiento, aislamiento empresa+centro)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_COLS = """
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    id_empresa CHAR(36) DEFAULT NULL,
    id_centro VARCHAR(64) DEFAULT NULL,
    id_camara BIGINT DEFAULT NULL,
    tipo VARCHAR(24) NOT NULL DEFAULT 'movimiento',
    instante DATETIME NOT NULL,
    score FLOAT NOT NULL DEFAULT 0,
    estado VARCHAR(16) NOT NULL DEFAULT 'nuevo',
    creado DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_evt (id_empresa, id_centro, instante),
    INDEX idx_evt_cam (id_camara, instante)"""


def aplicar(cur):
    cur.execute(f"CREATE TABLE IF NOT EXISTS camaras_eventos ({_COLS}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS camaras_eventos")
