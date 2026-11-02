"""
Capa de servicio de VENTA ONLINE desde TPV (F2) — neutra respecto a plataforma.

Aísla la lógica de pedidos online para poder conectar más adelante Shopify,
WooCommerce, PrestaShop o una web propia SIN tocar la UI ni la BD: el adaptador
de plataforma se registra con `set_proveedor(fn)` y recibe el pedido ya creado.
Por defecto no hace nada externo (modo 'interno').

Multitienda: cada pedido se registra bajo la empresa/tienda ACTIVAS y el
trabajador en sesión (cuenta para la tienda y el trabajador aunque el envío lo
haga el almacén central). Ver [[project_centro_documental]] / [[project_multitenant]].
"""

import logging
import uuid

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion, transaccion

logger = logging.getLogger("online_orders")

# Estados del ciclo de vida de un pedido online.
ESTADOS = ("PENDIENTE", "PAGADO", "PREPARANDO", "ENVIADO", "ENTREGADO", "CANCELADO")

# Adaptador de plataforma (Shopify/Woo/Presta/web). fn(pedido_dict) -> ref|None.
_proveedor = None


def set_proveedor(fn):
    """Registra el adaptador de e-commerce (futuras integraciones)."""
    global _proveedor
    _proveedor = fn


def _ctx():
    """(id_empresa, id_tienda, id_usuario, nombre) del contexto/sesión activos."""
    id_empresa, id_tienda = EMPRESA_DEFAULT_ID, None
    id_usuario, nombre = None, None
    try:
        from src.db.empresa import empresa_actual_id, tienda_actual_id
        id_empresa = empresa_actual_id()
        id_tienda = tienda_actual_id()
    except Exception:
        pass
    try:
        from src.db.usuario import sesion_global
        u = sesion_global.usuario_actual or {}
        id_usuario = u.get("id")
        nombre = u.get("nombre") or u.get("usuario")
    except Exception:
        pass
    return id_empresa, id_tienda, id_usuario, nombre


# ── Disponibilidad multi-origen ──────────────────────────────────────────────
# PCD Fase 3 (RFC-CD-005): DELEGAN en el Availability Engine (motor 100 % de lectura). Se conservan
# las firmas y la forma del resultado (fachada Strangler; el motor porta la lógica byte-idéntica).
def consultar_disponibilidad(codigo: str) -> dict:
    """Disponibilidad de un artículo (tienda activa/central/otras tiendas/online). Delega en el
    Availability Engine (lectura pura); forma de salida inalterada."""
    from src.services.comercio_digital.inventario import availability
    return availability.consultar_disponibilidad(codigo)


def localizar_articulo(codigo: str) -> dict:
    """Localiza un artículo indicando dónde hay stock. Delega en el Availability Engine
    (lectura pura); forma de salida inalterada."""
    from src.services.comercio_digital.inventario import availability
    return availability.localizar_articulo(codigo)


def _cp_desde_texto(texto: str | None) -> str | None:
    """Extrae un código postal ESPAÑOL (5 dígitos) de un texto libre (p. ej. `direccion_envio`,
    "Calle Mayor 1, Madrid 28001, ES") — best-effort, nunca inventa uno si no hay ninguna
    secuencia de 5 dígitos reconocible. Usado como ÚLTIMO recurso cuando no se pasó un CP
    explícito (p. ej. al enrutar un pedido de CONTINUACIÓN, que no vuelve a pedirle la dirección
    al cliente)."""
    import re
    if not texto:
        return None
    m = re.search(r"\b(\d{5})\b", str(texto))
    return m.group(1) if m else None


def buscar_almacenes_con_stock(codigo_articulo: str, id_tienda_solicitante,
                               id_empresa=None, *, cp_referencia: str | None = None) -> list[dict]:
    """Almacenes con existencias reales (>0) de ``codigo_articulo``, ordenados por proximidad
    — para elegir el almacén de ORIGEN de un encargo (ledger real `stock_almacen`, no columnas
    agregadas).

    El punto de referencia para la distancia es, por este orden: ``cp_referencia`` (código
    postal del CLIENTE, si se indica — caso pedido web/marketplace, donde interesa la cercanía al
    domicilio de entrega, no a ninguna tienda) o si no, la tienda ``id_tienda_solicitante`` (caso
    encargo entre tiendas/almacenes: la tienda que necesita el stock). Sin ninguno de los dos, se
    degrada honestamente (ver abajo).

    ARTÍCULOS EXCLUSIVOS DE ALMACÉN (solo venta online, nunca en tienda física): si NINGUNA fila
    de `stock_almacen` para este artículo es de un almacén `tipo_almacen='tienda'` (ni con
    cantidad cero: significa que ninguna tienda lo ha tenido nunca en su ledger real), los
    candidatos se restringen a almacenes NO-tienda (central/logístico) — un pedido de un
    artículo así nunca debe poder enrutarse a una tienda física por una coincidencia incidental
    de stock. Si alguna tienda SÍ lo ha tenido alguna vez, no se aplica ninguna restricción (el
    cascado normal ya prioriza por cercanía real).

    Cada resultado: ``{id_almacen, nombre, tipo_almacen, id_tienda, cantidad, distancia_km,
    ubicacion_desconocida}``. Los almacenes sin latitud/longitud registrada (o si no hay ningún
    punto de referencia resoluble) van al FINAL (``distancia_km=inf``,
    ``ubicacion_desconocida=True``) — nunca se excluyen, solo ordenan peor: no hay forma de
    saber si están cerca o lejos, pero puede que sean el único con existencias."""
    from src.db import stock_almacen as _SA
    from src.services.geo.distancia import haversine_km

    emp = id_empresa
    if emp is None:
        emp, _tnd, _u, _n = _ctx()

    detalle = _SA.obtener_stock_articulo(codigo_articulo, emp).get("detalle", [])
    # Exclusivo de almacén: NINGUNA fila (de cualquier cantidad) es de una tienda.
    exclusivo_almacen = detalle and not any(d.get("tipo_almacen") == "tienda" for d in detalle)
    candidatos = [dict(d) for d in detalle if int(d.get("cantidad") or 0) > 0]
    if exclusivo_almacen:
        candidatos = [d for d in candidatos if d.get("tipo_almacen") != "tienda"]
    if not candidatos:
        return []

    # Coordenadas: propias (tienda solicitante, si aplica) + de cada almacén candidato, en una
    # sola consulta (no una por candidato).
    ids = {int(d["id_almacen"]) for d in candidatos}
    alm_solicitante = _SA.almacen_de_tienda(id_tienda_solicitante, emp) if id_tienda_solicitante else None
    if alm_solicitante:
        ids.add(int(alm_solicitante))
    coords = {}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT id, latitud, longitud FROM almacen WHERE id IN "
                f"({','.join(['%s'] * len(ids))})", tuple(ids))
            for r in cur.fetchall():
                rid, lat, lng = (r["id"], r["latitud"], r["longitud"]) if isinstance(r, dict) else r
                coords[int(rid)] = (float(lat) if lat is not None else None,
                                    float(lng) if lng is not None else None)
    except Exception as e:
        logger.warning("buscar_almacenes_con_stock: no se pudieron leer coordenadas: %s", e)

    # Punto de referencia: CP del cliente (precisión de provincia, honesta — ver cp_espana.py)
    # tiene prioridad sobre la tienda solicitante, cuando se indica.
    origen_geo = None
    if cp_referencia:
        try:
            from src.services.geo.cp_espana import geocodificar_cp
            origen_geo = geocodificar_cp(cp_referencia)
        except Exception as e:
            logger.debug("buscar_almacenes_con_stock: geocodificar_cp(%s): %s", cp_referencia, e)
    if origen_geo is None and alm_solicitante:
        origen_geo = coords.get(int(alm_solicitante))

    for d in candidatos:
        geo = coords.get(int(d["id_almacen"]))
        dist = haversine_km(origen_geo, geo)   # inf si falta cualquiera de los dos puntos
        d["distancia_km"] = dist
        d["ubicacion_desconocida"] = dist == float("inf")

    candidatos.sort(key=lambda d: d["distancia_km"])
    return candidatos


# ── Reservas y solicitudes a otra tienda (TPV online) ────────────────────────
def reservar_articulo(codigo: str, cantidad: int = 1, cliente: str = None,
                      caduca_horas: int = 48, observaciones: str = None) -> int | None:
    """Aparta un artículo para un cliente en la tienda activa (no descuenta stock;
    es un apartado lógico con estado y trazabilidad). Devuelve el id de reserva."""
    import datetime as _dt
    from src.db import catalogo as _cat
    _emp, _tnd, _u, trabajador = _ctx()
    caduca = (_dt.datetime.now() + _dt.timedelta(hours=int(caduca_horas))) if caduca_horas else None
    rid = _cat.crear_reserva(codigo, cantidad=cantidad, cliente=cliente, trabajador=trabajador,
                             tipo="reserva", observaciones=observaciones, caduca=caduca)
    if rid:
        _auditar_stock("-", "RESERVA_ONLINE", [f"{codigo}x{cantidad}->{cliente or '-'}"])
    return rid


