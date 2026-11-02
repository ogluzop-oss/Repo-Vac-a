"""
Migración 0290 — Fase 3 e-commerce (Catálogo Web): zonas de envío + políticas legales de la
tienda. ADITIVA, reversible, idempotente.

`cd_envios_zonas` (prefijo `cd_`, mismo criterio que `cd_precios_lista`/`cd_reservas` del resto de
Comercio Digital — tabla NUEVA porque el cálculo de coste de envío por zona/peso/importe no
existía en ningún sitio del código, confirmado por auditoría previa): tarifa por zona geográfica,
con recargo opcional por kg y umbral de envío gratis propio.

`web_config` (tabla YA existente, una fila por empresa — NO se crea ninguna tabla nueva para
esto): se le añaden 4 columnas de texto para las políticas legales de la tienda (términos,
privacidad, devoluciones, envíos), editables desde Catálogo Web y servidas por el storefront real.
"""

from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0290"
DESCRIPCION = "Zonas de envío (cd_envios_zonas) + políticas legales de la tienda (web_config)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def _existe_columna(cur, tabla, columna) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
        "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, columna))
    r = cur.fetchone()
    n = r[0] if not isinstance(r, dict) else list(r.values())[0]
    return int(n) > 0


def _add_col(cur, tabla, columna, definicion):
    if not _existe_columna(cur, tabla, columna):
        cur.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS cd_envios_zonas (
            id                  BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa          CHAR(36)     NOT NULL DEFAULT '{emp}',
            nombre              VARCHAR(150) NOT NULL,
            paises              VARCHAR(500)          DEFAULT NULL,
            tarifa_base         DECIMAL(10,2) NOT NULL DEFAULT 0,
            tarifa_por_kg       DECIMAL(10,2) NOT NULL DEFAULT 0,
            envio_gratis_desde  DECIMAL(10,2)         DEFAULT NULL,
            activa              TINYINT(1)   NOT NULL DEFAULT 1,
            orden               INT          NOT NULL DEFAULT 0,
            INDEX idx_envzona_emp (id_empresa)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    for col in ("texto_terminos", "texto_privacidad", "texto_devoluciones", "texto_politica_envios"):
        _add_col(cur, "web_config", col, "MEDIUMTEXT DEFAULT NULL")


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS cd_envios_zonas")
    for col in ("texto_terminos", "texto_privacidad", "texto_devoluciones", "texto_politica_envios"):
        if _existe_columna(cur, "web_config", col):
            cur.execute(f"ALTER TABLE web_config DROP COLUMN {col}")
