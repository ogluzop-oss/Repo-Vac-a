"""
Migración 0181 — Clave de `articulos` multi-tenant. REVERSIBLE, idempotente.

Hasta ahora `articulos.codigo` era PRIMARY KEY GLOBAL → dos empresas NO podían compartir el mismo código de
producto (defecto multi-tenant, detectado al construir el importador maestro). Se cambia a **PK compuesta
(id_empresa, codigo)**, de modo que cada empresa tiene su propio espacio de códigos. `id_empresa` ya es NOT NULL
con default, así que el cambio es TRANSPARENTE para instalaciones de una sola empresa.

Pasos: (1) quitar la única FK a `articulos(codigo)` (`reab_config.fk_reab_cfg_art`), que impide cambiar la PK;
(2) PK compuesta (id_empresa, codigo); (3) índice `idx_art_codigo` para las lecturas por código (que ya no es
PK). La FK de `reab_config` no se recrea porque `codigo` ya no es clave única en `articulos` (la integridad de
esa tabla de configuración se gestiona en código).

NOTA de continuidad (Strangler): las ~40 lecturas que consultan `articulos` por `codigo` SIN `id_empresa` siguen
siendo correctas en instalaciones de una sola empresa; para multi-tenant real con códigos repetidos deben migrarse
gradualmente a filtrar por `id_empresa`. Esta migración habilita el esquema; el cableado de esas lecturas es el
siguiente paso incremental.
"""

VERSION = "0181"
DESCRIPCION = "articulos: PK compuesta (id_empresa, codigo) — habilita códigos por empresa (multi-tenant)"
REVERSIBLE = True
REQUIERE_BACKUP = True

_EMP_DEF = "00000000-0000-0000-0000-000000000001"


def _pk_cols(cur):
    cur.execute("SELECT COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME='articulos' AND CONSTRAINT_NAME='PRIMARY' ORDER BY ORDINAL_POSITION")
    return [r[0] if not isinstance(r, dict) else r["COLUMN_NAME"] for r in cur.fetchall()]


def _fk_existe(cur, tabla, fk):
    cur.execute("SELECT 1 FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA=DATABASE() AND "
                "TABLE_NAME=%s AND CONSTRAINT_NAME=%s AND CONSTRAINT_TYPE='FOREIGN KEY'", (tabla, fk))
    return cur.fetchone() is not None


def _idx_existe(cur, idx):
    cur.execute("SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND "
                "TABLE_NAME='articulos' AND INDEX_NAME=%s", (idx,))
    return cur.fetchone() is not None


def aplicar(cur):
    if _fk_existe(cur, "reab_config", "fk_reab_cfg_art"):
        cur.execute("ALTER TABLE reab_config DROP FOREIGN KEY fk_reab_cfg_art")
    cur.execute("UPDATE articulos SET id_empresa=%s WHERE id_empresa IS NULL OR id_empresa=''", (_EMP_DEF,))
    if _pk_cols(cur) != ["id_empresa", "codigo"]:
        cur.execute("ALTER TABLE articulos DROP PRIMARY KEY, ADD PRIMARY KEY (id_empresa, codigo)")
    if not _idx_existe(cur, "idx_art_codigo"):
        cur.execute("ALTER TABLE articulos ADD INDEX idx_art_codigo (codigo)")


def revertir(cur):
    """Revierte a PK(codigo) + FK de reab_config. Requiere que NO haya códigos repetidos entre empresas."""
    if _idx_existe(cur, "idx_art_codigo"):
        cur.execute("ALTER TABLE articulos DROP INDEX idx_art_codigo")
    if _pk_cols(cur) != ["codigo"]:
        cur.execute("ALTER TABLE articulos DROP PRIMARY KEY, ADD PRIMARY KEY (codigo)")
    if not _fk_existe(cur, "reab_config", "fk_reab_cfg_art"):
        cur.execute("ALTER TABLE reab_config ADD CONSTRAINT fk_reab_cfg_art FOREIGN KEY (codigo) "
                    "REFERENCES articulos(codigo) ON DELETE CASCADE")