def solicitar_a_otra_tienda(codigo: str, cantidad: int = 1, id_tienda_origen=None,
                            cliente: str = None, observaciones: str = None) -> int | None:
    """Solicita un artículo a otra tienda (apartado tipo 'solicitud_traspaso').
    La tienda de destino es la activa; ``id_tienda_origen`` es la que lo envía."""
    from src.db import catalogo as _cat
    _emp, _tnd, _u, trabajador = _ctx()
    rid = _cat.crear_reserva(codigo, cantidad=cantidad, cliente=cliente, trabajador=trabajador,
                             tipo="solicitud_traspaso", id_tienda_origen=id_tienda_origen,
                             observaciones=observaciones)
    if rid:
        _auditar_stock("-", "SOLICITUD_TRASPASO_ONLINE",
                       [f"{codigo}x{cantidad} de tienda {id_tienda_origen}"])
    return rid


def listar_reservas(estado=None, tipo=None):
    from src.db import catalogo as _cat
    return _cat.listar_reservas(estado=estado, tipo=tipo)


def cambiar_estado_reserva(id_reserva, estado) -> bool:
    from src.db import catalogo as _cat
    ok = _cat.cambiar_estado_reserva(id_reserva, estado)
    if ok:
        _auditar_stock("-", "RESERVA_ONLINE_ESTADO", [f"#{id_reserva}->{estado}"])
    return ok


