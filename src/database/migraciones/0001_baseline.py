"""
Baseline (0001): esquema inicial completo.

Delega en `conexion.ensure_schema()` (idempotente: CREATE/ALTER IF NOT EXISTS),
por lo que es seguro tanto en una base de datos nueva como en una ya existente.
En instalaciones ya desplegadas, el runner SELLA esta versión sin re-ejecutarla.

No contiene secretos ni credenciales (cumple la política de seguridad de C1).
"""

VERSION = "0001"
DESCRIPCION = "Baseline: esquema inicial (ensure_schema idempotente)"
REVERSIBLE = False
REQUIERE_BACKUP = False   # BD nueva: sin datos; BD existente: se sella (no se ejecuta)


def aplicar(cur):
    # El runner, para la baseline en BD nueva, llama directamente a ensure_schema;
    # este aplicar() lo replica para permitir ejecutarla también de forma directa.
    from src.db import conexion
    conexion.ensure_schema(force=True)


def revertir(cur):
    raise NotImplementedError("La baseline no es reversible (requiere recrear la BD).")
