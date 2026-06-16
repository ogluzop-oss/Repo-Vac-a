"""
Migración 0004 — Trazabilidad Verifactu (C3.3). ADITIVA y reversible.

NO toca el encadenado/serie/worker/evidencias/hooks de C3.2 (congelados). Solo
añade campos estrictamente necesarios para operar Verifactu:

- fiscal_config.entorno      : 'preproduccion' (default) | 'produccion' → conmuta
  el endpoint/QR de AEAT sin recompilar (certificado real se gestiona en C3.5).
- fiscal_registros.estado_aeat: estado devuelto por AEAT (Correcto/AceptadoConErrores/
  Incorrecto…) para monitorización y reenvíos. NULL hasta que se envía.
- fiscal_registros.csv_aeat   : Código Seguro de Verificación del acuse de AEAT.

El XML/acuse completos NO se guardan aquí: van como EVIDENCIAS documentales (C3.2).
Idempotente (comprueba existencia de columna). No contiene secretos.
"""

VERSION = "0004"
DESCRIPCION = "Trazabilidad Verifactu (entorno AEAT + estado_aeat/csv_aeat)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def _tiene_columna(cur, tabla, columna) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s",
        (tabla, columna))
    r = cur.fetchone()
    n = r[0] if not isinstance(r, dict) else list(r.values())[0]
    return int(n or 0) > 0


def aplicar(cur):
    if not _tiene_columna(cur, "fiscal_config", "entorno"):
        cur.execute("ALTER TABLE fiscal_config "
                    "ADD COLUMN entorno VARCHAR(15) NOT NULL DEFAULT 'preproduccion' "
                    "AFTER integrador")
    if not _tiene_columna(cur, "fiscal_registros", "estado_aeat"):
        cur.execute("ALTER TABLE fiscal_registros "
                    "ADD COLUMN estado_aeat VARCHAR(25) DEFAULT NULL AFTER estado")
    if not _tiene_columna(cur, "fiscal_registros", "csv_aeat"):
        cur.execute("ALTER TABLE fiscal_registros "
                    "ADD COLUMN csv_aeat VARCHAR(50) DEFAULT NULL AFTER estado_aeat")


def revertir(cur):
    for tabla, col in (("fiscal_registros", "csv_aeat"),
                       ("fiscal_registros", "estado_aeat"),
                       ("fiscal_config", "entorno")):
        if _tiene_columna(cur, tabla, col):
            cur.execute(f"ALTER TABLE {tabla} DROP COLUMN {col}")
