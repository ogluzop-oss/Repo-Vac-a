"""
Migración 0294 — Fase Productividad (Ventas): atribución FIABLE de cada venta al empleado que la
procesó. ADITIVA, reversible, idempotente.

`ventas.empleado` (VARCHAR legado) es un cajón de sastre poblado de forma inconsistente —a veces el
NOMBRE del cajero, a veces un id numérico como texto, a veces el literal "AUTOCOBRO", a veces
NULL— confirmado por auditoría previa: nunca fue una referencia fiable a `usuarios.id`. Se añade
`id_usuario INT DEFAULT NULL`, una columna NUEVA y limpia, poblada desde ahora por la ruta canónica
de venta (`db.conexion.registrar_venta_con_items`) con el id REAL del cajero activo en el TPV. Las
ventas ANTERIORES a esta migración se quedan con `id_usuario` NULL (nunca se inventa una atribución
retroactiva que no existía) — la analítica de Productividad por empleado solo es fiable desde que
esta columna empieza a poblarse.
"""

VERSION = "0294"
DESCRIPCION = "ventas.id_usuario — atribución fiable de la venta al empleado (Fase Productividad)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def _existe_columna(cur, tabla, columna) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
        "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, columna))
    r = cur.fetchone()
    n = r[0] if not isinstance(r, dict) else list(r.values())[0]
    return int(n) > 0


def aplicar(cur):
    if not _existe_columna(cur, "ventas", "id_usuario"):
        cur.execute("ALTER TABLE ventas ADD COLUMN id_usuario INT DEFAULT NULL")
        cur.execute("ALTER TABLE ventas ADD INDEX idx_ventas_id_usuario (id_usuario)")


def revertir(cur):
    if _existe_columna(cur, "ventas", "id_usuario"):
        cur.execute("ALTER TABLE ventas DROP COLUMN id_usuario")
