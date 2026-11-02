"""
Migración 0244 — Escaneo remoto desde el móvil (delegación universal de escaneo QR/código de barras).
ADITIVA, reversible.

Solicitudes de escaneo creadas desde escritorio (cualquier campo que necesite un código) y resueltas
desde el móvil (que ya tiene cámara utilizable) — ver `services/escaneo_remoto.py`. Resuelto por
sondeo REST corto (sin push/SSE — ver docstring del servicio), aislado por `id_empresa` y por
`id_usuario` (solo quien crea una solicitud puede completarla, no cualquiera de la empresa).
"""

VERSION = "0244"
DESCRIPCION = "escaneos_remotos: solicitudes de escaneo delegadas de escritorio a móvil"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLA = """
    id CHAR(36) PRIMARY KEY,
    id_empresa CHAR(36) DEFAULT NULL,
    id_usuario INT NOT NULL,
    contexto VARCHAR(60) DEFAULT NULL,
    estado VARCHAR(16) NOT NULL DEFAULT 'pendiente',
    valor_escaneado VARCHAR(255) DEFAULT NULL,
    creado DATETIME DEFAULT CURRENT_TIMESTAMP,
    completado DATETIME DEFAULT NULL,
    expira DATETIME NOT NULL,
    INDEX idx_esr (id_empresa, id_usuario, estado)
"""


def aplicar(cur):
    cur.execute(f"CREATE TABLE IF NOT EXISTS escaneos_remotos ({_TABLA}) "
                "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS escaneos_remotos")
