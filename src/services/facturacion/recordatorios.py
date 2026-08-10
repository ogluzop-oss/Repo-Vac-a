"""
Recordatorios de cobro (dunning de clientes).

Detecta facturas de cliente pendientes de cobro con vencimiento, calcula el NIVEL de escalado según los
días transcurridos desde el vencimiento y envía el recordatorio por el canal disponible (correo al cliente
vía el Centro de Notificaciones/CCP; degradable a 'simulado' si no hay correo). Registra cada envío en
`cobros_recordatorios` para NO duplicar (idempotente por factura+nivel) y auditar. `procesar()` es el
callable que ejecuta el scheduler a diario o el usuario a mano.

Reutiliza (N7): `facturas_cliente` como fuente de pendientes, `clientes.email` como destino, y
`ccp.notificaciones_centro.notificar` como transporte único (nunca un segundo sistema de envío).
"""

import datetime as _dt
import logging

from src.db.conexion import _filas_a_dicts, log_auditoria, obtener_conexion

logger = logging.getLogger("facturacion.recordatorios")

# Política de escalado. `dias` = offset respecto al vencimiento (negativo = antes; positivo = después).
NIVELES = [
    {"nivel": 0, "dias": -3, "etiqueta": "Aviso de vencimiento próximo"},
    {"nivel": 1, "dias": 1, "etiqueta": "Recordatorio de pago"},
    {"nivel": 2, "dias": 7, "etiqueta": "Segundo recordatorio de pago"},
    {"nivel": 3, "dias": 15, "etiqueta": "Reclamación de pago"},
]
_ESTADOS_PENDIENTE = ("emitida", "vencida", "impagada", "reclamada")
_TIPOS_FISCAL = ("factura", "simplificada", "rectificativa")


def _emp(id_empresa=None):
    if id_empresa is not None:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def pendientes(id_empresa=None):
    """Facturas fiscales con saldo pendiente (total-cobrado>0) y vencimiento, con nombre/email del cliente."""
    eid = _emp(id_empresa)
    em = ",".join(["%s"] * len(_ESTADOS_PENDIENTE))
    tm = ",".join(["%s"] * len(_TIPOS_FISCAL))
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT f.id_factura, f.serie, f.numero_serie, f.total, f.cobrado, f.fecha_vencimiento, "
                "f.id_cliente, c.nombre AS cliente_nombre, c.email AS cliente_email "
                "FROM facturas_cliente f LEFT JOIN clientes c ON c.id = f.id_cliente "
                "WHERE f.id_empresa=%s AND f.fecha_vencimiento IS NOT NULL "
                "AND COALESCE(f.total,0) - COALESCE(f.cobrado,0) > 0.005 "
                f"AND f.estado IN ({em}) AND f.tipo_documento IN ({tm})",
                (eid, *_ESTADOS_PENDIENTE, *_TIPOS_FISCAL))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("pendientes: %s", e)
        return []


def _dias_desde_venc(fecha_venc, ahora):
    if isinstance(fecha_venc, _dt.datetime):
        fv = fecha_venc.date()
    elif isinstance(fecha_venc, _dt.date):
        fv = fecha_venc
    else:
        try:
            fv = _dt.date.fromisoformat(str(fecha_venc)[:10])
        except Exception:
            return None
    return (ahora.date() - fv).days


def nivel_objetivo(dias):
    """Nivel MÁS ALTO cuyo offset ≤ días transcurridos desde el vencimiento (None si ninguno aplica)."""
    aplicables = [n for n in NIVELES if n["dias"] <= dias]
    return max(aplicables, key=lambda n: n["nivel"]) if aplicables else None


def _max_enviado(eid, id_factura):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COALESCE(MAX(nivel),-1) FROM cobros_recordatorios "
                        "WHERE id_empresa=%s AND id_factura=%s AND estado<>'error'", (eid, id_factura))
            r = cur.fetchone()
            return int(r[0]) if r and r[0] is not None else -1
    except Exception:
        return -1


def _registrar(eid, f, nivel_def, canal, destino, estado):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO cobros_recordatorios (id_empresa,id_factura,nivel,etiqueta,canal,"
                        "destino,estado) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (eid, f["id_factura"], nivel_def["nivel"], nivel_def["etiqueta"], canal, destino,
                         estado))
            conn.commit()
    except Exception as e:
        logger.error("_registrar: %s", e)


