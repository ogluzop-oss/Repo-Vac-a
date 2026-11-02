"""
Migración 0298 — Vinculación RFID (módulo Ubicación, pestaña RFID): número de serie SGTIN por
etiqueta. ADITIVA, reversible, idempotente.

`ubicaciones` (migr. 0105 y posteriores) ya es la tabla canónica de mapeo EPC↔artículo/ubicación
física — confirmado por auditoría: `services.rfid.antihurto` ya resuelve EPC→codigo_articulo
contra esta misma tabla, y `UNIQUE KEY uk_ubi_epc (epc)` ya impide dos filas con el mismo tag. NO
se crea una tabla nueva para "etiquetas RFID de producto": se amplía esta, igual que ya se amplió
para EPCs de estantería/satélite.

Falta, hasta ahora, una columna para el NÚMERO DE SERIE decimal de la trama SGTIN-96 codificada en
`epc` (`services.rfid.sgtin.codificar_sgtin96`): sin ella, saber "cuál es el siguiente serial libre
de este artículo" obligaría a decodificar el EPC de cada fila existente en cada alta. Con la
columna, es un simple `MAX(numero_serie) WHERE codigo_articulo=...`. NULL para las filas existentes
(estanterías/satélites, o EPCs antiguos no-SGTIN vía `generar_epc_manual`) — no son unidades de
producto serializadas y no se les asigna un valor inventado.
"""

VERSION = "0298"
DESCRIPCION = "Vinculación RFID: numero_serie (SGTIN) en ubicaciones + índice por artículo/serie"
REVERSIBLE = True
REQUIERE_BACKUP = False


def _existe_columna(cur, tabla, columna) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, columna))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def _existe_indice(cur, tabla, nombre) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND INDEX_NAME=%s", (tabla, nombre))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    if not _existe_columna(cur, "ubicaciones", "numero_serie"):
        cur.execute("ALTER TABLE ubicaciones ADD COLUMN numero_serie BIGINT NULL DEFAULT NULL")
    if not _existe_indice(cur, "ubicaciones", "idx_ubi_serie"):
        cur.execute("ALTER TABLE ubicaciones ADD INDEX idx_ubi_serie (codigo_articulo, numero_serie)")


def revertir(cur):
    if _existe_indice(cur, "ubicaciones", "idx_ubi_serie"):
        cur.execute("ALTER TABLE ubicaciones DROP INDEX idx_ubi_serie")
    if _existe_columna(cur, "ubicaciones", "numero_serie"):
        cur.execute("ALTER TABLE ubicaciones DROP COLUMN numero_serie")
