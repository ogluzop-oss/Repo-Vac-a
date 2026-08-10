"""
Panel de estado de la distribucion (Fase 2, SUBFASE 2.12) — SOLO BACKEND (sin GUI).

API interna para consultar: eventos/distribuciones pendientes, terminales conectadas y
desconectadas, ultima sincronizacion, cola por estado, errores y reintentos.
"""

import logging

from src.services.distribucion import terminales as _T

logger = logging.getLogger("distribucion.estado")


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


def _scalar(cur):
    r = cur.fetchone()
    if r is None:
        return None
    return r[0] if not isinstance(r, dict) else list(r.values())[0]


def resumen(id_empresa=None) -> dict:
    """Foto del estado de la distribucion para diagnostico/observabilidad."""
    emp = _emp(id_empresa)
    cola_estados, ack_estados = {}, {}
    errores = reintentos = pendientes_ev = 0
    ultima_sync = None
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT estado, COUNT(*) FROM distribucion_pendiente WHERE id_empresa=%s "
                        "GROUP BY estado", (emp,))
            for r in cur.fetchall():
                k = r[0] if not isinstance(r, dict) else list(r.values())[0]
                v = r[1] if not isinstance(r, dict) else list(r.values())[1]
                cola_estados[k] = int(v)
            cur.execute("SELECT COALESCE(SUM(reintentos),0), COALESCE(SUM(estado='ERROR'),0) "
                        "FROM distribucion_pendiente WHERE id_empresa=%s", (emp,))
            r = cur.fetchone()
            if r:
                reintentos = int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0)
                errores = int((r[1] if not isinstance(r, dict) else list(r.values())[1]) or 0)
            cur.execute("SELECT estado, COUNT(*) FROM distribucion_confirmaciones WHERE id_empresa=%s "
                        "GROUP BY estado", (emp,))
            for r in cur.fetchall():
                k = r[0] if not isinstance(r, dict) else list(r.values())[0]
                v = r[1] if not isinstance(r, dict) else list(r.values())[1]
                ack_estados[k] = int(v)
            cur.execute("SELECT MAX(fecha_envio) FROM distribucion_pendiente WHERE id_empresa=%s", (emp,))
            ultima_sync = _scalar(cur)
            # eventos del bus aun sin drenar
            try:
                cur.execute("SELECT COUNT(*) FROM eventos WHERE id_empresa=%s AND estado='PENDIENTE'", (emp,))
                pendientes_ev = int(_scalar(cur) or 0)
            except Exception:
                pendientes_ev = 0
    except Exception as e:
        logger.error("resumen: %s", e)

    terms = _T.listar(emp)
    conectadas = [t for t in terms if (t.get("modo") or "online") == "online"]
    desconectadas = [t for t in terms if (t.get("modo") or "online") == "offline"]
    return {
        "eventos_bus_pendientes": pendientes_ev,
        "cola": cola_estados,
        "cola_pendientes": cola_estados.get("PENDIENTE", 0),
        "cola_enviados": cola_estados.get("ENVIADO", 0),
        "cola_confirmados": cola_estados.get("CONFIRMADO", 0),
        "confirmaciones": ack_estados,
        "errores": errores,
        "reintentos": reintentos,
        "terminales_total": len(terms),
        "terminales_conectadas": len(conectadas),
        "terminales_desconectadas": len(desconectadas),
        "ultima_sincronizacion": ultima_sync,
    }
