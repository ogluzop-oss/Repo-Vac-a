"""
Migración 0051 — Endurecimiento de Tesorería. ADITIVA, idempotente, reversible.

Cierra riesgos residuales detectados en la auditoría de robustez:
  • conciliaciones: UNIQUE (empresa,línea) y (empresa,movimiento) → impide DOBLE conciliación
    y reutilizar un movimiento en dos líneas.
  • extracto_lineas: UNIQUE (extracto,hash) → impide líneas duplicadas (carrera de importación).
  • movimientos_tesoreria: índice (id_empresa,id) → cadena de hash O(1) por empresa (volumen).
Antes de cada UNIQUE se deduplica defensivamente conservando el id más bajo.
"""

VERSION = "0051"
DESCRIPCION = "Endurecimiento tesorería: UNIQUE conciliaciones/extracto_lineas + índice hash"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    # Dedup defensivo de conciliaciones (por si hubiera datos previos).
    cur.execute("""
        DELETE c1 FROM conciliaciones c1 JOIN conciliaciones c2
          ON c1.id_empresa=c2.id_empresa AND c1.id_linea=c2.id_linea AND c1.id>c2.id
    """)
    cur.execute("""
        DELETE c1 FROM conciliaciones c1 JOIN conciliaciones c2
          ON c1.id_empresa=c2.id_empresa AND c1.id_movimiento=c2.id_movimiento AND c1.id>c2.id
    """)
    cur.execute("ALTER TABLE conciliaciones ADD UNIQUE INDEX IF NOT EXISTS "
                "uq_conc_linea (id_empresa, id_linea)")
    cur.execute("ALTER TABLE conciliaciones ADD UNIQUE INDEX IF NOT EXISTS "
                "uq_conc_mov (id_empresa, id_movimiento)")
    # Dedup defensivo de líneas de extracto + UNIQUE por hash dentro del extracto.
    cur.execute("""
        DELETE l1 FROM extracto_lineas l1 JOIN extracto_lineas l2
          ON l1.id_extracto=l2.id_extracto AND l1.hash=l2.hash AND l1.id>l2.id
    """)
    cur.execute("ALTER TABLE extracto_lineas ADD UNIQUE INDEX IF NOT EXISTS "
                "uq_el_hash (id_extracto, hash)")
    # Índice para la cadena de hash por empresa (último movimiento).
    cur.execute("ALTER TABLE movimientos_tesoreria ADD INDEX IF NOT EXISTS "
                "idx_mt_emp_id (id_empresa, id)")


def revertir(cur):
    cur.execute("ALTER TABLE conciliaciones DROP INDEX IF EXISTS uq_conc_linea")
    cur.execute("ALTER TABLE conciliaciones DROP INDEX IF EXISTS uq_conc_mov")
    cur.execute("ALTER TABLE extracto_lineas DROP INDEX IF EXISTS uq_el_hash")
    cur.execute("ALTER TABLE movimientos_tesoreria DROP INDEX IF EXISTS idx_mt_emp_id")
