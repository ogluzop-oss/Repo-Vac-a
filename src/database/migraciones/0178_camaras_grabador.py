"""
Migración 0178 — Videovigilancia: orquestación multi-terminal de la grabación. ADITIVA, idempotente, reversible.

`camaras_grabador` = CONCESIÓN (lease) por cámara: qué terminal la graba y hasta cuándo. UNIQUE por id_camara
→ como máximo UNA terminal graba cada cámara. Failover: si la propietaria cae, la concesión caduca y otra la
reclama. AISLAMIENTO por `id_empresa`.
"""

VERSION = "0178"
DESCRIPCION = "Videovigilancia: camaras_grabador (concesión de grabación por terminal, anti-duplicado)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_COLS = """
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    id_empresa CHAR(36) DEFAULT NULL,
    id_camara BIGINT NOT NULL,
    terminal VARCHAR(120) NOT NULL,
    expira DATETIME NOT NULL,
    actualizado DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_grabador (id_camara),
    INDEX idx_grabador (id_empresa, expira)"""


def aplicar(cur):
    cur.execute(f"CREATE TABLE IF NOT EXISTS camaras_grabador ({_COLS}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS camaras_grabador")
