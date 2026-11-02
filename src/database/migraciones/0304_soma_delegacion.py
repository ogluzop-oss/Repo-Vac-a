"""
Migración 0304 — Delegación de tareas repetitivas al agente IA SOMA (SUPERADMIN).

`soma_delegaciones`: reglas por empresa — "cuando pase X [tipo, del catálogo de
`services.soma_delegacion.catalogo`], que SOMA actúe siguiendo estas instrucciones [texto libre
OBLIGATORIO]". `soma_delegaciones_historial`: registro de cada evaluación/ejecución (igual
función de auditoría que `automatizaciones_ejecuciones` del motor de Automatización clásico, pero
para esta capa nueva de instrucciones libres).
"""

VERSION = "0304"
DESCRIPCION = "Delegación de tareas repetitivas a SOMA: soma_delegaciones + historial"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = {
    "soma_delegaciones": """
        CREATE TABLE IF NOT EXISTS soma_delegaciones (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa      VARCHAR(36)  NOT NULL,
            tipo            VARCHAR(60)  NOT NULL,
            instrucciones   TEXT         NOT NULL,
            modo_aplicacion VARCHAR(20)  NOT NULL DEFAULT 'revisar_antes',
            activa          TINYINT(1)   NOT NULL DEFAULT 1,
            creado_por      VARCHAR(120)          DEFAULT NULL,
            creado          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            actualizado     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_soma_deleg (id_empresa, tipo, activa)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    "soma_delegaciones_historial": """
        CREATE TABLE IF NOT EXISTS soma_delegaciones_historial (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa      VARCHAR(36)  NOT NULL,
            id_regla        INT          NOT NULL,
            tipo            VARCHAR(60)  NOT NULL,
            contexto_json   MEDIUMTEXT            DEFAULT NULL,
            decision_json   MEDIUMTEXT            DEFAULT NULL,
            estado          VARCHAR(20)  NOT NULL DEFAULT 'aplicado',
            resultado       VARCHAR(500)          DEFAULT NULL,
            creado          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_soma_hist (id_empresa, id_regla, creado)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
}


def aplicar(cur):
    for ddl in _TABLAS.values():
        cur.execute(ddl)


def revertir(cur):
    for t in ("soma_delegaciones_historial", "soma_delegaciones"):
        cur.execute(f"DROP TABLE IF EXISTS {t}")
