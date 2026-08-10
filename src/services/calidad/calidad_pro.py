"""
Calidad PRO (Módulo 16, enriquecimiento). Añade SOLO lo ausente sobre el módulo de calidad existente
(inspecciones/NC/CAPA/auditorías/trazabilidad/analítica): METROLOGÍA/calibración de equipos de medida
(con plan y alertas de vencimiento), CERTIFICADOS de análisis por lote y SPC (Cp/Cpk). Multiempresa,
auditado. No duplica.
"""

import datetime as _dt
import json
import logging

logger = logging.getLogger("calidad.pro")


def _emp(id_empresa=None):
    # IOC v2 (Bloque III): resolución de empresa vía capa de identidad (Strangler).
    try:
        from src.services.calidad.identidad_calidad import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)


def _audit(accion, detalle, tabla):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("calidad", accion, tabla, (detalle or "")[:255])
    except Exception:
        pass


def _filas(cur):
    from src.db.conexion import _filas_a_dicts
    return _filas_a_dicts(cur, cur.fetchall())


# ── Metrología / calibración ─────────────────────────────────────────────────
def alta_equipo(codigo, nombre, *, ubicacion=None, frecuencia_dias=365, ultima_calibracion=None,
                id_empresa=None) -> int | None:
    emp = _emp(id_empresa)
    prox = None
    if ultima_calibracion:
        try:
            prox = (_dt.date.fromisoformat(str(ultima_calibracion)[:10]) +
                    _dt.timedelta(days=int(frecuencia_dias or 365))).isoformat()
        except Exception:
            prox = None
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO calidad_equipos_medida (id_empresa, codigo, nombre, ubicacion, "
                        "frecuencia_dias, ultima_calibracion, proxima_calibracion) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE nombre=VALUES(nombre), "
                        "ubicacion=VALUES(ubicacion), frecuencia_dias=VALUES(frecuencia_dias)",
                        (emp, codigo[:60], nombre[:160], ubicacion, int(frecuencia_dias or 365),
                         ultima_calibracion, prox))
            eid = cur.lastrowid
            if not eid:
                cur.execute("SELECT id FROM calidad_equipos_medida WHERE id_empresa<=>%s AND codigo=%s",
                            (emp, codigo))
                r = cur.fetchone()
                eid = (r[0] if not isinstance(r, dict) else list(r.values())[0]) if r else None
            c.commit()
        _audit("EQUIPO_ALTA", f"{eid}:{codigo}", "calidad_equipos_medida")
        return eid
    except Exception as e:
        logger.error("alta_equipo: %s", e)
        return None


def registrar_calibracion(id_equipo, *, fecha=None, resultado="CONFORME", certificado=None,
                          proveedor=None, desviacion=None, observaciones=None, id_empresa=None) -> dict:
    """Registra una calibración y actualiza última/próxima fecha del equipo (según su frecuencia)."""
    emp = _emp(id_empresa)
    fecha = fecha or _dt.date.today().isoformat()
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO calidad_calibraciones (id_empresa, id_equipo, fecha, resultado, "
                        "certificado, proveedor, desviacion, observaciones) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        (emp, id_equipo, fecha, resultado, certificado, proveedor, desviacion, observaciones))
            cur.execute("SELECT frecuencia_dias FROM calidad_equipos_medida WHERE id=%s", (id_equipo,))
            r = cur.fetchone()
            frec = int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 365) if r else 365
            prox = (_dt.date.fromisoformat(str(fecha)[:10]) + _dt.timedelta(days=frec)).isoformat()
            estado = "ACTIVO" if resultado == "CONFORME" else "FUERA_SERVICIO"
            cur.execute("UPDATE calidad_equipos_medida SET ultima_calibracion=%s, proxima_calibracion=%s, "
                        "estado=%s WHERE id=%s", (fecha, prox, estado, id_equipo))
            c.commit()
        # No conformidad automática si la calibración NO es conforme (reutiliza el módulo NC existente).
        if resultado != "CONFORME":
            try:
                from src.services.calidad import no_conformidades
                no_conformidades.abrir(f"Equipo de medida {id_equipo} no conforme en calibración",
                                       origen="interna", severidad="alta", id_empresa=emp)
            except Exception:
                pass
        _audit("CALIBRACION", f"equipo{id_equipo}:{resultado}", "calidad_calibraciones")
        return {"ok": True, "proxima_calibracion": prox, "estado": estado}
    except Exception as e:
        logger.error("registrar_calibracion: %s", e)
        return {"ok": False, "motivo": str(e)}


