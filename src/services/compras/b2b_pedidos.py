"""
Tramitación de pedidos B2B (Smart Suppliers · Fase B). NO crea un motor de pedidos/transacciones
paralelo: delega íntegramente en `services.comercio_digital.transacciones` (Transacción Comercial,
motor vigente de Comercio Digital) con `origen='b2b'` — el conector que el commit de desmontaje de la
Lonja (408548b) dejó anotado como pendiente para "Fase 2".

Un carrito puede mezclar artículos de varios proveedores (el catálogo B2B es transversal); tramitar
agrupa las líneas POR PROVEEDOR y crea una Transacción Comercial independiente por cada uno — un pedido
real solo puede ir a un proveedor. El pago/custodia de fondos (escrow) es la Fase C: aquí el pedido
queda CONFIRMADA (firme, pendiente de pago), no PAGADA.
"""

import logging

logger = logging.getLogger("compras.b2b_pedidos")


def tramitar(token_sesion, es_consignacion: bool = False) -> dict:
    """`es_consignacion` (Fase C — Stock en Consignación): marca TODOS los pedidos generados por esta
    tramitación (uno por proveedor, ver arriba) como consignación — es un flag POR TX, no por línea (un
    mismo carrito no mezcla consignación con compra firme; si en el futuro se necesitara mezclar, el
    carrito tendría que separarlas en tramitaciones distintas, no esta función). El checkout del Portal
    Empresa ya expone esta opción al comprador (Portal B2B, Fase 1 — casilla en
    `portal_empresa_b2b.py::pagina_carrito`, leída en `carrito_tramitar`), pero también es alcanzable
    programáticamente (o vía un cliente API).

    Validación de servidor (Fase 1, nunca se confía solo en la casilla del cliente): si
    `es_consignacion=True`, se comprueba que CADA línea del carrito corresponde a un artículo que su
    proveedor tiene realmente marcado `disponible_consignacion=1` en `b2b_catalogo`
    (`b2b_catalogo.articulos_disponibles_consignacion`). Si no es así para alguna línea, el flag se
    IGNORA para TODA la tramitación (degrada a compra firme, nunca falla el pedido completo por esto) —
    mismo criterio de "silenciosamente ignorar en vez de bloquear" que ya usa el resto del checkout."""
    from src.services.compras import b2b_carrito
    from src.services.compras import b2b_catalogo as CAT
    from src.services.compras import b2b_sesion_empresa as SES
    from src.services.comercio_digital import transacciones as TX

    sesion = SES.resolver_sesion(token_sesion)
    if not sesion:
        return {"ok": False, "error": "sesion_invalida"}
    lineas = b2b_carrito.listar(token_sesion)
    if not lineas:
        return {"ok": False, "error": "carrito_vacio"}

    if es_consignacion:
        codigos_por_proveedor: dict = {}
        for ln in lineas:
            codigos_por_proveedor.setdefault(ln["id_suministrador"], set()).add(ln["codigo"])
        for id_sum, codigos in codigos_por_proveedor.items():
            flageados = CAT.articulos_disponibles_consignacion(id_sum, list(codigos))
            if not codigos.issubset(flageados):
                logger.warning(
                    "tramitar: es_consignacion=True solicitado pero el proveedor %s tiene en el "
                    "carrito artículo(s) sin disponible_consignacion=1 (%s) — se ignora el flag para "
                    "toda la tramitación (nunca se confía en la entrada del cliente).",
                    id_sum, sorted(codigos - flageados))
                es_consignacion = False
                break

    por_proveedor: dict = {}
    for ln in lineas:
        por_proveedor.setdefault(ln["id_suministrador"], []).append(ln)

    pedidos_creados = []
    for id_suministrador, lns in por_proveedor.items():
        tx_lineas = [{"codigo": l["codigo"], "nombre": l["nombre"], "cantidad": l["cantidad"],
                     "precio_unitario": float(l["precio_unitario"])} for l in lns]
        id_tx = TX.crear(tipo="pedido", origen="b2b", estado="BORRADOR",
                         id_empresa=sesion["id_empresa"], id_tienda=sesion["id_tienda"],
                         lineas=tx_lineas,
                         metadata={"id_suministrador": id_suministrador,
                                  "usuario": sesion.get("nombre_usuario"),
                                  "es_consignacion": bool(es_consignacion)})
        if not id_tx:
            logger.error("tramitar: no se pudo crear transacción para suministrador %s", id_suministrador)
            continue
        _fijar_suministrador_y_unidades(id_tx, id_suministrador, sesion["id_tienda"], lns,
                                        es_consignacion=es_consignacion)
        r = TX.transicionar(id_tx, "CONFIRMADA", actor=sesion.get("nombre_usuario"),
                            id_empresa=sesion["id_empresa"], motivo="Pedido B2B tramitado")
        # Albarán automático: se genera en cuanto el pedido queda CONFIRMADA (tramitado por completo
        # y visible en el portal del proveedor — no hay ningún paso posterior de "aceptación" al que
        # anclarse). Un fallo aquí NUNCA debe impedir que el pedido se haya creado correctamente.
        try:
            from src.services.compras import b2b_albaran
            b2b_albaran.generar_albaran_pedido(id_tx)
        except Exception as e:
            logger.error("tramitar: no se pudo generar el albarán de %s: %s", id_tx, e)
        pedidos_creados.append({"id_tx": id_tx, "id_suministrador": id_suministrador,
                                "transicion": r})

    if not pedidos_creados:
        return {"ok": False, "error": "no_se_pudo_crear_ningun_pedido"}

    _marcar_reposicion_tramitada(lineas)
    b2b_carrito.vaciar(token_sesion)
    return {"ok": True, "pedidos": pedidos_creados}


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def obtener_para_proveedor(id_tx, id_suministrador) -> dict | None:
    """Autorización del lado Proveedor: la Transacción Comercial genérica (transacciones.obtener) solo
    filtra por id_empresa (lado Empresa) — no existía ningún filtro por id_suministrador sobre una
    transacción individual. Mismo patrón de lectura directa que b2b_disputas._contexto_transaccion.
    Incluye `lineas`, igual que `transacciones.obtener()`, para que ambos portales usen la misma forma."""
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM transaccion_comercial WHERE id_tx=%s AND id_suministrador=%s",
                        (id_tx, id_suministrador))
            row = cur.fetchone()
            if not row:
                return None
            tx = _fila(cur, row)
            cur.execute("SELECT * FROM transaccion_lineas WHERE id_tx=%s ORDER BY id", (id_tx,))
            tx["lineas"] = [_fila(cur, r) for r in cur.fetchall()]
            return tx
    except Exception as e:
        logger.error("obtener_para_proveedor(%s,%s): %s", id_tx, id_suministrador, e)
        return None


