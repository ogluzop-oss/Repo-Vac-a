"""
FASE C — Credito y riesgo de cliente. Motor de scoring (0-100) sobre historico de pagos/retrasos/
impagados/facturacion + riesgo acumulado (saldo vivo vs limite). Alertas, bloqueo configurable y
aprobacion via Workflow. Reutiliza clientes (limite_credito/estado_crediticio) y vencimientos.
Explicable y auditado. Multiempresa.
"""

import logging
from src.db.conexion import log_auditoria, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("finanzas.credito")
NIVELES = ("bajo", "medio", "alto", "critico")


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _val(cur, default=0):
    r = cur.fetchone()
    if not r:
        return default
    return (list(r.values())[0] if isinstance(r, dict) else r[0]) or default


def _metricas_cliente(id_cliente, eid) -> dict:
    """Recopila metricas reales del cliente desde vencimientos/ventas."""
    m = {"vencimientos": 0, "vencidos": 0, "impagados": 0, "facturacion": 0.0, "saldo_pendiente": 0.0}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            # Vencimientos de cobro del cliente (tercero = nombre/identificador).
            cur.execute("SELECT COUNT(*), COALESCE(SUM(pendiente),0) FROM vencimientos WHERE id_empresa=%s "
                        "AND tipo='COBRO' AND tercero=(SELECT nombre FROM clientes WHERE id=%s)", (eid, id_cliente))
            r = cur.fetchone(); r = list(r.values()) if isinstance(r, dict) else r
            m["vencimientos"] = int(r[0] or 0); m["saldo_pendiente"] = float(r[1] or 0)
            cur.execute("SELECT COUNT(*) FROM vencimientos WHERE id_empresa=%s AND tipo='COBRO' "
                        "AND estado='VENCIDO' AND tercero=(SELECT nombre FROM clientes WHERE id=%s)",
                        (eid, id_cliente))
            m["vencidos"] = int(_val(cur))
            # Facturacion del cliente (ventas).
            cur.execute("SELECT COALESCE(SUM(total),0) FROM ventas WHERE id_empresa=%s AND cliente_id=%s",
                        (eid, id_cliente))
            m["facturacion"] = float(_val(cur))
    except Exception as e:
        logger.debug("_metricas_cliente: %s", e)
    m["impagados"] = m["vencidos"]
    return m


def calcular_score(id_cliente, *, persistir=True, id_empresa=None) -> dict:
    """Score 0-100 (mayor = mejor). Penaliza vencidos/impagados/saldo; premia facturacion. Explicable."""
    eid = _emp(id_empresa)
    m = _metricas_cliente(id_cliente, eid)
    score = 100
    desglose = []
    if m["vencidos"]:
        pen = min(40, m["vencidos"] * 10)
        score -= pen; desglose.append(f"-{pen} por {m['vencidos']} vencimientos vencidos")
    if m["saldo_pendiente"] > 0:
        # limite del cliente
        try:
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("SELECT COALESCE(limite_credito,0) FROM clientes WHERE id=%s", (id_cliente,))
                limite = float(_val(cur))
        except Exception:
            limite = 0
        if limite > 0 and m["saldo_pendiente"] > limite:
            score -= 25; desglose.append("-25 por saldo pendiente sobre el limite")
        elif m["saldo_pendiente"] > 0:
            score -= 5; desglose.append("-5 por saldo pendiente")
    if m["facturacion"] > 10000:
        score += 5; desglose.append("+5 por facturacion alta")
    score = max(0, min(100, score))
    nivel = "bajo" if score >= 75 else "medio" if score >= 50 else "alto" if score >= 25 else "critico"
    if persistir:
        try:
            import json
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("INSERT INTO credit_scoring (id_empresa, id_cliente, score, nivel, detalle) "
                            "VALUES (%s,%s,%s,%s,%s)", (eid, id_cliente, score, nivel, json.dumps(desglose)))
                cur.execute("UPDATE clientes SET riesgo_actual=%s WHERE id=%s", (nivel, id_cliente))
                conn.commit()
        except Exception as e:
            logger.error("persistir score: %s", e)
    log_auditoria("finanzas", "FIN_CREDIT_SCORE", "credit_scoring",
                  f"cliente={id_cliente} score={score} {nivel}")
    return {"id_cliente": id_cliente, "score": score, "nivel_riesgo": nivel,
            "metricas": m, "explicacion": desglose}


