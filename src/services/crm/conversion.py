"""
Conversión CRM → Factura.

Genera, a partir de una oportunidad, un documento comercial para su cliente con el valor de la oportunidad
como línea, y enlaza oportunidad↔documento (`crm_oportunidades.id_factura`). IDEMPOTENTE: si la oportunidad
ya tiene documento, lo devuelve sin crear otro. Reutiliza el motor de facturación existente
(`facturas_cliente.crear_factura`) — no hay motor de facturas paralelo (N7).

Por defecto genera una **PROFORMA** (documento comercial NO fiscal, revisable): convertir automáticamente
en una factura fiscal 'emitida' sería irreversible (numeración/Verifactu/asiento) y peligroso desde un botón
del CRM. La proforma se convierte después en factura real desde Facturación cuando el usuario lo decide.
El valor de la oportunidad se toma como TOTAL del documento (IVA incluido), coherente con la convención de
precios (PVP) del resto de la app: el motor de facturación extrae la base y la cuota según el perfil fiscal
del cliente/empresa.
"""

import logging

from src.db.conexion import log_auditoria, obtener_conexion

logger = logging.getLogger("crm.conversion")


def _emp(id_empresa=None):
    from src.services.crm.identidad_crm import empresa_id
    return empresa_id(id_empresa)


def _oportunidad(oid, eid):
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM crm_oportunidades WHERE id=%s AND id_empresa=%s", (oid, eid))
        r = cur.fetchone()
        if not r:
            return None
        return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def convertir_a_factura(id_oportunidad, id_empresa=None, tipo_documento="proforma"):
    """Crea (o recupera) el documento de facturación de una oportunidad. Por defecto una proforma.
    Devuelve {ok, id_factura, existente, tipo} o {ok:False, error}."""
    eid = _emp(id_empresa)
    op = _oportunidad(id_oportunidad, eid)
    if not op:
        return {"ok": False, "error": "oportunidad inexistente"}
    if op.get("id_factura"):
        return {"ok": True, "id_factura": op["id_factura"], "existente": True, "tipo": tipo_documento}
    if not op.get("id_cliente"):
        return {"ok": False, "error": "la oportunidad no tiene cliente asociado"}
    try:
        valor = round(float(op.get("valor") or 0), 2)
    except (TypeError, ValueError):
        valor = 0
    if valor <= 0:
        return {"ok": False, "error": "la oportunidad no tiene valor económico"}

    from src.db import facturas_cliente as FC
    fid = FC.crear_factura(
        id_cliente=op["id_cliente"], id_empresa=eid, tipo_documento=tipo_documento,
        lineas=[{"descripcion": op.get("titulo") or f"Oportunidad {id_oportunidad}",
                 "cantidad": 1, "precio_unitario": valor}])
    if not fid:
        return {"ok": False, "error": "no se pudo crear el documento"}

    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE crm_oportunidades SET id_factura=%s WHERE id=%s AND id_empresa=%s",
                        (fid, id_oportunidad, eid))
            conn.commit()
    except Exception as e:
        logger.error("enlazar oportunidad→documento: %s", e)

    log_auditoria("crm", "CRM_OPPORTUNITY_INVOICED", "crm_oportunidades",
                  f"op={id_oportunidad} doc={fid} tipo={tipo_documento} valor={valor}")
    return {"ok": True, "id_factura": fid, "existente": False, "tipo": tipo_documento}


