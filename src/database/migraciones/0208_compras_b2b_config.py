"""
Migración 0208 — Configuración del conector B2B + reglas de precios del módulo Proveedores. ADITIVA,
idempotente, reversible.

Almacena por EMPRESA: proveedor/conector, endpoint, credenciales (cifradas en la capa de servicio),
entorno (sandbox/producción), y las reglas del monitor/motor de precios (umbral de variación y margen
objetivo). Sustituye al ecosistema retirado en la Fase 1 por un modelo de CONSUMO externo agnóstico.
"""

VERSION = "0208"
DESCRIPCION = "Config del conector B2B + reglas de precios (compras_b2b_config)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("compras_b2b_config", """
        id_empresa VARCHAR(36) NOT NULL PRIMARY KEY,
        proveedor VARCHAR(24) NOT NULL DEFAULT 'rest',
        endpoint VARCHAR(300) DEFAULT NULL,
        api_key VARCHAR(512) DEFAULT NULL,
        api_secret VARCHAR(512) DEFAULT NULL,
        entorno VARCHAR(16) NOT NULL DEFAULT 'sandbox',
        umbral_variacion_pct DECIMAL(6,2) NOT NULL DEFAULT 10.00,
        margen_objetivo_pct DECIMAL(6,2) NOT NULL DEFAULT 30.00,
        estado VARCHAR(16) NOT NULL DEFAULT 'activo',
        actualizado DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
