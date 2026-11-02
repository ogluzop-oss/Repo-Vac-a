"""
Migración 0295 — Fase Productividad (Ventas): esquema de objetivos de facturación por centro y
por empleado, más campañas comerciales. ADITIVA, reversible, idempotente.

Auditoría previa confirmó que las tablas existentes de objetivos (`rendimiento_diario`,
`prevision_objetivos`) NO son reutilizables: clave única incompatible (pensadas para una sola
granularidad) y sin aislamiento por tenant real. Se crean 3 tablas NUEVAS, con un criterio de
diseño deliberado para evitar un job de "cierre de periodo" en segundo plano:

- `productividad_objetivos` guarda OBJETIVOS VERSIONADOS (`vigente_desde`/`vigente_hasta`) en vez
  de mutarlos en sitio — así un objetivo editado hoy no altera silenciosamente las barras de
  progreso de periodos pasados ya cerrados, y la barra "facturado" de cualquier periodo (actual o
  histórico) se calcula SIEMPRE en vivo a partir de `ventas`/`fichajes` (nunca de una caché que
  haya que recalcular con un cron). `tipo_objetivo` distingue CENTRO (objetivo fijo, referencia
  `centros_trabajo.codigo`) de EMPLEADO (objetivo por HORA, referencia `usuarios.id` — el objetivo
  real se recalcula multiplicando por las horas trabajadas obtenidas de Fichajes). `periodo` cubre
  los 8 tipos pedidos (diario/semanal/bimensual/mensual/bimestral/trimestral/semestral/anual); el
  servicio de negocio es quien exige que mensual/semestral/anual estén siempre definidos (los otros
  5 son opcionales) — no se modela como restricción SQL para no acoplar la validez de negocio al
  esquema.
- `productividad_campanas` + `productividad_campana_objetivos`: objetivos de campaña, EXPLÍCITAMENTE
  PARALELOS a los objetivos ordinarios de arriba (nunca los sustituyen ni se mezclan) — una campaña
  tiene nombre libre, fecha de inicio/fin propias y uno o varios objetivos (centro fijo o empleado
  por hora) acotados a esas fechas. Al no solaparse con periodos recurrentes, no necesita
  versionado: se edita en sitio.
"""

VERSION = "0295"
DESCRIPCION = "productividad_objetivos / productividad_campanas / productividad_campana_objetivos"
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
    cur.execute("""
        CREATE TABLE IF NOT EXISTS productividad_objetivos (
            id              BIGINT        NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa      CHAR(36)      NOT NULL,
            tipo_objetivo   ENUM('centro','empleado') NOT NULL,
            centro_codigo   VARCHAR(40)            DEFAULT NULL,
            usuario_id      INT                    DEFAULT NULL,
            periodo         ENUM('diario','semanal','bimensual','mensual','bimestral',
                                  'trimestral','semestral','anual') NOT NULL,
            valor           DECIMAL(12,2) NOT NULL DEFAULT 0,
            vigente_desde   DATE          NOT NULL,
            vigente_hasta   DATE                   DEFAULT NULL,
            creado_por_id   INT                    DEFAULT NULL,
            creado_en       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_prodobj_centro (id_empresa, tipo_objetivo, centro_codigo, periodo, vigente_desde),
            INDEX idx_prodobj_empleado (id_empresa, tipo_objetivo, usuario_id, periodo, vigente_desde)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS productividad_campanas (
            id              BIGINT        NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_empresa      CHAR(36)      NOT NULL,
            nombre          VARCHAR(150)  NOT NULL,
            fecha_inicio    DATE          NOT NULL,
            fecha_fin       DATE          NOT NULL,
            creado_por_id   INT                    DEFAULT NULL,
            creado_en       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_prodcamp_emp (id_empresa, fecha_inicio, fecha_fin)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS productividad_campana_objetivos (
            id              BIGINT        NOT NULL AUTO_INCREMENT PRIMARY KEY,
            id_campana      BIGINT        NOT NULL,
            id_empresa      CHAR(36)      NOT NULL,
            tipo_objetivo   ENUM('centro','empleado') NOT NULL,
            centro_codigo   VARCHAR(40)            DEFAULT NULL,
            usuario_id      INT                    DEFAULT NULL,
            valor           DECIMAL(12,2) NOT NULL DEFAULT 0,
            creado_en       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_prodcampobj_campana (id_campana),
            INDEX idx_prodcampobj_centro (id_empresa, tipo_objetivo, centro_codigo),
            INDEX idx_prodcampobj_empleado (id_empresa, tipo_objetivo, usuario_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def revertir(cur):
    cur.execute("DROP TABLE IF EXISTS productividad_campana_objetivos")
    cur.execute("DROP TABLE IF EXISTS productividad_campanas")
    cur.execute("DROP TABLE IF EXISTS productividad_objetivos")
