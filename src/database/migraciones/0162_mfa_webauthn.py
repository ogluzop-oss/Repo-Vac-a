"""
Migración 0162 — Credenciales WebAuthn / Passkeys (Gobernanza MFA · Fase 5). ADITIVA, reversible.

WebAuthn es un SEGUNDO método MFA (adicional a TOTP, que sigue como fallback). La ceremonia
(`navigator.credentials`) ocurre en el navegador; el servidor (relying party) solo guarda DATOS
PÚBLICOS de la credencial: `credential_id`, la CLAVE PÚBLICA (COSE) y el contador de firmas. NUNCA se
almacenan claves privadas ni secretos del autenticador (esos no salen del dispositivo). Multiempresa.
"""

VERSION = "0162"
DESCRIPCION = "Seguridad: tabla mfa_webauthn_credenciales (passkeys — solo datos públicos)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mfa_webauthn_credenciales (
            id INT AUTO_INCREMENT PRIMARY KEY,
            id_usuario VARCHAR(64) NOT NULL,
            id_empresa VARCHAR(36) DEFAULT NULL,
            credential_id VARCHAR(500) NOT NULL,
            public_key TEXT NOT NULL,
            sign_count BIGINT NOT NULL DEFAULT 0,
            transports VARCHAR(160) DEFAULT NULL,
            nombre VARCHAR(120) DEFAULT NULL,
            rp_id VARCHAR(120) DEFAULT NULL,
            revocado TINYINT NOT NULL DEFAULT 0,
            creado DATETIME DEFAULT CURRENT_TIMESTAMP,
            ultima_uso DATETIME DEFAULT NULL,
            UNIQUE KEY uq_wa_cred (credential_id),
            INDEX idx_wa_usr (id_usuario)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS mfa_webauthn_credenciales")
