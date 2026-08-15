"""
Migración 0195 — Unificación de `id_tienda` (INT) · grupo RRHH: `rrhh_empleados`, `rrhh_jornadas`,
`rrhh_turnos_plan`. Idempotente, reversible.

Continúa la unificación (0192-0194). Matiz por tabla:
- `rrhh_empleados`: un empleado SIEMPRE pertenece a una tienda (columna NOT NULL) → INT NOT NULL DEFAULT 0
  (sin tienda o central 'ALMC' → 0, nunca NULL).
- `rrhh_jornadas`, `rrhh_turnos_plan`: la jornada/turno puede no estar acotada a tienda → INT NULL
  ('' → NULL = sin acotar; código → 0; numérico → int).

El código de RRHH (control_horario, rrhh_pro, empleados) coacciona en el mismo PR con helpers `_tid`.
"""

VERSION = "0195"
DESCRIPCION = "Unificar id_tienda a INT (grupo RRHH: empleados NOT NULL/0, jornadas y turnos NULL)"
REVERSIBLE = True
REQUIERE_BACKUP = False

# tabla -> (nullable?, longitud varchar original para revertir)
_TABLAS = {
    "rrhh_empleados": (False, 64),
    "rrhh_jornadas": (True, 64),
    "rrhh_turnos_plan": (True, 40),
}


def _tipo_columna(cur, tabla, col):
    cur.execute("SELECT DATA_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, col))
    r = cur.fetchone()
    return (r[0] if not isinstance(r, dict) else list(r.values())[0]) if r else None


def aplicar(cur):
    for t, (nullable, _ancho) in _TABLAS.items():
        if _tipo_columna(cur, t, "id_tienda") == "int":
            continue
        # relajar a VARCHAR NULL para poder normalizar valores sin chocar con NOT NULL
        cur.execute(f"ALTER TABLE {t} MODIFY id_tienda VARCHAR(64) NULL DEFAULT NULL")
        if nullable:
            # jornadas/turnos: '' = sin acotar → NULL; código → 0; numérico → int
            cur.execute(f"UPDATE {t} SET id_tienda = CASE "
                        "WHEN id_tienda='' THEN NULL "
                        "WHEN id_tienda REGEXP '^[0-9]+$' THEN id_tienda ELSE '0' END")
            cur.execute(f"ALTER TABLE {t} MODIFY id_tienda INT NULL DEFAULT NULL")
        else:
            # empleados: siempre una tienda; '' / NULL / código → 0
            cur.execute(f"UPDATE {t} SET id_tienda = CASE "
                        "WHEN id_tienda IS NULL OR id_tienda='' THEN '0' "
                        "WHEN id_tienda REGEXP '^[0-9]+$' THEN id_tienda ELSE '0' END")
            cur.execute(f"ALTER TABLE {t} MODIFY id_tienda INT NOT NULL DEFAULT 0")


def revertir(cur):
    for t, (nullable, ancho) in _TABLAS.items():
        if _tipo_columna(cur, t, "id_tienda") != "int":
            continue
        if nullable:
            cur.execute(f"ALTER TABLE {t} MODIFY id_tienda VARCHAR({ancho}) NULL DEFAULT NULL")
        else:
            cur.execute(f"ALTER TABLE {t} MODIFY id_tienda VARCHAR({ancho}) NOT NULL DEFAULT ''")
