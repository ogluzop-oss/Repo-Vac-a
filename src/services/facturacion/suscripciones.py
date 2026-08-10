"""
FASE 4.2/4.3 — Suscripciones COMERCIALES del cliente + cobros recurrentes.

Capa SaaS empresarial sobre la base de facturación: cada renovación genera (reutilizando el
motor) factura + vencimiento AR + (opcional) cobro/remesa recurrente. No duplica el sistema de
pagos ni el de tesorería: reutiliza facturas_cliente, vencimientos y remesas SEPA.
"""

import datetime as _dt
import logging

from src.services.facturacion import recurrente as _R

logger = logging.getLogger("facturacion.suscripciones")

MODOS = ("mensual", "anual", "consumo", "hibrido")


def _emp(id_empresa=None):
    # IOC v2 (Bloque III): resolución de empresa vía capa de identidad (Strangler).
    try:
        from src.services.facturacion.identidad_facturacion import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        from src.db.empresa import empresa_actual_id
        return id_empresa or empresa_actual_id()


def crear(id_cliente, plan, precio, *, frecuencia="mensual", modo="mensual", divisa=None,
          renovacion_automatica=True, fecha_inicio=None, fecha_fin=None, id_empresa=None) -> int | None:
    id_empresa = _emp(id_empresa)
    ini = fecha_inicio or _dt.date.today().isoformat()
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO cliente_suscripciones (id_empresa, id_cliente, plan, estado, "
                "fecha_inicio, fecha_fin, renovacion_automatica, precio, divisa, frecuencia, modo, "
                "proxima_renovacion) VALUES (%s,%s,%s,'activa',%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, id_cliente, plan, ini, fecha_fin, 1 if renovacion_automatica else 0,
                 round(float(precio or 0), 2), divisa, frecuencia, modo, ini))
            sid = cur.lastrowid
            conn.commit()
            return sid
    except Exception as e:
        logger.error("suscripciones.crear: %s", e); return None


def listar(id_empresa=None, estado=None) -> list:
    id_empresa = _emp(id_empresa)
    from src.db.conexion import _filas_a_dicts, obtener_conexion
    cond, params = ["id_empresa=%s"], [id_empresa]
    if estado:
        cond.append("estado=%s"); params.append(estado)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT * FROM cliente_suscripciones WHERE {' AND '.join(cond)} "
                        "ORDER BY proxima_renovacion", params)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("suscripciones.listar: %s", e); return []


def renovar_una(susc, id_empresa=None, domiciliar=False) -> dict:
    """Renueva UNA suscripción: genera factura + vencimiento AR (motor único) y, si se pide,
    deja el cobro listo para domiciliar (remesa SEPA). Devuelve {id_factura}."""
    id_empresa = _emp(id_empresa)
    from src.db import facturas_cliente as FC
    lineas = [{"descripcion": f"Suscripción {susc.get('plan') or ''}".strip(), "cantidad": 1,
               "precio_unitario": float(susc.get("precio") or 0),
               "subtotal": float(susc.get("precio") or 0)}]
    # Condiciones de pago aplazadas → crea vencimiento AR (crédito) automáticamente.
    fid = FC.crear_factura(id_cliente=susc.get("id_cliente"), lineas=lineas,
                           fecha_vencimiento=_dt.date.today().isoformat(), id_empresa=id_empresa)
    if not fid:
        return {"ok": False}
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE facturas_cliente SET origen='suscripcion', id_suscripcion=%s "
                        "WHERE id_factura=%s", (susc.get("id"), fid))
            conn.commit()
        FC.registrar_evento(fid, "FACTURA_SUSCRIPCION", detalle=str(susc.get("id")), id_empresa=id_empresa)
        FC.registrar_evento(fid, "RENOVACION_SUSCRIPCION", detalle=susc.get("plan"), id_empresa=id_empresa)
        if domiciliar:
            FC.registrar_evento(fid, "COBRO_RECURRENTE", id_empresa=id_empresa)
    except Exception:
        pass
    return {"ok": True, "id_factura": fid}


def renovar_pendientes(hoy=None, id_empresa=None) -> dict:
    """Renueva todas las suscripciones activas con renovación automática vencidas. Devuelve
    {renovadas, ids}. Avanza proxima_renovacion según la frecuencia."""
    id_empresa = _emp(id_empresa)
    hoy = _dt.date.fromisoformat(hoy) if isinstance(hoy, str) else (hoy or _dt.date.today())
    from src.db.conexion import obtener_conexion
    ids = []
    for s in listar(id_empresa, estado="activa"):
        if not int(s.get("renovacion_automatica") or 0):
            continue
        prox = s.get("proxima_renovacion")
        if isinstance(prox, str):
            try: prox = _dt.date.fromisoformat(prox[:10])
            except Exception: prox = None
        if not prox or prox > hoy:
            continue
        res = renovar_una(s, id_empresa)
        if res.get("ok"):
            ids.append(res["id_factura"])
            nueva = _R.avanzar(prox, s.get("frecuencia") or "mensual")
            try:
                with obtener_conexion() as conn, conn.cursor() as cur:
                    cur.execute("UPDATE cliente_suscripciones SET ultima_renovacion=%s, "
                                "proxima_renovacion=%s WHERE id=%s",
                                (prox.isoformat(), nueva.isoformat(), s.get("id")))
                    conn.commit()
            except Exception as e:
                logger.error("susc avanzar(%s): %s", s.get("id"), e)
    return {"renovadas": len(ids), "ids": ids}