def listar_para_suministrador(id_suministrador, *, estado=None, limite: int = 200) -> list[dict]:
    """Pedidos B2B del proveedor. `transacciones.listar()` solo filtra por id_empresa (lado Empresa);
    el lado Proveedor nunca tuvo una vista de sus propios pedidos, así que se consulta directamente."""
    try:
        from src.db.conexion import obtener_conexion
        q = "SELECT * FROM transaccion_comercial WHERE id_suministrador=%s"
        params = [id_suministrador]
        if estado:
            q += " AND estado=%s"
            params.append(estado)
        q += " ORDER BY creada DESC LIMIT %s"
        params.append(int(limite))
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, params)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_para_suministrador(%s): %s", id_suministrador, e)
        return []


def _fijar_suministrador_y_unidades(id_tx, id_suministrador, id_tienda, lineas,
                                    es_consignacion: bool = False):
    """Completa las columnas propias de Smart Suppliers (migración 0221) que `transacciones.crear`
    no conoce — sin tocar esa función existente (aditivo, cabecera + líneas del motor genérico ya
    quedaron creadas correctamente).

    Trazabilidad (Punto 3 bis, migración 0261): también copia sobre la línea el lote/caducidad que
    el PROVEEDOR ya declaró en su catálogo B2B (`b2b_catalogo.lote/fecha_caducidad`, solo si el
    artículo está marcado `es_perecedero`) — así el pedido nace YA con ese dato, antes de que la
    mercancía llegue a ningún almacén. Un artículo no marcado perecedero en el catálogo no lleva
    lote/caducidad al pedido (nada que declarar).

    `es_consignacion` (Fase C, migración 0269): otra columna propia que `transacciones.crear` no
    conoce — se fija aquí igual que `id_suministrador`/`id_tienda_destino`, en la MISMA columna que
    lee `recibir_mercancia()` (el `metadata` JSON de la tx, poblado por `tramitar()`, es solo para
    lectura humana/depuración — esta columna dedicada es la fuente real que consulta el código)."""
    try:
        from src.db.conexion import obtener_conexion
        from src.services.compras import b2b_catalogo as CAT
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE transaccion_comercial SET id_suministrador=%s, id_tienda_destino=%s, "
                        "es_consignacion=%s WHERE id_tx=%s",
                        (id_suministrador, id_tienda, 1 if es_consignacion else 0, id_tx))
            for ln in lineas:
                cat = None
                try:
                    cat = CAT.obtener_activo(id_suministrador, ln["codigo"])
                except Exception as e:
                    logger.debug("_fijar_suministrador_y_unidades: catalogo(%s): %s", ln["codigo"], e)
                lote = fecha_caducidad = None
                if cat and cat.get("es_perecedero"):
                    lote = cat.get("lote")
                    fecha_caducidad = cat.get("fecha_caducidad")
                cur.execute("UPDATE transaccion_lineas SET unidad_medida=%s, lote=%s, "
                            "fecha_caducidad=%s WHERE id_tx=%s AND codigo_articulo=%s",
                            (ln.get("unidad_medida"), lote, fecha_caducidad, id_tx, ln["codigo"]))
            conn.commit()
    except Exception as e:
        logger.error("_fijar_suministrador_y_unidades(%s): %s", id_tx, e)


