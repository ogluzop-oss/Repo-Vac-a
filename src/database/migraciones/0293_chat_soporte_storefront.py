"""
Migración 0293 — Fase 6 e-commerce (Catálogo Web / Canal Web): chat de soporte del storefront
(IA primero, con escalado a humano). ADITIVA, reversible, idempotente.

`cd_chat_visitantes`: una fila por sesión de chat de un visitante anónimo (token aleatorio, sin
cuenta de usuario — el storefront no exige login). Mientras `id_ticket` es NULL, la conversación
la lleva la IA (histórico en `cd_chat_mensajes`, tabla NUEVA: no existía ninguna infraestructura de
chat para clientes públicos, confirmado por auditoría previa — `sat.tickets`/`ticket_comentarios`
son de personal interno, `compras.b2b_chat` es extranet B2B autenticada). En cuanto se escala
(petición explícita del visitante o la IA no puede ayudar), se crea un ticket SAT real
(`services.sat.tickets.crear_ticket(canal="chat_web", ...)`, columna `canal` ya existente y libre
de formato — CERO cambio de esquema en `tickets`) y la conversación pasa a vivir ENTERAMENTE en
`ticket_comentarios` (la MISMA tabla que ya usa el panel de soporte interno,
`gui/sat_dashboard.py`) — nunca dos fuentes de verdad para el mismo hilo.
"""

VERSION = "0293"
DESCRIPCION = "Chat de soporte del storefront, IA + escalado a SAT (cd_chat_visitantes/cd_chat_mensajes)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cd_chat_visitantes (
            token            CHAR(32)     NOT NULL PRIMARY KEY,
            id_empresa       CHAR(36)     NOT NULL,
            id_ticket        BIGINT                DEFAULT NULL,
            creado_en        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            ultima_actividad DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_chatvis_emp (id_empresa)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cd_chat_mensajes (
            id          BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            token       CHAR(32)     NOT NULL,
            remitente   VARCHAR(12)  NOT NULL,
            texto       TEXT         NOT NULL,
            creado_en   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_chatmsg_token (token)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS cd_chat_mensajes")
    cur.execute("DROP TABLE IF EXISTS cd_chat_visitantes")
