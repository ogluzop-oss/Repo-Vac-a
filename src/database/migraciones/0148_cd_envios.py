"""
Migración 0148 — PCD · Etapa B · Fase B7: envíos / logística comercial (cd_envios).

Registro de envíos por Transacción Comercial. El TRANSPORTISTA se integra como adaptador
(provider-agnostic, degradable; credenciales en cd_conexiones cifradas). Aquí se traza el envío,
la etiqueta (referencia/URL, nunca el fichero), el tracking, el estado y las incidencias.

ADITIVA, idempotente, reversible. Multiempresa. No elimina ni altera datos.
"""

VERSION = "0148"
DESCRIPCION = "PCD Etapa B/F7: cd_envios (logística comercial: etiquetas/tracking/incidencias)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("cd_envios", """
        id             BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
        id_empresa     CHAR(36)              DEFAULT NULL,
        id_tx          CHAR(36)     NOT NULL,
        transportista  VARCHAR(40)           DEFAULT NULL,   -- mrw|gls|correos|dhl|ups|fedex|seur|simulado
        tracking       VARCHAR(120)          DEFAULT NULL,
        etiqueta_ref   VARCHAR(255)          DEFAULT NULL,   -- URL o referencia (documental/storage)
        estado         VARCHAR(20)  NOT NULL DEFAULT 'preparando', -- preparando|etiquetado|en_transito|entregado|incidencia|cancelado
        peso           DECIMAL(10,3)         DEFAULT NULL,
        direccion      VARCHAR(255)          DEFAULT NULL,
        incidencia     VARCHAR(255)          DEFAULT NULL,
        eventos        MEDIUMTEXT,                            -- historial de tracking (JSON)
        actor          VARCHAR(120)          DEFAULT NULL,
        ts_creado      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
        ts_actualizado DATETIME              DEFAULT NULL,
        INDEX idx_envios_tx (id_empresa, id_tx),
        INDEX idx_envios_track (id_empresa, tracking),
        INDEX idx_envios_estado (id_empresa, estado)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
