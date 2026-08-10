"""
Migración 0161 — Dispositivos de confianza MFA (Gobernanza MFA · Fase 4). ADITIVA, reversible.

NO es un sistema de dispositivos paralelo: es la CAPA DE CONFIANZA sobre la identidad de terminal ya
existente (`ioc_terminales`, migr 0121). Vincula (usuario + empresa + `codigo_terminal`) con una
ventana de confianza, de modo que en un terminal ya validado con MFA no se re-exija el 2º factor en
cada login (nunca un bypass universal: es por usuario+empresa+terminal y revocable/caducable).
El FACTOR sigue siendo del usuario (`mfa_usuarios`). El dispositivo NUNCA sustituye a la identidad.
"""

VERSION = "0161"
DESCRIPCION = "Seguridad: tabla mfa_dispositivos_confianza (dispositivos de confianza por usuario+terminal)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mfa_dispositivos_confianza (
            id INT AUTO_INCREMENT PRIMARY KEY,
            id_usuario VARCHAR(64) NOT NULL,
            id_empresa VARCHAR(36) DEFAULT NULL,
            codigo_terminal VARCHAR(60) NOT NULL,
            nombre VARCHAR(120) DEFAULT NULL,
            confianza_hasta DATETIME DEFAULT NULL,
            revocado TINYINT NOT NULL DEFAULT 0,
            creado DATETIME DEFAULT CURRENT_TIMESTAMP,
            ultima_confianza DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_disp (id_usuario, id_empresa, codigo_terminal),
            INDEX idx_disp_emp (id_empresa),
            INDEX idx_disp_usr (id_usuario)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS mfa_dispositivos_confianza")