def _mensaje(f, nivel_def):
    ref = f"{f.get('serie') or ''}{f.get('numero_serie') or f['id_factura']}"
    pend = round(float(f.get("total") or 0) - float(f.get("cobrado") or 0), 2)
    venc = str(f.get("fecha_vencimiento"))[:10]
    titulo = f"{nivel_def['etiqueta']} — factura {ref}"
    cuerpo = (f"Estimado/a {f.get('cliente_nombre') or 'cliente'},\n\n"
              f"Le recordamos que la factura {ref}, con un importe pendiente de {pend:.2f} €, "
              f"tiene vencimiento el {venc}.\n"
              f"Le rogamos proceda a su pago. Si ya lo ha efectuado, disculpe este aviso.\n\n"
              f"Un saludo.")
    return titulo, cuerpo


def _enviar(eid, f, nivel_def):
    """Envía el recordatorio. Devuelve (canal, destino, estado). Degradable a 'simulado'."""
    titulo, cuerpo = _mensaje(f, nivel_def)
    email = (f.get("cliente_email") or "").strip()
    canal, destino, estado = "simulado", (email or "-"), "simulado"
    try:
        from src.services.ccp import notificaciones_centro as NC
        if email:
            res = NC.notificar(titulo, cuerpo, id_empresa=eid, destinatario=email,
                               contexto="cobros", tipo="cobro", prioridad="normal")
            if res and res.get("externa"):
                canal, destino, estado = "email", email, "enviado"
    except Exception as e:
        logger.debug("_enviar: %s", e)
        estado = "error"
    return canal, destino, estado


def procesar(id_empresa=None, ahora=None, enviar=True):
    """Procesa los recordatorios de cobro pendientes. Con `enviar=False` es una SIMULACIÓN (no envía ni
    registra). Devuelve {evaluadas, enviados, errores, por_nivel}."""
    eid = _emp(id_empresa)
    ahora = ahora or _dt.datetime.now()
    res = {"evaluadas": 0, "enviados": 0, "errores": 0, "por_nivel": {}}
    for f in pendientes(eid):
        res["evaluadas"] += 1
        dias = _dias_desde_venc(f.get("fecha_vencimiento"), ahora)
        if dias is None:
            continue
        obj = nivel_objetivo(dias)
        if not obj or obj["nivel"] <= _max_enviado(eid, f["id_factura"]):
            continue                                  # nada nuevo que enviar para esta factura
        if not enviar:
            res["enviados"] += 1
            res["por_nivel"][obj["nivel"]] = res["por_nivel"].get(obj["nivel"], 0) + 1
            continue
        canal, destino, estado = _enviar(eid, f, obj)
        _registrar(eid, f, obj, canal, destino, estado)
        if estado == "error":
            res["errores"] += 1
        else:
            res["enviados"] += 1
            res["por_nivel"][obj["nivel"]] = res["por_nivel"].get(obj["nivel"], 0) + 1
    log_auditoria("facturacion", "COBROS_RECORDATORIOS", "cobros_recordatorios",
                  f"eval={res['evaluadas']} env={res['enviados']} err={res['errores']}")
    return res


def resumen(id_empresa=None, ahora=None):
    """Vista para la GUI: por cada factura pendiente, su nivel actual, si toca enviar y el último enviado."""
    eid = _emp(id_empresa)
    ahora = ahora or _dt.datetime.now()
    out = []
    for f in pendientes(eid):
        dias = _dias_desde_venc(f.get("fecha_vencimiento"), ahora)
        obj = nivel_objetivo(dias) if dias is not None else None
        maxenv = _max_enviado(eid, f["id_factura"])
        pend = round(float(f.get("total") or 0) - float(f.get("cobrado") or 0), 2)
        ref = f"{f.get('serie') or ''}{f.get('numero_serie') or f['id_factura']}"
        out.append({"id_factura": f["id_factura"], "ref": ref, "cliente": f.get("cliente_nombre"),
                    "vence": str(f.get("fecha_vencimiento"))[:10], "pendiente": pend, "dias": dias,
                    "nivel_actual": obj["etiqueta"] if obj else "—",
                    "pendiente_envio": bool(obj and obj["nivel"] > maxenv),
                    "ultimo_nivel": maxenv})
    return out


def historial(id_factura, id_empresa=None):
    eid = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM cobros_recordatorios WHERE id_empresa=%s AND id_factura=%s "
                        "ORDER BY fecha", (eid, id_factura))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("historial: %s", e)
        return []
