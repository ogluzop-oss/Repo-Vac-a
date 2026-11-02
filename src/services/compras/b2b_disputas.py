"""
Puente de disputas B2B (Smart Suppliers · Fase D). Requisito 6 del prompt original: "Las
reclamaciones o solicitudes de reembolso fuera de plazo se deben tramitar obligatoriamente a través de
las pestañas 'Incidencias' o 'Devoluciones' (requiriendo mediación o aprobación del proveedor)."

NO crea un sistema de incidencias/devoluciones nuevo: usa las funciones YA EXISTENTES de
`src/db/compras.py` (`registrar_incidencia`/`crear_devolucion`, las mismas que respaldan hoy las
pestañas "Incidencias"/"Devoluciones" del módulo de Compras) y solo las conecta con la custodia de
fondos del pedido B2B — abrir una disputa bloquea la liberación automática
(`b2b_escrow.abrir_disputa`) hasta que se resuelva.
"""

import logging

logger = logging.getLogger("compras.b2b_disputas")


def _contexto_transaccion(id_tx):
    """(id_empresa, id_suministrador) de la transacción, o (None, None) si no existe."""
    from src.db.conexion import obtener_conexion
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id_empresa, id_suministrador FROM transaccion_comercial WHERE id_tx=%s",
                   (id_tx,))
        row = cur.fetchone()
    if not row:
        return None, None
    return (row if not isinstance(row, dict) else (row["id_empresa"], row["id_suministrador"]))


def _id_proveedor_de(id_empresa, id_suministrador) -> int | None:
    """Resuelve el `proveedores.id_proveedor` (registro POR EMPRESA) a partir del
    `id_suministrador` (identidad de plataforma, ver Fase A) — puente entre ambos mundos."""
    if not id_suministrador:
        return None
    from src.db.conexion import obtener_conexion
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id_proveedor FROM proveedores WHERE id_suministrador=%s AND id_empresa=%s "
                   "LIMIT 1", (id_suministrador, id_empresa))
        row = cur.fetchone()
    return (row[0] if not isinstance(row, dict) else row["id_proveedor"]) if row else None


def abrir_disputa(id_tx, motivo: str, *, usuario=None) -> dict:
    """Abre la disputa: bloquea la custodia de fondos del pedido (no se libera solo ni por
    expiración) Y registra la reclamación en Incidencias (la pestaña existente, no una nueva)."""
    id_empresa, id_suministrador = _contexto_transaccion(id_tx)
    if not id_empresa:
        return {"ok": False, "error": "transaccion_no_encontrada"}

    from src.services.compras import b2b_escrow as ESC
    r_escrow = ESC.abrir_disputa(id_tx, actor=usuario)
    if not r_escrow.get("ok"):
        return r_escrow

    id_proveedor = _id_proveedor_de(id_empresa, id_suministrador)
    id_incidencia = None
    try:
        from src.db import compras as C
        id_incidencia = C.registrar_incidencia(
            "otros", id_proveedor=id_proveedor,
            descripcion=f"[Pedido B2B {id_tx}] {motivo}"[:255], usuario=usuario, id_empresa=id_empresa)
    except Exception as e:
        logger.error("abrir_disputa registrar_incidencia(%s): %s", id_tx, e)
    return {"ok": True, "escrow": r_escrow, "id_incidencia": id_incidencia}


