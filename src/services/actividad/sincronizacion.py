"""
Panel de sincronizacion visual (Fase 3, SUBFASE 3.7/3.8).

Estado de cada terminal de la empresa: sincronizada / pendiente (con nº de cambios) / offline,
y ultima sincronizacion. Se apoya en el registro de terminales (edge_nodes) y en la cola de
distribucion + confirmaciones (Fase 2). Solo lectura; multiempresa.
"""

import logging

logger = logging.getLogger("actividad.sincronizacion")


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


def _pendientes_por_tienda(emp) -> dict:
    """{id_tienda: nº de cambios sin confirmar}."""
    out = {}
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT COALESCE(destino_tienda,0), COUNT(*) FROM distribucion_pendiente "
                        "WHERE id_empresa=%s AND estado IN ('PENDIENTE','ENVIADO','ERROR') "
                        "GROUP BY destino_tienda", (emp,))
            for r in cur.fetchall():
                k = r[0] if not isinstance(r, dict) else list(r.values())[0]
                v = r[1] if not isinstance(r, dict) else list(r.values())[1]
                out[int(k or 0)] = int(v)
    except Exception as e:
        logger.debug("pendientes por tienda: %s", e)
    return out


def panel(id_empresa=None) -> list:
    """Lista de terminales con su estado de sincronizacion (para el panel visual)."""
    emp = _emp(id_empresa)
    try:
        from src.services.distribucion import terminales as _T
        terms = _T.listar(emp)
    except Exception:
        terms = []
    pend = _pendientes_por_tienda(emp)
    filas = []
    for t in terms:
        idt = int(t.get("id_tienda") or 0)
        modo = t.get("modo") or "online"
        n = pend.get(idt, 0)
        if modo == "offline":
            estado = "OFFLINE"
        elif n > 0:
            estado = "PENDIENTE"
        else:
            estado = "SINCRONIZADA"
        filas.append({
            "id_tienda": idt,
            "nombre": t.get("nombre") or ("central" if idt == 0 else f"tienda-{idt}"),
            "modo": modo,
            "estado": estado,
            "cambios_pendientes": n,
            "ultima_sincronizacion": t.get("ultima_sincronizacion"),
            "salud": t.get("salud"),
        })
    # Central primero, luego por id_tienda.
    filas.sort(key=lambda f: (f["id_tienda"] != 0, f["id_tienda"]))
    return filas


def infraestructura(id_empresa=None) -> dict:
    """Dashboard de infraestructura (Fase 4, SUBFASE 4.12/4.13). Amplia el panel con version,
    latencia, paquetes, ancho de banda y ultima conexion por terminal + metricas globales."""
    emp = _emp(id_empresa)
    base = panel(emp)
    ver, lat, paq = {}, {}, {}
    glob = {"sesiones": 0, "errores": 0, "paquetes": 0, "bytes": 0, "sincronizando": 0}
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT id_tienda, version_sw, version_db, ultima_sync FROM terminal_versiones "
                        "WHERE id_empresa=%s", (emp,))
            for r in cur.fetchall():
                g = (lambda i: r[i] if not isinstance(r, dict) else list(r.values())[i])
                ver[int(g(0) or 0)] = {"version_sw": g(1), "version_db": g(2), "ultima_sync": g(3)}
            cur.execute("SELECT destino_tienda, ROUND(AVG(duracion_ms)), COUNT(*), "
                        "COALESCE(SUM(estado='EN_CURSO'),0) FROM sync_sesiones WHERE id_empresa=%s "
                        "GROUP BY destino_tienda", (emp,))
            for r in cur.fetchall():
                g = (lambda i: r[i] if not isinstance(r, dict) else list(r.values())[i])
                lat[int(g(0) or 0)] = {"latencia_ms": int(g(1) or 0), "sesiones": int(g(2) or 0),
                                       "sincronizando": int(g(3) or 0)}
            cur.execute("SELECT destino_tienda, COUNT(*), COALESCE(SUM(bytes_comprimido),0) "
                        "FROM sync_paquetes WHERE id_empresa=%s GROUP BY destino_tienda", (emp,))
            for r in cur.fetchall():
                g = (lambda i: r[i] if not isinstance(r, dict) else list(r.values())[i])
                paq[int(g(0) or 0)] = {"paquetes": int(g(1) or 0), "bytes": int(g(2) or 0)}
            cur.execute("SELECT COUNT(*), COALESCE(SUM(estado='ERROR'),0), "
                        "COALESCE(SUM(estado='EN_CURSO'),0) FROM sync_sesiones WHERE id_empresa=%s", (emp,))
            r = cur.fetchone()
            if r:
                g = (lambda i: r[i] if not isinstance(r, dict) else list(r.values())[i])
                glob["sesiones"] = int(g(0) or 0); glob["errores"] = int(g(1) or 0)
                glob["sincronizando"] = int(g(2) or 0)
    except Exception as e:
        logger.error("infraestructura: %s", e)

    for t in base:
        idt = t["id_tienda"]
        t.update(ver.get(idt, {}))
        t.update(lat.get(idt, {}))
        t.update(paq.get(idt, {}))
        glob["paquetes"] += int(t.get("paquetes") or 0)
        glob["bytes"] += int(t.get("bytes") or 0)
    return {"terminales": base, "global": glob}


def sesiones(id_empresa=None, limite=50) -> list:
    """Observabilidad (4.13): ultimas sesiones de sincronizacion (inicio/fin/duracion/bytes/eventos)."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM sync_sesiones WHERE id_empresa=%s ORDER BY id DESC LIMIT %s",
                        (emp, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("sesiones: %s", e)
        return []
