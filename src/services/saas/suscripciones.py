"""
Suscripciones SaaS + ciclo de facturación (FASE SAAS-D).

Gestiona alta/renovación/upgrade/downgrade/cancelación/suspensión/reactivación de la suscripción
de cada empresa, integrando el LicensingService (plan activo) y el BillingProvider (cobro).
Estados: prueba/activa/suspendida/cancelada/vencida. Audita cada evento.
"""

import datetime as _dt
import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, ensure_schema, obtener_conexion
from src.services.saas import licensing as _L
from src.services.saas import planes as _P
from src.services.saas.billing import base as _B

logger = logging.getLogger("saas.suscripciones")

CICLOS = {"mensual": 30, "trimestral": 90, "anual": 365}
ESTADOS = ("prueba", "activa", "suspendida", "cancelada", "vencida")

# Umbrales (días) para los avisos de vencimiento de la suscripción.
UMBRAL_AVISO = 15      # a partir de aquí se recuerda renovar
UMBRAL_URGENTE = 3     # a partir de aquí, urgente


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def crear(id_empresa, codigo_plan, *, ciclo="mensual", proveedor=None, prueba=True,
          dias_prueba=15) -> int | None:
    """Alta de suscripción. En prueba no cobra; activa el plan en la licencia."""
    id_empresa = _emp(id_empresa)
    codigo_plan = (codigo_plan or "BASIC").upper()
    if not _P.plan(codigo_plan):
        raise ValueError(f"plan inexistente: {codigo_plan}")
    hoy = _dt.date.today()
    estado = "prueba" if prueba else "activa"
    prox = hoy + _dt.timedelta(days=dias_prueba if prueba else CICLOS.get(ciclo, 30))
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO suscripciones (id_empresa, codigo_plan, ciclo, estado, "
                        "proveedor_pago, fecha_inicio, proximo_cobro) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (id_empresa, codigo_plan, ciclo, estado, proveedor, hoy, prox))
            sid = cur.lastrowid
            conn.commit()
        _L.asignar_plan(id_empresa, codigo_plan, estado="prueba" if prueba else "activa")
        if not prueba:
            _facturar_y_cobrar(id_empresa, sid, codigo_plan, ciclo, proveedor)
        _audit("LICENCIA_ACTIVADA", id_empresa, f"suscripcion={sid} {codigo_plan} {estado}")
        return sid
    except (ValueError, _L.LicenciaError):
        raise
    except Exception as e:
        logger.error("crear: %s", e)
        return None


def _suscripcion(id_empresa):
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM suscripciones WHERE id_empresa=%s ORDER BY id DESC LIMIT 1", (id_empresa,))
        r = cur.fetchone()
        return _fila(cur, r) if r else None


def _facturar_y_cobrar(id_empresa, sid, codigo_plan, ciclo, proveedor):
    cfg = _P.plan(codigo_plan)
    meses = {"mensual": 1, "trimestral": 3, "anual": 12}.get(ciclo, 1)
    importe = round(float(cfg["precio"]) * meses, 2)
    import uuid
    numero = "SAAS-" + uuid.uuid4().hex[:10].upper()
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO facturas_saas (id_empresa, id_suscripcion, numero, importe, estado, fecha) "
                    "VALUES (%s,%s,%s,%s,'emitida',%s)",
                    (id_empresa, sid, numero, importe, _dt.date.today()))
        fid = cur.lastrowid
        conn.commit()
    res = _B.proveedor(proveedor).cobrar(importe, referencia=numero)
    estado_pago = "pagado" if res.get("ok") else "fallido"
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO pagos_saas (id_empresa, id_factura, proveedor, importe, estado, "
                    "ref_externa, intentos) VALUES (%s,%s,%s,%s,%s,%s,1)",
                    (id_empresa, fid, res.get("proveedor"), importe, estado_pago, res.get("ref_externa")))
        if estado_pago == "pagado":
            cur.execute("UPDATE facturas_saas SET estado='pagada' WHERE id=%s", (fid,))
        conn.commit()
    _audit("PAGO_RECIBIDO" if estado_pago == "pagado" else "PAGO_FALLIDO", id_empresa,
           f"factura={numero} {importe}")
    return estado_pago


