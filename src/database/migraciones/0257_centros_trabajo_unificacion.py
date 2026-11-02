"""
Migración 0257 — Unificación de "Centros": `centros_trabajo` pasa a ser la ÚNICA tabla de centros
físicos de la empresa (identidad + geolocalización por CP + aislamiento por creador). ADITIVA sobre
`centros_trabajo`/`usuarios`, DESTRUCTIVA solo sobre `centros_perfil` (retirada — justificación
abajo). Reversible.

Decisión (sesión 2026-09-15, tras revisar un informe de investigación): la tabla `centros_perfil`
(migración 0256, creada en esta MISMA sesión) duplicaba la identidad de centro (nombre/dirección/
CP/municipio/provincia/país/teléfono/email) ya cubierta por `centros_trabajo` (artefacto RRHH/
Seguridad Social preexistente, backing table de ~40 adaptadores de `services/identidad/`). Se
decidió CONSOLIDAR en `centros_trabajo` (la tabla más antigua, con más dependencias reales) en vez
de mantener dos tablas solapadas:

- Se añaden a `centros_trabajo` las 3 capacidades que solo tenía `centros_perfil`:
  `tipo_centro` (tienda|almacen|fabrica|oficina|otro — texto libre, sin CHECK constraint, mismo
  criterio que `almacen.tipo_almacen`; DISTINTA de la columna `tipo` que ya añadió la migración 0121
  para el IOC — esa es de otro dominio, valores en mayúsculas tipo 'OTRO', no se toca), `id_almacen`
  (enlace opcional adicional a `almacen.id`, junto al `id_tienda` ya existente) y `creado_por_id`
  (superadmin creador — base del aislamiento entre superadmins en "Cambiar de Centro"/"Vincular a
  centro", ver `gui/selector_tienda.py`/`gui/gestion_usuarios.py`).
- `centros_perfil` se RETIRA (DROP) en esta misma migración: se creó y usó ÚNICAMENTE dentro de esta
  sesión de hoy — verificado en vivo antes de escribir esta migración: `SELECT COUNT(*) FROM
  centros_perfil` devolvió 0 filas y `SELECT COUNT(*) FROM usuarios WHERE id_centro_perfil IS NOT
  NULL` devolvió 0 — sin datos reales en juego. Por seguridad, `aplicar()` repite esa comprobación en
  cada entorno donde se ejecute: SOLO hace DROP si la tabla está realmente vacía; si alguna
  instalación tuviera filas (no debería, es una tabla de hoy), la deja intacta en vez de arriesgar
  datos (huérfana pero inofensiva — revisar manualmente ese caso).
- `usuarios.id_centro_perfil` (INT NULL, migración 0256) apuntaba a `centros_perfil.id` (INT
  autoincremental). El nuevo destino, `centros_trabajo.id_centro`, es CHAR(36) (UUID) — un INT no
  puede almacenarlo, así que mantener el nombre/tipo de columna habría sido activamente engañoso (no
  solo un cambio de nombre). Se retira esa columna (0 usuarios vinculados, verificado arriba) y se
  sustituye por `usuarios.id_centro_trabajo VARCHAR(36) NULL`, con el nombre/tipo ya correctos — ver
  `db/usuario.py::vincular_centro_trabajo` (antes `vincular_centro_perfil`) y todos sus consumidores
  (`gui/gestion_usuarios.py`, `gui/menu_principal.py`).
- El geocode-on-save (`services/geo/cp_espana.py::geocodificar_cp`, precisión de provincia) +
  propagación a `almacen.latitud/longitud` (migración 0254, usado por
  `services/tpv/online_orders_service.py::buscar_almacenes_con_stock`) que hacía `db/centros_perfil.
  py` se REPLICA ahora en `db/centros.py::crear_centro`/`actualizar_centro` — mismo comportamiento,
  nueva ubicación. `centros_trabajo` NO guarda latitud/longitud propias (no se añaden esas columnas
  aquí): la única propagación real, como antes, es hacia el almacén enlazado por `id_almacen`.

NO se toca `src/services/identidad/` (los ~40 adaptadores IOC): son columnas nuevas, nullable,
aditivas sobre `centros_trabajo` — no cambian su comportamiento existente en absoluto.
"""