def equipos_a_calibrar(id_empresa=None, *, dias=30) -> list:
    emp = _emp(id_empresa)
    limite = (_dt.date.today() + _dt.timedelta(days=int(dias))).isoformat()
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM calidad_equipos_medida WHERE id_empresa<=>%s AND estado='ACTIVO' "
                        "AND proxima_calibracion IS NOT NULL AND proxima_calibracion<=%s "
                        "ORDER BY proxima_calibracion", (emp, limite))
            return _filas(cur)
    except Exception as e:
        logger.error("equipos_a_calibrar: %s", e)
        return []


def _job_calibraciones(id_empresa=None) -> dict:
    emp = _emp(id_empresa)
    pend = equipos_a_calibrar(emp, dias=30)
    if pend:
        try:
            from src.services.comunicaciones import notificaciones
            notificaciones.emitir("calidad_calibracion", "Equipos de medida a calibrar",
                                  f"{len(pend)} equipo(s) requieren calibración en 30 días.",
                                  prioridad="alta", modulo="calidad",
                                  roles=["ADMINISTRADOR", "GERENTE"], id_empresa=emp)
        except Exception:
            pass
    return {"pendientes": len(pend)}


def registrar_jobs_calidad(id_empresa=None):
    try:
        from src.services import scheduler
        scheduler.registrar("calidad_calibraciones_alerta", _job_calibraciones)
        scheduler.registrar_job("calidad_calibraciones_alerta", intervalo_horas=168,
                                descripcion="Alerta de calibración de equipos de medida")
    except Exception as e:
        logger.debug("registrar_jobs_calidad: %s", e)


# ── Certificados de análisis ─────────────────────────────────────────────────
def emitir_certificado(articulo, *, id_lote=None, resultados=None, numero=None, emitido_por=None,
                       id_empresa=None) -> int | None:
    """Emite un certificado de análisis para un lote/artículo. `resultados`: [{parametro, valor,
    min, max}]. Conforme si todos los valores están dentro de límites."""
    emp = _emp(id_empresa)
    resultados = resultados or []
    conforme = 1
    for r in resultados:
        try:
            v = float(r.get("valor"))
            if r.get("min") is not None and v < float(r["min"]):
                conforme = 0
            if r.get("max") is not None and v > float(r["max"]):
                conforme = 0
        except Exception:
            pass
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO calidad_certificados (id_empresa, numero, articulo, id_lote, "
                        "resultados, conforme, emitido_por, fecha) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        (emp, numero, str(articulo), id_lote,
                         json.dumps(resultados, ensure_ascii=False, default=str), conforme, emitido_por,
                         _dt.date.today().isoformat()))
            cid = cur.lastrowid
            c.commit()
        _audit("CERTIFICADO", f"{cid}:{articulo} conforme={conforme}", "calidad_certificados")
        return cid
    except Exception as e:
        logger.error("emitir_certificado: %s", e)
        return None


def certificados_de_lote(id_lote, *, id_empresa=None) -> list:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM calidad_certificados WHERE id_empresa<=>%s AND id_lote=%s "
                        "ORDER BY fecha DESC", (emp, id_lote))
            filas = _filas(cur)
        for f in filas:
            try:
                f["resultados"] = json.loads(f.get("resultados") or "[]")
            except Exception:
                f["resultados"] = []
        return filas
    except Exception as e:
        logger.error("certificados_de_lote: %s", e)
        return []


# ── SPC — capacidad de proceso (Cp/Cpk) ──────────────────────────────────────
def cp_cpk(mediciones, lim_inf, lim_sup) -> dict:
    """Índices de capacidad de proceso a partir de una serie de mediciones y los límites de
    especificación. Cp = (LSE-LIE)/6σ; Cpk = min((LSE-µ),(µ-LIE))/3σ."""
    try:
        datos = [float(x) for x in mediciones if x is not None]
        n = len(datos)
        if n < 2:
            return {"ok": False, "motivo": "insuficientes mediciones"}
        media = sum(datos) / n
        var = sum((x - media) ** 2 for x in datos) / (n - 1)
        sigma = var ** 0.5
        lie, lse = float(lim_inf), float(lim_sup)
        if sigma <= 0:
            return {"ok": True, "media": round(media, 4), "sigma": 0.0, "cp": None, "cpk": None,
                    "capaz": lie <= media <= lse}
        cp = (lse - lie) / (6 * sigma)
        cpk = min(lse - media, media - lie) / (3 * sigma)
        return {"ok": True, "n": n, "media": round(media, 4), "sigma": round(sigma, 4),
                "cp": round(cp, 3), "cpk": round(cpk, 3), "capaz": cpk >= 1.33}
    except Exception as e:
        logger.error("cp_cpk: %s", e)
        return {"ok": False, "motivo": str(e)}