def renovar(id_empresa, *, proveedor=None) -> dict:
    id_empresa = _emp(id_empresa)
    s = _suscripcion(id_empresa)
    if not s:
        return {"ok": False, "error": "sin suscripción"}
    estado_pago = _facturar_y_cobrar(id_empresa, s["id"], s["codigo_plan"], s["ciclo"],
                                     proveedor or s.get("proveedor_pago"))
    nuevo_estado = "activa" if estado_pago == "pagado" else "suspendida"
    prox = _dt.date.today() + _dt.timedelta(days=CICLOS.get(s["ciclo"], 30))
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("UPDATE suscripciones SET estado=%s, proximo_cobro=%s WHERE id=%s",
                    (nuevo_estado, prox, s["id"]))
        conn.commit()
    _L.asignar_plan(id_empresa, s["codigo_plan"], estado="activa" if estado_pago == "pagado" else "suspendida")
    _audit("RENOVACION", id_empresa, f"{s['codigo_plan']} → {nuevo_estado}")
    return {"ok": estado_pago == "pagado", "estado": nuevo_estado}


def cambiar_plan(id_empresa, nuevo_plan) -> bool:
    """Upgrade o downgrade del plan."""
    id_empresa = _emp(id_empresa)
    s = _suscripcion(id_empresa)
    nuevo_plan = (nuevo_plan or "").upper()
    if not _P.plan(nuevo_plan):
        raise ValueError(f"plan inexistente: {nuevo_plan}")
    anterior = s["codigo_plan"] if s else "BASIC"
    orden = {"BASIC": 1, "PLUS": 2, "PRO": 3}
    evento = "UPGRADE" if orden.get(nuevo_plan, 0) > orden.get(anterior, 0) else "DOWNGRADE"
    with obtener_conexion() as conn, conn.cursor() as cur:
        if s:
            cur.execute("UPDATE suscripciones SET codigo_plan=%s WHERE id=%s", (nuevo_plan, s["id"]))
        conn.commit()
    _L.asignar_plan(id_empresa, nuevo_plan, estado="activa")
    _audit(evento, id_empresa, f"{anterior} → {nuevo_plan}")
    return True


def _set_estado(id_empresa, estado, lic_estado, evento):
    id_empresa = _emp(id_empresa)
    s = _suscripcion(id_empresa)
    if s:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE suscripciones SET estado=%s WHERE id=%s", (estado, s["id"]))
            conn.commit()
        _L.asignar_plan(id_empresa, s["codigo_plan"], estado=lic_estado)
    _audit(evento, id_empresa, estado)
    return True


def cancelar(id_empresa):
    return _set_estado(id_empresa, "cancelada", "cancelada", "EMPRESA_BLOQUEADA")


def suspender(id_empresa):
    return _set_estado(id_empresa, "suspendida", "suspendida", "LICENCIA_SUSPENDIDA")


def reactivar(id_empresa):
    return _set_estado(id_empresa, "activa", "activa", "EMPRESA_REACTIVADA")


def estado(id_empresa=None) -> dict | None:
    return _suscripcion(_emp(id_empresa))


# ── Avisos de vencimiento de la suscripción ──────────────────────────────────
def _a_fecha(v):
    """Normaliza date/datetime/str → date, o None."""
    if v is None:
        return None
    if hasattr(v, "date") and not isinstance(v, _dt.date):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    try:
        return _dt.date.fromisoformat(str(v)[:10])
    except Exception:
        return None


def dias_para_vencer(id_empresa=None):
    """Días hasta el próximo cobro/renovación de la suscripción (negativo si ya venció), o None."""
    s = _suscripcion(_emp(id_empresa))
    if not s:
        return None
    fin = _a_fecha(s.get("proximo_cobro"))
    if not fin:
        return None
    return (fin - _dt.date.today()).days


