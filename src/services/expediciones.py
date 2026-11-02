"""
Expediciones / Distribución mayorista B2B (R8·it3) — FUNCIÓN BASE (no una edición): ORQUESTA la cadena
que YA existe (nombre `expediciones` para no chocar con el paquete `services/distribucion`, que es el motor
de sincronización de datos entre terminales):

    pedido de cliente  →  preparación (picking WMS)  →  expedición  →  salida de stock OFICIAL

Reutiliza íntegramente los motores existentes (N7 — cero lógica de pedido/stock/documento paralela):
  · `db/ventas_comercial`  — pedido de cliente + conversión a venta (dispara la salida de stock oficial).
  · `services/inventario/almacen_pro` + `picking_ruta` — picking y ruta óptima de picking.
  · `services/logistica/logistica_pro` — expediciones y transportistas.
  · `services/comercio_digital/comercial` — tarifa mayorista (`cd_precios_lista`, lista="mayorista").

Multi-tenant por `id_empresa` (la conversión a venta usa el contexto de empresa activo, como el TPV).
"""

import logging

logger = logging.getLogger("expediciones")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def precio_mayorista(codigo, id_empresa=None):
    """Precio de la tarifa 'mayorista' para el artículo, o None si no hay (→ se usa el precio base)."""
    try:
        from src.services.comercio_digital.comercial import precio_de_lista
        return precio_de_lista(codigo, lista="mayorista", id_empresa=_emp(id_empresa))
    except Exception:
        return None


# ── Pedido mayorista ──────────────────────────────────────────────────────────
def crear_pedido(id_cliente, lineas, observaciones=None, id_empresa=None, usuario=None) -> int | None:
    """Crea un pedido de cliente reutilizando `ventas_comercial.crear_pedido_cliente`. Por cada línea, si
    no se aporta precio se resuelve la TARIFA MAYORISTA (o el precio base). `lineas=[{codigo, cantidad,
    precio?}]`."""
    emp = _emp(id_empresa)
    try:
        from src.db import ventas_comercial as VC
    except Exception as e:
        logger.error("crear_pedido import: %s", e)
        return None
    lns = []
    for l in (lineas or []):
        cod = (l.get("codigo") or l.get("codigo_articulo") or "").strip()
        if not cod:
            continue
        precio = l.get("precio") if l.get("precio") is not None else l.get("precio_unitario")
        if precio in (None, "", 0):
            precio = precio_mayorista(cod, emp) or _precio_base(cod, emp) or 0
        lns.append({"codigo": cod, "descripcion": l.get("descripcion"),
                    "cantidad": int(l.get("cantidad") or 0), "precio_unitario": round(float(precio or 0), 2)})
    if not lns:
        return None
    try:
        return VC.crear_pedido_cliente(id_cliente=id_cliente, lineas=lns, observaciones=observaciones,
                                       usuario=usuario, id_empresa=emp)
    except Exception as e:
        logger.error("crear_pedido: %s", e)
        return None


def _precio_base(codigo, id_empresa):
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT precio FROM articulos WHERE codigo=%s AND id_empresa=%s", (codigo, id_empresa))
            r = cur.fetchone()
            if r:
                return float((r[0] if not isinstance(r, dict) else r.get("precio")) or 0)
    except Exception:
        pass
    return 0.0


# ── Preparación (picking WMS) ─────────────────────────────────────────────────
def preparar(id_pedido, responsable=None, id_empresa=None) -> int | None:
    """Crea un PICKING para el pedido (reutiliza `almacen_pro.crear_picking`, origen='pedido')."""
    emp = _emp(id_empresa)
    try:
        from src.db import ventas_comercial as VC
        from src.services.inventario import almacen_pro as AP
    except Exception as e:
        logger.error("preparar import: %s", e)
        return None
    ped = VC.obtener_pedido_cliente(id_pedido, id_empresa=emp)
    if not ped:
        return None
    lineas = [{"codigo": l.get("codigo_articulo"), "cantidad": int(l.get("cantidad") or 0)}
              for l in ped.get("lineas", []) if l.get("codigo_articulo")]
    if not lineas:
        return None
    try:
        return AP.crear_picking(lineas, referencia=f"pedido:{id_pedido}", origen="pedido",
                                id_documento=id_pedido, responsable=responsable, id_empresa=emp)
    except Exception as e:
        logger.error("preparar: %s", e)
        return None


