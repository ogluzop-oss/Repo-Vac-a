"""
Migración 0312 — tabla `confirmaciones_perfil_empleado`. ADITIVA, idempotente, reversible.

"Generar perfil empleado" (Configuración → Usuarios) creaba el perfil de forma síncrona e
inmediata en cuanto el SUPERADMIN pulsaba "Registrar empleado", sin ninguna verificación de que el
email introducido pertenece realmente al nuevo empleado. Se añade un paso de confirmación por
código de 6 dígitos enviado al email indicado: el perfil YA NO se crea en `usuarios` hasta que el
código se valida.

Como el empleado aún no existe (no hay `id_usuario` al que colgar un código, a diferencia de
`mfa_recovery_codes` que exige uno), esta tabla almacena temporalmente los datos del alta en
curso — incluido el PIN, CIFRADO con `utils.cripto.cifrar` (reversible, misma clave maestra que ya
protege credenciales de báscula/SMTP en este proyecto; nunca en claro) — hasta que se confirme o
caduque. Solo entonces se invoca el `crear_perfil` real (`db/usuario.py`), que es quien aplica el
hash de contraseña definitivo e inserta la fila real en `usuarios`.
"""

VERSION = "0312"
DESCRIPCION = "confirmaciones_perfil_empleado (verificación por email al generar perfil empleado)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS confirmaciones_perfil_empleado (
            id INT AUTO_INCREMENT PRIMARY KEY,
            id_empresa VARCHAR(36) NULL,
            nombre VARCHAR(160) NOT NULL,
            password_pin_cifrado VARCHAR(512) NOT NULL,
            perfil_tipo VARCHAR(20) NOT NULL,
            centro_codigo VARCHAR(40) NULL,
            email VARCHAR(255) NOT NULL,
            codigo_hash VARCHAR(64) NOT NULL,
            intentos INT NOT NULL DEFAULT 0,
            usado TINYINT NOT NULL DEFAULT 0,
            creado_por_id INT NULL,
            creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
            expira_en DATETIME NOT NULL,
            INDEX idx_cpe_empresa (id_empresa),
            INDEX idx_cpe_vigencia (usado, expira_en)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS confirmaciones_perfil_empleado")