# ── Crear / listar / actualizar pedidos online ───────────────────────────────
def crear_pedido_online(cliente: dict, lineas: list[dict], direccion_envio: str = "",
                        observaciones: str = "", plataforma: str = "interno",
                        referencia_externa: str | None = None,
                        estado: str = "PENDIENTE",
                        modo_entrega: str = "domicilio",
                        direccion_facturacion: str = "",
                        contexto: dict | None = None) -> str | None:
    """Crea un pedido online bajo la empresa/tienda/trabajador ACTIVOS.

    - cliente: {id?, nombre, telefono?, email?}
    - lineas: [{codigo, nombre, cantidad, precio, subtotal?, origen_stock?}]
    - modo_entrega: 'domicilio' (por defecto, igual que siempre) | 'recogida_tienda' (solo tiene
      sentido en un encargo entre tiendas/almacenes: el cliente pasa a recogerlo por la tienda que
      lo pidió, no hay envío ni dirección que guardar).
    - direccion_facturacion: solo relevante con modo_entrega='domicilio' y distinta de la de
      envío (p. ej. empresa que factura a una sede distinta de donde recibe la mercancía).
    - contexto (opcional): {id_empresa, id_tienda, id_usuario, trabajador} — para invocar desde un
      proceso SIN sesión de escritorio activa (p. ej. el Portal del Empleado, servido por el
      backend Flask en su propio proceso, donde `_ctx()`/`sesion_global` no reflejan al empleado
      real). Si se omite (caso normal: GUI de escritorio, adaptadores de marketplace), se resuelve
      como siempre desde `_ctx()` — comportamiento sin cambios para el resto de llamadores.
    Devuelve el id_pedido o None.
    """
    if not lineas:
        return None
    if estado not in ESTADOS:
        estado = "PENDIENTE"
    if modo_entrega not in ("domicilio", "recogida_tienda"):
        modo_entrega = "domicilio"
    if contexto:
        id_empresa = contexto.get("id_empresa")
        id_tienda = contexto.get("id_tienda")
        id_usuario = contexto.get("id_usuario")
        trabajador = contexto.get("trabajador")
    else:
        id_empresa, id_tienda, id_usuario, trabajador = _ctx()
    cliente = cliente or {}
    total = 0.0
    norm = []
    for l in lineas:
        cant = float(l.get("cantidad", 1) or 1)
        precio = float(l.get("precio", 0) or 0)
        sub = float(l.get("subtotal") if l.get("subtotal") is not None else cant * precio)
        total += sub
        norm.append((l.get("codigo"), l.get("nombre"), int(cant), precio, sub,
                     l.get("origen_stock") or "central", l.get("id_almacen")))
    id_pedido = str(uuid.uuid4())
    try:
        with transaccion() as conn, conn.cursor() as cur:   # A2.2: pedido + ítems atómicos
            cur.execute(
                "INSERT INTO pedidos_online "
                "(id_pedido, id_empresa, id_tienda, id_usuario, trabajador, cliente_id, "
                " cliente_nombre, cliente_telefono, cliente_email, direccion_envio, total, "
                " estado, plataforma, referencia_externa, observaciones, modo_entrega, "
                " direccion_facturacion) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_pedido, id_empresa, id_tienda, id_usuario, trabajador,
                 cliente.get("id"), cliente.get("nombre"), cliente.get("telefono"),
                 cliente.get("email"), direccion_envio, round(total, 2), estado,
                 plataforma, referencia_externa, observaciones, modo_entrega,
                 direccion_facturacion or None))
            for codigo, nombre, cant, precio, sub, origen, id_almacen in norm:
                cur.execute(
                    "INSERT INTO pedidos_online_items "
                    "(id_pedido, codigo_articulo, nombre, cantidad, precio_unitario, subtotal, "
                    " origen_stock, id_almacen) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (id_pedido, codigo, nombre, cant, precio, sub, origen, id_almacen))
            # commit gestionado por transaccion()
    except Exception as e:
        logger.error("crear_pedido_online: %s", e)
        return None

    # Reserva de stock (Reservation Ledger, CD-005 Fase 5) para TODAS las líneas del pedido —
    # capa de seguridad adicional (petición explícita): el stock de la tienda/almacén encargado
    # de servir el pedido NO se descuenta aquí, solo se RESERVA (bucket "almacen:<id>" cuando el
    # pedido ya está enrutado a un almacén/tienda-almacén concreto, o "tienda:<id>" cuando lo
    # sirve directamente la tienda emisora del pedido sin almacén intermedio) para que ninguna
    # otra tienda/canal pueda vender en silencio lo que ya está comprometido con este pedido. El
    # descuento FÍSICO real ocurre más tarde, al pasar a ENVIADO (ver `_descontar_stock_pedido`,
    # invocado desde `registrar_envio`). Soft (TTL corto) hasta que se confirme el pago (se
    # consume, ver `_consumir_reservas_pedido`) o se cancele (se libera, ver
    # `_liberar_reservas_pedido`). Degrada sin bloquear la creación del pedido.
    try:
        from src.services.comercio_digital.inventario import reservas as _RSV
        for codigo, nombre, cant, precio, sub, origen, id_almacen in norm:
            bucket = f"almacen:{id_almacen}" if id_almacen else f"tienda:{id_tienda}"
            _RSV.reservar(id_pedido, codigo, cant, bucket,
                          tipo="soft", id_empresa=id_empresa, actor=trabajador,
                          canal="pedido_online")
    except Exception as e:
        logger.debug("reserva de stock pedido online (%s): %s", id_pedido, e)

    # Sincronización con la plataforma de e-commerce. No bloquea la creación local.
    try:
        ped = obtener_pedido(id_pedido)
        if _proveedor is not None:          # override manual (set_proveedor)
            ref = _proveedor(ped)
        else:                                # adaptador multiplataforma configurado
            from src.services.tpv.ecommerce import adaptador_actual
            ref = adaptador_actual().crear_pedido(ped)
        if ref:
            cambiar_referencia_externa(id_pedido, ref)
    except Exception as e:
        logger.warning("Sincronización e-commerce falló (pedido %s): %s", id_pedido, e)
    # Si el pedido nace ya PAGADO, emite el justificante de pago.
    if estado == "PAGADO":
        _on_pagado(id_pedido)
    # PCD Fase 2 (RFC-CD-006) — WRITE-THROUGH a la Transacción Comercial (espejo NO destructivo).
    # No bloquea ni altera este flujo: `pedidos_online` sigue siendo el sistema de registro durante
    # el Strangler; la Transacción se puebla en paralelo. Degradable.
    try:
        from src.services.comercio_digital import transacciones as _tx
        _tx.desde_pedido_online(id_pedido)
    except Exception as e:
        logger.debug("write-through Transacción Comercial (%s): %s", id_pedido, e)
    return id_pedido


def crear_encargo_almacen(cliente: dict, lineas: list[dict], direccion_envio: str = "",
                          observaciones: str = "", modo_entrega: str = "domicilio",
                          direccion_facturacion: str = "",
                          contexto: dict | None = None) -> str | None:
    """Crea un ENCARGO A ALMACÉN — la única vía de creación para este flujo concreto. Se construye
    en el Portal del Empleado (`src/backend/portal_empleado_web.py`, ruta `/encargo`); el TPV solo
    lo cobra después (`confirmar_pago_encargo`, ver `_VentaOnlineDialog` en `gui/tpv.py`).

    A diferencia de `crear_pedido_online` (genérico, usado también por Click&Collect y los
    adaptadores de marketplace — NO se toca su firma para no romper esos llamadores ni los
    tests que crean pedidos ya PAGADOS a propósito), esta función NO acepta un `estado`: todo
    encargo nace SIEMPRE en PENDIENTE, sin excepción — "si el cliente no ha pagado, no se podrá
    hacer ningún encargo" queda garantizado por construcción (nunca se puede invocar con
    PAGADO). El único camino legítimo de PENDIENTE→PAGADO para este flujo es
    `confirmar_pago_encargo`, tras el cobro real en el TPV.

    - lineas: [{codigo, nombre, cantidad, precio, subtotal?, id_almacen}] — `id_almacen` es el
      almacén de origen elegido (p.ej. vía `buscar_almacenes_con_stock`), persistido por línea
      en `pedidos_online_items.id_almacen` (columna ya existente, migración 0166).
    - modo_entrega/direccion_facturacion: ver `crear_pedido_online` (migración 0310) — el cajero
      los elige en el propio formulario del Portal ("Nuevo pedido").
    - contexto: ver `crear_pedido_online` (necesario al invocar desde el Portal del Empleado,
      que corre en el proceso del backend Flask, sin sesión de escritorio).
    Devuelve el id_pedido o None."""
    return crear_pedido_online(cliente, lineas, direccion_envio=direccion_envio,
                               observaciones=observaciones, plataforma="interno",
                               estado="PENDIENTE", modo_entrega=modo_entrega,
                               direccion_facturacion=direccion_facturacion, contexto=contexto)


def _rellenar_almacenes_cercanos(lineas: list[dict], id_empresa, excluir: set[int] | None = None,
                                 *, cp_referencia: str | None = None):
    """Para cada línea ``{codigo, ...}``, resuelve el almacén con stock MÁS CERCANO (mejor
    esfuerzo: `buscar_almacenes_con_stock` ordena por distancia real cuando hay coordenadas
    registradas; si faltan, degrada honestamente sin inventar una proximidad — nunca excluye un
    candidato con stock solo por falta de coordenadas, nunca falla la creación del pedido).
    ``cp_referencia`` (código postal del cliente) prioriza la cercanía a SU domicilio/punto de
    entrega — ver `buscar_almacenes_con_stock`. Los almacenes en ``excluir`` (ya intentados en
    esta misma cadena) se descartan. Devuelve ``(lineas_con_id_almacen, id_tienda_destino)`` — el
    destino es la tienda propietaria del almacén elegido para la PRIMERA línea que resuelve a una
    tienda (si ninguna resuelve a una tienda —p. ej. un artículo exclusivo de almacén—, el pedido
    queda sin destino propio — visible solo vía `id_almacen_origen`, nunca una tienda al azar)."""
    excluir = excluir or set()
    out = []
    id_tienda_destino = None
    for l in lineas:
        codigo = l.get("codigo")
        candidatos = []
        try:
            candidatos = [c for c in buscar_almacenes_con_stock(codigo, None, id_empresa,
                                                                cp_referencia=cp_referencia)
                         if int(c["id_almacen"]) not in excluir]
        except Exception as e:
            logger.warning("_rellenar_almacenes_cercanos(%s): %s", codigo, e)
        nueva = dict(l)
        if candidatos:
            nueva["id_almacen"] = candidatos[0]["id_almacen"]
            if id_tienda_destino is None and candidatos[0].get("id_tienda"):
                id_tienda_destino = candidatos[0]["id_tienda"]
        out.append(nueva)
    return out, id_tienda_destino


def crear_pedido_canal_externo(cliente: dict, lineas: list[dict], *, plataforma: str,
                               direccion_envio: str = "", observaciones: str = "",
                               referencia_externa: str | None = None,
                               cp_cliente: str | None = None,
                               id_empresa=None) -> str | None:
    """Crea un pedido de la WEB PROPIA o de un MARKETPLACE (Amazon, WooCommerce...), enrutando
    cada línea al almacén/tienda MÁS CERCANO con stock, priorizando la cercanía al CLIENTE (ver
    `_rellenar_almacenes_cercanos`/`buscar_almacenes_con_stock`): ``cp_cliente`` es el código
    postal de entrega (recomendado, pásalo siempre que el canal lo conozca); si no se indica, se
    intenta extraer de ``direccion_envio`` como último recurso (nunca inventa uno si no hay
    ningún código de 5 dígitos reconocible — degrada a enrutar sin preferencia de cercanía, igual
    que antes). El reparto en cascada entre varias tiendas (si la más cercana no puede cubrir
    TODA la cantidad) no se decide aquí por stock teórico: cada tienda confirma MANUAL y
    OBLIGATORIAMENTE cuánto puede suministrar al 'Preparar' el pedido
    (`confirmar_cantidad_servida`), que es quien dispara la continuación hacia la siguiente
    tienda más cercana, si procede. Si ningún centro tiene stock de una línea, se crea sin
    `id_almacen` (bajo pedido, igual que el resto de `crear_pedido_online`)."""
    emp = id_empresa
    if emp is None:
        emp, _t, _u, _n = _ctx()
    cp = cp_cliente or _cp_desde_texto(direccion_envio)
    norm_lineas, id_tienda_destino = _rellenar_almacenes_cercanos(lineas, emp, cp_referencia=cp)
    return crear_pedido_online(
        cliente, norm_lineas, direccion_envio=direccion_envio, observaciones=observaciones,
        plataforma=plataforma, referencia_externa=referencia_externa, estado="PENDIENTE",
        contexto={"id_empresa": emp, "id_tienda": id_tienda_destino, "id_usuario": None,
                 "trabajador": plataforma})


def confirmar_cantidad_servida(id_pedido: str, cantidades: dict, *, usuario: str | None = None,
                               id_empresa=None) -> dict:
    """Confirmación MANUAL y OBLIGATORIA (una cantidad por artículo, nunca asumida a partir del
    stock teórico) de cuánto puede suministrar REALMENTE la tienda a la que se asignó este
    pedido, al prepararlo. ``cantidades``: {codigo_articulo: cantidad_confirmada}.

    Si alguna línea queda por debajo de lo pedido, crea AUTOMÁTICAMENTE un pedido de
    CONTINUACIÓN (mismo cliente/envío/referencia, `id_pedido_origen` apuntando a este) por la
    cantidad restante, enrutado a la SIGUIENTE tienda más cercana con stock de esa línea
    (excluyendo los almacenes ya intentados en esta cadena) — resultando en un envío conjunto
    desde varias tiendas al mismo cliente. Devuelve
    ``{ok, id_pedido_continuacion, lineas_incompletas}``."""
    pedido = obtener_pedido(id_pedido)
    if not pedido:
        return {"ok": False, "motivo": "pedido no encontrado"}
    items = pedido.get("items", [])
    if any(it.get("codigo_articulo") not in cantidades for it in items):
        return {"ok": False, "motivo": "faltan confirmaciones de cantidad por artículo"}
    emp = id_empresa or pedido.get("id_empresa")
    pendientes = []
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            for it in items:
                codigo = it.get("codigo_articulo")
                pedida = int(it.get("cantidad", 0) or 0)
                servida = max(0, min(int(cantidades.get(codigo, 0) or 0), pedida))
                cur.execute(
                    "UPDATE pedidos_online_items SET cantidad_servida=%s "
                    "WHERE id_pedido=%s AND codigo_articulo=%s", (servida, id_pedido, codigo))
                restante = pedida - servida
                if restante > 0:
                    pendientes.append({**it, "cantidad": restante})
            conn.commit()
    except Exception as e:
        logger.error("confirmar_cantidad_servida(%s): %s", id_pedido, e)
        return {"ok": False, "motivo": "error de base de datos"}
    _auditar_stock(id_pedido, "CONFIRMACION_CANTIDAD_SERVIDA",
                  [f"{c}:{cantidades.get(c)}" for c in cantidades])

    id_continuacion = None
    if pendientes:
        ya_intentados = {int(it["id_almacen"]) for it in items if it.get("id_almacen")}
        cp = _cp_desde_texto(pedido.get("direccion_envio"))
        nuevas_lineas, id_tienda_destino = _rellenar_almacenes_cercanos(
            [{"codigo": it.get("codigo_articulo"), "nombre": it.get("nombre"),
              "cantidad": it.get("cantidad"), "precio": it.get("precio_unitario")}
             for it in pendientes], emp, excluir=ya_intentados, cp_referencia=cp)
        id_continuacion = crear_pedido_online(
            {"id": pedido.get("cliente_id"), "nombre": pedido.get("cliente_nombre"),
             "telefono": pedido.get("cliente_telefono"), "email": pedido.get("cliente_email")},
            nuevas_lineas, direccion_envio=pedido.get("direccion_envio") or "",
            observaciones=f"Continuación del pedido {str(id_pedido)[:8]} (suministro parcial).",
            plataforma=pedido.get("plataforma") or "interno",
            referencia_externa=pedido.get("referencia_externa"), estado="PENDIENTE",
            contexto={"id_empresa": emp, "id_tienda": id_tienda_destino, "id_usuario": None,
                     "trabajador": pedido.get("trabajador")})
        if id_continuacion:
            try:
                with obtener_conexion() as conn, conn.cursor() as cur:
                    cur.execute(
                        "UPDATE pedidos_online SET id_pedido_origen=%s WHERE id_pedido=%s",
                        (id_pedido, id_continuacion))
                    conn.commit()
            except Exception as e:
                logger.warning("confirmar_cantidad_servida: id_pedido_origen(%s): %s",
                              id_continuacion, e)
            _auditar_stock(id_continuacion, "PEDIDO_CONTINUACION_CREADO", [f"origen:{id_pedido}"])
    return {"ok": True, "id_pedido_continuacion": id_continuacion, "lineas_incompletas": pendientes}


def confirmar_pago_encargo(id_pedido: str, datos_pago: dict | None = None,
                           usuario: str | None = None) -> dict:
    """Único camino legítimo para pasar un ENCARGO A ALMACÉN de PENDIENTE a PAGADO.

    Se invoca desde el TPV justo después de que el cobro real se haya confirmado
    (`registrar_venta_con_items` con éxito) — nunca desde un combo libre de la GUI. Reutiliza
    `cambiar_estado`/`_on_pagado` (mismo justificante PDF + descuento de stock + aviso al
    cliente que ya usa el resto del ciclo de vida; no duplica esos efectos), pero es una entrada
    deliberadamente más ESTRECHA: rechaza cualquier pedido que no esté en PENDIENTE (nunca
    reabre un PAGADO/CANCELADO ni salta etapas), dejando inequívoca la intención del futuro
    llamador de la GUI. Patrón de referencia: `services/comercio_digital/pickup/__init__.py::pagar()`
    (cobro obligatorio antes de continuar).

    ``datos_pago`` es opcional y de forma libre (todavía no hay un llamador real: lo fijará la
    fase de GUI que invoque esto tras `registrar_venta_con_items`) — si trae `venta_id`/`id_venta`
    o `referencia`, se guarda en `pedidos_online.referencia_pago` como trazabilidad hacia la
    venta real del TPV (columna ya existente, usada hoy por el cobro online vía pasarela).
    Devuelve {ok, motivo?, estado}."""
    pedido = obtener_pedido(id_pedido)
    if not pedido:
        return {"ok": False, "motivo": "pedido no encontrado", "estado": None}
    estado_actual = pedido.get("estado")
    if estado_actual != "PENDIENTE":
        return {"ok": False,
               "motivo": f"el pedido no está PENDIENTE (estado actual: {estado_actual})",
               "estado": estado_actual}
    ref = None
    if datos_pago:
        ref = (datos_pago.get("referencia") or datos_pago.get("venta_id")
               or datos_pago.get("id_venta"))
        if ref is not None:
            try:
                with obtener_conexion() as conn, conn.cursor() as cur:
                    cur.execute("UPDATE pedidos_online SET referencia_pago=%s WHERE id_pedido=%s",
                               (str(ref)[:160], id_pedido))
                    conn.commit()
            except Exception as e:
                logger.warning("confirmar_pago_encargo: no se pudo guardar referencia_pago (%s): %s",
                               id_pedido, e)
    ok = cambiar_estado(id_pedido, "PAGADO")   # dispara justificante + descuento de stock + aviso
    if ok:
        _auditar_stock(id_pedido, "ENCARGO_ALMACEN_PAGADO",
                       [f"por {usuario or '-'}" + (f", ref={ref}" if ref else "")])
    return {"ok": ok, "estado": "PAGADO" if ok else estado_actual}


def importar_pedidos_remotos(id_empresa=None, id_tienda="auto") -> dict:
    """Trae los pedidos de la plataforma de e-commerce a la tabla local (espejo).

    Deduplica por ``referencia_externa`` (no reimporta lo ya traído). Es un espejo
    de solo lectura: NO vuelve a crear el pedido en la plataforma ni descuenta
    stock local (la plataforma es el sistema de registro de esos pedidos).
    Devuelve {'importados': n, 'total_remotos': m, 'plataforma': str}."""
    ctx_emp, ctx_tienda, id_usuario, trabajador = _ctx()
    if id_empresa is None:
        id_empresa = ctx_emp
    if id_tienda == "auto":
        id_tienda = ctx_tienda
    try:
        from src.services.tpv.ecommerce import adaptador_actual
        ad = adaptador_actual()
        remotos = ad.listar_pedidos_remotos() or []
        plataforma = getattr(ad, "nombre", "web")
    except Exception as e:
        logger.warning("importar_pedidos_remotos: adaptador no disponible: %s", e)
        return {"importados": 0, "total_remotos": 0, "plataforma": "web"}
    # Referencias ya presentes (para deduplicar).
    existentes = set()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT referencia_externa FROM pedidos_online "
                        "WHERE id_empresa=%s AND referencia_externa IS NOT NULL", (id_empresa,))
            existentes = {str(r[0] if not isinstance(r, dict) else r["referencia_externa"])
                          for r in cur.fetchall()}
    except Exception as e:
        logger.error("importar_pedidos_remotos (existentes): %s", e)
        return {"importados": 0, "total_remotos": len(remotos), "plataforma": plataforma}

    importados = 0
    for rem in remotos:
        ref = str(rem.get("referencia_externa") or "").strip()
        if not ref or ref in existentes:
            continue
        estado = rem.get("estado") if rem.get("estado") in ESTADOS else "PENDIENTE"
        items = rem.get("items") or []
        total = rem.get("total")
        if total is None:
            total = sum(float(it.get("subtotal") or 0) for it in items)
        pid = str(uuid.uuid4())
        try:
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO pedidos_online "
                    "(id_pedido, id_empresa, id_tienda, id_usuario, trabajador, cliente_nombre, "
                    " cliente_telefono, cliente_email, direccion_envio, total, estado, plataforma, "
                    " referencia_externa, observaciones) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (pid, id_empresa, id_tienda, id_usuario, trabajador,
                     rem.get("cliente_nombre"), rem.get("cliente_telefono"),
                     rem.get("cliente_email"), rem.get("direccion_envio"),
                     round(float(total or 0), 2), estado, plataforma, ref,
                     rem.get("observaciones")))
                for it in items:
                    cant = int(it.get("cantidad", 1) or 1)
                    precio = float(it.get("precio", 0) or 0)
                    sub = float(it.get("subtotal") if it.get("subtotal") is not None else cant * precio)
                    cur.execute(
                        "INSERT INTO pedidos_online_items "
                        "(id_pedido, codigo_articulo, nombre, cantidad, precio_unitario, subtotal, origen_stock) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (pid, it.get("codigo"), it.get("nombre"), cant, precio, sub,
                         it.get("origen_stock") or "online"))
                conn.commit()
            existentes.add(ref)
            importados += 1
        except Exception as e:
            logger.error("importar_pedidos_remotos (insert %s): %s", ref, e)
    if importados:
        _auditar_stock("-", "IMPORTAR_PEDIDOS_ONLINE",
                       [f"{plataforma}:{importados}/{len(remotos)}"])
    return {"importados": importados, "total_remotos": len(remotos), "plataforma": plataforma}


