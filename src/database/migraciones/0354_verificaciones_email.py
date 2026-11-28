"""
Migración 0354 — Verificación de email por código de 6 dígitos (petición explícita, 2026-11-22).
NUEVA tabla, aditiva, reversible.

Paso obligatorio, compartido por los 3 formularios de registro (web oficial `/registro`, Portal
Empresa B2B `/portal/empresa/registro`, Portal Proveedor `/portal/proveedor/registro`): antes de
completar el alta, se envía un código de 6 dígitos al email introducido y hay que confirmarlo. Una
única tabla/servicio (`services.verificacion_email`) reutilizado por los tres, en vez de triplicar
la lógica.
"""

VERSION = "0354"
DESCRIPCION = "Tabla verificaciones_email — código de 6 dígitos para los 3 formularios de registro"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS verificaciones_email (
            id INT AUTO_INCREMENT PRIMARY KEY,
            email VARCHAR(255) NOT NULL,
            codigo CHAR(6) NOT NULL,
            intentos INT NOT NULL DEFAULT 0,
            verificado TINYINT(1) NOT NULL DEFAULT 0,
            creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expira DATETIME NOT NULL,
            INDEX idx_verif_email (email),
            INDEX idx_verif_email_verificado (email, verificado)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS verificaciones_email")
