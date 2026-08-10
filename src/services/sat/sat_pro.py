"""
SAT PRO (Módulo 18, enriquecimiento). Añade SOLO lo ausente sobre el SAT/Helpdesk existente
(tickets/SLA/colas/intervenciones/KB/email/portal/analítica): ENCUESTAS DE SATISFACCIÓN (CSAT/NPS)
al cierre y BOLSA DE HORAS de contrato (consumo por intervención). Reutiliza tickets/Comunicaciones/
contratos existentes. Multiempresa, auditado. No duplica.
"""

import datetime as _dt
import logging
import secrets

logger = logging.getLogger("sat.pro")


def _emp(id_empresa=None):
    # IOC v2 (Bloque III): resolución de empresa vía capa de identidad (Strangler).
    try:
        from src.services.sat.identidad_sat import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)


def _audit(accion, detalle, tabla):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("sat", accion, tabla, (detalle or "")[:255])
    except Exception:
        pass


def _filas(cur):
    from src.db.conexion import _filas_a_dicts
    return _filas_a_dicts(cur, cur.fetchall())


# ── Encuestas de satisfacción (CSAT) ─────────────────────────────────────────
def enviar_encuesta(id_ticket, *, id_cliente=None, id_empresa=None) -> dict:
    """Genera y 'envía' (por Comunicaciones) una encuesta de satisfacción para un ticket cerrado."""
    emp = _emp(id_empresa)
    token = secrets.token_urlsafe(16)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO sat_encuestas (id_empresa, id_ticket, id_cliente, token, enviada, "
                        "fecha_envio) VALUES (%s,%s,%s,%s,1,NOW())", (emp, id_ticket, id_cliente, token))
            eid = cur.lastrowid
            c.commit()
        try:
            from src.services.comunicaciones import notificaciones
            notificaciones.emitir("sat_encuesta", "Valore su atención",
                                  f"Su incidencia #{id_ticket} ha sido resuelta. Valórenos (1-5).",
                                  prioridad="baja", modulo="sat", id_empresa=emp)
        except Exception:
            pass
        _audit("ENCUESTA_ENVIADA", f"{eid}:ticket{id_ticket}", "sat_encuestas")
        return {"ok": True, "id_encuesta": eid, "token": token}
    except Exception as e:
        logger.error("enviar_encuesta: %s", e)
        return {"ok": False, "motivo": str(e)}


def responder_encuesta(token, puntuacion, *, comentario=None, id_empresa=None) -> dict:
    if not (1 <= int(puntuacion) <= 5):
        return {"ok": False, "motivo": "puntuación fuera de rango (1-5)"}
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("UPDATE sat_encuestas SET puntuacion=%s, comentario=%s, respondida=1, "
                        "fecha_respuesta=NOW() WHERE token=%s AND respondida=0",
                        (int(puntuacion), (comentario or "")[:500], token))
            afectadas = cur.rowcount
            c.commit()
        _audit("ENCUESTA_RESPUESTA", f"token…{token[-6:]}={puntuacion}", "sat_encuestas")
        return {"ok": afectadas > 0}
    except Exception as e:
        logger.error("responder_encuesta: %s", e)
        return {"ok": False, "motivo": str(e)}


def csat(id_empresa=None, *, desde=None, hasta=None) -> dict:
    """CSAT medio (1-5), % de satisfechos (≥4) y nº de respuestas en el período."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            q = ("SELECT COUNT(*) AS n, COALESCE(AVG(puntuacion),0) AS media, "
                 "COALESCE(SUM(CASE WHEN puntuacion>=4 THEN 1 ELSE 0 END),0) AS satisfechos "
                 "FROM sat_encuestas WHERE id_empresa<=>%s AND respondida=1")
            p = [emp]
            if desde:
                q += " AND fecha_respuesta>=%s"; p.append(desde)
            if hasta:
                q += " AND fecha_respuesta<=%s"; p.append(hasta)
            cur.execute(q, p)
            r = _filas(cur)[0]
        n = int(r.get("n") or 0)
        return {"respuestas": n, "csat_medio": round(float(r.get("media") or 0), 2),
                "pct_satisfechos": round(float(r.get("satisfechos") or 0) / n * 100, 1) if n else None}
    except Exception as e:
        logger.error("csat: %s", e)
        return {"respuestas": 0, "csat_medio": 0}


# ── Bolsa de horas de contrato ───────────────────────────────────────────────
def crear_bolsa_horas(horas_totales, *, id_contrato=None, id_cliente=None, descripcion=None,
                      id_empresa=None) -> int | None:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO sat_bolsas_horas (id_empresa, id_contrato, id_cliente, descripcion, "
                        "horas_totales) VALUES (%s,%s,%s,%s,%s)",
                        (emp, id_contrato, id_cliente, descripcion, float(horas_totales or 0)))
            bid = cur.lastrowid
            c.commit()
        _audit("BOLSA_ALTA", f"{bid}:{horas_totales}h", "sat_bolsas_horas")
        return bid
    except Exception as e:
        logger.error("crear_bolsa_horas: %s", e)
        return None


def consumir_horas(id_bolsa, horas, *, id_ticket=None, concepto=None, id_empresa=None) -> dict:
    """Consume horas de la bolsa (típicamente desde una intervención). Avisa si el saldo es negativo
    o se agota; marca la bolsa no vigente al llegar a 0."""
    emp = _emp(id_empresa)
    horas = round(float(horas or 0), 2)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT horas_totales, horas_consumidas FROM sat_bolsas_horas WHERE id=%s "
                        "AND id_empresa<=>%s", (id_bolsa, emp))
            r = cur.fetchone()
            if not r:
                return {"ok": False, "motivo": "bolsa no existe"}
            r = r if not isinstance(r, dict) else list(r.values())
            totales, consumidas = float(r[0] or 0), float(r[1] or 0)
            nuevo = round(consumidas + horas, 2)
            cur.execute("INSERT INTO sat_consumo_horas (id_empresa, id_bolsa, id_ticket, horas, concepto, "
                        "fecha) VALUES (%s,%s,%s,%s,%s,%s)",
                        (emp, id_bolsa, id_ticket, horas, concepto, _dt.date.today().isoformat()))
            vigente = 0 if nuevo >= totales else 1
            cur.execute("UPDATE sat_bolsas_horas SET horas_consumidas=%s, vigente=%s WHERE id=%s",
                        (nuevo, vigente, id_bolsa))
            c.commit()
        saldo = round(totales - nuevo, 2)
        _audit("BOLSA_CONSUMO", f"bolsa{id_bolsa} -{horas}h saldo{saldo}", "sat_consumo_horas")
        return {"ok": True, "consumidas": nuevo, "saldo": saldo, "agotada": saldo <= 0}
    except Exception as e:
        logger.error("consumir_horas: %s", e)
        return {"ok": False, "motivo": str(e)}


def saldo_bolsa(id_bolsa, *, id_empresa=None) -> dict:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT horas_totales, horas_consumidas FROM sat_bolsas_horas WHERE id=%s "
                        "AND id_empresa<=>%s", (id_bolsa, emp))
            r = cur.fetchone()
            if not r:
                return {}
            r = r if not isinstance(r, dict) else list(r.values())
            return {"horas_totales": float(r[0] or 0), "horas_consumidas": float(r[1] or 0),
                    "saldo": round(float(r[0] or 0) - float(r[1] or 0), 2)}
    except Exception as e:
        logger.error("saldo_bolsa: %s", e)
        return {}