def listar_pedidos_online(id_empresa=None, id_tienda="auto", estado=None,
                          texto=None, limite=1000, id_almacen_origen=None) -> list[dict]:
    """Lista pedidos online de la empresa ACTIVA.

    Visibilidad (aislamiento): por defecto, solo los pedidos cuya tienda de DESTINO es la
    ``id_tienda`` (activa si se deja en "auto"). Si además se indica ``id_almacen_origen``
    (INT, opcional — el almacén del que un ENCARGO se está sirviendo, `pedidos_online_items
    .id_almacen`), la visibilidad se AMPLÍA: también se listan los pedidos que no son de esta
    tienda pero que este almacén sirve como origen (para que el personal del almacén los vea en
    su pestaña "Preparar") — sin tocar la máquina de estados, solo la condición de visibilidad.
    Con ``id_tienda=None`` e ``id_almacen_origen`` fijado, lista SOLO los que este almacén sirve
    (sin exigir ninguna tienda de destino concreta)."""
    try:
        from src.db.empresa import empresa_actual_id, tienda_actual_id
        if id_empresa is None:
            id_empresa = empresa_actual_id()
        if id_tienda == "auto":
            id_tienda = tienda_actual_id()
    except Exception:
        if id_tienda == "auto":
            id_tienda = None
    filtros, params = ["id_empresa=%s"], [id_empresa]
    _existe_linea_almacen = ("EXISTS (SELECT 1 FROM pedidos_online_items poi WHERE "
                             "poi.id_pedido = pedidos_online.id_pedido AND poi.id_almacen=%s)")
    if id_tienda is not None and id_almacen_origen is not None:
        filtros.append(f"(id_tienda=%s OR {_existe_linea_almacen})")
        params.append(id_tienda); params.append(id_almacen_origen)
    elif id_tienda is not None:
        filtros.append("id_tienda=%s"); params.append(id_tienda)
    elif id_almacen_origen is not None:
        filtros.append(_existe_linea_almacen); params.append(id_almacen_origen)
    if estado:
        filtros.append("estado=%s"); params.append(estado)
    if texto:
        filtros.append("(cliente_nombre LIKE %s OR cliente_telefono LIKE %s "
                       "OR cliente_email LIKE %s OR id_pedido LIKE %s "
                       "OR referencia_externa LIKE %s)")
        params += [f"%{texto}%"] * 5
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM pedidos_online WHERE " + " AND ".join(filtros) +
                " ORDER BY fecha DESC, id_pedido DESC LIMIT %s", (*params, int(limite)))
            cols = [d[0] for d in cur.description]
            filas = cur.fetchall()
            return [r if isinstance(r, dict) else dict(zip(cols, r)) for r in filas]
    except Exception as e:
        logger.error("listar_pedidos_online: %s", e)
        return []


# Estados que cuentan como venta confirmada para las analíticas (todo lo que no
# está pendiente de cobro ni cancelado).
ESTADOS_FACTURABLES = ("PAGADO", "PREPARANDO", "ENVIADO", "ENTREGADO")


def facturacion_por_dia(fecha_desde=None, fecha_hasta=None,
                        id_empresa=None, id_tienda="auto") -> dict:
    """Facturación de pedidos online por día (clave 'YYYY-MM-DD' -> total) de la
    empresa/tienda ACTIVAS. Solo cuenta estados facturables. Integra el canal
    online en las analíticas de Ventas."""
    try:
        from src.db.empresa import empresa_actual_id, tienda_actual_id
        if id_empresa is None:
            id_empresa = empresa_actual_id()
        if id_tienda == "auto":
            id_tienda = tienda_actual_id()
    except Exception:
        if id_tienda == "auto":
            id_tienda = None
    filtros, params = ["id_empresa=%s"], [id_empresa]
    if id_tienda is not None:
        filtros.append("id_tienda=%s"); params.append(id_tienda)
    filtros.append("estado IN (%s)" % ",".join(["%s"] * len(ESTADOS_FACTURABLES)))
    params += list(ESTADOS_FACTURABLES)
    if fecha_desde:
        filtros.append("DATE(fecha) >= %s"); params.append(str(fecha_desde)[:10])
    if fecha_hasta:
        filtros.append("DATE(fecha) <= %s"); params.append(str(fecha_hasta)[:10])
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT DATE(fecha) AS d, COALESCE(SUM(total),0) AS t "
                "FROM pedidos_online WHERE " + " AND ".join(filtros) + " GROUP BY DATE(fecha)",
                tuple(params))
            out = {}
            for r in cur.fetchall():
                d = r["d"] if isinstance(r, dict) else r[0]
                t = r["t"] if isinstance(r, dict) else r[1]
                if d is not None:
                    out[str(d)[:10]] = float(t or 0)
            return out
    except Exception as e:
        logger.error("facturacion_por_dia: %s", e)
        return {}


