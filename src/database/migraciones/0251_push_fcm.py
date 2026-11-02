"""
Migración 0251 — Push real (Firebase Cloud Messaging) para alertas antihurto móviles. ADITIVA e
IDEMPOTENTE.

Dos tablas nuevas:
  · `dispositivos_push` — token de dispositivo por usuario+empresa (varios dispositivos por usuario;
                           cada guardia de cada empresa cliente registra el suyo). Antes vivía solo en
                           memoria (`services/mobile/push.py::_DISPOSITIVOS`), perdido en cada reinicio
                           del backend — inaceptable para un guardia que depende del aviso.
  · `fcm_config`         — configuración FCM GLOBAL (una única fila, `id` fijo = 1): el proyecto Firebase
                           es propiedad del VENDEDOR de Smart Manager (no de cada empresa cliente) y se
                           reutiliza para todas las empresas, sin gate por plan SaaS: el push antihurto
                           está disponible para Basic, Pro y Plus por igual. La credencial del
                           *service account* se guarda CIFRADA vía Secret Manager.
No modifica datos existentes.
"""

VERSION = "0251"
DESCRIPCION = "Push FCM: dispositivos_push + fcm_config"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS dispositivos_push (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa  VARCHAR(36)  DEFAULT NULL,
            id_usuario  VARCHAR(36)  NOT NULL,
            token       VARCHAR(255) NOT NULL,
            plataforma  VARCHAR(20)  NOT NULL DEFAULT 'android',
            activo      TINYINT(1)   NOT NULL DEFAULT 1,
            creado      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            actualizado DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_dispositivo_push (id_empresa, id_usuario, token),
            INDEX idx_dispositivo_push_usuario (id_empresa, id_usuario)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fcm_config (
            id                       INT          PRIMARY KEY,
            project_id               VARCHAR(120)          DEFAULT NULL,
            service_account_cifrado  TEXT                  DEFAULT NULL,
            modo_simulado            TINYINT(1)   NOT NULL DEFAULT 1,
            creado                   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS dispositivos_push")
    cur.execute("DROP TABLE IF EXISTS fcm_config")