VERSION = "0257"
DESCRIPCION = ("Unifica \"Centros\" en centros_trabajo (tipo_centro/id_almacen/creado_por_id) y "
               "retira centros_perfil (vacía, solo usada en esta sesión); "
               "usuarios.id_centro_perfil (INT) -> id_centro_trabajo (VARCHAR(36))")
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLA_RETIRADA = "centros_perfil"

_COLUMNAS_CENTROS_TRABAJO = [
    ("centros_trabajo", "tipo_centro", "VARCHAR(20) NULL"),
    ("centros_trabajo", "id_almacen", "INT NULL"),
    ("centros_trabajo", "creado_por_id", "INT NULL"),
]

# CREATE TABLE original de centros_perfil (migración 0256) — para recrearla tal cual en `revertir`.
_CREATE_CENTROS_PERFIL = """
    CREATE TABLE centros_perfil (
        id              INT AUTO_INCREMENT PRIMARY KEY,
        id_empresa      CHAR(36)     NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001',
        tipo_centro     VARCHAR(20)  NOT NULL DEFAULT 'tienda',
        id_tienda       INT          NULL,
        id_almacen      INT          NULL,
        nombre_centro   VARCHAR(150) NOT NULL DEFAULT '',
        codigo_centro   VARCHAR(20)  NOT NULL DEFAULT '',
        direccion       VARCHAR(255) NULL,
        codigo_postal   VARCHAR(10)  NULL,
        municipio       VARCHAR(100) NULL,
        provincia       VARCHAR(100) NULL,
        pais            VARCHAR(100) NOT NULL DEFAULT 'ESPAÑA',
        telefono        VARCHAR(30)  NULL,
        email           VARCHAR(150) NULL,
        latitud         DECIMAL(10,7) NULL,
        longitud        DECIMAL(10,7) NULL,
        creado_por_id   INT          NULL,
        fecha_creacion  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_cp_empresa (id_empresa),
        INDEX idx_cp_creador (creado_por_id),
        INDEX idx_cp_tienda (id_tienda),
        INDEX idx_cp_almacen (id_almacen)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


def _existe_tabla(cur, tabla) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s", (tabla,))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def _existe_columna(cur, tabla, columna) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, columna))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


def aplicar(cur):
    for tabla, col, definicion in _COLUMNAS_CENTROS_TRABAJO:
        if not _existe_columna(cur, tabla, col):
            cur.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {definicion}")

    # usuarios.id_centro_trabajo (VARCHAR(36)) sustituye a id_centro_perfil (INT) — ver docstring.
    if not _existe_columna(cur, "usuarios", "id_centro_trabajo"):
        cur.execute("ALTER TABLE usuarios ADD COLUMN id_centro_trabajo VARCHAR(36) NULL")
    if _existe_columna(cur, "usuarios", "id_centro_perfil"):
        cur.execute("ALTER TABLE usuarios DROP COLUMN id_centro_perfil")

    # Retirar centros_perfil SOLO si está vacía (verificado en vivo antes de escribir esta
    # migración: 0 filas). Defensivo: si alguna instalación tuviera filas reales, NO se destruyen —
    # se deja la tabla intacta en vez de arriesgar datos.
    if _existe_tabla(cur, _TABLA_RETIRADA):
        cur.execute(f"SELECT COUNT(*) FROM {_TABLA_RETIRADA}")
        r = cur.fetchone()
        total = int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0)
        if total == 0:
            cur.execute(f"DROP TABLE {_TABLA_RETIRADA}")


def revertir(cur):
    if not _existe_tabla(cur, _TABLA_RETIRADA):
        cur.execute(_CREATE_CENTROS_PERFIL)

    if not _existe_columna(cur, "usuarios", "id_centro_perfil"):
        cur.execute("ALTER TABLE usuarios ADD COLUMN id_centro_perfil INT NULL")
    if _existe_columna(cur, "usuarios", "id_centro_trabajo"):
        cur.execute("ALTER TABLE usuarios DROP COLUMN id_centro_trabajo")

    for tabla, col, _def in reversed(_COLUMNAS_CENTROS_TRABAJO):
        if _existe_columna(cur, tabla, col):
            cur.execute(f"ALTER TABLE {tabla} DROP COLUMN {col}")