def resumen_online(fecha_desde=None, fecha_hasta=None, id_empresa=None, id_tienda="auto") -> dict:
    """{'pedidos': int, 'facturacion': float} de pedidos online en el rango — mismo filtro de
    tenant/estados facturables que `facturacion_por_dia` (ningún criterio paralelo), para alimentar
    el KPI "Ventas online" del Resumen de Ventas (petición explícita)."""
    try:
        from src.db.empresa import empresa_actual_id, tienda_actual_id
        if id_empresa is None:
            id_empresa = empresa_actual_id()
        if id_tienda == "auto":
            id_tienda = tienda_actual_id()
    except Exception:
        if id_tienda == "auto":
            id_tienda = None
    filtros, params = ["id_empresa=%s"], [id_empresa]
    if id_tienda is not None:
        filtros.append("id_tienda=%s"); params.append(id_tienda)
    filtros.append("estado IN (%s)" % ",".join(["%s"] * len(ESTADOS_FACTURABLES)))
    params += list(ESTADOS_FACTURABLES)
    if fecha_desde:
        filtros.append("DATE(fecha) >= %s"); params.append(str(fecha_desde)[:10])
    if fecha_hasta:
        filtros.append("DATE(fecha) <= %s"); params.append(str(fecha_hasta)[:10])
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*), COALESCE(SUM(total),0) FROM pedidos_online WHERE "
                + " AND ".join(filtros), tuple(params))
            fila = cur.fetchone() or (0, 0)
            return {"pedidos": int(fila[0] or 0), "facturacion": float(fila[1] or 0)}
    except Exception as e:
        logger.error("resumen_online: %s", e)
        return {"pedidos": 0, "facturacion": 0.0}


def obtener_pedido(id_pedido: str) -> dict | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM pedidos_online WHERE id_pedido=%s", (id_pedido,))
            r = cur.fetchone()
            if not r:
                return None
            if not isinstance(r, dict):
                r = dict(zip([d[0] for d in cur.description], r))
            cur.execute(
                "SELECT codigo_articulo, nombre, cantidad, precio_unitario, subtotal, "
                "origen_stock, id_almacen "
                "FROM pedidos_online_items WHERE id_pedido=%s", (id_pedido,))
            items = []
            for f in cur.fetchall():
                if isinstance(f, dict):
                    items.append(f)
                else:
                    items.append({"codigo_articulo": f[0], "nombre": f[1], "cantidad": f[2],
                                  "precio_unitario": f[3], "subtotal": f[4], "origen_stock": f[5],
                                  "id_almacen": f[6]})
            r["items"] = items
            return r
    except Exception as e:
        logger.error("obtener_pedido(%s): %s", id_pedido, e)
        return None


def cambiar_estado(id_pedido: str, nuevo_estado: str) -> bool:
    if nuevo_estado not in ESTADOS:
        return False
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE pedidos_online SET estado=%s WHERE id_pedido=%s",
                        (nuevo_estado, id_pedido))
            conn.commit()
        if nuevo_estado == "PAGADO":
            _on_pagado(id_pedido)
        elif nuevo_estado == "CANCELADO":
            _reponer_stock_pedido(id_pedido)
            _liberar_reservas_pedido(id_pedido)
        elif nuevo_estado == "PREPARANDO":
            _notificar_cliente(id_pedido, "PREPARANDO")
        elif nuevo_estado == "ENTREGADO":
            # Red de seguridad idempotente (flag `stock_descontado`): los pedidos que se entregan
            # directamente en tienda (recogida, sin pasar por "ENVIADO"/`registrar_envio`) deben
            # descontar aquí el stock físico reservado — si ya se descontó al enviar, es un no-op.
            try:
                _descontar_stock_pedido(id_pedido)
            except Exception as e:
                logger.warning("No se pudo descontar el stock del pedido al entregarlo (%s): %s",
                               id_pedido, e)
            _notificar_cliente(id_pedido, "ENTREGADO")
        return True
    except Exception as e:
        logger.error("cambiar_estado(%s): %s", id_pedido, e)
        return False


def _generar_pdf_pedido(id_pedido: str, titulo: str, prefijo: str,
                        es_justificante: bool = False, tipo_doc: str = "pedido",
                        extra_cabecera=None) -> str | None:
    """Genera un PDF (comprobante / justificante / envío) de un pedido online y lo
    registra en el centro documental. Devuelve la ruta o None."""
    import os
    pedido = obtener_pedido(id_pedido)
    if not pedido:
        return None
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
    except Exception as e:
        logger.warning("reportlab no disponible para %s: %s", prefijo, e)
        return None
    try:
        from src.db.empresa import info_documento
        emp = info_documento()
    except Exception:
        emp = {}
    try:
        from src.utils.recursos import ruta_datos
        carpeta = ruta_datos("pedidos")
    except Exception:
        carpeta = os.path.join("documentos", "pedidos")
    os.makedirs(carpeta, exist_ok=True)
    ruta = os.path.join(carpeta, f"{prefijo}_{id_pedido}.pdf")
    try:
        c = canvas.Canvas(ruta, pagesize=A4)
        W, H = A4
        y = H - 24 * mm
        c.setFont("Helvetica-Bold", 15)
        c.drawString(20 * mm, y, (emp.get("nombre") or "SMART MANAGER")[:60])
        y -= 6 * mm
        c.setFont("Helvetica", 9)
        for ln in (emp.get("direccion_completa"), f"CIF: {emp.get('cif','')}",
                   emp.get("telefono"), emp.get("email")):
            if ln:
                c.drawString(20 * mm, y, str(ln)[:90]); y -= 4.5 * mm
        y -= 4 * mm
        c.setFont("Helvetica-Bold", 13)
        c.drawString(20 * mm, y, titulo); y -= 8 * mm
        c.setFont("Helvetica", 9)
        fecha = str(pedido.get("fecha") or "")[:19]
        cabecera = [f"Pedido: {id_pedido}", f"Fecha: {fecha}",
                    f"Estado: {pedido.get('estado','')}",
                    f"Plataforma: {pedido.get('plataforma','')}",
                    f"Trabajador: {pedido.get('trabajador') or '-'}",
                    f"Cliente: {pedido.get('cliente_nombre') or '-'}",
                    f"Tel.: {pedido.get('cliente_telefono') or '-'}   "
                    f"Email: {pedido.get('cliente_email') or '-'}",
                    f"Envío: {pedido.get('direccion_envio') or '-'}"]
        if es_justificante:
            ref = pedido.get("referencia_externa")
            cabecera.append("PAGO CONFIRMADO" + (f"   Ref.: {ref}" if ref else ""))
        for ln in (extra_cabecera or []):
            if ln:
                cabecera.append(str(ln))
        for ln in cabecera:
            c.drawString(20 * mm, y, ln[:100]); y -= 5 * mm
        y -= 3 * mm
        c.setFont("Helvetica-Bold", 9)
        c.drawString(20 * mm, y, "Artículo"); c.drawString(120 * mm, y, "Cant.")
        c.drawString(140 * mm, y, "Precio"); c.drawString(170 * mm, y, "Subtotal")
        y -= 2 * mm; c.line(20 * mm, y, 190 * mm, y); y -= 5 * mm
        c.setFont("Helvetica", 9)
        for it in pedido.get("items", []):
            c.drawString(20 * mm, y, str(it.get("nombre") or it.get("codigo_articulo") or "")[:60])
            c.drawRightString(132 * mm, y, str(it.get("cantidad", 0)))
            c.drawRightString(162 * mm, y, f"{float(it.get('precio_unitario',0)):.2f}")
            c.drawRightString(190 * mm, y, f"{float(it.get('subtotal',0)):.2f}")
            y -= 5 * mm
        y -= 2 * mm; c.line(120 * mm, y, 190 * mm, y); y -= 6 * mm
        c.setFont("Helvetica-Bold", 11)
        etiqueta_total = "TOTAL PAGADO: " if es_justificante else "TOTAL: "
        c.drawRightString(190 * mm, y, f"{etiqueta_total}{float(pedido.get('total',0)):.2f}")
        c.setFont("Helvetica", 7)
        c.drawString(20 * mm, 15 * mm, f"Trazabilidad: {id_pedido}")
        c.showPage(); c.save()
    except Exception as e:
        logger.error("_generar_pdf_pedido(%s, %s): %s", id_pedido, prefijo, e)
        return None
    # Registrar en el centro documental.
    try:
        from src.db import documentos as _docreg
        _docreg.registrar_documento(
            ruta, tipo=tipo_doc, referencia=id_pedido,
            cliente=pedido.get("cliente_nombre"), trabajador=pedido.get("trabajador"),
            importe=pedido.get("total"), estado=pedido.get("estado"))
    except Exception as e:
        logger.debug("No se pudo registrar %s: %s", prefijo, e)
    return ruta