def aviso_vencimiento(id_empresa=None) -> dict | None:
    """Aviso si la suscripción vence pronto o ya venció. Devuelve {dias, fecha, nivel, mensaje} o None
    (nivel: 'aviso' | 'urgente' | 'vencida'). Solo aplica a suscripciones en prueba/activa."""
    s = _suscripcion(_emp(id_empresa))
    if not s or s.get("estado") not in ("prueba", "activa"):
        return None
    d = dias_para_vencer(id_empresa)
    if d is None:
        return None
    fecha = str(_a_fecha(s.get("proximo_cobro")))
    etiqueta = "período de prueba" if s.get("estado") == "prueba" else "suscripción"
    if d < 0:
        return {"dias": d, "fecha": fecha, "nivel": "vencida",
                "mensaje": f"Tu {etiqueta} venció hace {abs(d)} día(s) ({fecha}). Renueva para no "
                           f"perder el servicio."}
    if d <= UMBRAL_URGENTE:
        return {"dias": d, "fecha": fecha, "nivel": "urgente",
                "mensaje": f"Tu {etiqueta} vence en {d} día(s) ({fecha}). Renueva cuanto antes."}
    if d <= UMBRAL_AVISO:
        return {"dias": d, "fecha": fecha, "nivel": "aviso",
                "mensaje": f"Tu {etiqueta} vence en {d} día(s) ({fecha}). Recuerda renovar."}
    return None


def suscripciones_por_vencer(dias=UMBRAL_AVISO) -> list:
    """[(id_empresa, codigo_plan, estado, proximo_cobro, dias)] de suscripciones en prueba/activa que
    vencen en <= `dias` (o ya vencidas). Para el job de avisos y la vista del operador."""
    hoy = _dt.date.today()
    limite = (hoy + _dt.timedelta(days=int(dias))).isoformat()
    out = []
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_empresa, codigo_plan, estado, proximo_cobro FROM suscripciones "
                        "WHERE estado IN ('prueba','activa') AND proximo_cobro IS NOT NULL "
                        "AND proximo_cobro <= %s ORDER BY proximo_cobro", (limite,))
            for r in cur.fetchall():
                r = r if not isinstance(r, dict) else list(r.values())
                pc = _a_fecha(r[3])
                if not pc:
                    continue
                out.append((r[0], r[1], r[2], pc.isoformat(), (pc - hoy).days))
    except Exception as e:
        logger.error("suscripciones_por_vencer: %s", e)
    return out


def job_avisos_vencimiento(id_empresa=None) -> dict:
    """Job (opt-in): notifica a cada empresa cuya suscripción vence pronto o ya venció. Idempotente en el
    sentido de que reemite el estado actual; el sistema de notificaciones deduplica por contenido/fecha."""
    avisadas = 0
    for emp, plan, _est, fecha, d in suscripciones_por_vencer(UMBRAL_AVISO):
        try:
            from src.services import notificaciones
            if d < 0:
                tit = f"Suscripción vencida ({plan})"
                msg = f"Tu suscripción venció el {fecha}. Renueva para mantener el servicio."
                pr = "alta"
            elif d <= UMBRAL_URGENTE:
                tit = f"Suscripción vence en {d} día(s)"
                msg = f"Tu suscripción ({plan}) vence el {fecha}. Renueva cuanto antes."
                pr = "alta"
            else:
                tit = f"Suscripción vence en {d} día(s)"
                msg = f"Tu suscripción ({plan}) vence el {fecha}. Recuerda renovar."
                pr = "normal"
            notificaciones.emitir("saas_vencimiento", tit, msg, prioridad=pr, modulo="saas",
                                  roles=["ADMINISTRADOR", "GERENTE"], id_empresa=emp)
            avisadas += 1
        except Exception as e:
            logger.debug("aviso vencimiento empresa %s: %s", emp, e)
    return {"avisadas": avisadas}


def registrar_jobs_saas_avisos(id_empresa=None):
    """Registra el job de avisos de vencimiento (opt-in, diario) en el planificador."""
    try:
        from src.services import scheduler as S
        S.registrar("saas_avisos_vencimiento", lambda emp: f"avisos={job_avisos_vencimiento()}")
        S.registrar_job("saas_avisos_vencimiento", intervalo_horas=24,
                        descripcion="Avisos de vencimiento de suscripción SaaS", id_empresa=id_empresa)
    except Exception as e:
        logger.error("registrar_jobs_saas_avisos: %s", e)


def _audit(accion, id_empresa, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("saas", accion, "suscripciones", f"{id_empresa}: {detalle}")
    except Exception:
        pass
