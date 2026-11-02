"""
Migración 0256 — Sistema de "Centros" (identidad + proximidad por CP + aislamiento). ADITIVA,
idempotente, reversible.

Nueva tabla `centros_perfil`: generaliza la ficha de "Datos de empresa" (identidad — nombre,
dirección, CP, municipio, provincia, país, teléfono, email) a CADA centro físico de la empresa
(tienda/almacén/fábrica/oficina/otro), con enlace opcional a la fila física existente
(`id_tienda`/`id_almacen`, sin tocar el esquema de `tiendas`/`almacen`) y `creado_por_id` como base
del aislamiento entre superadmins (cada uno ve solo los centros que creó, salvo desbloqueo por PIN
— ver `db/centros_perfil.py`). NO reutiliza `centros_trabajo` (artefacto RRHH/Seguridad Social con
semántica distinta — se deja intacto, ver `db/centros.py`).

`tipo_centro` es texto libre (`tienda|almacen|fabrica|oficina|otro`), sin CHECK constraint — mismo
criterio ya usado en `almacen.tipo_almacen`.

`latitud`/`longitud` son INTERNAS (nunca editables a mano): se autocompletan una única vez al
guardar el `codigo_postal` vía `services/geo/cp_espana.py::geocodificar_cp` (precisión de
PROVINCIA, no de dirección exacta — ver docstring de ese módulo). Si el centro tiene `id_almacen`,
el mismo par se replica en `almacen.latitud/longitud` (migración 0254) para que
`services/tpv/online_orders_service.py::buscar_almacenes_con_stock` siga ordenando por proximidad
sin cambios.

También añade `usuarios.id_centro_perfil` (NULL, vínculo empleado↔centro) — ADITIVA: convive con
`usuarios.centro_codigo`, que se mantiene intacto y sincronizado (se sigue escribiendo con
`centros_perfil.codigo_centro` al vincular) para no romper ningún consumidor existente (kárdex,
logística, sesión).
"""

VERSION = "0256"
DESCRIPCION = ("Sistema de Centros: tabla centros_perfil (identidad + geolocalización por CP + "
               "aislamiento por creador) y usuarios.id_centro_perfil")
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLA = "centros_perfil"


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
    if not _existe_tabla(cur, _TABLA):
        cur.execute(f"""
            CREATE TABLE {_TABLA} (
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
        """)
    if not _existe_columna(cur, "usuarios", "id_centro_perfil"):
        cur.execute("ALTER TABLE usuarios ADD COLUMN id_centro_perfil INT NULL")


def revertir(cur):
    if _existe_columna(cur, "usuarios", "id_centro_perfil"):
        cur.execute("ALTER TABLE usuarios DROP COLUMN id_centro_perfil")
    if _existe_tabla(cur, _TABLA):
        cur.execute(f"DROP TABLE {_TABLA}")
