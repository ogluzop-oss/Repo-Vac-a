"""
CRM · Rutas comerciales + geolocalización (Módulo 1, enriquecimiento). Planifica rutas de visitas
comerciales sobre los clientes geolocalizados (latitud/longitud en `clientes`), con optimización por
proximidad (vecino más cercano) y marcado de visitas que reutiliza `crm.actividades` (tipo 'visita').
Integra auditoría. No duplica lógica: se apoya en clientes y actividades ya existentes.
"""

import logging
import math

logger = logging.getLogger("crm.rutas")


def _emp(id_empresa=None):
    # IOC v3 (Bloque V): resolución de empresa vía capa de identidad (Strangler).
    try:
        from src.services.crm.identidad_crm import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)


def _audit(accion, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("crm", accion, "crm_rutas", (detalle or "")[:255])
    except Exception:
        pass


def set_geolocalizacion(id_cliente, latitud, longitud) -> bool:
    """Guarda la geolocalización de un cliente (para planificar rutas/visitas)."""
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("UPDATE clientes SET latitud=%s, longitud=%s WHERE id=%s",
                        (float(latitud), float(longitud), id_cliente))
            c.commit()
        return True
    except Exception as e:
        logger.error("set_geolocalizacion: %s", e)
        return False


def crear_ruta(nombre, *, responsable=None, fecha=None, id_empresa=None) -> int | None:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO crm_rutas (id_empresa, nombre, responsable, fecha) "
                        "VALUES (%s,%s,%s,%s)", (emp, nombre[:160], responsable, fecha))
            rid = cur.lastrowid
            c.commit()
        _audit("RUTA_CREADA", f"{rid}:{nombre}")
        return rid
    except Exception as e:
        logger.error("crear_ruta: %s", e)
        return None


def añadir_parada(id_ruta, id_cliente, *, orden=None, notas=None) -> int | None:
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            if orden is None:
                cur.execute("SELECT COALESCE(MAX(orden),0)+1 FROM crm_ruta_paradas WHERE id_ruta=%s",
                            (id_ruta,))
                r = cur.fetchone()
                orden = int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 1)
            cur.execute("INSERT INTO crm_ruta_paradas (id_ruta, id_cliente, orden, notas) "
                        "VALUES (%s,%s,%s,%s)", (id_ruta, id_cliente, int(orden), notas))
            pid = cur.lastrowid
            c.commit()
        return pid
    except Exception as e:
        logger.error("añadir_parada: %s", e)
        return None


def _distancia(a, b) -> float:
    """Distancia aproximada (haversine, km) entre dos (lat,lng)."""
    if None in a or None in b:
        return float("inf")
    R = 6371.0
    la1, lo1, la2, lo2 = map(math.radians, [float(a[0]), float(a[1]), float(b[0]), float(b[1])])
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def optimizar(id_ruta, *, origen=None, id_empresa=None) -> dict:
    """Reordena las paradas por proximidad geográfica (vecino más cercano) desde `origen` (lat,lng) o
    desde la primera parada geolocalizada. Reutiliza la geolocalización de clientes."""
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT p.id, p.id_cliente, cl.latitud, cl.longitud FROM crm_ruta_paradas p "
                        "LEFT JOIN clientes cl ON cl.id=p.id_cliente WHERE p.id_ruta=%s ORDER BY p.orden",
                        (id_ruta,))
            paradas = _filas_a_dicts(cur, cur.fetchall())
            geo = [(p, (p.get("latitud"), p.get("longitud"))) for p in paradas]
            con_geo = [g for g in geo if g[1][0] is not None and g[1][1] is not None]
            sin_geo = [g for g in geo if not (g[1][0] is not None and g[1][1] is not None)]
            orden_final = []
            actual = origen
            restantes = list(con_geo)
            if actual is None and restantes:
                orden_final.append(restantes.pop(0)); actual = orden_final[-1][1]
            while restantes:
                restantes.sort(key=lambda g: _distancia(actual, g[1]))
                sig = restantes.pop(0); orden_final.append(sig); actual = sig[1]
            orden_final += sin_geo   # sin geolocalización al final
            for i, (p, _g) in enumerate(orden_final, start=1):
                cur.execute("UPDATE crm_ruta_paradas SET orden=%s WHERE id=%s", (i, p["id"]))
            c.commit()
        _audit("RUTA_OPTIMIZADA", f"{id_ruta}:{len(orden_final)} paradas")
        return {"ok": True, "paradas": len(orden_final), "geolocalizadas": len(con_geo)}
    except Exception as e:
        logger.error("optimizar: %s", e)
        return {"ok": False, "motivo": str(e)}


def marcar_visitada(id_parada, *, responsable=None, notas=None, id_empresa=None) -> dict:
    """Marca una parada como visitada y crea la ACTIVIDAD 'visita' correspondiente (reutiliza
    crm.actividades, que a su vez genera tarea + evento de calendario). No duplica lógica."""
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT id_ruta, id_cliente FROM crm_ruta_paradas WHERE id=%s", (id_parada,))
            r = cur.fetchone()
            if not r:
                return {"ok": False, "motivo": "parada inexistente"}
            d = r if isinstance(r, dict) else {"id_ruta": r[0], "id_cliente": r[1]}
        id_act = None
        try:
            from src.services.crm import actividades
            id_act = actividades.crear_actividad("visita", f"Visita comercial (ruta {d['id_ruta']})",
                                                 id_cliente=d["id_cliente"], responsable=responsable,
                                                 notas=notas, id_empresa=id_empresa)
        except Exception as e:
            logger.debug("crear actividad visita: %s", e)
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("UPDATE crm_ruta_paradas SET estado='VISITADA', id_actividad=%s WHERE id=%s",
                        (id_act, id_parada))
            c.commit()
        _audit("RUTA_PARADA_VISITADA", f"parada={id_parada}")
        return {"ok": True, "id_actividad": id_act}
    except Exception as e:
        logger.error("marcar_visitada: %s", e)
        return {"ok": False, "motivo": str(e)}


def listar_rutas(id_empresa=None) -> list:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM crm_rutas WHERE id_empresa<=>%s ORDER BY creada DESC", (emp,))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_rutas: %s", e)
        return []


def paradas(id_ruta) -> list:
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT p.*, cl.nombre AS cliente FROM crm_ruta_paradas p "
                        "LEFT JOIN clientes cl ON cl.id=p.id_cliente WHERE p.id_ruta=%s ORDER BY p.orden",
                        (id_ruta,))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("paradas: %s", e)
        return []
