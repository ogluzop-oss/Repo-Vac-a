"""
Migración 0288 — Carpetas reales de Correo: Borradores, Papelera, Programados, Pospuestos,
Importantes.

Hasta ahora el sidebar estilo Gmail de `gui/correo_corporativo.py` mostraba estas 5 carpetas con un
aviso honesto de "no disponible" (CLAUDE.md: nunca falsear con mocks una capacidad que no existe de
verdad) porque no había ninguna columna que soportara su estado. Esta migración añade las columnas
mínimas para que las 5 sean REALES (backend genuino, no solo un sidebar que no hace nada):

  · `com_circulares`/`com_encuestas` YA TENÍAN `estado VARCHAR(20) DEFAULT 'PUBLICADA'` (migración
    0157) — se reutiliza para BORRADOR/PROGRAMADA/PAPELERA (no se añade columna nueva para esto).
  · `fecha_programada DATETIME NULL` (circulares/encuestas) — envío programado (Programados):
    cuándo debe "dispararse" un registro en estado PROGRAMADA (ver scheduler, job
    `com_programados_envio`, catálogo en `services/scheduler_registry.py`).
  · `pospuesto_hasta DATETIME NULL` (circulares/encuestas/correos_recibidos) — snooze (Pospuestos):
    mientras `pospuesto_hasta > NOW()`, el mensaje se excluye de "Recibidos" y aparece en
    "Pospuestos"; se resuelve solo en la siguiente lectura (sin job dedicado, igual que el
    comportamiento de snooze de Gmail desde la perspectiva del usuario).
  · `importante TINYINT(1) NOT NULL DEFAULT 0` (circulares/encuestas/correos_recibidos) — estrella
    manual del usuario (Importantes): Gmail real no expone su etiqueta algorítmica IMPORTANT por
    sync de solo lectura (confirmado en una sesión anterior), así que esto es un flag MANUAL,
    honesto y 100% real (el usuario lo pone él mismo, como el propio Gmail permite a mano).
  · `correos_recibidos.papelera TINYINT(1) NOT NULL DEFAULT 0` — papelera LOCAL para el correo
    sincronizado de Gmail (solo lectura: nunca se llama a la API de Gmail para mover/borrar nada en
    la cuenta real del usuario — es un estado interno de Smart Manager únicamente).

Índices ligeros `(id_empresa, estado)` en circulares/encuestas: las nuevas carpetas filtran por
`estado` (antes solo se indexaba por `creado`), y la tabla ya tenía un índice compuesto por
`id_empresa` así que el coste adicional es mínimo.

ADITIVA e idempotente (comprobación de columna/índice antes de cada ALTER, igual que 0287).
Reversible: `revertir()` elimina exactamente lo añadido aquí.
"""

VERSION = "0288"
DESCRIPCION = ("Columnas de Borradores/Papelera/Programados/Pospuestos/Importantes para circulares, "
               "encuestas y correo Gmail sincronizado (carpetas reales del sidebar de Correo)")
REVERSIBLE = True
REQUIERE_BACKUP = False


def _existe_columna(cur, tabla, columna) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, columna))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def _existe_indice(cur, tabla, indice) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND INDEX_NAME=%s", (tabla, indice))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def _add_col(cur, tabla, columna, ddl):
    if not _existe_columna(cur, tabla, columna):
        cur.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {ddl}")


def _add_idx(cur, tabla, indice, cols):
    if not _existe_indice(cur, tabla, indice):
        cur.execute(f"ALTER TABLE {tabla} ADD INDEX {indice} ({cols})")


def _drop_col_si_existe(cur, tabla, columna):
    if _existe_columna(cur, tabla, columna):
        cur.execute(f"ALTER TABLE {tabla} DROP COLUMN {columna}")


def _drop_idx_si_existe(cur, tabla, indice):
    if _existe_indice(cur, tabla, indice):
        cur.execute(f"ALTER TABLE {tabla} DROP INDEX {indice}")


def aplicar(cur):
    for tabla in ("com_circulares", "com_encuestas"):
        _add_col(cur, tabla, "fecha_programada", "DATETIME NULL DEFAULT NULL")
        _add_col(cur, tabla, "pospuesto_hasta", "DATETIME NULL DEFAULT NULL")
        _add_col(cur, tabla, "importante", "TINYINT(1) NOT NULL DEFAULT 0")
    _add_idx(cur, "com_circulares", "idx_circ_estado", "id_empresa, estado")
    _add_idx(cur, "com_encuestas", "idx_enc_estado", "id_empresa, estado")

    _add_col(cur, "correos_recibidos", "papelera", "TINYINT(1) NOT NULL DEFAULT 0")
    _add_col(cur, "correos_recibidos", "pospuesto_hasta", "DATETIME NULL DEFAULT NULL")
    _add_col(cur, "correos_recibidos", "importante", "TINYINT(1) NOT NULL DEFAULT 0")


def revertir(cur):
    _drop_idx_si_existe(cur, "com_circulares", "idx_circ_estado")
    _drop_idx_si_existe(cur, "com_encuestas", "idx_enc_estado")
    for tabla in ("com_circulares", "com_encuestas"):
        for col in ("fecha_programada", "pospuesto_hasta", "importante"):
            _drop_col_si_existe(cur, tabla, col)
    for col in ("papelera", "pospuesto_hasta", "importante"):
        _drop_col_si_existe(cur, "correos_recibidos", col)
