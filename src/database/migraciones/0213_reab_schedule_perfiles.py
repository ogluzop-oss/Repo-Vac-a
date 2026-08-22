"""
Migración 0213 — Reabastecimiento: destinatarios por PERFIL (no email). ADITIVA, idempotente, reversible.

`reab_schedule.perfiles` guarda los IDs de los perfiles (usuarios) responsables de logística —separados
por comas— que reciben la solicitud de reabastecimiento en su MÓDULO DE CORREO (bandeja interna), en vez
de por email SMTP. Las columnas email/smtp_* quedan en desuso (se conservan por compatibilidad). Se
mantiene dias/hora/minuto (programación de envío). No crea tablas.
"""

VERSION = "0213"
DESCRIPCION = "reab_schedule.perfiles (responsables de logística por perfil → correo interno)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLA = "reab_schedule"
_COLUMNA = "perfiles"


def _tiene_columna(cur, tabla, col) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, col))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    if not _tiene_columna(cur, _TABLA, _COLUMNA):
        cur.execute(f"ALTER TABLE {_TABLA} ADD COLUMN {_COLUMNA} VARCHAR(255) DEFAULT NULL")


def revertir(cur):
    if _tiene_columna(cur, _TABLA, _COLUMNA):
        cur.execute(f"ALTER TABLE {_TABLA} DROP COLUMN {_COLUMNA}")
