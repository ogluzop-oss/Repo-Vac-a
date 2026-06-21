"""
Migración 0043 — Idempotencia de la cola contable (M1). ADITIVA y reversible.

Deduplica `contab_cola` por (id_empresa, evento, ref) conservando el id más bajo y añade
UNIQUE `uq_cc_ref` para impedir eventos duplicados (doble clic / reintentos). No toca
asientos, hash ni numeración.
"""

VERSION = "0043"
DESCRIPCION = "Idempotencia contab_cola: dedup + UNIQUE(id_empresa,evento,ref)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    # Dedup defensivo: elimina duplicados de evento/ref por empresa conservando MIN(id).
    cur.execute("""
        DELETE c1 FROM contab_cola c1
        JOIN contab_cola c2
          ON c1.id_empresa = c2.id_empresa AND c1.evento = c2.evento
         AND c1.ref = c2.ref AND c1.id > c2.id
    """)
    cur.execute("ALTER TABLE contab_cola ADD UNIQUE INDEX IF NOT EXISTS "
                "uq_cc_ref (id_empresa, evento, ref)")


def revertir(cur):
    cur.execute("ALTER TABLE contab_cola DROP INDEX IF EXISTS uq_cc_ref")
