"""
Migración 0151 — Etapa F · Fase F5 (Rendimiento). ADITIVA, idempotente, reversible.

Añade índices sobre `id_empresa` a tablas HOT que se consultan con `WHERE id_empresa` como filtro
principal y que NO tenían índice en esa columna (full-scan del filtro multi-tenant). NO cambia el
comportamiento funcional: los índices solo aceleran; los resultados son idénticos.

Selección data-driven: tablas con columna `id_empresa`, sin índice líder en ella y con filtro
`FROM t WHERE id_empresa` en el código. `scheduler_ejecuciones` recibe un índice compuesto
`(id_empresa, estado)` porque las consultas operacionales (F1/F3) filtran por ambos.
"""

VERSION = "0151"
DESCRIPCION = "F5 Rendimiento: índices id_empresa en tablas hot sin índice"
REVERSIBLE = True
REQUIERE_BACKUP = False

# (tabla, nombre_indice, columnas)
_INDICES = [
    ("scheduler_ejecuciones", "idx_f5_sch_ej_emp", "id_empresa, estado"),
    ("scheduler_historial", "idx_f5_sch_hist_emp", "id_empresa"),
    ("tiendas", "idx_f5_tiendas_emp", "id_empresa"),
    ("articulos", "idx_f5_articulos_emp", "id_empresa"),
    ("almacen", "idx_f5_almacen_emp", "id_empresa"),
    ("fiscal_cola", "idx_f5_fiscal_cola_emp", "id_empresa"),
    ("ventas_errores", "idx_f5_ventas_err_emp", "id_empresa"),
    ("ubicaciones", "idx_f5_ubicaciones_emp", "id_empresa"),
    ("mermas", "idx_f5_mermas_emp", "id_empresa"),
    ("reab_propuestas", "idx_f5_reab_prop_emp", "id_empresa"),
    ("rrhh_vacaciones", "idx_f5_rrhh_vac_emp", "id_empresa"),
    ("rrhh_ausencias", "idx_f5_rrhh_aus_emp", "id_empresa"),
    ("rrhh_conceptos_recurrentes", "idx_f5_rrhh_cr_emp", "id_empresa"),
    ("documento_retencion", "idx_f5_doc_ret_emp", "id_empresa"),
]


def _existe_tabla(cur, tabla) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s", (tabla,))
    return bool((cur.fetchone() or [0])[0])


def _existe_columna(cur, tabla, col) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, col))
    return bool((cur.fetchone() or [0])[0])


def _existe_indice(cur, tabla, idx) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND INDEX_NAME=%s", (tabla, idx))
    return bool((cur.fetchone() or [0])[0])


def aplicar(cur):
    for tabla, idx, cols in _INDICES:
        if not _existe_tabla(cur, tabla):
            continue
        if not all(_existe_columna(cur, tabla, c.strip()) for c in cols.split(",")):
            continue
        if _existe_indice(cur, tabla, idx):
            continue
        try:
            cur.execute(f"CREATE INDEX {idx} ON {tabla} ({cols})")
        except Exception:
            pass      # idempotente/degradable: no rompe el arranque


def revertir(cur):
    for tabla, idx, _cols in _INDICES:
        try:
            if _existe_tabla(cur, tabla) and _existe_indice(cur, tabla, idx):
                cur.execute(f"DROP INDEX {idx} ON {tabla}")
        except Exception:
            pass
