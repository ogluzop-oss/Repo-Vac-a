"""
Configuracion de distribucion por empresa (Fase 2): ventana de mantenimiento, horario
laboral (nunca distribuir programado en horario laboral), politica de reintentos y
estrategia de conflicto por defecto. Multiempresa.
"""

import logging
from datetime import datetime, timedelta

logger = logging.getLogger("distribucion.config")

_DEF = {"ventana_hora": 3, "ventana_activa": 1, "laboral_inicio": 8, "laboral_fin": 22,
        "reintentos_seg": "60,300,900,1800,3600,43200,86400",
        "estrategia_conflicto": "version_superior"}


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        try:
            from src.db.conexion import EMPRESA_DEFAULT_ID
            return EMPRESA_DEFAULT_ID
        except Exception:
            return None


def obtener(id_empresa=None) -> dict:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM distribucion_config WHERE id_empresa=%s", (emp,))
            r = _filas_a_dicts(cur, cur.fetchall())
            if r:
                return r[0]
    except Exception as e:
        logger.debug("config obtener: %s", e)
    d = dict(_DEF); d["id_empresa"] = emp
    return d


def guardar(id_empresa=None, **campos) -> bool:
    emp = _emp(id_empresa)
    cfg = obtener(emp)
    cfg.update({k: v for k, v in campos.items() if v is not None})
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(
                "INSERT INTO distribucion_config (id_empresa, ventana_hora, ventana_activa, "
                "laboral_inicio, laboral_fin, reintentos_seg, estrategia_conflicto) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
                "ventana_hora=VALUES(ventana_hora), ventana_activa=VALUES(ventana_activa), "
                "laboral_inicio=VALUES(laboral_inicio), laboral_fin=VALUES(laboral_fin), "
                "reintentos_seg=VALUES(reintentos_seg), estrategia_conflicto=VALUES(estrategia_conflicto)",
                (emp, int(cfg["ventana_hora"]), int(cfg["ventana_activa"]), int(cfg["laboral_inicio"]),
                 int(cfg["laboral_fin"]), cfg["reintentos_seg"], cfg["estrategia_conflicto"]))
            c.commit()
        return True
    except Exception as e:
        logger.error("config guardar: %s", e)
        return False


def reintentos_lista(id_empresa=None) -> list:
    raw = obtener(id_empresa).get("reintentos_seg") or _DEF["reintentos_seg"]
    try:
        return [int(x) for x in str(raw).split(",") if str(x).strip()]
    except Exception:
        return [60, 300, 900, 1800, 3600, 43200, 86400]


def proxima_ventana(id_empresa=None) -> datetime:
    """Siguiente ventana de mantenimiento (por defecto 03:00). Nunca en horario laboral."""
    cfg = obtener(id_empresa)
    h = int(cfg.get("ventana_hora") or 3)
    now = datetime.now()
    target = now.replace(hour=h, minute=0, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    return target


def en_horario_laboral(id_empresa=None, momento: datetime = None) -> bool:
    cfg = obtener(id_empresa)
    m = momento or datetime.now()
    return int(cfg.get("laboral_inicio") or 8) <= m.hour < int(cfg.get("laboral_fin") or 22)
