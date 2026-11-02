"""
Migración 0242 — `activos_documentos.id_documento` de INT a VARCHAR(36).

La columna se declaró `INT DEFAULT NULL` en la migración 0063 (GMAO), pero nunca tuvo llamador
(`activos.adjuntar_documento` existía sin usarse) hasta el Rediseño móvil · Grupo B, módulo 2 (foto de
la reparación de una OT), que la enlaza con `documentos_registro.id_documento` — un UUID `CHAR(36)`
(motor documental compartido de todo el proyecto), no un entero. Sin este cambio, cualquier intento de
enlazar una foto real falla con "Incorrect integer value" en MariaDB. Aditiva/reversible: solo cambia
el tipo de columna, no borra datos (no había ninguno real: sin llamador previo).
"""

VERSION = "0242"
DESCRIPCION = "activos_documentos.id_documento: INT -> VARCHAR(36) (UUID de documentos_registro)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("SHOW COLUMNS FROM activos_documentos LIKE 'id_documento'")
    col = cur.fetchone()
    tipo = (col[1] if col and not isinstance(col, dict) else (col or {}).get("Type", "")) or ""
    if col and "int" in tipo.lower():
        cur.execute("ALTER TABLE activos_documentos MODIFY COLUMN id_documento VARCHAR(36) DEFAULT NULL")


def revertir(cur):
    cur.execute("SHOW COLUMNS FROM activos_documentos LIKE 'id_documento'")
    col = cur.fetchone()
    tipo = (col[1] if col and not isinstance(col, dict) else (col or {}).get("Type", "")) or ""
    if col and "varchar" in tipo.lower():
        cur.execute("ALTER TABLE activos_documentos MODIFY COLUMN id_documento INT DEFAULT NULL")
