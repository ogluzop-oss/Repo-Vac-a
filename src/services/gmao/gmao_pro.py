"""
GMAO PRO (Módulo 17, enriquecimiento). Añade SOLO lo ausente sobre el GMAO existente (activos, planes
preventivos por calendario, OT con repuestos/costes, analítica MTTR/MTBF): mantenimiento por USO/
CONDICIÓN (medidores/horómetros con umbral que disparan OT) y RONDAS/CHECKLISTS de inspección.
Reutiliza `gmao.ordenes.crear_ot` para generar las OT. Multiempresa, auditado. No duplica.
"""

import datetime as _dt
import json
import logging

logger = logging.getLogger("gmao.pro")


def _emp(id_empresa=None):
    # IOC v2 (Bloque III): resolución de empresa vía capa de identidad (Strangler).
    try:
        from src.services.gmao.identidad_gmao import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)


def _audit(accion, detalle, tabla):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("gmao", accion, tabla, (detalle or "")[:255])
    except Exception:
        pass


def _filas(cur):
    from src.db.conexion import _filas_a_dicts
    return _filas_a_dicts(cur, cur.fetchall())


# ── Medidores / mantenimiento por uso ────────────────────────────────────────
def alta_medidor(id_activo, *, tipo="horas", umbral_preventivo=None, lectura_actual=0,
                 id_empresa=None) -> int | None:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO gmao_medidores (id_empresa, id_activo, tipo, lectura_actual, "
                        "umbral_preventivo, lectura_ultima_ot) VALUES (%s,%s,%s,%s,%s,%s)",
                        (emp, id_activo, tipo, float(lectura_actual or 0), umbral_preventivo,
                         float(lectura_actual or 0)))
            mid = cur.lastrowid
            c.commit()
        _audit("MEDIDOR_ALTA", f"{mid}:activo{id_activo} {tipo}", "gmao_medidores")
        return mid
    except Exception as e:
        logger.error("alta_medidor: %s", e)
        return None


def registrar_lectura(id_medidor, valor, *, fecha=None, operario=None, id_empresa=None) -> dict:
    """Registra una lectura del medidor. Si el uso desde la última OT alcanza el umbral, genera una
    OT preventiva (por condición) reutilizando `gmao.ordenes.crear_ot` y reinicia el contador."""
    emp = _emp(id_empresa)
    valor = float(valor or 0)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT id_activo, tipo, umbral_preventivo, lectura_ultima_ot FROM gmao_medidores "
                        "WHERE id=%s AND id_empresa<=>%s", (id_medidor, emp))
            r = cur.fetchone()
            if not r:
                return {"ok": False, "motivo": "medidor no existe"}
            r = r if not isinstance(r, dict) else list(r.values())
            id_activo, tipo, umbral, ult_ot = r[0], r[1], r[2], float(r[3] or 0)
            cur.execute("INSERT INTO gmao_lecturas (id_empresa, id_medidor, valor, fecha, operario) "
                        "VALUES (%s,%s,%s,%s,%s)", (emp, id_medidor, valor,
                        fecha or _dt.date.today().isoformat(), operario))
            cur.execute("UPDATE gmao_medidores SET lectura_actual=%s WHERE id=%s", (valor, id_medidor))
            c.commit()
        ot_generada = None
        if umbral and (valor - ult_ot) >= float(umbral):
            try:
                from src.services.gmao import ordenes
                ot_generada = ordenes.crear_ot(tipo="preventiva", id_activo=id_activo,
                                               descripcion=f"Preventivo por uso ({tipo}={valor})",
                                               prioridad="media", id_empresa=emp)
                if ot_generada:
                    from src.db.conexion import obtener_conexion as _oc
                    with _oc() as c, c.cursor() as cur:
                        cur.execute("UPDATE gmao_medidores SET lectura_ultima_ot=%s WHERE id=%s",
                                    (valor, id_medidor))
                        c.commit()
            except Exception as e:
                logger.debug("crear_ot por uso: %s", e)
        _audit("LECTURA", f"medidor{id_medidor}={valor} ot={ot_generada}", "gmao_lecturas")
        return {"ok": True, "ot_generada": ot_generada, "uso_desde_ot": round(valor - ult_ot, 3)}
    except Exception as e:
        logger.error("registrar_lectura: %s", e)
        return {"ok": False, "motivo": str(e)}


# ── Rondas / checklists de inspección ────────────────────────────────────────
def crear_checklist(codigo, nombre, items, *, id_empresa=None) -> int | None:
    """`items`: [{texto, tipo}] (tipo: ok_ko / valor / texto)."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO gmao_checklists (id_empresa, codigo, nombre, items) "
                        "VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE nombre=VALUES(nombre), "
                        "items=VALUES(items), activo=1",
                        (emp, codigo[:40], nombre[:160], json.dumps(items, ensure_ascii=False, default=str)))
            cid = cur.lastrowid
            if not cid:
                cur.execute("SELECT id FROM gmao_checklists WHERE id_empresa<=>%s AND codigo=%s", (emp, codigo))
                rr = cur.fetchone()
                cid = (rr[0] if not isinstance(rr, dict) else list(rr.values())[0]) if rr else None
            c.commit()
        _audit("CHECKLIST_ALTA", f"{cid}:{codigo}", "gmao_checklists")
        return cid
    except Exception as e:
        logger.error("crear_checklist: %s", e)
        return None


def ejecutar_ronda(id_checklist, *, id_activo=None, resultados=None, operario=None, id_empresa=None) -> dict:
    """Registra la ejecución de una ronda. Conforme si ningún ítem falla (resultado 'ko'/False). Si
    hay fallos, genera una OT correctiva reutilizando `gmao.ordenes.crear_ot`."""
    emp = _emp(id_empresa)
    resultados = resultados or []
    fallos = [r for r in resultados if str(r.get("resultado")).lower() in ("ko", "false", "0", "no")]
    conforme = 0 if fallos else 1
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO gmao_ronda_ejecuciones (id_empresa, id_checklist, id_activo, "
                        "resultados, conforme, operario, fecha) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (emp, id_checklist, id_activo,
                         json.dumps(resultados, ensure_ascii=False, default=str), conforme, operario,
                         _dt.date.today().isoformat()))
            rid = cur.lastrowid
            c.commit()
        ot_generada = None
        if fallos:
            try:
                from src.services.gmao import ordenes
                desc = "Ronda con incidencias: " + "; ".join(str(f.get("texto") or f.get("item")) for f in fallos)
                ot_generada = ordenes.crear_ot(tipo="correctiva", id_activo=id_activo,
                                               descripcion=desc[:200], prioridad="alta", id_empresa=emp)
            except Exception as e:
                logger.debug("crear_ot ronda: %s", e)
        _audit("RONDA", f"{rid}:checklist{id_checklist} conforme={conforme} ot={ot_generada}",
               "gmao_ronda_ejecuciones")
        return {"ok": True, "id_ejecucion": rid, "conforme": bool(conforme), "fallos": len(fallos),
                "ot_generada": ot_generada}
    except Exception as e:
        logger.error("ejecutar_ronda: %s", e)
        return {"ok": False, "motivo": str(e)}
