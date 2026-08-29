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


def tramitar(token_sesion) -> dict:
    from src.services.compras import b2b_carrito
    from src.services.compras import b2b_sesion_empresa as SES
    from src.services.comercio_digital import transacciones as TX

    sesion = SES.resolver_sesion(token_sesion)
    if not sesion:
        return {"ok": False, "error": "sesion_invalida"}
    lineas = b2b_carrito.listar(token_sesion)
    if not lineas:
        return {"ok": False, "error": "carrito_vacio"}

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
                                  "usuario": sesion.get("nombre_usuario")})
        if not id_tx:
            logger.error("tramitar: no se pudo crear transacción para suministrador %s", id_suministrador)
            continue
        _fijar_suministrador_y_unidades(id_tx, id_suministrador, sesion["id_tienda"], lns)
        r = TX.transicionar(id_tx, "CONFIRMADA", actor=sesion.get("nombre_usuario"),
                            id_empresa=sesion["id_empresa"], motivo="Pedido B2B tramitado")
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


def _fijar_suministrador_y_unidades(id_tx, id_suministrador, id_tienda, lineas):
    """Completa las columnas propias de Smart Suppliers (migración 0221) que `transacciones.crear`
    no conoce — sin tocar esa función existente (aditivo, cabecera + líneas del motor genérico ya
    quedaron creadas correctamente)."""
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE transaccion_comercial SET id_suministrador=%s, id_tienda_destino=%s "
                        "WHERE id_tx=%s", (id_suministrador, id_tienda, id_tx))
            for ln in lineas:
                cur.execute("UPDATE transaccion_lineas SET unidad_medida=%s WHERE id_tx=%s "
                            "AND codigo_articulo=%s", (ln.get("unidad_medida"), id_tx, ln["codigo"]))
            conn.commit()
    except Exception as e:
        logger.error("_fijar_suministrador_y_unidades(%s): %s", id_tx, e)


def _marcar_reposicion_tramitada(lineas):
    from src.db import reabastecimiento as R
    for ln in lineas:
        if ln.get("origen") == "reposicion" and ln.get("id_reab_propuesta"):
            try:
                R.cambiar_estado_propuesta(ln["id_reab_propuesta"], "tramitada")
            except Exception as e:
                logger.debug("_marcar_reposicion_tramitada(%s): %s", ln["id_reab_propuesta"], e)