def ruta_optima(id_picking, id_empresa=None):
    """Ruta óptima de picking (serpentín) del picking (reutiliza `picking_ruta.ruta_picking`)."""
    try:
        from src.services.inventario.picking_ruta import ruta_picking
        return ruta_picking(id_picking, id_empresa=_emp(id_empresa))
    except Exception as e:
        logger.error("ruta_optima: %s", e)
        return ([], {})


# ── Expedición (salida de stock OFICIAL + registro de envío) ──────────────────
def expedir(id_pedido, id_transportista=None, direccion=None, id_empresa=None, usuario=None) -> dict:
    """Expide el pedido: convierte a VENTA (salida de stock OFICIAL vía `convertir_a_venta`, protegida
    contra doble conversión) y registra la EXPEDICIÓN (`logistica_pro.crear_expedicion`)."""
    emp = _emp(id_empresa)
    try:
        from src.db import ventas_comercial as VC
    except Exception as e:
        return {"ok": False, "error": str(e)}
    venta_id = VC.convertir_a_venta(id_pedido, usuario=usuario, id_empresa=emp)
    if not venta_id:
        return {"ok": False, "error": "El pedido no se pudo expedir (inexistente, ya convertido o cancelado)."}
    exp_id = None
    try:
        from src.services.logistica import logistica_pro as LP
        exp_id = LP.crear_expedicion(referencia=f"pedido:{id_pedido}", id_transportista=id_transportista,
                                     origen="pedido", id_documento=id_pedido, direccion=direccion, id_empresa=emp)
    except Exception as e:
        logger.error("expedir/expedicion: %s", e)
    return {"ok": True, "venta_id": venta_id, "expedicion_id": exp_id}


# ── Listados / transportistas (passthrough) ───────────────────────────────────
def listar_pedidos(id_empresa=None, estado=None) -> list:
    try:
        from src.db import ventas_comercial as VC
        return VC.listar("pedidos_cliente", id_empresa=_emp(id_empresa), estado=estado)
    except Exception as e:
        logger.error("listar_pedidos: %s", e)
        return []


def listar_transportistas(id_empresa=None) -> list:
    try:
        from src.services.logistica import logistica_pro as LP
        return LP.transportistas(id_empresa=_emp(id_empresa))
    except Exception as e:
        logger.error("listar_transportistas: %s", e)
        return []


def crear_transportista(nombre, contacto=None, telefono=None, id_empresa=None) -> int | None:
    try:
        from src.services.logistica import logistica_pro as LP
        return LP.crear_transportista(nombre, contacto=contacto, telefono=telefono, id_empresa=_emp(id_empresa))
    except Exception as e:
        logger.error("crear_transportista: %s", e)
        return None


# ── Seguimiento post-expedición (passthrough) ──────────────────────────────────
def listar_expediciones(id_empresa=None, estado=None) -> list:
    try:
        from src.services.logistica import logistica_pro as LP
        return LP.expediciones(id_empresa=_emp(id_empresa), estado=estado)
    except Exception as e:
        logger.error("listar_expediciones: %s", e)
        return []


def actualizar_seguimiento(id_expedicion, estado=None, tracking=None, id_empresa=None) -> dict:
    try:
        from src.services.logistica import logistica_pro as LP
        return LP.actualizar_seguimiento(id_expedicion, estado=estado, tracking=tracking,
                                         id_empresa=_emp(id_empresa))
    except Exception as e:
        logger.error("actualizar_seguimiento: %s", e)
        return {"ok": False, "motivo": str(e)}


def registrar_incidencia_expedicion(id_expedicion, descripcion, id_empresa=None) -> dict:
    try:
        from src.services.logistica import logistica_pro as LP
        return LP.registrar_incidencia_expedicion(id_expedicion, descripcion, id_empresa=_emp(id_empresa))
    except Exception as e:
        logger.error("registrar_incidencia_expedicion: %s", e)
        return {"ok": False, "motivo": str(e)}


def coste_logistico(id_empresa=None, desde=None, hasta=None) -> float:
    try:
        from src.services.logistica import logistica_pro as LP
        return LP.coste_logistico(id_empresa=_emp(id_empresa), desde=desde, hasta=hasta)
    except Exception as e:
        logger.error("coste_logistico: %s", e)
        return 0.0


