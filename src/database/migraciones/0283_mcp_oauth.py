"""
Migración 0283 — MCP (Model Context Protocol): códigos de autorización OAuth 2.1/PKCE.
ADITIVA, idempotente, reversible.

Contexto (ver `src/mcp_server/oauth.py`): el conector MCP de SOMA expone un flujo OAuth 2.1
(Dynamic Client Registration + Authorization Code + PKCE) que es una ENVOLTURA de los JWT que
el sistema ya emite (`seguridad.tokens`) — no un motor de auth paralelo. La identidad del
CLIENTE MCP (client_id/secret/redirect_uri) reutiliza la tabla `api_dev_apps` ya existente
(migr. 0135, `services/api_publica/developer.py`), que ya está pensada para apps de terceros
OAuth2 y acepta `id_empresa=NULL` (apps no atadas a una empresa concreta, como un conector MCP
registrado dinámicamente). Lo que NO existe en ningún sitio del sistema es el paso intermedio
de un flujo de autorización con consentimiento humano: el CÓDIGO DE AUTORIZACIÓN de un solo uso
que enlaza "este usuario se autenticó con sus credenciales reales" con "este cliente MCP puede
canjearlo por un JWT" — de ahí la única tabla nueva, pequeña y propia de esa responsabilidad.
"""

VERSION = "0283"
DESCRIPCION = "MCP OAuth 2.1: tabla de códigos de autorización de un solo uso (PKCE)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLA = "mcp_oauth_codes"


def aplicar(cur):
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {_TABLA} (
            id                     BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            code_hash              VARCHAR(128) NOT NULL,
            client_id              VARCHAR(48)  NOT NULL,
            id_usuario              BIGINT       NOT NULL,
            id_empresa             CHAR(36)              DEFAULT NULL,
            redirect_uri           VARCHAR(500) NOT NULL,
            code_challenge         VARCHAR(128) NOT NULL,
            code_challenge_method  VARCHAR(10)  NOT NULL DEFAULT 'S256',
            scope                  VARCHAR(255)          DEFAULT NULL,
            amr                    VARCHAR(32)           DEFAULT NULL,  -- 'pwd' | 'pwd,otp'
            creado                 DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expira                 DATETIME     NOT NULL,
            usado                  TINYINT      NOT NULL DEFAULT 0,
            UNIQUE KEY uq_mcp_code_hash (code_hash),
            INDEX idx_mcp_code_client (client_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute(f"DROP TABLE IF EXISTS {_TABLA}")
