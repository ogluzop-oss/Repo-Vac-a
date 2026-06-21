"""
Migración 0023 — Multialmacén real (INV.4.1). ADITIVA y reversible.

Crea `stock_almacen` (ledger fuente de verdad: cantidad por almacén+artículo) y añade
`almacen.id_tienda` (asocia almacenes tipo tienda a una tienda). No elimina ni cambia
articulos/stock_tienda; las columnas Stock_* quedan como caché de compatibilidad. Asegura
un almacén central por empresa. El sembrado inicial de existencias lo realiza el servicio
`stock_almacen` (reseed) de forma idempotente.
"""

from src.db.conexion import EMPRESA_DEFAULT_ID

VERSION = "0023"
DESCRIPCION = "Multialmacén: stock_almacen + almacen.id_tienda + central por empresa"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    emp = EMPRESA_DEFAULT_ID
    cur.execute("ALTER TABLE almacen ADD COLUMN IF NOT EXISTS id_tienda INT DEFAULT NULL")
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS stock_almacen (
            id                 BIGINT      NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa         CHAR(36)    NOT NULL DEFAULT '{emp}',
            id_almacen         INT         NOT NULL,
            codigo_articulo    VARCHAR(50) NOT NULL,
            cantidad           INT         NOT NULL DEFAULT 0,
            fecha_actualizacion DATETIME   NOT NULL DEFAULT CURRENT_TIMESTAMP
                                           ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_sa (id_empresa, id_almacen, codigo_articulo),
            INDEX idx_sa_articulo (id_empresa, codigo_articulo),
            INDEX idx_sa_almacen (id_almacen)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    # Garantiza un almacén CENTRAL por empresa conocida (default + cualquiera con almacenes).
    cur.execute("SELECT DISTINCT id_empresa FROM almacen")
    empresas = {(r[0] if not isinstance(r, dict) else list(r.values())[0]) for r in cur.fetchall()}
    empresas.add(emp)
    for e in empresas:
        cur.execute("SELECT COUNT(*) FROM almacen WHERE id_empresa=%s AND tipo_almacen='central'", (e,))
        n = cur.fetchone()
        n = n[0] if not isinstance(n, dict) else list(n.values())[0]
        if not n:
            # almacen.nombre es UNIQUE global → sufijo por empresa para evitar colisión.
            nombre = "ALMACÉN CENTRAL" if e == emp else f"ALMACÉN CENTRAL {str(e)[:8]}"
            cur.execute("INSERT INTO almacen (nombre, activo, id_empresa, codigo_almacen, "
                        "tipo_almacen, estado) VALUES (%s,1,%s,%s,'central','activo')",
                        (nombre, e, "ALM-CENTRAL"))


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS stock_almacen")
    cur.execute("ALTER TABLE almacen DROP COLUMN IF EXISTS id_tienda")