# ── Cross-Docking (Landed Cost/Consignación/Cross-Docking, Fase D) ────────────
# Agregación de demanda de salida PENDIENTE, unificando las tres fuentes dispares que hoy existen en
# la app — no había ninguna consulta que las combinara. Se usa desde `gui/recepcion_pale.py` en el
# momento de la recepción (traspaso interno Y B2B) para avisar si lo que se acaba de recibir coincide
# con un pedido de salida ya esperando ese artículo.
def _almacen_para_tienda(id_tienda, id_empresa):
    """Resuelve un almacén de destino a partir de una tienda (o el central si no hay tienda/almacén
    de tienda). Mismo criterio que ya usan `b2b_pedidos.recibir_mercancia`/`online_orders_service.
    _descontar_stock_pedido` para localizar el almacén real de una tienda."""
    try:
        from src.db import stock_almacen as SA
        alm = None
        if id_tienda is not None:
            try:
                alm = SA.almacen_de_tienda(id_tienda, id_empresa=id_empresa)
            except Exception:
                alm = None
        return alm or SA.almacen_central(id_empresa)
    except Exception:
        return None


def demanda_pendiente_por_articulo(id_empresa, codigos=None) -> dict:
    """Demanda de salida PENDIENTE por artículo, unificando TRES fuentes dispares (no existía ninguna
    consulta que las combinara):

    1. `pedidos_cliente` (`db.ventas_comercial`, tabla `ventas_pedidos_cliente`): líneas de pedidos que
       no han sido convertidos a venta ni cancelados (`estado NOT IN ('convertido','cancelado')` — el
       único otro estado real de este doc type es 'borrador'; no hay seguimiento de cumplimiento
       parcial por línea, así que la cantidad pendiente es la cantidad íntegra de la línea).
    2. `pedidos_online` (`services.tpv.online_orders_service`, tabla `pedidos_online`/`_items`): líneas
       de pedidos en estado PENDIENTE|PAGADO|PREPARANDO Y con `stock_descontado=0` (un pedido con el
       stock ya descontado —vía `_descontar_stock_pedido`— ya no es demanda pendiente real, aunque su
       estado siga siendo uno de los tres; evita ofrecer cross-docking sobre algo que ya tiene stock
       asignado).
    3. `transaccion_comercial` — lado VENDEDOR de un pedido B2B (`origen='b2b'`, `id_suministrador IS
       NULL`, `id_empresa=<esta empresa>`, línea con `estado_linea='pendiente'`), DISTINTO del lado
       comprador ya usado en el resto de este plan (`b2b_pedidos.py`, donde `id_empresa` es quien
       COMPRA e `id_suministrador` — siempre externo a esta plataforma— es quien vende). Investigado a
       fondo: hoy NINGÚN punto del código crea una `transaccion_comercial` con `origen='b2b'` e
       `id_empresa` en el lado vendedor (los dos únicos creadores, `b2b_pedidos.tramitar`/`b2b_rfq`,
       siempre fijan `id_suministrador` — comprador). La consulta queda correcta y lista (forward-
       compatible, mismo criterio "degradar honesto" que el resto de la app) para cuando exista un
       punto de venta B2B propio (p. ej. `checkout.confirmar(origen="b2b", ...)`, hoy sin llamador con
       ese origen); mientras tanto devuelve honestamente vacío, no inventa datos.

    Devuelve ``{codigo_articulo: [{fuente, id_pedido_o_tx, cantidad_pendiente, id_almacen_destino},
    ...]}`` — la lista de cada artículo viene ordenada de más antigua a más reciente (mismo criterio
    FEFO de "la demanda más antigua se sirve primero" que ya usa el resto de la app). ``codigos``
    (opcional) filtra a esa lista de códigos — usado por la recepción para acotar la consulta a las
    líneas del documento escaneado."""
    id_empresa = _emp(id_empresa)
    if not id_empresa:
        return {}
    codigos_filtro = None
    if codigos:
        codigos_filtro = {str(c).strip().upper() for c in codigos if str(c or "").strip()}
        if not codigos_filtro:
            return {}

    filas = []  # (fecha, codigo, fuente, id_pedido_o_tx, cantidad, id_almacen_destino)
    try:
        from src.db.conexion import obtener_conexion
    except Exception as e:
        logger.error("demanda_pendiente_por_articulo: %s", e)
        return {}

    # ── 1) pedidos_cliente (ventas_pedidos_cliente) ──────────────────────────
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT p.id, p.id_tienda, p.fecha, l.codigo_articulo, l.cantidad "
                "FROM ventas_pedidos_cliente_lineas l "
                "JOIN ventas_pedidos_cliente p ON p.id = l.id_doc "
                "WHERE p.id_empresa=%s AND p.estado NOT IN ('convertido','cancelado') "
                "ORDER BY p.fecha ASC", (id_empresa,))
            for r in cur.fetchall():
                r = r if isinstance(r, dict) else dict(zip(
                    ("id", "id_tienda", "fecha", "codigo_articulo", "cantidad"), r))
                cod = str(r.get("codigo_articulo") or "").strip().upper()
                cant = int(r.get("cantidad") or 0)
                if not cod or cant <= 0:
                    continue
                if codigos_filtro and cod not in codigos_filtro:
                    continue
                alm = _almacen_para_tienda(r.get("id_tienda"), id_empresa)
                filas.append((r.get("fecha"), cod, "pedidos_cliente", r.get("id"), cant, alm))
    except Exception as e:
        logger.error("demanda_pendiente_por_articulo(pedidos_cliente): %s", e)

    # ── 2) pedidos_online ─────────────────────────────────────────────────────
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT po.id_pedido, po.id_tienda, po.fecha, i.codigo_articulo, i.cantidad, "
                "i.id_almacen "
                "FROM pedidos_online_items i "
                "JOIN pedidos_online po ON po.id_pedido = i.id_pedido "
                "WHERE po.id_empresa=%s AND po.estado IN ('PENDIENTE','PAGADO','PREPARANDO') "
                "AND COALESCE(po.stock_descontado,0)=0 "
                "ORDER BY po.fecha ASC", (id_empresa,))
            for r in cur.fetchall():
                r = r if isinstance(r, dict) else dict(zip(
                    ("id_pedido", "id_tienda", "fecha", "codigo_articulo", "cantidad",
                     "id_almacen"), r))
                cod = str(r.get("codigo_articulo") or "").strip().upper()
                cant = int(r.get("cantidad") or 0)
                if not cod or cant <= 0:
                    continue
                if codigos_filtro and cod not in codigos_filtro:
                    continue
                alm = r.get("id_almacen") or _almacen_para_tienda(r.get("id_tienda"), id_empresa)
                filas.append((r.get("fecha"), cod, "pedidos_online", r.get("id_pedido"), cant, alm))
    except Exception as e:
        logger.error("demanda_pendiente_por_articulo(pedidos_online): %s", e)

    # ── 3) transaccion_comercial — lado VENDEDOR de un pedido B2B ────────────
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT t.id_tx, t.id_tienda, t.creada, l.codigo_articulo, l.cantidad "
                "FROM transaccion_lineas l "
                "JOIN transaccion_comercial t ON t.id_tx = l.id_tx "
                "WHERE t.id_empresa=%s AND t.origen='b2b' AND t.id_suministrador IS NULL "
                "AND t.estado IN ('BORRADOR','CONFIRMADA','PAGADA','PREPARANDO') "
                "AND COALESCE(l.estado_linea,'pendiente')='pendiente' "
                "ORDER BY t.creada ASC", (id_empresa,))
            for r in cur.fetchall():
                r = r if isinstance(r, dict) else dict(zip(
                    ("id_tx", "id_tienda", "creada", "codigo_articulo", "cantidad"), r))
                cod = str(r.get("codigo_articulo") or "").strip().upper()
                cant = int(r.get("cantidad") or 0)
                if not cod or cant <= 0:
                    continue
                if codigos_filtro and cod not in codigos_filtro:
                    continue
                alm = _almacen_para_tienda(r.get("id_tienda"), id_empresa)
                filas.append((r.get("creada"), cod, "b2b_venta", r.get("id_tx"), cant, alm))
    except Exception as e:
        logger.error("demanda_pendiente_por_articulo(transaccion_comercial): %s", e)

    filas.sort(key=lambda f: (f[0] is None, f[0]))
    out: dict = {}
    for _fecha, cod, fuente, id_ref, cant, alm in filas:
        out.setdefault(cod, []).append({
            "fuente": fuente, "id_pedido_o_tx": id_ref, "cantidad_pendiente": cant,
            "id_almacen_destino": alm,
        })
    return out


