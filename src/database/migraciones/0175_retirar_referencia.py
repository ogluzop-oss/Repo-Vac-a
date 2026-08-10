"""
Migración 0175 — Retirada de «Asignar referencia» (deprecación → Identidad Operativa/IOC). REVERSIBLE.

Paso final de la deprecación: (1) VUELCA la referencia legada (configuraciones.ref_tienda/ref_almacen) al
código VISIBLE del centro IOC principal del tipo correspondiente (TIENDA/ALMACEN), preservando el dato antes
de borrarlo; (2) ELIMINA las columnas ref_tienda/ref_almacen. Best-effort en el volcado (si no hay columnas
o no hay centro, se omite). `revertir` re-crea las columnas (vacías; el dato ya vive en IOC).

Requiere que la infraestructura IOC exista (migr 0121, anterior). Idempotente: DROP ... IF EXISTS.
"""

VERSION = "0175"
DESCRIPCION = "Retira «Asignar referencia»: vuelca ref a IOC y elimina configuraciones.ref_tienda/ref_almacen"
REVERSIBLE = True
REQUIERE_BACKUP = True


def _columnas(cur):
    cur.execute("SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='configuraciones'")
    return {(r[0] if not isinstance(r, dict) else list(r.values())[0]) for r in cur.fetchall()}


def _volcar(cur):
    presentes = [c for c in ("ref_tienda", "ref_almacen") if c in _columnas(cur)]
    if not presentes:
        return
    try:
        cur.execute(f"SELECT {', '.join(presentes)} FROM configuraciones ORDER BY id ASC LIMIT 1")
        fila = cur.fetchone()
    except Exception:
        return
    if not fila:
        return
    vals = list(fila.values()) if isinstance(fila, dict) else list(fila)
    ref = dict(zip(presentes, vals))
    for valor, tipo in ((str(ref.get("ref_tienda") or "").strip(), "TIENDA"),
                        (str(ref.get("ref_almacen") or "").strip(), "ALMACEN")):
        if not valor:
            continue
        try:
            cur.execute(
                "INSERT INTO ioc_centro_codigos (id_empresa, id_centro, tipo_codigo, valor) "
                "SELECT c.id_empresa, c.id_centro, 'VISIBLE', %s FROM centros_trabajo c "
                "WHERE c.tipo=%s AND COALESCE(c.es_principal,0)=1 "
                "AND NOT EXISTS (SELECT 1 FROM ioc_centro_codigos k "
                "                WHERE k.id_centro=c.id_centro AND k.tipo_codigo='VISIBLE')",
                (valor[:80], tipo))
        except Exception:
            pass


def aplicar(cur):
    _volcar(cur)
    cur.execute("ALTER TABLE configuraciones DROP COLUMN IF EXISTS ref_tienda")
    cur.execute("ALTER TABLE configuraciones DROP COLUMN IF EXISTS ref_almacen")


def revertir(cur):
    cur.execute("ALTER TABLE configuraciones ADD COLUMN IF NOT EXISTS ref_tienda  VARCHAR(100) NOT NULL DEFAULT ''")
    cur.execute("ALTER TABLE configuraciones ADD COLUMN IF NOT EXISTS ref_almacen VARCHAR(100) NOT NULL DEFAULT ''")
