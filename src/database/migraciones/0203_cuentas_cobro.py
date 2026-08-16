"""
Migración 0203 — Cuentas bancarias de proveedores/vendedores + cobro del servicio. ADITIVA, idempotente,
reversible.

Las cuentas bancarias de las EMPRESAS ya existen (`cuentas_bancarias`, migr 0045, IBAN cifrado). Aquí:
- `proveedores.iban`/`iban_mascara`/`titular_cuenta`: cuenta del proveedor (IBAN cifrado; máscara para UI).
- `lonja_vendedores.iban`/`iban_mascara`: cuenta del vendedor del mercado (para cobrar sus ventas).
- `servicio_cobros`: cobro del servicio Smart Manager a AMBAS partes (a la empresa la app; al proveedor el
  portal) + comisiones de venta. Idempotente por (empresa, parte, proveedor, concepto, periodo).
"""

VERSION = "0203"
DESCRIPCION = "Cuentas bancarias de proveedores/vendedores + servicio_cobros (cobro del servicio)"
REVERSIBLE = True
REQUIERE_BACKUP = False

# `iban_cifrado` (no `iban`, que ya existe en proveedores desde migr 0028 en claro/VARCHAR(34)): aquí se
# guarda el IBAN CIFRADO (mismo patrón que cuentas_bancarias), con máscara para la UI.
_COLS_PROV = (("iban_cifrado", "VARCHAR(255) DEFAULT NULL"),
              ("iban_mascara", "VARCHAR(40) DEFAULT NULL"),
              ("titular_cuenta", "VARCHAR(160) DEFAULT NULL"))
_COLS_VEND = (("iban_cifrado", "VARCHAR(255) DEFAULT NULL"),
              ("iban_mascara", "VARCHAR(40) DEFAULT NULL"))

_TABLAS = [
    ("servicio_cobros", """
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_empresa VARCHAR(36) NOT NULL,
        parte VARCHAR(12) NOT NULL DEFAULT 'empresa',
        id_proveedor BIGINT DEFAULT NULL,
        concepto VARCHAR(16) NOT NULL DEFAULT 'app',
        importe DECIMAL(12,2) NOT NULL DEFAULT 0,
        divisa VARCHAR(8) NOT NULL DEFAULT 'EUR',
        periodo VARCHAR(7) DEFAULT NULL,
        estado VARCHAR(12) NOT NULL DEFAULT 'pendiente',
        iban_mascara VARCHAR(40) DEFAULT NULL,
        creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
        cobrado_en DATETIME DEFAULT NULL,
        UNIQUE KEY uq_scobro (id_empresa, parte, id_proveedor, concepto, periodo),
        INDEX idx_scobro (id_empresa, estado)"""),
]


def _tiene_columna(cur, tabla, col) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, col))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    for col, ddl in _COLS_PROV:
        if not _tiene_columna(cur, "proveedores", col):
            cur.execute(f"ALTER TABLE proveedores ADD COLUMN {col} {ddl}")
    for col, ddl in _COLS_VEND:
        if not _tiene_columna(cur, "lonja_vendedores", col):
            cur.execute(f"ALTER TABLE lonja_vendedores ADD COLUMN {col} {ddl}")
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
    for col, _ in reversed(_COLS_VEND):
        if _tiene_columna(cur, "lonja_vendedores", col):
            cur.execute(f"ALTER TABLE lonja_vendedores DROP COLUMN {col}")
    for col, _ in reversed(_COLS_PROV):
        if _tiene_columna(cur, "proveedores", col):
            cur.execute(f"ALTER TABLE proveedores DROP COLUMN {col}")