def aplicar_cross_docking(codigo, cantidad, entry, *, almacen_recepcion, id_empresa=None,
                          usuario=None, id_documento=None) -> dict:
    """Ejecuta el Cross-Docking (Fase D) para una línea de recepción que coincide con demanda de
    salida pendiente (`entry`, una entrada de `demanda_pendiente_por_articulo`). Secuencia (plan
    aprobado, sin estado de lote nuevo): `traspasar_stock(tipo_kardex="CROSS_DOCKING")` (muelle de
    recepción → almacén de la demanda coincidente) → `lotes.registrar_entrada` (lote sintético,
    permanencia cero) → INMEDIATAMENTE `lotes.consumir_fefo(...)` contra el pedido de salida
    coincidente → transición del pedido/línea coincidente a su equivalente de "Listo para Despacho",
    vía la función que YA posee cada módulo origen (nunca se inventa un mecanismo nuevo):

      · `pedidos_online`  → `online_orders_service.cambiar_estado(id_pedido, "PREPARANDO")` (el
        vocabulario de estados de este doc type no tiene un "Listo para Despacho" literal; PREPARANDO
        es su equivalente real más próximo) + `marcar_stock_descontado` (idempotencia: evita que
        `_on_pagado` vuelva a descontar esta misma cantidad más tarde).
      · `transaccion_comercial` (lado vendedor B2B) → se marca la LÍNEA coincidente
        (`transaccion_lineas.estado_linea='cross_docking'`) y, best-effort, `transacciones.
        transicionar(..., "PREPARANDO")` a nivel de cabecera.
      · `pedidos_cliente` → NO soportado en esta iteración (ver motivo abajo): se devuelve
        ``{"ok": False, "error": "pedidos_cliente_sin_transicion_segura"}`` sin tocar stock.

    Por qué `pedidos_cliente` queda fuera: este doc type (`ventas_comercial`) SOLO tiene una vía de
    cumplimiento — `convertir_a_venta()`, que vuelve a consumir stock ÍNTEGRO de TODAS sus líneas vía
    `registrar_venta_con_items` — y ningún seguimiento de cumplimiento parcial por línea (solo el flag
    booleano `reservado`, ya fijado desde la creación). Ejecutar aquí el consumo FEFO y, más tarde,
    dejar que `convertir_a_venta()` vuelva a consumirlo íntegro sería un doble consumo real de stock.
    No existe ningún mecanismo existente de cumplimiento parcial que reutilizar sin tocar ese motor
    (fuera de alcance) — se prioriza NUNCA introducir esa regresión antes que ofrecer la ejecución
    también para esta fuente; queda documentado para una decisión de producto explícita."""
    id_empresa = _emp(id_empresa)
    codigo = str(codigo or "").strip().upper()
    cantidad = int(cantidad or 0)
    fuente = (entry or {}).get("fuente")
    id_ref = (entry or {}).get("id_pedido_o_tx")
    almacen_expedicion = (entry or {}).get("id_almacen_destino")
    if not codigo or cantidad <= 0 or not entry or not almacen_recepcion:
        return {"ok": False, "error": "datos_incompletos"}
    if fuente == "pedidos_cliente":
        logger.info("aplicar_cross_docking: pedidos_cliente %s sin transición segura (ver docstring)",
                   id_ref)
        return {"ok": False, "error": "pedidos_cliente_sin_transicion_segura"}
    if fuente not in ("pedidos_online", "b2b_venta"):
        return {"ok": False, "error": "fuente_desconocida"}
    if not almacen_expedicion:
        return {"ok": False, "error": "sin_almacen_destino"}

    from src.db import stock_almacen as SA
    from src.db import lotes as L
    import uuid

    # Saneado defensivo (motor legacy de traspasos internos, `db.logistica.procesar_recepcion_
    # logistica`): ese motor actualiza `articulos.Stock_total/Stock_tienda` directamente y NUNCA
    # escribe en el ledger por almacén `stock_almacen` — así que el almacén de recepción puede no
    # tener fila (o tenerla desfasada) en `stock_almacen` justo tras una recepción de traspaso interno.
    # `traspasar_stock` opera SOLO sobre `stock_almacen`; sin este saneado el traspaso muelle a muelle
    # podría dejar el ledger en negativo pese a que el stock físico (cache `articulos`) sí es correcto.
    # Se completa ÚNICAMENTE el déficit exacto que este cross-dock necesita mover — no se toca nada
    # del resto del saldo, y en la vía B2B (que sí mantiene `stock_almacen` al día) esto no hace nada.
    try:
        detalle = SA.obtener_stock_articulo(codigo, id_empresa).get("detalle", [])
        actual = 0
        for d in detalle:
            if int(d.get("id_almacen") or 0) == int(almacen_recepcion):
                actual = int(d.get("cantidad") or 0)
                break
        if actual < cantidad:
            SA.incrementar_stock(codigo, almacen_recepcion, cantidad - actual, id_empresa=id_empresa)
    except Exception as e:
        logger.warning("aplicar_cross_docking: saneado stock_almacen(%s): %s", codigo, e)

    if int(almacen_recepcion) != int(almacen_expedicion):
        ok_traspaso = SA.traspasar_stock(codigo, almacen_recepcion, almacen_expedicion, cantidad,
                                         id_empresa=id_empresa, id_documento=id_documento,
                                         usuario=usuario, tipo_kardex="CROSS_DOCKING")
        if not ok_traspaso:
            return {"ok": False, "error": "traspaso_fallido"}

    lote_xdock = f"XDOCK-{uuid.uuid4().hex[:10].upper()}"
    id_lote = L.registrar_entrada(codigo, lote_xdock, cantidad, id_empresa=id_empresa,
                                  id_almacen=almacen_expedicion, origen="cross_docking",
                                  id_documento=id_documento, usuario=usuario)
    if not id_lote:
        return {"ok": False, "error": "alta_lote_fallida"}

    res_consumo = L.consumir_fefo(codigo, cantidad, tipo="SALIDA_VENTA", id_empresa=id_empresa,
                                  id_almacen=almacen_expedicion, id_documento=str(id_ref),
                                  usuario=usuario, observaciones=f"Cross-docking ({fuente} {id_ref})",
                                  idempotente=True)

    transicion = None
    if fuente == "pedidos_online":
        try:
            from src.services.tpv import online_orders_service as OS
            OS.cambiar_estado(str(id_ref), "PREPARANDO")
            # `stock_descontado` es un flag a nivel de PEDIDO, no de línea (el esquema de
            # `pedidos_online_items` no tiene seguimiento por línea) — solo es seguro fijarlo aquí
            # cuando el pedido tiene una única línea; en un pedido multilínea, marcar todo el pedido
            # como "ya descontado" dejaría sin descontar de verdad las líneas NO cross-dockeadas
            # cuando el pedido pase a PAGADO más tarde.
            ped = OS.obtener_pedido(str(id_ref)) or {}
            if len(ped.get("items") or []) == 1:
                OS.marcar_stock_descontado(str(id_ref), 1)
            transicion = "PREPARANDO"
        except Exception as e:
            logger.warning("aplicar_cross_docking: transición pedidos_online %s: %s", id_ref, e)
    elif fuente == "b2b_venta":
        try:
            from src.db.conexion import transaccion as _tx
            with _tx() as conn, conn.cursor() as cur:
                cur.execute("UPDATE transaccion_lineas SET estado_linea='cross_docking' "
                           "WHERE id_tx=%s AND codigo_articulo=%s", (id_ref, codigo))
            from src.services.comercio_digital import transacciones as TX
            # `transicionar()` valida la máquina de estados oficial (BORRADOR→CONFIRMADA→PAGADA→
            # PREPARANDO, sin saltos) — se camina un paso a la vez desde el estado ACTUAL hasta
            # PREPARANDO, reutilizando exactamente esa misma función (nunca se salta la validación).
            r = {"ok": True}
            tx_now = TX.obtener(id_ref, id_empresa=id_empresa) or {}
            estado_actual = tx_now.get("estado")
            _RUTA = ("BORRADOR", "CONFIRMADA", "PAGADA", "PREPARANDO")
            if estado_actual in _RUTA:
                for siguiente in _RUTA[_RUTA.index(estado_actual) + 1:]:
                    r = TX.transicionar(id_ref, siguiente, actor=usuario, id_empresa=id_empresa,
                                        motivo="Cross-docking")
                    if not r.get("ok"):
                        break
            else:
                r = {"ok": False, "error": f"estado_no_transicionable: {estado_actual}"}
            transicion = "PREPARANDO" if r.get("ok") else r.get("error")
        except Exception as e:
            logger.warning("aplicar_cross_docking: transición b2b_venta %s: %s", id_ref, e)

    return {"ok": True, "id_lote": id_lote, "consumo": res_consumo, "transicion": transicion,
           "almacen_recepcion": almacen_recepcion, "almacen_expedicion": almacen_expedicion}