def _guardar_adjunto_rma(id_devolucion, id_empresa, usuario, file_storage, indice=0):
    """Guarda UNA foto de evidencia de un RMA autoservicio en el centro documental compartido
    (`db.documentos`) — MISMO patrón (escribir bytes a disco con hash + registrar) ya usado por
    `api/routers/losses.py::_guardar_foto_merma` para las fotos de mermas; no se inventa un
    mecanismo nuevo ni una tabla de adjuntos aparte. `referencia=f"DEVOLUCION:{id_devolucion}"`
    permite recuperar TODAS las fotos de un mismo RMA con `db.documentos.listar_documentos`."""
    import hashlib
    import os
    from datetime import datetime

    from src.db.documentos import registrar_documento
    from src.utils.recursos import ruta_datos

    nombre_original = getattr(file_storage, "filename", "") or ""
    ext = os.path.splitext(nombre_original)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".pdf"):
        ext = ".jpg"
    carpeta = ruta_datos("devoluciones")
    os.makedirs(carpeta, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
    ruta = os.path.join(carpeta, f"RMA_{id_devolucion}_{ts}_{indice}{ext}")
    datos = file_storage.read()
    if not datos:
        return None
    with open(ruta, "wb") as f:
        f.write(datos)
    h = hashlib.sha256(datos).hexdigest()
    return registrar_documento(
        ruta=ruta, tipo="devolucion", referencia=f"DEVOLUCION:{id_devolucion}",
        nombre=nombre_original or None, hash_documental=h, id_empresa=id_empresa, id_tienda=None,
        id_usuario=usuario)


# Límites de adjuntos del RMA de autoservicio — MISMA convención ya documentada y usada para los
# adjuntos de correo corporativo (`gui/correo_corporativo.py::_AdjuntosMultiplesWidget`): 10
# archivos / 25 MB en total. Reutilizar el número evita inventar un límite de producto distinto
# para un problema (adjuntar varios ficheros a un formulario) que ya se resolvió una vez.
MAX_ADJUNTOS_RMA = 10
MAX_BYTES_ADJUNTOS_RMA = 25 * 1024 * 1024


def solicitar_devolucion_autoservicio(id_tx, lineas: list, motivo: str, *, usuario=None,
                                      fotos=None) -> dict:
    """Autoservicio del comprador B2B: el comprador, desde el detalle de un pedido ya ENTREGADA
    (`portal_empresa_b2b.py::pagina_pedido_detalle`), solicita la devolución de líneas concretas.
    A diferencia de `tramitar_devolucion` (back-office/mediación, ejecución INMEDIATA de stock +
    reembolso), aquí la devolución nace en `estado='pendiente_aprobacion'`
    (`db.compras.crear_devolucion(estado_inicial=...)`) — el efecto de stock y el reembolso quedan
    DIFERIDOS hasta que el proveedor la apruebe (`aprobar_devolucion_autoservicio`) o la rechace
    (`db.compras.rechazar_devolucion`). `fotos`: lista de `FileStorage` (Flask) opcional, cada una
    se adjunta vía `db.documentos` (mismo patrón que la foto de evidencia de mermas)."""
    id_empresa, id_suministrador = _contexto_transaccion(id_tx)
    if not id_empresa:
        return {"ok": False, "error": "transaccion_no_encontrada"}
    id_proveedor = _id_proveedor_de(id_empresa, id_suministrador)
    if not id_proveedor:
        return {"ok": False, "error": "proveedor_no_resuelto"}

    from src.db import compras as C
    id_devolucion = C.crear_devolucion(
        id_proveedor=id_proveedor, lineas=lineas, motivo=motivo, usuario=usuario,
        id_empresa=id_empresa, estado_inicial="pendiente_aprobacion", id_tx=id_tx)
    if not id_devolucion:
        return {"ok": False, "error": "no_se_pudo_registrar_la_devolucion"}

    adjuntos = []
    for i, foto in enumerate(fotos or []):
        if not getattr(foto, "filename", None):
            continue
        try:
            id_doc = _guardar_adjunto_rma(id_devolucion, id_empresa, usuario, foto, indice=i)
            if id_doc:
                adjuntos.append(id_doc)
        except Exception as e:
            logger.warning("solicitar_devolucion_autoservicio foto #%s: %s", id_devolucion, e)
    return {"ok": True, "id_devolucion": id_devolucion, "adjuntos": adjuntos}


def listar_rma_pendientes_proveedor(id_suministrador) -> list:
    """Devoluciones RMA (autoservicio B2B, `estado='pendiente_aprobacion'`) pendientes de revisión
    para TODAS las empresas que compran a este proveedor (identidad de plataforma
    `id_suministrador`) — cada empresa tiene su propia fila de `proveedores`/`id_proveedor`, pero el
    pedido B2B comparte la MISMA identidad de suministrador, así que se localiza por JOIN contra
    `transaccion_comercial.id_tx` en vez de intentar resolver `id_proveedor` por empresa una a
    una."""
    from src.db.conexion import _filas_a_dicts, obtener_conexion
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT d.*, tc.id_suministrador FROM compras_devoluciones d "
                "JOIN transaccion_comercial tc ON tc.id_tx=d.id_tx "
                "WHERE d.estado='pendiente_aprobacion' AND tc.id_suministrador=%s "
                "ORDER BY d.fecha DESC", (id_suministrador,))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_rma_pendientes_proveedor(%s): %s", id_suministrador, e)
        return []


