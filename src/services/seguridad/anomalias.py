"""
Detección de anomalías (SEC-4): fuerza bruta, múltiples IP, abuso. Genera incidente automático.
Se apoya en auditoria_logs (LOGIN_FALLIDO) ya registrados por la rama RBAC.
"""

import logging
from src.db.conexion import obtener_conexion

logger = logging.getLogger("seguridad.anomalias")


def detectar_fuerza_bruta(*, umbral=5, ventana_min=15, id_empresa=None) -> list:
    """Detecta usuarios/IP con >= umbral LOGIN_FALLIDO en la ventana. Abre incidente por cada uno."""
    incidentes = []
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT usuario, ip_origen, COUNT(*) n FROM auditoria_logs "
                "WHERE accion='LOGIN_FALLIDO' AND fecha >= (NOW() - INTERVAL %s MINUTE) "
                "GROUP BY usuario, ip_origen HAVING n >= %s", (int(ventana_min), int(umbral)))
            filas = [(r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r)))
                     for r in cur.fetchall()]
    except Exception as e:
        logger.error("detectar_fuerza_bruta: %s", e)
        return incidentes
    from src.services.seguridad import incidentes as _inc
    for f in filas:
        iid = _inc.abrir("fuerza_bruta", severidad="alta", ip_origen=f.get("ip_origen"),
                         detalle=f"{f.get('n')} intentos fallidos de {f.get('usuario')}", id_empresa=id_empresa)
        incidentes.append(iid)
    return incidentes