# ── Recepción de mercancía (stock/lote) ──────────────────────────────────────
# Punto 3 bis: la recepción FÍSICA de stock de un pedido B2B es una acción DISTINTA de la
# confirmación de entrega del escrow (`b2b_escrow.confirmar_entrega`, que solo libera fondos y hoy
# no toca stock/lotes en absoluto — no existe ningún otro punto del código que dé de alta stock/
# lotes para un pedido B2B). Se implementa aquí, aparte, para no tocar `b2b_escrow.py` (fuera de
# alcance) ni acoplar la recepción física al ciclo de custodia de fondos. Sigue EXACTAMENTE el
# mismo patrón que `db.compras.recibir` (almacén destino + kárdex + lotes best-effort tras commit).
def recibir_mercancia(id_tx, *, actor=None, id_empresa=None, lineas_override=None) -> dict:
    """Registra la recepción física de un pedido B2B ya tramitado: incrementa stock en el almacén
    destino y da de alta lote/caducidad (INV.3/FEFO) usando el dato YA DECLARADO por el proveedor
    en `transaccion_lineas.lote/fecha_caducidad` (Punto 3 bis) — el operario/gestor de la Empresa
    solo lo CONFIRMA; `lineas_override` = {id_linea: {lote, fecha_caducidad}} es el único punto de
    entrada manual, y solo actúa como RELLENO cuando la línea no trae dato del proveedor (p. ej.
    catálogo sin marcar perecedero pero el artículo exige lote en `articulos.requiere_lote`).
    Idempotente vía `transaccion_comercial.stock_recibido_en`."""
    from src.db.conexion import obtener_conexion, transaccion
    lineas_override = lineas_override or {}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM transaccion_comercial WHERE id_tx=%s", (id_tx,))
            row = cur.fetchone()
            if not row:
                return {"ok": False, "error": "pedido_no_encontrado"}
            tx = row if isinstance(row, dict) else dict(zip([d[0] for d in cur.description], row))
            if id_empresa and str(tx.get("id_empresa")) != str(id_empresa):
                return {"ok": False, "error": "pedido_no_encontrado"}
            if tx.get("stock_recibido_en"):
                return {"ok": True, "idempotente": True}
            if tx.get("estado") in ("BORRADOR", "CANCELADA"):
                return {"ok": False, "error": f"estado_invalido_para_recibir ({tx.get('estado')})"}
            cur.execute("SELECT * FROM transaccion_lineas WHERE id_tx=%s ORDER BY id", (id_tx,))
            lcols = [d[0] for d in cur.description]
            lineas = [r if isinstance(r, dict) else dict(zip(lcols, r)) for r in cur.fetchall()]
        if not lineas:
            return {"ok": False, "error": "pedido_sin_lineas"}

        id_empresa_tx = tx.get("id_empresa")
        id_tienda = tx.get("id_tienda_destino") or tx.get("id_tienda")
        # Fase C — Stock en Consignación: un pedido en consignación NUNCA genera pasivo/PMP al
        # recibirse (la mercancía sigue siendo del proveedor hasta que se consume) — se marca aquí,
        # UNA vez, y se usa tanto para SALTAR el ajuste de coste medio (abajo) como para dar de alta
        # los lotes con `propiedad='consignacion'` (best-effort, tras commit).
        es_consignacion = bool(tx.get("es_consignacion"))
        id_suministrador = tx.get("id_suministrador")
        from src.db import stock_almacen as SA
        destino = SA.almacen_de_tienda(id_tienda, id_empresa=id_empresa_tx) if id_tienda else None
        if not destino:
            destino = SA.almacen_central(id_empresa_tx)

        entradas = []  # (codigo, cantidad, lote, fecha_caducidad, precio)
        with transaccion() as conn, conn.cursor() as cur:
            from src.db import compras as CPR
            for ln in lineas:
                codigo = ln.get("codigo_articulo")
                cantidad = int(ln.get("cantidad") or 0)
                if not codigo or cantidad <= 0:
                    continue
                override = lineas_override.get(str(ln.get("id"))) or lineas_override.get(ln.get("id")) or {}
                lote_raw = ln.get("lote") or override.get("lote")
                lote = str(lote_raw).strip() if lote_raw else None
                if not lote and es_consignacion:
                    # La consignación NECESITA un lote para que `lotes.propiedad='consignacion'`
                    # exista y `consumir_fefo` pueda detectarlo/liquidarlo (Fase C, punto 4) — a
                    # diferencia de una compra firme normal, aquí NO es opcional (sin lote, este
                    # stock sería indistinguible de stock propio al consumirse). Sintético pero
                    # honesto: un identificador estable por (pedido, artículo), no un dato inventado
                    # sobre la mercancía en sí (caducidad/lote de fabricante siguen NULL si el
                    # proveedor no los declaró).
                    lote = f"CONSIG-{id_tx}"
                cad_raw = ln.get("fecha_caducidad") or override.get("fecha_caducidad")
                # `fecha_caducidad` puede llegar como str (override manual del formulario) o como
                # datetime.date (columna DATE ya tipada por el driver al leer transaccion_lineas).
                fecha_caducidad = (cad_raw.isoformat() if hasattr(cad_raw, "isoformat")
                                   else str(cad_raw).strip() if cad_raw else None)
                precio = round(float(ln.get("precio_unitario") or 0), 2)
                # Prerrequisito Landed Cost (Fase B): cierra el bug histórico por el que la
                # recepción B2B nunca actualizaba articulos.coste_medio/coste_actual — mismo
                # patrón EXACTO que db.compras.recibir() (lee stock_previo ANTES del incremento
                # best-effort posterior, misma transacción/cursor que el resto de esta función).
                # Consignación (Fase C): se SALTA a propósito — esta mercancía no es propiedad de
                # la empresa todavía, así que no debe entrar en su PMP/coste medio.
                if precio > 0 and not es_consignacion:
                    cur.execute("SELECT COALESCE(Stock_total,0) FROM articulos WHERE codigo=%s",
                                (codigo,))
                    fila_prev = cur.fetchone()
                    if fila_prev is not None:
                        stock_previo = (fila_prev[0] if not isinstance(fila_prev, dict)
                                       else list(fila_prev.values())[0])
                        CPR.actualizar_costes_entrada(cur, codigo, int(stock_previo or 0), cantidad,
                                                      precio, id_empresa=id_empresa_tx)
                cur.execute(
                    "INSERT INTO movimientos_stock (codigo_articulo, tipo_movimiento, cantidad, "
                    "id_documento, origen, usuario, observaciones, id_almacen_destino) "
                    "VALUES (%s,'ENTRADA_COMPRA',%s,%s,%s,%s,%s,%s)",
                    (codigo, cantidad, f"B2B-{id_tx}", "compra_b2b", actor,
                     f"Recepción pedido B2B {id_tx}", destino))
                entradas.append((codigo, cantidad, lote, fecha_caducidad, precio))
            actualizadas = cur.execute(
                "UPDATE transaccion_comercial SET stock_recibido_en=NOW() WHERE id_tx=%s "
                "AND stock_recibido_en IS NULL", (id_tx,))
            if not actualizadas:
                raise RuntimeError("recepcion_ya_registrada_concurrentemente")

        # Best-effort tras commit (mismo criterio que db.compras.recibir): el pedido ya quedó
        # marcado como recibido aunque el ajuste de stock/lote tuviera un fallo puntual.
        try:
            from src.db import lotes as L
            for codigo, cantidad, lote, fecha_caducidad, precio in entradas:
                SA.incrementar_stock(codigo, destino, cantidad, id_empresa=id_empresa_tx)
                if lote:
                    kw_propiedad = ({"propiedad": "consignacion", "id_suministrador": id_suministrador}
                                    if es_consignacion else {})
                    L.registrar_entrada(codigo, lote, cantidad, fecha_caducidad=fecha_caducidad,
                                        id_empresa=id_empresa_tx, id_almacen=destino,
                                        origen="compra_b2b", id_documento=f"B2B-{id_tx}",
                                        usuario=actor, id_tx_origen=id_tx, **kw_propiedad)
                if es_consignacion:
                    _registrar_deposito_consignacion(id_tx, codigo, cantidad, precio, id_suministrador,
                                                      id_empresa_tx)
        except Exception as e:
            logger.warning("recibir_mercancia: sync stock/lotes pedido %s: %s", id_tx, e)
        return {"ok": True, "id_almacen": destino, "lineas": len(entradas)}
    except Exception as e:
        logger.error("recibir_mercancia(%s): %s", id_tx, e)
        return {"ok": False, "error": "error_interno"}