def rma_pertenece_a_suministrador(id_devolucion, id_suministrador, id_empresa=None) -> bool:
    """Verifica que el RMA es realmente de un pedido B2B de ESTE proveedor antes de dejarle
    aprobar/rechazar nada (el token de sesión del proveedor no basta por sí solo)."""
    from src.db.conexion import obtener_conexion
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cond = "d.id_devolucion=%s AND tc.id_suministrador=%s"
            params = [id_devolucion, id_suministrador]
            if id_empresa:
                cond += " AND d.id_empresa=%s"
                params.append(id_empresa)
            cur.execute(
                f"SELECT 1 FROM compras_devoluciones d JOIN transaccion_comercial tc "
                f"ON tc.id_tx=d.id_tx WHERE {cond} LIMIT 1", params)
            return cur.fetchone() is not None
    except Exception as e:
        logger.error("rma_pertenece_a_suministrador(%s): %s", id_devolucion, e)
        return False


def aprobar_devolucion_autoservicio(id_devolucion, *, id_suministrador, usuario=None) -> dict:
    """Autoriza el retorno de un RMA de autoservicio ("Autorizar Retorno", Portal Proveedor):
    1) aplica AHORA el efecto de stock diferido (`db.compras.aprobar_devolucion`);
    2) intenta el reembolso REAL vía escrow — reutiliza la MISMA rama de 3 casos que ya usa
       `tramitar_devolucion` (fondos aún retenidos → `cancelar_y_reembolsar`; disputa abierta →
       `resolver_disputa_con_reembolso`; fondos ya liberados al proveedor → conciliación manual,
       honesto, sin fingir un reembolso que no ocurrió — el comprador solicita el RMA sobre un
       pedido YA 'ENTREGADA', y `b2b_escrow.confirmar_entrega` SIEMPRE libera los fondos antes de
       marcar esa entrega, así que este último caso es el habitual en la práctica, no una rama
       muerta);
    3) genera la orden de recogida (`services.transporte.generar_orden_recogida`) — la mercancía
       física vuelve al proveedor independientemente de cómo se resuelva el reembolso."""
    from src.db import compras as C
    dev = C.obtener_devolucion(id_devolucion)
    if not dev:
        return {"ok": False, "error": "devolucion_no_encontrada"}
    if not rma_pertenece_a_suministrador(id_devolucion, id_suministrador, dev.get("id_empresa")):
        return {"ok": False, "error": "no_autorizado"}
    id_tx = dev.get("id_tx")
    id_empresa = dev.get("id_empresa")

    r_stock = C.aprobar_devolucion(id_devolucion, usuario=usuario, id_empresa=id_empresa)
    if not r_stock.get("ok"):
        return r_stock

    reembolso, conciliacion_manual, aviso = None, True, None
    try:
        from src.services.compras import b2b_escrow as ESC
        esc = ESC.estado(id_tx) or {}
        estado_pago = (esc.get("escrow") or {}).get("estado_pago")
        if estado_pago in ("FUNDS_HELD", "IN_FULFILLMENT"):
            reembolso = ESC.cancelar_y_reembolsar(id_tx, motivo=f"RMA aprobado #{id_devolucion}",
                                                  actor=usuario)
            conciliacion_manual = not reembolso.get("ok")
        elif estado_pago == "IN_DISPUTE":
            reembolso = ESC.resolver_disputa_con_reembolso(
                id_tx, motivo=f"RMA aprobado #{id_devolucion}", actor=usuario)
            conciliacion_manual = not reembolso.get("ok")
        else:
            aviso = ("Los fondos de este pedido ya se liberaron al proveedor (pedido entregado); "
                    "requiere conciliación manual del reembolso.")
    except Exception as e:
        logger.error("aprobar_devolucion_autoservicio reembolso #%s: %s", id_devolucion, e)
        aviso = str(e)

    id_recogida = None
    try:
        from src.services import transporte as T
        id_recogida = T.generar_orden_recogida(
            id_devolucion, id_proveedor=dev.get("id_proveedor"), id_tx=id_tx,
            id_empresa=id_empresa, usuario=usuario)
    except Exception as e:
        logger.error("aprobar_devolucion_autoservicio recogida #%s: %s", id_devolucion, e)

    return {"ok": True, "id_devolucion": id_devolucion, "reembolso": reembolso,
           "conciliacion_manual": conciliacion_manual, "aviso": aviso,
           "id_recogida": id_recogida}