def generar_comprobante(id_pedido: str) -> str | None:
    """Comprobante PDF del pedido online (centro documental, tipo 'pedido')."""
    return _generar_pdf_pedido(
        id_pedido, "COMPROBANTE DE PEDIDO ONLINE", "comprobante_pedido")


def generar_justificante_pago(id_pedido: str) -> str | None:
    """Justificante de pago PDF del pedido online. Se genera automáticamente al
    pasar el pedido a PAGADO (centro documental, tipo 'pedido')."""
    return _generar_pdf_pedido(
        id_pedido, "JUSTIFICANTE DE PAGO", "justificante_pago",
        es_justificante=True)


def generar_documento_envio(id_pedido: str) -> str | None:
    """Documento de envío (albarán) PDF del pedido online, con transportista y nº
    de seguimiento (centro documental, tipo 'albaran')."""
    ped = obtener_pedido(id_pedido) or {}
    extra = [f"Transportista: {ped.get('transportista') or '-'}",
             f"Nº seguimiento: {ped.get('seguimiento') or '-'}"]
    return _generar_pdf_pedido(
        id_pedido, "DOCUMENTO DE ENVÍO", "envio_pedido",
        tipo_doc="albaran", extra_cabecera=extra)


def registrar_envio(id_pedido: str, transportista: str = "", seguimiento: str = "") -> bool:
    """Guarda los datos de envío del pedido (transportista, nº de seguimiento,
    fecha) y genera el documento de envío. Se invoca al pasar a ENVIADO.

    Capa de seguridad adicional sobre el stock (petición explícita): es AQUÍ, y no al pagar,
    donde se descuenta físicamente el stock de la tienda/almacén emisor — una vez el empleado
    ha terminado la preparación y confirma el envío (ver `_descontar_stock_pedido`). Hasta este
    momento el stock del artículo solo aparecía "reservado" (ver Reservation Ledger), nunca
    descontado, para que ninguna tienda vendiera en silencio algo ya comprometido."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE pedidos_online SET transportista=%s, seguimiento=%s, "
                "fecha_envio=NOW() WHERE id_pedido=%s",
                (transportista or None, seguimiento or None, id_pedido))
            conn.commit()
    except Exception as e:
        logger.error("registrar_envio(%s): %s", id_pedido, e)
        return False
    try:
        _descontar_stock_pedido(id_pedido)
    except Exception as e:
        logger.warning("No se pudo descontar el stock del pedido al enviarlo (%s): %s",
                       id_pedido, e)
    try:
        generar_documento_envio(id_pedido)
    except Exception as e:
        logger.warning("No se pudo generar el documento de envío (%s): %s", id_pedido, e)
    _auditar_stock(id_pedido, "ENVIO_PEDIDO_ONLINE",
                   [f"{transportista or '-'}/{seguimiento or '-'}"])
    _notificar_cliente(id_pedido, "ENVIADO")
    return True


def _marcar_stock_descontado(id_pedido: str, valor: int) -> None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE pedidos_online SET stock_descontado=%s WHERE id_pedido=%s",
                        (valor, id_pedido))
            conn.commit()
    except Exception as e:
        logger.debug("marcar_stock_descontado(%s): %s", id_pedido, e)


def marcar_stock_descontado(id_pedido: str, valor: int = 1) -> None:
    """Wrapper público de `_marcar_stock_descontado` (mismo criterio ya usado para
    `db.compras._actualizar_costes` → `actualizar_costes_entrada`): Cross-Docking (Fase D) necesita
    fijar este flag idempotente desde `services.expediciones.aplicar_cross_docking` tras consumir por
    FEFO la cantidad cross-docked de un pedido online — así `_descontar_stock_pedido` (disparada más
    tarde al pasar el pedido a PAGADO) no vuelve a descontar esa misma cantidad. Reservado a pedidos de
    UNA sola línea (ver `aplicar_cross_docking`): en un pedido multilínea marcar todo el pedido como
    "ya descontado" dejaría sin descuento real las líneas NO cross-dockeadas."""
    _marcar_stock_descontado(id_pedido, valor)


def _descontar_stock_pedido(id_pedido: str) -> None:
    """Descuenta del inventario las líneas de un pedido online (idempotente). Se invoca al
    ENVIAR el pedido (ver `registrar_envio`), nunca al pagarlo — hasta entonces el stock solo
    estaba RESERVADO (Reservation Ledger), nunca descontado físicamente (capa de seguridad
    adicional, petición explícita).

    Usa el descuento canónico con bloqueo de fila (central→tienda). Solo actúa
    una vez por pedido (flag ``stock_descontado``). No bloquea el cambio de
    estado: si una línea no tiene stock, se registra y se continúa.

    EXCEPCIÓN — líneas de un ENCARGO A ALMACÉN/PEDIDO ENTRE TIENDAS (``id_almacen`` fijado en la
    línea, ver `crear_encargo_almacen`): para esas, en vez de `traspasar_stock` (que sumaba al
    destino de forma INSTANTÁNEA en la misma transacción) se hace un descuento DE UN SOLO SENTIDO
    en el almacén de origen (`stock_almacen.decrementar_stock`) y se registra un documento
    logístico 'TRASPASO' (`logistica.registrar_documento_traspaso_pedido_online`) hacia el
    almacén/tienda de destino — el stock de la tienda RECEPTORA solo se suma cuando allí
    confirmen la recepción física, reutilizando TAL CUAL el motor de recepción de palés ya
    existente (nunca al emitirse el envío). El resto de pedidos (sin `id_almacen` por línea:
    tienda online, marketplaces...) sigue el descuento genérico de siempre, sin tocar."""
    pedido = obtener_pedido(id_pedido)
    if not pedido or int(pedido.get("stock_descontado") or 0):
        return
    try:
        from src.db.conexion import descontar_stock
    except Exception as e:
        logger.warning("descontar_stock no disponible (%s): %s", id_pedido, e)
        return
    from src.db import stock_almacen as _SA
    id_empresa_ped = pedido.get("id_empresa")
    id_tienda_ped = pedido.get("id_tienda")
    almacen_destino = None
    if id_tienda_ped is not None:
        try:
            almacen_destino = _SA.almacen_de_tienda(id_tienda_ped, id_empresa_ped)
        except Exception as e:
            logger.warning("_descontar_stock_pedido: almacen_de_tienda(%s): %s", id_tienda_ped, e)
    detalle = []
    # Líneas de traspaso inter-almacén agrupadas por almacén de origen (un pedido puede, en
    # teoría, enrutar líneas distintas desde orígenes distintos): cada grupo genera su propio
    # documento logístico de traspaso.
    traspasos: dict[int, list] = {}
    for it in pedido.get("items", []):
        codigo = it.get("codigo_articulo")
        nombre = it.get("nombre") or codigo
        cant = int(it.get("cantidad", 0) or 0)
        if not codigo or cant <= 0:
            continue
        id_almacen_origen = it.get("id_almacen")
        ok = False
        if id_almacen_origen and almacen_destino and int(id_almacen_origen) != int(almacen_destino):
            try:
                ok = _SA.decrementar_stock(codigo, int(id_almacen_origen), cant, id_empresa_ped)
            except Exception as e:
                ok = False
                logger.warning("decrementar_stock(%s, almacen=%s, %s): %s", codigo,
                               id_almacen_origen, cant, e)
            if ok:
                traspasos.setdefault(int(id_almacen_origen), []).append(
                    {"codigo": codigo, "nombre": nombre, "cantidad": cant})
                detalle.append(f"{codigo}x{cant}(traspaso {id_almacen_origen}->{almacen_destino}, "
                               f"pendiente de recepción)")
            else:
                logger.warning("Pedido online %s: fallo descuento %s desde almacén %s; "
                               "recurriendo al descuento genérico.", id_pedido, codigo,
                               id_almacen_origen)
        if not ok:
            try:
                ok, _t, _ti = descontar_stock(codigo, cant)
            except Exception as e:
                ok = False
                logger.warning("descontar_stock(%s, %s): %s", codigo, cant, e)
            detalle.append(f"{codigo}x{cant}{'' if ok else '(sin stock)'}")
        if not ok:
            logger.warning("Pedido online %s: sin stock para %s x%s", id_pedido, codigo, cant)
    if traspasos:
        try:
            from src.db import logistica as _LOG
            almacenes = _SA.listar_almacenes(id_empresa_ped, solo_activos=False)
            nombres = {int(a["id"]): a.get("nombre") or str(a["id"]) for a in almacenes}
            destino_nombre = nombres.get(int(almacen_destino), str(almacen_destino))
            destino_tienda_id = id_tienda_ped
            for id_alm_origen, lineas in traspasos.items():
                origen_nombre = nombres.get(id_alm_origen, str(id_alm_origen))
                _LOG.registrar_documento_traspaso_pedido_online(
                    f"{id_pedido}-{id_alm_origen}" if len(traspasos) > 1 else id_pedido,
                    origen=origen_nombre, destino=destino_nombre, usuario=pedido.get("trabajador"),
                    lineas=lineas, id_empresa=id_empresa_ped, id_tienda=destino_tienda_id)
        except Exception as e:
            logger.warning("No se pudo registrar el documento de traspaso del pedido %s: %s",
                           id_pedido, e)
    _marcar_stock_descontado(id_pedido, 1)
    _auditar_stock(id_pedido, "DESCUENTO_STOCK_ONLINE", detalle)
    _consumir_reservas_pedido(id_pedido)


def _consumir_reservas_pedido(id_pedido: str) -> None:
    """El stock físico de este pedido YA se movió (pago confirmado): las reservas soft del
    Ledger pasan a CONSUMED (deja de restar del ATP por esta vía — el descuento real ya lo hizo
    `_descontar_stock_pedido`/`traspasar_stock`, el Ledger nunca mueve stock por sí mismo)."""
    try:
        from src.services.comercio_digital.inventario import reservas as _RSV
        for r in _RSV.activas(id_tx=id_pedido):
            _RSV.consumir(r["id_reserva"])
    except Exception as e:
        logger.debug("_consumir_reservas_pedido(%s): %s", id_pedido, e)


def _liberar_reservas_pedido(id_pedido: str) -> None:
    """Pedido cancelado: libera cualquier reserva de stock activa del Ledger asociada a este
    `id_tx` — deja de bloquear el ATP para otras tiendas/canales. Independiente de si ya se
    había descontado stock físico (eso lo gestiona `_reponer_stock_pedido` por separado)."""
    try:
        from src.services.comercio_digital.inventario import reservas as _RSV
        for r in _RSV.activas(id_tx=id_pedido):
            _RSV.liberar(r["id_reserva"])
    except Exception as e:
        logger.debug("_liberar_reservas_pedido(%s): %s", id_pedido, e)


def contar_pedidos_pendientes_tienda(id_tienda=None, id_empresa=None) -> int:
    """Nº de pedidos online PENDIENTES relevantes para esta tienda: los que la tienen como
    DESTINO (web/Click&Collect/Marketplace) + los pedidos de OTRA tienda que el almacén de ESTA
    tienda debe servir (encargo entre tiendas/almacenes). Alimenta el badge rojo de "Ver pedidos
    online"/"Cobrar pedido" en el TPV — solo lectura, nunca inventa ni descuenta nada."""
    try:
        from src.db import empresa as _emp_mod
        from src.db import stock_almacen as _SA
        emp = id_empresa if id_empresa is not None else _emp_mod.empresa_actual_id()
        tienda = id_tienda if id_tienda is not None else _emp_mod.tienda_actual_id()
        if tienda is None:
            return 0
        propios = listar_pedidos_online(id_empresa=emp, id_tienda=tienda, estado="PENDIENTE",
                                        limite=500)
        vistos = {p.get("id_pedido") for p in propios}
        try:
            id_almacen = _SA.almacen_de_tienda(tienda, emp)
        except Exception:
            id_almacen = None
        ajenos = 0
        if id_almacen:
            servidos = listar_pedidos_online(id_empresa=emp, id_tienda=None, estado="PENDIENTE",
                                             id_almacen_origen=id_almacen, limite=500)
            ajenos = len([p for p in servidos if p.get("id_pedido") not in vistos
                         and p.get("id_tienda") != tienda])
        # Click & Collect (motor independiente `comercio_digital.transacciones`, NO pasa por
        # `pedidos_online`): cuenta las recogidas PAGADA/PREPARANDO de esta tienda — las que
        # requieren acción del personal (preparar/entregar), igual criterio que los pendientes
        # de arriba.
        pickups = 0
        try:
            import json as _json
            from src.services.comercio_digital import transacciones as _TX
            for estado_tx in ("PAGADA", "PREPARANDO"):
                for tx in _TX.listar(id_empresa=emp, id_tienda=tienda, estado=estado_tx, limite=500):
                    meta = tx.get("metadata")
                    try:
                        meta = _json.loads(meta) if isinstance(meta, str) else (meta or {})
                    except Exception:
                        meta = {}
                    if meta.get("cumplimiento") == "PICKUP_STORE":
                        pickups += 1
        except Exception as e:
            logger.debug("contar_pedidos_pendientes_tienda (pickups): %s", e)
        return len(propios) + ajenos + pickups
    except Exception as e:
        logger.debug("contar_pedidos_pendientes_tienda: %s", e)
        return 0


