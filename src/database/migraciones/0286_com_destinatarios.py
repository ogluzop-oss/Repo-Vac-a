"""
Migración 0286 — Destinatarios reales (Para/CC/Cco) de circulares y encuestas internas.

Hasta ahora `com_circulares`/`com_encuestas` (0157) eran SIEMPRE una difusión a toda la empresa:
`listar_circulares`/`listar_encuestas` no filtraban por destinatario, así que cualquier usuario de
la empresa veía TODO lo publicado. Esta migración añade `com_destinatarios`, que permite targetear
una circular/encuesta a usuarios concretos de la propia empresa (Para/CC/Cco, como un correo real),
y también registra los REENVÍOS (un reenvío no duplica la circular/encuesta: solo añade más filas
de destinatario apuntando al mismo `id_entidad`, con `reenviado_por` indicando quién reenvió).

Retrocompatibilidad deliberada: una circular/encuesta con CERO filas en `com_destinatarios` sigue
siendo "difusión a toda la empresa" (el comportamiento histórico) — así ninguna fila ya existente
deja de ser visible para nadie. `tipo_entidad` reutiliza las mismas constantes ENTIDAD ya usadas en
`com_adjuntos` ('CIRCULAR' | 'ENCUESTA').

ADITIVA, idempotente (`CREATE TABLE IF NOT EXISTS`), reversible.
"""

VERSION = "0286"
DESCRIPCION = "Destinatarios Para/CC/Cco + reenvíos de circulares y encuestas internas"
REVERSIBLE = True
REQUIERE_BACKUP = False

_SQL = """
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    tipo_entidad VARCHAR(20) NOT NULL,
    id_entidad BIGINT NOT NULL,
    usuario_id INT NOT NULL,
    usuario_nombre VARCHAR(120) DEFAULT NULL,
    tipo VARCHAR(10) NOT NULL DEFAULT 'PARA',
    reenviado_por VARCHAR(64) DEFAULT NULL,
    leido TINYINT(1) NOT NULL DEFAULT 0,
    creado DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_destinatario_entidad (tipo_entidad, id_entidad),
    INDEX idx_destinatario_usuario (usuario_id, tipo_entidad, creado)
"""


def aplicar(cur):
    cur.execute(f"CREATE TABLE IF NOT EXISTS com_destinatarios ({_SQL}) "
                f"ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS com_destinatarios")
