"""
Migración 0362 — Persistencia real de Integraciones Comerciales (petición explícita, 2026-11-24).

`services/marketplace/integraciones_comerciales/servicio.py` guardaba cada integración (URL,
referencia de credenciales, habilitada/estado) en un diccionario Python en memoria (`_REGISTRO`),
sin tabla detrás — un reinicio del backend borraba silenciosamente la configuración de cualquier
canal conectado (WooCommerce/Shopify/Amazon/...). Esta tabla es el nuevo origen de verdad; ver
`db/ic_integraciones.py`. Sin FK a `empresa` (mismo criterio que `tpv_datafono_config`/
`stock_almacen`: multiempresa por columna simple).
"""

VERSION = "0362"
DESCRIPCION = "Tabla ic_integraciones (persistencia real de Integraciones Comerciales)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def _existe_tabla(cur, tabla) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() "
        "AND table_name=%s", (tabla,))
    row = cur.fetchone()
    return (row[0] if not isinstance(row, dict) else row["COUNT(*)"]) > 0


def aplicar(cur):
    if not _existe_tabla(cur, "ic_integraciones"):
        cur.execute(
            "CREATE TABLE ic_integraciones ("
            "id_empresa VARCHAR(64) NOT NULL, "
            "plataforma VARCHAR(32) NOT NULL, "
            "nombre VARCHAR(120), "
            "tipo VARCHAR(20), "
            "estado VARCHAR(20), "
            "url VARCHAR(255), "
            "version VARCHAR(20), "
            "ultima_sync DATETIME NULL, "
            "frecuencia VARCHAR(20), "
            "observaciones TEXT, "
            "credenciales_ref VARCHAR(120), "
            "habilitada TINYINT(1) DEFAULT 1, "
            "creado DATETIME, "
            "UNIQUE KEY uq_ic_integracion (id_empresa, plataforma)"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    if _existe_tabla(cur, "ic_integraciones"):
        cur.execute("DROP TABLE ic_integraciones")
