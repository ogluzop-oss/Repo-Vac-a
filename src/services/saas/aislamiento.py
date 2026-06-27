"""
Hardening de aislamiento multitenant (FASE P2.2).

Herramienta de guardia: detecta tablas de datos SIN columna id_empresa (posible fuga) para
auditar la cobertura del aislamiento por tenant. No reescribe consultas (no rompe globales
legítimas); sirve para tests exhaustivos y revisión continua.
"""

import logging
from src.db.conexion import obtener_conexion

logger = logging.getLogger("saas.aislamiento")

# Tablas legítimamente GLOBALES (catálogos/sistema) que NO requieren id_empresa.
GLOBALES = {"permisos", "planes_saas", "modulos_saas", "plan_modulos", "migraciones_aplicadas",
            "bi_kpi_def", "scheduler_jobs", "scheduler_historial"}


def tablas_sin_tenant() -> list:
    """Lista de tablas de datos que NO tienen id_empresa y no están marcadas como globales."""
    fuera = []
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SHOW TABLES")
            tablas = [(r[0] if not isinstance(r, dict) else list(r.values())[0]) for r in cur.fetchall()]
            for t in tablas:
                if t in GLOBALES:
                    continue
                cur.execute(f"SHOW COLUMNS FROM {t} LIKE 'id_empresa'")
                if cur.fetchone() is None:
                    fuera.append(t)
    except Exception as e:
        logger.error("tablas_sin_tenant: %s", e)
    return fuera


def verificar(tabla) -> bool:
    """True si la tabla está aislada por tenant (tiene id_empresa) o es global declarada."""
    if tabla in GLOBALES:
        return True
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SHOW COLUMNS FROM {tabla} LIKE 'id_empresa'")
            return cur.fetchone() is not None
    except Exception:
        return False
