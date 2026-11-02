"""
Migración 0301 — Generador de Apps Móviles (PWA) · Fase 2: sesión del CLIENTE final (no empleado).
ADITIVA, reversible, idempotente.

Hasta ahora no existía NINGÚN mecanismo de sesión para el comprador del storefront público más allá
del carrito anónimo (`cd_carrito_lineas`, token opaco sin identidad). `cd_clientes_sesiones` es el
equivalente, pero YA IDENTIFICADO (tras login sin contraseña — Magic Link o WebAuthn, ver
`services/comercio_digital/clientes_auth.py`): token opaco de 64 hex (32 bytes aleatorios,
`secrets.token_hex`) en una cookie httponly, igual criterio de seguridad que `sm_cart_<id_empresa>`
pero DB-backed y revocable (a diferencia de un JWT stateless) — cerrar sesión/expirar de verdad
borra la fila, sin necesidad de lista de revocación aparte.

NO se crea una tabla de credenciales de cliente propia para WebAuthn: la Fase 2 reutiliza
`mfa_webauthn_credenciales` (migr. 0162) tal cual — su `id_usuario` ya es VARCHAR libre, sin FK a
`usuarios`; los clientes se guardan con el prefijo `cli:<id>` para convivir sin ambigüedad con los
empleados en la MISMA tabla (nunca una tabla paralela de "passkeys de cliente")."""

VERSION = "0301"
DESCRIPCION = "Apps móviles (PWA) Fase 2: cd_clientes_sesiones (sesión del cliente final, passwordless)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cd_clientes_sesiones (
            token            CHAR(64)     NOT NULL PRIMARY KEY,
            id_empresa       CHAR(36)     NOT NULL,
            id_cliente       INT          NOT NULL,
            creado           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            ultima_actividad DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            expira           DATETIME     NOT NULL,
            INDEX idx_cd_sesion_cliente (id_empresa, id_cliente),
            INDEX idx_cd_sesion_expira (expira)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS cd_clientes_sesiones")
