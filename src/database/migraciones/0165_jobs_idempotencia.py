"""
Migración 0165 — Idempotencia de jobs MULTI-WORKER (Fase 12, H3). ADITIVA. Tabla persistente compartida que
permite que varios workers (SQS real) deduzcan atómicamente si un job ya fue procesado o está en curso, sin
crear un segundo sistema de jobs. La clave primaria (job_id) da la atomicidad: un INSERT concurrente del mismo
job_id falla en todos los workers menos uno → sólo uno ejecuta; el resto → JOB_DUPLICATE_IGNORED.
"""

VERSION = "0165"
DESCRIPCION = "Jobs: tabla jobs_idempotencia (dedup atómico multi-worker para SQS)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS jobs_idempotencia (
            job_id      VARCHAR(48)  NOT NULL PRIMARY KEY,
            id_empresa  VARCHAR(36)  DEFAULT NULL,
            estado      VARCHAR(20)  NOT NULL DEFAULT 'EN_CURSO',  -- EN_CURSO|COMPLETADO|FALLIDO|PENDIENTE
            attempt     INT          NOT NULL DEFAULT 0,
            actualizado DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            creado      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_jidem_estado (estado)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS jobs_idempotencia")