def rechazar_devolucion_autoservicio(id_devolucion, motivo: str, *, id_suministrador,
                                     usuario=None) -> dict:
    """Rechaza un RMA de autoservicio ("Rechazar con alegación", Portal Proveedor): sin efecto de
    stock ni reembolso, solo registra la alegación del proveedor."""
    from src.db import compras as C
    dev = C.obtener_devolucion(id_devolucion)
    if not dev:
        return {"ok": False, "error": "devolucion_no_encontrada"}
    if not rma_pertenece_a_suministrador(id_devolucion, id_suministrador, dev.get("id_empresa")):
        return {"ok": False, "error": "no_autorizado"}
    ok = C.rechazar_devolucion(id_devolucion, motivo=motivo, usuario=usuario,
                               id_empresa=dev.get("id_empresa"))
    if not ok:
        return {"ok": False, "error": "no_se_pudo_rechazar (¿ya no está pendiente?)"}
    return {"ok": True, "id_devolucion": id_devolucion}


def tramitar_devolucion(id_tx, lineas: list, motivo: str, *, usuario=None) -> dict:
    """Procesa la devolución física al proveedor (descuenta stock, kárdex — reutiliza
    `db.compras.crear_devolucion` tal cual). El reembolso depende de dónde estén los fondos:
    - Aún retenidos sin disputa (FUNDS_HELD/IN_FULFILLMENT): se reembolsan directamente
      (`cancelar_y_reembolsar`, autoservicio).
    - Retenidos por una disputa abierta (IN_DISPUTE — ver `abrir_disputa`): se reembolsan vía
      resolución mediada (`resolver_disputa_con_reembolso`) — el dinero SIGUE en custodia, no se ha
      liberado, solo bloqueado hasta que se resuelva.
    - Ya liberados al proveedor (cualquier otro estado): el dinero ya salió de la custodia y NO hay
      reembolso automático posible desde aquí — se marca explícitamente para conciliación manual en
      vez de fingir un reembolso que no ha ocurrido."""
    id_empresa, id_suministrador = _contexto_transaccion(id_tx)
    if not id_empresa:
        return {"ok": False, "error": "transaccion_no_encontrada"}
    id_proveedor = _id_proveedor_de(id_empresa, id_suministrador)
    if not id_proveedor:
        return {"ok": False, "error": "proveedor_no_resuelto"}

    from src.db import compras as C
    id_devolucion = C.crear_devolucion(id_proveedor=id_proveedor, lineas=lineas, motivo=motivo,
                                       usuario=usuario, id_empresa=id_empresa)
    if not id_devolucion:
        return {"ok": False, "error": "no_se_pudo_registrar_la_devolucion"}

    from src.services.compras import b2b_escrow as ESC
    esc = ESC.estado(id_tx) or {}
    estado_pago = (esc.get("escrow") or {}).get("estado_pago")
    if estado_pago in ("FUNDS_HELD", "IN_FULFILLMENT"):
        r = ESC.cancelar_y_reembolsar(id_tx, motivo=f"Devolución: {motivo}", actor=usuario)
        return {"ok": True, "id_devolucion": id_devolucion, "reembolso": r, "conciliacion_manual": False}
    if estado_pago == "IN_DISPUTE":
        r = ESC.resolver_disputa_con_reembolso(id_tx, motivo=f"Devolución: {motivo}", actor=usuario)
        return {"ok": True, "id_devolucion": id_devolucion, "reembolso": r, "conciliacion_manual": False}
    return {"ok": True, "id_devolucion": id_devolucion, "reembolso": None, "conciliacion_manual": True,
           "aviso": "Los fondos ya se habían liberado al proveedor; requiere conciliación manual."}