def convertir_a_pedido_borrador(id_oportunidad, id_empresa=None, usuario=None):
    """Crea (o recupera) un PEDIDO DE CLIENTE en estado 'borrador' a partir de una oportunidad ganada,
    reutilizando el motor de ventas comercial YA EXISTENTE (`db.ventas_comercial.crear_pedido_cliente`
    — VTA.6, el mismo motor que la pestaña Presupuestos usa para "Convertir a Pedido"). IDEMPOTENTE vía
    `crm_oportunidades.id_pedido_borrador` (migración 0279), mismo patrón que `convertir_a_factura`/
    `convertir_a_proyecto`.

    LIMITACIÓN CONOCIDA Y DOCUMENTADA (no un descuido): `crm_oportunidades` no guarda detalle de
    líneas, solo un `valor` total — igual que ya asumía `convertir_a_factura`. El pedido nace con UNA
    línea genérica (descripción = título de la oportunidad, cantidad=1, precio_unitario=valor). Si en
    el futuro se necesitan líneas reales por artículo, habría que extender `crm_oportunidades`/
    `oportunidades.py` con una tabla de líneas propia — fuera de alcance aquí, no se inventa.

    NO reutiliza `services.compras.b2b_pedidos` (motor de APROVISIONAMIENTO Empresa←Proveedor vía
    sesión del Portal Proveedor — `token_sesion`/`id_suministrador`/carrito por proveedor): es la
    dirección opuesta a vender a un cliente propio desde el CRM, y no comparte ningún concepto
    reutilizable (ni cliente, ni líneas, ni sesión) con este caso."""
    eid = _emp(id_empresa)
    op = _oportunidad(id_oportunidad, eid)
    if not op:
        return {"ok": False, "error": "oportunidad inexistente"}
    if op.get("id_pedido_borrador"):
        return {"ok": True, "id_pedido": op["id_pedido_borrador"], "existente": True}
    if not op.get("id_cliente"):
        return {"ok": False, "error": "la oportunidad no tiene cliente asociado"}
    try:
        valor = round(float(op.get("valor") or 0), 2)
    except (TypeError, ValueError):
        valor = 0
    if valor <= 0:
        return {"ok": False, "error": "la oportunidad no tiene valor económico"}

    from src.db import ventas_comercial as VC
    # `codigo_articulo` es NOT NULL en `ventas_pedidos_cliente_lineas` — la oportunidad no referencia
    # ningún artículo real (no hay itemización, ver limitación arriba), así que se usa un código
    # SINTÉTICO pero honesto, estable por oportunidad (nunca inventa un artículo del catálogo real):
    # mismo criterio que el lote sintético `CONSIG-{id_tx}` de `services.compras.b2b_pedidos`.
    pid = VC.crear_pedido_cliente(
        id_cliente=op["id_cliente"],
        lineas=[{"codigo": f"CRM-OP-{id_oportunidad}",
                 "descripcion": op.get("titulo") or f"Oportunidad {id_oportunidad}",
                 "cantidad": 1, "precio_unitario": valor}],
        observaciones=f"Generado desde oportunidad CRM #{id_oportunidad}",
        usuario=usuario, id_empresa=eid)
    if not pid:
        return {"ok": False, "error": "no se pudo crear el pedido"}

    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE crm_oportunidades SET id_pedido_borrador=%s WHERE id=%s AND id_empresa=%s",
                        (pid, id_oportunidad, eid))
            conn.commit()
    except Exception as e:
        logger.error("enlazar oportunidad→pedido: %s", e)

    log_auditoria("crm", "CRM_OPPORTUNITY_ORDERED", "crm_oportunidades",
                  f"op={id_oportunidad} pedido={pid} valor={valor}")
    return {"ok": True, "id_pedido": pid, "existente": False}


def convertir_a_proyecto(id_oportunidad, id_empresa=None):
    """Crea (o recupera) el proyecto de una oportunidad, con su valor como presupuesto y su cliente.
    IDEMPOTENTE (enlace en `crm_oportunidades.id_proyecto`). Reutiliza `services.proyectos` (N7)."""
    eid = _emp(id_empresa)
    op = _oportunidad(id_oportunidad, eid)
    if not op:
        return {"ok": False, "error": "oportunidad inexistente"}
    if op.get("id_proyecto"):
        return {"ok": True, "id_proyecto": op["id_proyecto"], "existente": True}
    try:
        valor = round(float(op.get("valor") or 0), 2)
    except (TypeError, ValueError):
        valor = 0

    from src.services.proyectos import proyectos as PROY
    resp = op.get("responsable")
    pid = PROY.crear_proyecto(
        op.get("titulo") or f"Oportunidad {id_oportunidad}", id_empresa=eid,
        presupuesto=valor, id_cliente=op.get("id_cliente"),
        responsable=(str(resp) if resp is not None else None), estado="planificado")
    if not pid:
        return {"ok": False, "error": "no se pudo crear el proyecto"}

    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE crm_oportunidades SET id_proyecto=%s WHERE id=%s AND id_empresa=%s",
                        (pid, id_oportunidad, eid))
            conn.commit()
    except Exception as e:
        logger.error("enlazar oportunidad→proyecto: %s", e)

    log_auditoria("crm", "CRM_OPPORTUNITY_PROJECTED", "crm_oportunidades",
                  f"op={id_oportunidad} proyecto={pid} presupuesto={valor}")
    return {"ok": True, "id_proyecto": pid, "existente": False}