def verificar_venta_bloqueada_por_reserva(codigo: str, cantidad: int, id_tienda=None,
                                          id_empresa=None) -> dict | None:
    """Comprobación de SOLO LECTURA para el TPV, previa a confirmar una venta: si vender
    ``cantidad`` unidades de ``codigo`` dejaría el stock físico de esta tienda por debajo de lo
    YA reservado (Reservation Ledger) para pedidos de OTRAS tiendas/almacenes, devuelve un aviso
    ``{reservado, libre, tiendas}`` para que la GUI pida confirmación al cajero antes de vender
    stock ya comprometido. Nunca bloquea por sí misma (no es su responsabilidad: solo lee) y
    degrada a None (sin aviso) ante cualquier fallo — nunca impide la venta por un error interno."""
    try:
        from src.db import empresa as _emp_mod
        from src.db import stock_almacen as _SA
        from src.services.comercio_digital.inventario import reservas as _RSV
        emp = id_empresa if id_empresa is not None else _emp_mod.empresa_actual_id()
        tienda = id_tienda if id_tienda is not None else _emp_mod.tienda_actual_id()
        if tienda is None or not codigo:
            return None
        id_almacen = _SA.almacen_de_tienda(tienda, emp)
        if not id_almacen:
            return None
        reservado = _RSV.reservado(codigo, emp, bucket=f"almacen:{id_almacen}")
        if reservado <= 0:
            return None
        stock_fisico = _SA.obtener_stock_almacen(codigo, id_almacen, id_empresa=emp)
        libre = stock_fisico - reservado
        if float(cantidad or 0) <= libre:
            return None
        tiendas_dest = []
        try:
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT DISTINCT t.nombre FROM pedidos_online p "
                    "JOIN pedidos_online_items i ON i.id_pedido = p.id_pedido "
                    "JOIN tiendas t ON t.id = p.id_tienda "
                    "WHERE i.id_almacen = %s AND i.codigo_articulo = %s "
                    "AND p.estado = 'PENDIENTE' AND p.id_tienda != %s",
                    (id_almacen, codigo, tienda))
                for f in cur.fetchall():
                    v = list(f.values())[0] if isinstance(f, dict) else f[0]
                    if v:
                        tiendas_dest.append(v)
        except Exception as e:
            logger.debug("verificar_venta_bloqueada_por_reserva tiendas(%s): %s", codigo, e)
        return {"reservado": reservado, "libre": max(0, libre), "tiendas": tiendas_dest}
    except Exception as e:
        logger.debug("verificar_venta_bloqueada_por_reserva(%s): %s", codigo, e)
        return None


def _reponer_stock_pedido(id_pedido: str) -> None:
    """Repone el stock de un pedido online cancelado (solo si se había descontado)."""
    pedido = obtener_pedido(id_pedido)
    if not pedido or not int(pedido.get("stock_descontado") or 0):
        return
    detalle = []
    emp = pedido.get("id_empresa")          # PK compuesta (migr 0181): la reposición filtra por empresa
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            for it in pedido.get("items", []):
                codigo = it.get("codigo_articulo")
                cant = int(it.get("cantidad", 0) or 0)
                if not codigo or cant <= 0:
                    continue
                cur.execute(
                    "UPDATE articulos SET Stock_total = COALESCE(Stock_total,0) + %s "
                    "WHERE codigo = %s AND (%s IS NULL OR id_empresa = %s)", (cant, codigo, emp, emp))
                detalle.append(f"{codigo}x{cant}")
            conn.commit()
    except Exception as e:
        logger.warning("reponer_stock_pedido(%s): %s", id_pedido, e)
        return
    _marcar_stock_descontado(id_pedido, 0)
    _auditar_stock(id_pedido, "REPOSICION_STOCK_ONLINE", detalle)


def _auditar_stock(id_pedido: str, accion: str, detalle: list) -> None:
    try:
        from src.db.conexion import log_auditoria
        usuario = _ctx()[3] or "sistema"
        log_auditoria(usuario, accion, "pedidos_online",
                      f"{id_pedido}: {', '.join(detalle) or '-'}")
    except Exception as e:
        logger.debug("auditar_stock(%s): %s", id_pedido, e)


def _buzon_activo(id_empresa=None):
    """Buzón corporativo activo de la empresa (prefiere el de la tienda activa).
    Devuelve el id_correo o None."""
    try:
        from src.db import correo as correo_db
        emp, tienda, _u, _n = _ctx()
        buzones = correo_db.listar_correos(id_empresa or emp)
        activos = [b for b in buzones if b.get("estado") == "activo"]
        if not activos:
            return None
        de_tienda = [b for b in activos if tienda is not None and b.get("id_tienda") == tienda]
        return (de_tienda or activos)[0].get("id_correo")
    except Exception as e:
        logger.debug("_buzon_activo: %s", e)
        return None


_URLS_SEGUIMIENTO = {
    "seur": "https://www.seur.com/livetracking/?segOnlineIdentificador={cod}",
    "correos": "https://www.correos.es/es/es/herramientas/localizador/envios?codigo_identifica={cod}",
    "correos express": "https://www.correosexpress.com/es/seguimiento-de-envios?codigo={cod}",
    "mrw": "https://www.mrw.es/seguimiento_envios/MRW_Seguimiento.asp?Numero={cod}",
    "gls": "https://www.gls-spain.es/es/parcel-tracking?match={cod}",
    "nacex": "https://www.nacex.es/seguimientoEnvios.jsp?codigo={cod}",
    "tourline": "https://www.tourlineexpress.com/seguimiento?codexp={cod}",
    "dhl": "https://www.dhl.com/es-es/home/tracking.html?tracking-id={cod}",
    "ups": "https://www.ups.com/track?tracknum={cod}",
    "fedex": "https://www.fedex.com/fedextrack/?trknbr={cod}",
}


