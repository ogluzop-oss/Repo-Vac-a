"""
Migración 0224 — Smart Suppliers: reentrada automática al Portal Proveedor. ADITIVA, idempotente,
reversible.

`notificar_reentrada` (envío automático de un enlace nuevo al cerrar sesión/pestaña) necesita saber
CUÁNDO se envió el último aviso para no disparar varios seguidos (p. ej. varias pestañas cerrándose
casi a la vez). No sirve mirar la fila más reciente de `suministrador_sesiones`: esa tabla también
registra la sesión que el proveedor está usando AHORA MISMO (creada al entrar), así que "la sesión
más reciente es de hace <60s" sería casi siempre cierto nada más entrar y suprimiría el primer aviso
real. Se añade una columna dedicada, escrita SOLO por `notificar_reentrada`.
"""

VERSION = "0224"
DESCRIPCION = "Smart Suppliers: suministradores.ultima_notificacion_reentrada (cooldown del aviso automático)"
REVERSIBLE = True
REQUIERE_BACKUP = False

_COLS = [("ultima_notificacion_reentrada", "DATETIME DEFAULT NULL")]


def aplicar(cur):
    for col, ddl in _COLS:
        cur.execute(f"ALTER TABLE suministradores ADD COLUMN IF NOT EXISTS {col} {ddl}")


def revertir(cur):
    for col, _ in _COLS:
        cur.execute(f"ALTER TABLE suministradores DROP COLUMN IF EXISTS {col}")