def _registrar_deposito_consignacion(id_tx, codigo, cantidad, precio, id_suministrador, id_empresa):
    """Fase C — Stock en Consignación: upsert del saldo agregado (`b2b_consignacion_saldo`) + evento
    DEPOSITO append-only (`b2b_consignacion_movimientos`). `precio_unitario` se CONGELA en el primer
    depósito de este (id_tx, codigo) — `ON DUPLICATE KEY` solo acumula `cantidad_depositada`, nunca
    reescribe el precio (un mismo artículo repetido en dos líneas del mismo pedido, caso raro pero no
    imposible, no debe poder cambiar el precio ya fijado). `id_documento=NULL` a propósito en el
    movimiento DEPOSITO (a diferencia de LIQUIDACION, que sí lleva uno — ver
    `registrar_consumo_consignacion` — el único protegido por `uq_bcm_liquidacion`): en MariaDB varios
    NULL conviven en una UNIQUE KEY, así que dos líneas del mismo artículo en el mismo pedido nunca
    chocan aquí. Llamada ya dentro del try/except best-effort de `recibir_mercancia` — cualquier fallo
    se propaga a ese `except` y solo se loguea (el pedido ya quedó marcado como recibido).

    `comision_unitaria` (Portal B2B, Fase 1): se CONGELA aquí también, mismo momento y mismo criterio
    que `precio_unitario` — se lee del catálogo VIVO del proveedor para este `codigo` (0 si el artículo
    no está activo/marcado en consignación, nunca None, para que `registrar_consumo_consignacion` pueda
    sumarla directamente sin comprobaciones de NULL)."""
    from src.db.conexion import transaccion
    from src.services.compras import b2b_catalogo as CAT
    articulo_cat = CAT.obtener_activo(id_suministrador, codigo)
    comision = float((articulo_cat or {}).get("comision_unitaria") or 0)
    with transaccion() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO b2b_consignacion_saldo (id_tx, codigo_articulo, id_suministrador, "
            "id_empresa, cantidad_depositada, precio_unitario, comision_unitaria) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE cantidad_depositada=cantidad_depositada+VALUES(cantidad_depositada)",
            (id_tx, codigo, id_suministrador, id_empresa, cantidad, precio, comision))
        cur.execute(
            "INSERT INTO b2b_consignacion_movimientos (id_tx, id_suministrador, codigo_articulo, "
            "tipo, cantidad, id_documento) VALUES (%s,%s,%s,'DEPOSITO',%s,NULL)",
            (id_tx, id_suministrador, codigo, cantidad))