def enlace_seguimiento(transportista: str, codigo: str) -> str | None:
    """URL pública de seguimiento de la agencia de transporte indicada (si se reconoce),
    con el código real del envío ya insertado. Degrada a None (nunca inventa una URL) si
    falta el código o la agencia no está en el pequeño catálogo de agencias conocidas."""
    if not codigo:
        return None
    clave = str(transportista or "").strip().casefold()
    plantilla = _URLS_SEGUIMIENTO.get(clave)
    if not plantilla:
        return None
    from urllib.parse import quote
    return plantilla.format(cod=quote(str(codigo)))


def _notificar_cliente(id_pedido: str, estado: str) -> None:
    """Envía un aviso por correo al cliente al cambiar el pedido a un estado
    relevante (PAGADO/ENVIADO/ENTREGADO), adjuntando el documento correspondiente.
    Degrada con elegancia: si no hay buzón, email o módulo de correo, no hace nada
    y nunca bloquea el cambio de estado."""
    import os
    pedido = obtener_pedido(id_pedido)
    if not pedido:
        return
    email = (pedido.get("cliente_email") or "").strip()
    if not email:
        return
    id_correo = _buzon_activo(pedido.get("id_empresa"))
    if not id_correo:
        logger.info("Sin buzón corporativo activo; no se notifica al cliente (%s).", id_pedido)
        return
    try:
        from src.utils.i18n import tr
    except Exception:
        def tr(_k, default="", **kw):
            return default.format(**kw) if kw else default
    try:
        from src.db.empresa import info_documento
        empresa = (info_documento() or {}).get("nombre") or "Smart Manager"
    except Exception:
        empresa = "Smart Manager"
    from src.utils import divisas  # importe localizado
    enlace = enlace_seguimiento(pedido.get("transportista"), pedido.get("seguimiento"))
    ctx = {"pedido": str(id_pedido)[:8], "cliente": pedido.get("cliente_nombre") or "",
           "empresa": empresa, "total": divisas.formatear(float(pedido.get("total") or 0)),
           "transportista": pedido.get("transportista") or "-",
           "seguimiento": pedido.get("seguimiento") or "-",
           "enlace_seguimiento": enlace or "",
           "linea_enlace": f"Sigue tu envío aquí: {enlace}" if enlace else ""}
    defaults_subj = {
        "PAGADO": "Hemos recibido tu pago — Pedido {pedido}",
        "PREPARANDO": "Tu pedido {pedido} ya está preparado",
        "ENVIADO": "Tu pedido {pedido} ha sido enviado",
        "ENTREGADO": "Tu pedido {pedido} ha sido entregado",
    }
    defaults_body = {
        "PAGADO": ("Hola {cliente}:\n\nHemos confirmado el pago de tu pedido {pedido} "
                   "por un importe de {total}. Adjuntamos el justificante de pago.\n"
                   "{linea_enlace}\n"
                   "Gracias por tu compra.\n{empresa}"),
        "PREPARANDO": ("Hola {cliente}:\n\nTu pedido {pedido} ya está preparado y en breve saldrá "
                       "hacia su destino.\n\nGracias por tu compra.\n{empresa}"),
        "ENVIADO": ("Hola {cliente}:\n\nTu pedido {pedido} ya está en camino.\n"
                    "Transportista: {transportista}\nNº de seguimiento: {seguimiento}\n"
                    "{linea_enlace}\n"
                    "Gracias por tu compra.\n{empresa}"),
        "ENTREGADO": ("Hola {cliente}:\n\nTu pedido {pedido} ha sido entregado. "
                      "Esperamos que lo disfrutes.\n\nGracias por confiar en nosotros.\n{empresa}"),
    }
    if estado not in defaults_subj:
        return
    asunto = tr(f"online.mail_subj_{estado}", default=defaults_subj[estado], **ctx)
    cuerpo = tr(f"online.mail_body_{estado}", default=defaults_body[estado], **ctx)
    # Adjunto según el estado.
    adj = []
    carpeta = os.path.join("documentos", "pedidos")
    try:
        from src.utils.recursos import ruta_datos
        carpeta = ruta_datos("pedidos")
    except Exception:
        pass
    fichero = {"PAGADO": f"justificante_pago_{id_pedido}.pdf",
               "ENVIADO": f"envio_pedido_{id_pedido}.pdf"}.get(estado)
    if fichero:
        ruta = os.path.join(carpeta, fichero)
        if os.path.exists(ruta):
            adj.append(ruta)
    try:
        from src.services.correo.servicio import enviar_documento
        ok, msg = enviar_documento(id_correo, email, asunto, cuerpo, adj)
        logger.info("Aviso cliente (%s, %s): %s", id_pedido, estado, msg)
        _auditar_stock(id_pedido, "AVISO_CLIENTE_ONLINE", [f"{estado}->{email}:{'ok' if ok else 'ko'}"])
    except Exception as e:
        logger.warning("No se pudo notificar al cliente (%s): %s", id_pedido, e)


def _on_pagado(id_pedido: str) -> None:
    """Acciones automáticas al confirmarse el pago de un pedido online.

    Capa de seguridad adicional sobre el stock (petición explícita): al PAGAR el pedido NO se
    descuenta stock físico todavía — solo queda RESERVADO (ver la reserva creada en
    `crear_pedido_online`). El descuento real se produce al pasar a ENVIADO, una vez el empleado
    termina la preparación y pulsa "Enviar" en el Portal del Empleado (ver `registrar_envio` →
    `_descontar_stock_pedido`). Así todas las tiendas ven el stock real menos lo ya reservado por
    pedidos pendientes, en vez de un stock ya fantasma-descontado antes de que el pedido exista
    físicamente preparado."""
    try:
        generar_justificante_pago(id_pedido)
    except Exception as e:
        logger.warning("No se pudo generar el justificante de pago (%s): %s",
                       id_pedido, e)
    _notificar_cliente(id_pedido, "PAGADO")


def cambiar_referencia_externa(id_pedido: str, referencia: str) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE pedidos_online SET referencia_externa=%s WHERE id_pedido=%s",
                        (referencia, id_pedido))
            conn.commit()
        return True
    except Exception as e:
        logger.error("cambiar_referencia_externa(%s): %s", id_pedido, e)
        return False


# ── Cobro online (pasarela de pago) ──────────────────────────────────────────
def crear_cobro(id_pedido: str) -> dict:
    """Inicia un cobro real del pedido con la pasarela configurada y guarda el
    enlace/referencia de pago. Devuelve {ok, url, referencia, estado, mensaje}."""
    pedido = obtener_pedido(id_pedido)
    if not pedido:
        return {"ok": False, "url": "", "referencia": "", "estado": "pendiente",
                "mensaje": "Pedido no encontrado."}
    try:
        from src.db import pagos as pagos_db
        from src.services.tpv.pagos import pasarela_para
        # Resuelve la pasarela de la EMPRESA DEL PEDIDO, nunca de la "empresa activa" ambiente
        # (`pasarela_actual()`): un pedido online puede crearse desde el backend Flask del
        # storefront (un proceso SIN sesión de escritorio, donde `empresa_actual_id()` no refleja
        # la tienda del comprador) — cobrar con la pasarela equivocada sería un fallo de
        # aislamiento multiempresa real, no solo cosmético.
        res = pasarela_para(pagos_db.obtener_config(pedido.get("id_empresa"))).crear_cobro(pedido)
    except Exception as e:
        logger.error("crear_cobro(%s): %s", id_pedido, e)
        return {"ok": False, "url": "", "referencia": "", "estado": "pendiente",
                "mensaje": f"Error: {e}"}
    if res.get("ok"):
        try:
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute(
                    "UPDATE pedidos_online SET referencia_pago=%s, enlace_pago=%s, "
                    "estado_pago=%s WHERE id_pedido=%s",
                    (res.get("referencia"), res.get("url"), "pendiente", id_pedido))
                conn.commit()
        except Exception as e:
            logger.error("crear_cobro guardar(%s): %s", id_pedido, e)
        _auditar_stock(id_pedido, "COBRO_ONLINE_INICIADO", [res.get("referencia") or "-"])
    return res


def verificar_pago(id_pedido: str) -> str:
    """Consulta el estado del cobro en la pasarela. Si está 'pagado' y el pedido
    aún no estaba PAGADO, lo marca (lo que dispara justificante, stock y aviso).
    Devuelve 'pendiente' | 'pagado' | 'fallido'."""
    pedido = obtener_pedido(id_pedido)
    if not pedido:
        return "pendiente"
    ref = pedido.get("referencia_pago")
    if not ref:
        return "pendiente"
    try:
        from src.db import pagos as pagos_db
        from src.services.tpv.pagos import pasarela_para
        # Misma razón que en `crear_cobro`: la pasarela se resuelve por la empresa DEL PEDIDO,
        # nunca por el contexto ambiente del proceso que verifica el pago.
        estado = pasarela_para(pagos_db.obtener_config(pedido.get("id_empresa"))).verificar_pago(ref)
    except Exception as e:
        logger.warning("verificar_pago(%s): %s", id_pedido, e)
        return "pendiente"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE pedidos_online SET estado_pago=%s WHERE id_pedido=%s",
                        (estado, id_pedido))
            conn.commit()
    except Exception as e:
        logger.debug("verificar_pago estado(%s): %s", id_pedido, e)
    if estado == "pagado" and pedido.get("estado") != "PAGADO":
        cambiar_estado(id_pedido, "PAGADO")
    return estado
