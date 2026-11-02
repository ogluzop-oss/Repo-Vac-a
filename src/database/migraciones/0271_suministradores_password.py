"""
Migración 0271 — Smart Suppliers: login con contraseña para proveedores. ADITIVA, idempotente,
reversible.

Sustituye el acceso sin contraseña (enlace mágico reenviado por email en cada cierre de sesión) por
un login real de email+contraseña: `suministradores.password` guarda el hash Argon2id (mismo motor
que ya usan los usuarios de escritorio, `src/seguridad/passwords.py` — `hash_password()`/
`verificar()`, sin motor paralelo). Por defecto vacío ('') para las filas ya existentes creadas antes
de este cambio (proveedores dados de alta bajo el flujo antiguo, sin contraseña todavía) — `password`
vacío nunca verifica correctamente contra `passwords.verificar()`, así que esas cuentas simplemente no
pueden iniciar sesión hasta que se les fije una contraseña (no hay usuarios reales en producción
todavía sobre esta tabla nueva, Fase A de Smart Suppliers).
"""

VERSION = "0271"
DESCRIPCION = "Smart Suppliers: suministradores.password (login con contraseña, Argon2id)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_COLS = [("password", "VARCHAR(255) NOT NULL DEFAULT ''")]


def aplicar(cur):
    for col, ddl in _COLS:
        cur.execute(f"ALTER TABLE suministradores ADD COLUMN IF NOT EXISTS {col} {ddl}")


def revertir(cur):
    for col, _ in _COLS:
        cur.execute(f"ALTER TABLE suministradores DROP COLUMN IF EXISTS {col}")