def _filas(cur):
    cols = [d[0] for d in cur.description]
    return [r if isinstance(r, dict) else dict(zip(cols, r)) for r in cur.fetchall()]


# ── Consumo/liquidación de consignación (Fase C, punto 4) ───────────────────────
# Único punto de entrada llamado desde `db.lotes.consumir_fefo` (tras su propio commit, best-effort,
# nunca bloquea la salida real de stock) cuando detecta lotes `propiedad='consignacion'` consumidos.
# Consume el saldo abierto EN ORDEN DE DEPÓSITO (más antiguo primero, señal = el `id` AUTO_INCREMENT
# de la primera fila DEPOSITO de cada (id_tx, codigo) en `b2b_consignacion_movimientos` — ni
# `transaccion_comercial.creada` [DATETIME, precisión de segundo: dos depósitos del mismo artículo en
# el mismo segundo empatarían] ni `b2b_consignacion_saldo.actualizado` [cambia con cada consumo/
# devolución posterior, no refleja el orden de depósito] sirven aquí), pudiendo repartirse entre
# VARIOS `id_tx` si un solo depósito no cubre toda la cantidad consumida.
#
# Idempotencia de EXACTAMENTE-UNA-VEZ: el INSERT del evento `LIQUIDACION` es el propio reclamo
# atómico (protegido por `uq_bcm_liquidacion (id_suministrador, codigo_articulo, tipo, id_documento)`,
# migración 0269) — mismo principio que `b2b_rappels.liquidar_rappel` (`uq_rl_ventana`), pero aquí el
# reclamo se hace ANTES de escribir ninguna mutación de saldo (no un placeholder vacío que se rellena
# después): si el INSERT falla por clave duplicada, otra llamada YA liquidó este mismo evento de
# consumo y esta se corta aquí sin haber escrito nada — no-op estructuralmente seguro ante
# reintentos/duplicados del propio `consumir_fefo`. La clave usa `id_suministrador`, NO `id_tx`:
# un mismo evento puede repartirse entre VARIOS `id_tx` de depósito, y cuál de ellos acaba siendo
# "el principal" del reparto depende del saldo disponible EN ESE MOMENTO — que cambia entre la
# llamada original y un reintento (si el primer depósito ya se agotó, un reintento repartiría desde
# el siguiente). Anclar la clave a `id_tx` haría que ese reintento nunca chocara contra la
# liquidación original: `id_suministrador` sí es estable para el mismo evento de consumo, así que el
# reclamo protege igual sin importar qué depósito(s) concretos acaban financiándolo.
def registrar_consumo_consignacion(id_suministrador, codigo, cantidad_consumida, id_documento,
                                   id_empresa, usuario=None) -> dict:
    """Liquida (consume saldo + auto-factura idempotente) `cantidad_consumida` unidades de `codigo` en
    consignación del `id_suministrador` dado, atribuidas al evento de consumo `id_documento` (el mismo
    `id_documento` que recibió `lotes.consumir_fefo` para la salida real — la clave de la idempotencia).
    Devuelve {ok, motivo/error} si no hay nada que hacer o ya se liquidó; {ok: True, ...} con el
    detalle del reparto FIFO entre depósitos y de la factura generada (si la hubo)."""
    from src.db.conexion import transaccion
    cantidad_consumida = int(cantidad_consumida or 0)
    if not id_suministrador or not codigo or cantidad_consumida <= 0:
        return {"ok": False, "error": "parametros_invalidos"}
    plan: list = []
    try:
        with transaccion() as conn, conn.cursor() as cur:
            # Señal de "más antiguo" = el `id` (BIGINT AUTO_INCREMENT) de la PRIMERA fila DEPOSITO
            # de cada (id_tx, codigo) — NO `transaccion_comercial.creada`: esa columna es DATETIME
            # (precisión de segundo), así que dos depósitos del mismo artículo tramitados en el
            # mismo segundo (nada raro en un alta por lote/script) empatarían y el desempate por
            # `id_tx` (cadena UUID) sería esencialmente aleatorio respecto al orden real — el
            # AUTO_INCREMENT de `b2b_consignacion_movimientos` sí garantiza orden de inserción
            # estricto sin ambigüedad, sea cual sea la resolución del reloj.
            cur.execute(
                "SELECT s.id_tx, s.cantidad_depositada, s.cantidad_consumida, s.cantidad_devuelta, "
                "s.precio_unitario, s.comision_unitaria FROM b2b_consignacion_saldo s "
                "JOIN (SELECT id_tx, codigo_articulo, MIN(id) AS primer_deposito "
                "FROM b2b_consignacion_movimientos WHERE tipo='DEPOSITO' "
                "GROUP BY id_tx, codigo_articulo) d "
                "ON d.id_tx=s.id_tx AND d.codigo_articulo=s.codigo_articulo "
                "WHERE s.id_suministrador=%s AND s.codigo_articulo=%s AND s.id_empresa=%s "
                "AND (s.cantidad_depositada - s.cantidad_consumida - s.cantidad_devuelta) > 0 "
                "ORDER BY d.primer_deposito ASC FOR UPDATE",
                (id_suministrador, codigo, id_empresa))
            filas = _filas(cur)
            restante = cantidad_consumida
            for f in filas:
                if restante <= 0:
                    break
                disponible = (int(f["cantidad_depositada"]) - int(f["cantidad_consumida"])
                             - int(f["cantidad_devuelta"]))
                toma = min(restante, disponible)
                if toma <= 0:
                    continue
                # `comision_unitaria` (Portal B2B, Fase 1): congelada en el depósito (`b2b_consignacion_
                # saldo.comision_unitaria`, DEFAULT 0 — nunca NULL) junto a `precio_unitario`. Se lleva
                # aparte en el plan (no sumada aquí) para que el reparto FIFO y el resto de esta función
                # sigan operando exactamente igual que antes; solo se usa más abajo, al construir el
                # importe por unidad de la factura.
                plan.append((f["id_tx"], toma, float(f["precio_unitario"]),
                            float(f.get("comision_unitaria") or 0)))
                restante -= toma
            if not plan:
                logger.warning("registrar_consumo_consignacion: sin saldo abierto (sum=%s cod=%s "
                               "emp=%s evento=%s)", id_suministrador, codigo, id_empresa, id_documento)
                return {"ok": False, "error": "sin_saldo_consignacion"}
            cantidad_liquidada = cantidad_consumida - restante
            id_tx_principal = plan[0][0]  # el depósito más antiguo del reparto — solo informativo
            try:
                cur.execute(
                    "INSERT INTO b2b_consignacion_movimientos (id_tx, id_suministrador, "
                    "codigo_articulo, tipo, cantidad, id_documento) VALUES (%s,%s,%s,'LIQUIDACION',%s,%s)",
                    (id_tx_principal, id_suministrador, codigo, cantidad_liquidada, id_documento))
            except Exception:
                logger.info("registrar_consumo_consignacion: evento %s ya liquidado (sum=%s cod=%s) "
                           "— no-op idempotente", id_documento, id_suministrador, codigo)
                return {"ok": False, "motivo": "ya_liquidado"}
            for id_tx, toma, _precio, _comision in plan:
                cur.execute(
                    "UPDATE b2b_consignacion_saldo SET cantidad_consumida=cantidad_consumida+%s "
                    "WHERE id_tx=%s AND codigo_articulo=%s", (toma, id_tx, codigo))
                # id_documento=NULL a propósito (igual que DEPOSITO, ver `_registrar_deposito_
                # consignacion`): un mismo evento puede generar VARIAS filas CONSUMO (una por
                # depósito drenado) que compartirían (id_suministrador, codigo, 'CONSUMO',
                # id_documento) si llevaran el id_documento real — chocarían entre sí. Solo la fila
                # LIQUIDACION (única por evento) lleva el id_documento real y está sujeta al reclamo.
                cur.execute(
                    "INSERT INTO b2b_consignacion_movimientos (id_tx, id_suministrador, "
                    "codigo_articulo, tipo, cantidad, id_documento) VALUES (%s,%s,%s,'CONSUMO',%s,NULL)",
                    (id_tx, id_suministrador, codigo, toma))
    except Exception as e:
        logger.error("registrar_consumo_consignacion(%s,%s,evento=%s): %s", id_suministrador, codigo,
                    id_documento, e)
        return {"ok": False, "error": "error_interno"}

    # Auto-factura: el reclamo (INSERT LIQUIDACION) y el consumo de saldo YA quedaron confirmados
    # arriba pase lo que pase de aquí en adelante — un fallo generando la factura es una
    # inconsistencia contable REAL que se loguea alto para revisión manual, nunca se reintenta solo
    # (reintentar aquí con el mismo id_documento chocaría con `uq_bcm_liquidacion` — el propio reclamo
    # ya consumido — y con un id_documento distinto facturaría dos veces el mismo evento). Se elige
    # DELIBERADAMENTE no borrar el reclamo, a diferencia de `_borrar_liquidacion_placeholder` en
    # `b2b_rappels.py`: aquella libera un PLACEHOLDER vacío (gasto_total=0, sin ningún efecto de
    # negocio aún aplicado) — la fila `LIQUIDACION` de aquí, en cambio, YA representa un hecho real y
    # completo (saldo consumido, `cantidad`/`id_documento` verdaderos), no un hueco reservado; una
    # línea de tiempo donde una liquidación ya aplicada pudiera "desaparecer" sería peor que una
    # liquidación real sin factura visible para revisión.
    # Importe por unidad facturado (Portal B2B, Fase 1): `precio_unitario + comision_unitaria`, ambos
    # ya congelados en el depósito (`_registrar_deposito_consignacion`). Cambio ADITIVO y
    # retrocompatible por construcción: `comision_unitaria` es `DEFAULT 0` en toda fila de
    # `b2b_consignacion_saldo` creada antes de esta migración (o depositada desde un artículo sin
    # comisión declarada), así que `precio + 0 == precio` — el importe no cambia para ningún caso
    # existente. Ningún otro dato de `plan` (reparto FIFO, `toma`, idempotencia) se toca.
    lineas_factura = [{"codigo": codigo, "cantidad": toma, "precio_unitario": precio + comision}
                      for _id_tx, toma, precio, comision in plan]
    id_proveedor = None
    id_factura = None
    try:
        from src.services.compras.b2b_rappels import resolver_id_proveedor
        id_proveedor = resolver_id_proveedor(id_suministrador)
        if not id_proveedor:
            logger.error("registrar_consumo_consignacion: sin proveedor tradicional vinculado a "
                        "id_suministrador=%s — evento %s YA reclamado/consumido SIN factura "
                        "(revisión manual, proveedores.id_suministrador sin homologar)",
                        id_suministrador, id_documento)
        else:
            from src.db import compras as C
            id_factura = C.registrar_factura(
                id_proveedor=id_proveedor,
                numero_factura=f"CONSIG-{id_suministrador}-{codigo}-{id_documento}",
                lineas=lineas_factura, id_empresa=id_empresa, tipo_documento="factura",
                fecha_factura=_dt_hoy(), observaciones=f"Liquidación consignación · evento {id_documento}")
            if not id_factura:
                logger.error("registrar_consumo_consignacion: registrar_factura devolvió None — "
                            "evento %s YA reclamado/consumido SIN factura (revisión manual)",
                            id_documento)
    except Exception as e:
        logger.error("registrar_consumo_consignacion: fallo generando factura tras reclamo ya "
                    "confirmado (evento %s): %s — revisión manual", id_documento, e)
    return {"ok": True, "cantidad_liquidada": cantidad_liquidada, "id_tx_principal": id_tx_principal,
           "reparto": [{"id_tx": t, "cantidad": c} for t, c, _p, _com in plan],
           "id_proveedor": id_proveedor, "id_factura": id_factura}