def evaluar_operacion(id_cliente, importe, *, bloqueo_automatico=True, usuario=None, id_empresa=None) -> dict:
    """Evalua una nueva operacion de venta: comprueba limite + bloqueos. Devuelve decision auditada.
    permitido/bloqueado/requiere_aprobacion. NO modifica la venta (lo consume ventas/TPV)."""
    eid = _emp(id_empresa)
    # Bloqueo manual activo?
    if bloqueo_activo(id_cliente, id_empresa=eid):
        _alerta(id_cliente, "bloqueo_activo", importe, eid)
        log_auditoria("finanzas", "FIN_CREDIT_DENEGADO", "bloqueos_credito", f"cliente={id_cliente} bloqueado")
        return {"decision": "bloqueado", "motivo": "cliente con bloqueo de credito activo"}
    m = _metricas_cliente(id_cliente, eid)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COALESCE(limite_credito,0) FROM clientes WHERE id=%s", (id_cliente,))
            limite = float(_val(cur))
    except Exception:
        limite = 0
    expuesto = m["saldo_pendiente"] + float(importe)
    if limite <= 0:
        return {"decision": "permitido", "motivo": "sin limite definido", "expuesto": round(expuesto, 2)}
    if expuesto <= limite:
        return {"decision": "permitido", "expuesto": round(expuesto, 2), "limite": limite}
    # Supera el limite -> alerta + (bloqueo o workflow)
    _alerta(id_cliente, "limite_superado", expuesto - limite, eid)
    if m["impagados"] > 0 and bloqueo_automatico:
        log_auditoria("finanzas", "FIN_CREDIT_DENEGADO", "alertas_credito",
                      f"cliente={id_cliente} expuesto={expuesto:.2f}>{limite}")
        return {"decision": "bloqueado", "motivo": "limite superado con impagados",
                "expuesto": round(expuesto, 2), "limite": limite}
    # Requiere aprobacion (workflow si disponible)
    _solicitar_aprobacion(id_cliente, expuesto, eid, usuario)
    log_auditoria("finanzas", "FIN_CREDIT_APROBACION", "alertas_credito",
                  f"cliente={id_cliente} expuesto={expuesto:.2f}")
    return {"decision": "requiere_aprobacion", "expuesto": round(expuesto, 2), "limite": limite}


def bloquear(id_cliente, *, motivo=None, usuario=None, id_empresa=None) -> int | None:
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO bloqueos_credito (id_empresa, id_cliente, motivo, creado_por) "
                        "VALUES (%s,%s,%s,%s)", (eid, id_cliente, motivo, usuario))
            bid = cur.lastrowid       # capturar antes del UPDATE (resetearia lastrowid)
            cur.execute("UPDATE clientes SET estado_crediticio='bloqueado' WHERE id=%s", (id_cliente,))
            conn.commit()
        log_auditoria("finanzas", "FIN_CREDIT_BLOQUEO", "bloqueos_credito", f"cliente={id_cliente}")
        return bid
    except Exception as e:
        logger.error("bloquear: %s", e)
        return None


def desbloquear(id_cliente, *, id_empresa=None) -> bool:
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE bloqueos_credito SET activo=0, liberado_en=NOW() WHERE id_empresa=%s "
                        "AND id_cliente=%s AND activo=1", (eid, id_cliente))
            cur.execute("UPDATE clientes SET estado_crediticio='normal' WHERE id=%s", (id_cliente,))
            conn.commit()
        log_auditoria("finanzas", "FIN_CREDIT_DESBLOQUEO", "bloqueos_credito", f"cliente={id_cliente}")
        return True
    except Exception as e:
        logger.error("desbloquear: %s", e)
        return False


def bloqueo_activo(id_cliente, *, id_empresa=None) -> bool:
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM bloqueos_credito WHERE id_empresa=%s AND id_cliente=%s AND activo=1",
                        (eid, id_cliente))
            return int(_val(cur)) > 0
    except Exception:
        return False


def listar_alertas(*, estado="abierta", id_empresa=None) -> list:
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            q = "SELECT * FROM alertas_credito WHERE id_empresa=%s"
            p = [eid]
            if estado:
                q += " AND estado=%s"; p.append(estado)
            q += " ORDER BY creado_en DESC LIMIT 500"
            cur.execute(q, p)
            return [(r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r)))
                    for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_alertas: %s", e)
        return []


def _alerta(id_cliente, tipo, importe, eid):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO alertas_credito (id_empresa, id_cliente, tipo, importe) "
                        "VALUES (%s,%s,%s,%s)", (eid, id_cliente, tipo, round(float(importe), 2)))
            conn.commit()
        from src.services import notificaciones
        notificaciones.emitir("credito", f"Alerta credito cliente {id_cliente}", tipo, modulo="finanzas",
                              prioridad="alta", roles=["GERENTE", "ADMINISTRADOR"], id_empresa=eid)
    except Exception as e:
        logger.debug("_alerta: %s", e)


def _solicitar_aprobacion(id_cliente, importe, eid, usuario):
    try:
        from src.services.workflow import workflow_engine
        workflow_engine.iniciar_proceso("credito", id_documento=f"CRED:{id_cliente}", importe=float(importe),
                                        solicitante=usuario, id_empresa=eid)
    except Exception as e:
        logger.debug("_solicitar_aprobacion (workflow opcional): %s", e)
