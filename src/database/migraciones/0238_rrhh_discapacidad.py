"""
Migración 0238 — Grado de discapacidad del empleado (`rrhh_empleados.discapacidad_pct`).

Necesario para que la Calculadora Fiscal (Contabilidad) pueda derivar automáticamente, desde datos
REALES de RRHH, cuántas de las nuevas contrataciones indefinidas del ejercicio son "bonificadas"
(menores de 30 años o con discapacidad ≥33%, el umbral que usa la normativa española de bonificaciones
de empleo). NULL/0 = sin discapacidad reconocida. ADITIVA, idempotente, reversible.
"""

VERSION = "0238"
DESCRIPCION = "Columna rrhh_empleados.discapacidad_pct (grado de discapacidad, 0-100)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("SHOW COLUMNS FROM rrhh_empleados LIKE 'discapacidad_pct'")
    if not cur.fetchone():
        cur.execute("ALTER TABLE rrhh_empleados ADD COLUMN discapacidad_pct INT NULL")


def revertir(cur):
    cur.execute("SHOW COLUMNS FROM rrhh_empleados LIKE 'discapacidad_pct'")
    if cur.fetchone():
        cur.execute("ALTER TABLE rrhh_empleados DROP COLUMN discapacidad_pct")