def _dt_hoy():
    import datetime as _dt
    return _dt.date.today().isoformat()


# ── Devolución al proveedor (Fase C, punto 5) ────────────────────────────────
def solicitar_devolucion_consignacion(id_tx, codigo, cantidad, actor=None) -> dict:
    """Devuelve `cantidad` unidades de `codigo` en consignación del pedido de depósito `id_tx` al
    proveedor, SIN impacto financiero — estructuralmente, no como caso especial: consume el stock
    físico con `tipo='DEVOLUCION_PROVEEDOR'` (tipo ya existente en `lotes.TIPOS_SALIDA`), que
    `db.lotes._liquidar_consumo_consignacion` EXCLUYE a propósito del disparador de auto-factura (Fase
    C, punto 4) — una devolución nunca puede generar una liquidación/factura por construcción, no
    porque aquí se evite llamar a la facturación.

    LIMITACIÓN CONOCIDA Y DOCUMENTADA (alcance de la Fase C, no un descuido): `consumir_fefo` no
    filtra por `propiedad`/`id_suministrador`/`id_tx` de origen — si el mismo artículo tuviera A LA
    VEZ lotes propios y de consignación de proveedores distintos, la devolución podría consumir
    físicamente del lote FEFO más próximo a caducar SIN que sea necesariamente el de ESTE `id_tx`
    (mismo comportamiento que tendría cualquier otra salida). La validación de `cantidad_disponible`
    contra el LEDGER de este `id_tx` (abajo) sigue siendo correcta como control financiero/contable;
    solo la trazabilidad física exacta lote-a-lote no está garantizada en ese escenario mixto, que no
    se da en el uso normal (un artículo de consignación de un proveedor no se compra también en
    firme al mismo tiempo salvo decisión explícita del comprador)."""
    from src.db.conexion import obtener_conexion, transaccion
    import uuid
    cantidad = int(cantidad or 0)
    if not id_tx or not codigo or cantidad <= 0:
        return {"ok": False, "error": "parametros_invalidos"}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT cantidad_depositada, cantidad_consumida, cantidad_devuelta, id_empresa, "
                "id_suministrador FROM b2b_consignacion_saldo WHERE id_tx=%s AND codigo_articulo=%s",
                (id_tx, codigo))
            row = cur.fetchone()
            if not row:
                return {"ok": False, "error": "saldo_no_encontrado"}
            saldo = row if isinstance(row, dict) else dict(zip([d[0] for d in cur.description], row))
    except Exception as e:
        logger.error("solicitar_devolucion_consignacion(%s,%s): %s", id_tx, codigo, e)
        return {"ok": False, "error": "error_interno"}

    disponible = (int(saldo["cantidad_depositada"]) - int(saldo["cantidad_consumida"])
                 - int(saldo["cantidad_devuelta"]))
    if cantidad > disponible:
        return {"ok": False, "error": "cantidad_supera_disponible", "disponible": disponible}

    # Corto a propósito: comparte columna con `lotes_movimientos.id_documento` (VARCHAR(50), el
    # límite más estrecho de los dos ledgers que lo usan) — el prefijo del id_tx (8 chars) + un
    # sufijo aleatorio bastan para que sea único por llamada sin acercarse a ese límite.
    id_doc = f"CDEV-{id_tx[:8]}-{uuid.uuid4().hex[:12]}"
    from src.db import lotes as L
    r = L.consumir_fefo(codigo, cantidad, tipo="DEVOLUCION_PROVEEDOR", id_documento=id_doc,
                        id_empresa=saldo["id_empresa"], usuario=actor,
                        observaciones=f"Devolución consignación {id_tx}")
    devuelto = int(r.get("consumido") or 0)
    if devuelto <= 0:
        return {"ok": False, "error": "sin_stock_fisico_disponible", "detalle": r}
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE b2b_consignacion_saldo SET cantidad_devuelta=cantidad_devuelta+%s "
                "WHERE id_tx=%s AND codigo_articulo=%s", (devuelto, id_tx, codigo))
            cur.execute(
                "INSERT INTO b2b_consignacion_movimientos (id_tx, id_suministrador, codigo_articulo, "
                "tipo, cantidad, id_documento) VALUES (%s,%s,%s,'DEVOLUCION',%s,%s)",
                (id_tx, saldo["id_suministrador"], codigo, devuelto, id_doc))
    except Exception as e:
        logger.error("solicitar_devolucion_consignacion: saldo consumido físicamente (%s uds) pero "
                    "fallo actualizando el ledger (%s,%s): %s — revisión manual", devuelto, id_tx,
                    codigo, e)
        return {"ok": False, "error": "error_actualizando_ledger", "devuelto_fisicamente": devuelto}
    return {"ok": True, "devuelto": devuelto, "faltante": cantidad - devuelto, "id_documento": id_doc}


def _marcar_reposicion_tramitada(lineas):
    from src.db import reabastecimiento as R
    for ln in lineas:
        if ln.get("origen") == "reposicion" and ln.get("id_reab_propuesta"):
            try:
                R.cambiar_estado_propuesta(ln["id_reab_propuesta"], "tramitada")
            except Exception as e:
                logger.debug("_marcar_reposicion_tramitada(%s): %s", ln["id_reab_propuesta"], e)
