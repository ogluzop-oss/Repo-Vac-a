"""
Capa de datos de COMPRAS (E2) — pedidos, recepción, costes, facturas, informes.

Ciclo: proveedor → pedido → recepción (stock + movimientos) → costes → factura.
Multiempresa por `id_empresa`. Reutiliza `articulos`/`movimientos_stock` existentes
sin romper TPV/stock/catálogo. Operaciones que mueven stock son ATÓMICAS
(`transaccion()`).

Este módulo crece por subfases (E2.2 pedidos; E2.3 recepción; E2.4 costes;
E2.5 facturas; E2.6 informes).
"""

import logging

from src.db.conexion import (EMPRESA_DEFAULT_ID, _fila_a_dict, _filas_a_dicts,
                             ensure_schema, obtener_conexion, transaccion)

logger = logging.getLogger("compras_db")

ESTADOS_PEDIDO = ("BORRADOR", "ENVIADO", "PARCIAL", "RECIBIDO", "CANCELADO")
# Transiciones permitidas.
_TRANSICIONES = {
    "BORRADOR": {"ENVIADO", "CANCELADO"},
    "ENVIADO": {"PARCIAL", "RECIBIDO", "CANCELADO"},
    "PARCIAL": {"PARCIAL", "RECIBIDO", "CANCELADO"},
    "RECIBIDO": set(),
    "CANCELADO": set(),
}


def _empresa(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def _hoy():
    import datetime as _dt
    return _dt.date.today().strftime("%Y-%m-%d")


# ── Pedidos de compra (E2.2) ─────────────────────────────────────────────────
def crear_pedido(id_proveedor=None, lineas=None, observaciones=None, usuario=None,
                 id_empresa=None) -> int | None:
    """Crea un pedido en BORRADOR con sus líneas. `lineas`: [{codigo, descripcion,
    cantidad, precio_unitario}]. Calcula subtotales y total."""
    id_empresa = _empresa(id_empresa)
    lineas = lineas or []
    try:
        ensure_schema()
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO compras_pedidos (id_empresa, id_proveedor, estado, "
                "observaciones, usuario) VALUES (%s,%s,'BORRADOR',%s,%s)",
                (id_empresa, id_proveedor, observaciones, usuario))
            pid = cur.lastrowid
            cur.execute("UPDATE compras_pedidos SET numero=%s WHERE id_pedido=%s",
                        (f"PC{pid:06d}", pid))
            total = _insertar_lineas(cur, pid, lineas)
            cur.execute("UPDATE compras_pedidos SET total=%s WHERE id_pedido=%s", (total, pid))
        return pid
    except Exception as e:
        logger.error("crear_pedido: %s", e)
        return None


def _insertar_lineas(cur, id_pedido, lineas) -> float:
    total = 0.0
    for ln in lineas:
        cant = int(ln.get("cantidad") or 0)
        precio = round(float(ln.get("precio_unitario") or 0), 2)
        subtotal = round(cant * precio, 2)
        total += subtotal
        cur.execute(
            "INSERT INTO compras_pedidos_lineas (id_pedido, codigo_articulo, descripcion, "
            "cantidad, precio_unitario, subtotal) VALUES (%s,%s,%s,%s,%s,%s)",
            (id_pedido, ln.get("codigo") or ln.get("codigo_articulo"),
             ln.get("descripcion"), cant, precio, subtotal))
    return round(total, 2)


def obtener_pedido(id_pedido, id_empresa=None) -> dict | None:
    """Cabecera + líneas del pedido."""
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM compras_pedidos WHERE id_pedido=%s AND id_empresa=%s",
                        (id_pedido, id_empresa))
            cab = _fila_a_dict(cur, cur.fetchone())
            if not cab:
                return None
            cur.execute("SELECT * FROM compras_pedidos_lineas WHERE id_pedido=%s ORDER BY id",
                        (id_pedido,))
            cab["lineas"] = _filas_a_dicts(cur, cur.fetchall())
            return cab
    except Exception as e:
        logger.error("obtener_pedido(%s): %s", id_pedido, e)
        return None


def listar_pedidos(id_empresa=None, estado=None, id_proveedor=None, limite=500) -> list:
    id_empresa = _empresa(id_empresa)
    filtros, params = ["id_empresa=%s"], [id_empresa]
    if estado:
        filtros.append("estado=%s"); params.append(estado)
    if id_proveedor:
        filtros.append("id_proveedor=%s"); params.append(id_proveedor)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM compras_pedidos WHERE " + " AND ".join(filtros)
                        + " ORDER BY id_pedido DESC LIMIT %s", (*params, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_pedidos: %s", e)
        return []


def modificar_lineas(id_pedido, lineas, id_empresa=None) -> bool:
    """Reemplaza las líneas de un pedido (solo en BORRADOR) y recalcula el total."""
    id_empresa = _empresa(id_empresa)
    ped = obtener_pedido(id_pedido, id_empresa)
    if not ped or ped["estado"] != "BORRADOR":
        return False
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM compras_pedidos_lineas WHERE id_pedido=%s", (id_pedido,))
            total = _insertar_lineas(cur, id_pedido, lineas)
            cur.execute("UPDATE compras_pedidos SET total=%s WHERE id_pedido=%s", (total, id_pedido))
        return True
    except Exception as e:
        logger.error("modificar_lineas(%s): %s", id_pedido, e)
        return False


def cambiar_estado(id_pedido, nuevo_estado, id_empresa=None) -> bool:
    """Cambia el estado validando la transición permitida."""
    id_empresa = _empresa(id_empresa)
    if nuevo_estado not in ESTADOS_PEDIDO:
        return False
    ped = obtener_pedido(id_pedido, id_empresa)
    if not ped:
        return False
    if nuevo_estado != ped["estado"] and nuevo_estado not in _TRANSICIONES.get(ped["estado"], set()):
        logger.warning("Transición no permitida %s->%s (pedido %s)", ped["estado"], nuevo_estado, id_pedido)
        return False
    campos = "estado=%s"
    params = [nuevo_estado]
    if nuevo_estado == "ENVIADO":
        campos += ", fecha_envio=NOW()"
    if nuevo_estado == "RECIBIDO":
        campos += ", fecha_recepcion=NOW()"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE compras_pedidos SET {campos} WHERE id_pedido=%s AND id_empresa=%s",
                        (*params, id_pedido, id_empresa))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception as e:
        logger.error("cambiar_estado(%s): %s", id_pedido, e)
        return False


def enviar_pedido(id_pedido, id_empresa=None) -> bool:
    return cambiar_estado(id_pedido, "ENVIADO", id_empresa)


def cancelar_pedido(id_pedido, id_empresa=None) -> bool:
    return cambiar_estado(id_pedido, "CANCELADO", id_empresa)


# ── Recepción contra pedido (E2.3) ───────────────────────────────────────────
def recibir(id_pedido, lineas_recibidas, usuario=None, observaciones=None,
            id_empresa=None) -> dict | None:
    """Registra una recepción (parcial o total) de un pedido. `lineas_recibidas`:
    [{id_linea|codigo, cantidad}]. Suma a cantidad_recibida, ACTUALIZA STOCK
    (articulos.Stock_total/Stock_central) y genera movimientos_stock. Recalcula el
    estado del pedido (PARCIAL/RECIBIDO). Todo ATÓMICO. Devuelve
    {id_recepcion, estado_pedido, unidades} o None."""
    id_empresa = _empresa(id_empresa)
    ped = obtener_pedido(id_pedido, id_empresa)
    if not ped or ped["estado"] not in ("ENVIADO", "PARCIAL"):
        logger.warning("recibir: pedido %s no recepcionable (estado %s)",
                       id_pedido, ped.get("estado") if ped else None)
        return None
    lineas_por_id = {ln["id"]: ln for ln in ped["lineas"]}
    _recibidos_cod = set()
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO compras_recepciones (id_empresa, id_pedido, usuario, "
                        "observaciones) VALUES (%s,%s,%s,%s)",
                        (id_empresa, id_pedido, usuario, observaciones))
            rid = cur.lastrowid
            unidades = 0
            for rec in lineas_recibidas:
                cant = int(rec.get("cantidad") or 0)
                if cant <= 0:
                    continue
                lp = lineas_por_id.get(rec.get("id_linea"))
                if lp is None and rec.get("codigo"):
                    lp = next((x for x in ped["lineas"]
                               if x["codigo_articulo"] == rec["codigo"]), None)
                codigo = (lp or {}).get("codigo_articulo") or rec.get("codigo")
                id_linea = (lp or {}).get("id")
                cur.execute("INSERT INTO compras_recepciones_lineas (id_recepcion, "
                            "id_linea_pedido, codigo_articulo, cantidad) VALUES (%s,%s,%s,%s)",
                            (rid, id_linea, codigo, cant))
                if id_linea is not None:
                    cur.execute("UPDATE compras_pedidos_lineas SET cantidad_recibida="
                                "cantidad_recibida+%s WHERE id=%s", (cant, id_linea))
                # Entrada de stock (almacén central) — solo si el artículo existe.
                if codigo:
                    precio = round(float((lp or {}).get("precio_unitario") or 0), 2)
                    cur.execute("SELECT COALESCE(Stock_total,0) FROM articulos WHERE codigo=%s",
                                (codigo,))
                    fila_prev = cur.fetchone()
                    stock_previo = (fila_prev[0] if fila_prev and not isinstance(fila_prev, dict)
                                    else (list(fila_prev.values())[0] if fila_prev else None))
                    cur.execute("UPDATE articulos SET Stock_total=COALESCE(Stock_total,0)+%s, "
                                "Stock_central=COALESCE(Stock_central,0)+%s WHERE codigo=%s",
                                (cant, cant, codigo))
                    if fila_prev is not None and precio > 0:
                        _actualizar_costes(cur, codigo, int(stock_previo or 0), cant, precio)
                    cur.execute(
                        "INSERT INTO movimientos_stock (codigo_articulo, tipo_movimiento, "
                        "cantidad, id_documento, origen, usuario, observaciones) "
                        "VALUES (%s,'ENTRADA_COMPRA',%s,%s,%s,%s,%s)",
                        (codigo, cant, f"PC{id_pedido}-R{rid}", "compra", usuario,
                         f"Recepción compra pedido {id_pedido}"))
                    _recibidos_cod.add(codigo)
                unidades += cant
            cur.execute("UPDATE compras_recepciones SET total_unidades=%s WHERE id_recepcion=%s",
                        (unidades, rid))
            # Recalcular estado del pedido.
            cur.execute("SELECT SUM(GREATEST(cantidad-cantidad_recibida,0)) AS pendiente, "
                        "SUM(cantidad_recibida) AS recibido FROM compras_pedidos_lineas "
                        "WHERE id_pedido=%s", (id_pedido,))
            r = cur.fetchone()
            pendiente = (r["pendiente"] if isinstance(r, dict) else r[0]) or 0
            recibido = (r["recibido"] if isinstance(r, dict) else r[1]) or 0
            nuevo = "RECIBIDO" if pendiente == 0 else ("PARCIAL" if recibido > 0 else ped["estado"])
            extra = ", fecha_recepcion=NOW()" if nuevo == "RECIBIDO" else ""
            cur.execute(f"UPDATE compras_pedidos SET estado=%s{extra} WHERE id_pedido=%s",
                        (nuevo, id_pedido))
        # INV.4.6: sincroniza el ledger multialmacén (almacén central) tras la recepción.
        try:
            from src.db import stock_almacen as SA
            for cod in _recibidos_cod:
                SA.reseed_articulo(cod, id_empresa)
        except Exception:
            pass
        return {"id_recepcion": rid, "estado_pedido": nuevo, "unidades": unidades}
    except Exception as e:
        logger.error("recibir(%s): %s", id_pedido, e)
        return None


def _actualizar_costes(cur, codigo, stock_previo, cantidad, precio):
    """Actualiza costes del artículo tras una entrada (E2.4): último/actual = precio
    de compra; medio = media ponderada por existencias. Tolerante si faltan columnas
    (instalaciones antiguas sin migración 0011)."""
    try:
        cur.execute("SELECT COALESCE(coste_medio,0) FROM articulos WHERE codigo=%s", (codigo,))
        r = cur.fetchone()
        medio_old = float((r[0] if r and not isinstance(r, dict) else
                           (list(r.values())[0] if r else 0)) or 0)
        prev = max(int(stock_previo or 0), 0)
        nuevo_total = prev + int(cantidad)
        medio = round(((medio_old * prev) + (precio * cantidad)) / nuevo_total, 2) if nuevo_total else precio
        cur.execute("UPDATE articulos SET ultimo_coste=%s, coste_actual=%s, coste_medio=%s "
                    "WHERE codigo=%s", (precio, precio, medio, codigo))
    except Exception as e:
        logger.debug("No se pudieron actualizar costes (%s): %s", codigo, e)


def obtener_costes(codigo) -> dict:
    """Costes de aprovisionamiento del artículo."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT ultimo_coste, coste_actual, coste_medio FROM articulos "
                        "WHERE codigo=%s", (codigo,))
            r = cur.fetchone()
            if not r:
                return {}
            if isinstance(r, dict):
                return {k: float(v or 0) for k, v in r.items()}
            return {"ultimo_coste": float(r[0] or 0), "coste_actual": float(r[1] or 0),
                    "coste_medio": float(r[2] or 0)}
    except Exception as e:
        logger.error("obtener_costes(%s): %s", codigo, e)
        return {}


def listar_recepciones(id_pedido, id_empresa=None) -> list:
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM compras_recepciones WHERE id_pedido=%s AND id_empresa=%s "
                        "ORDER BY id_recepcion", (id_pedido, id_empresa))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_recepciones(%s): %s", id_pedido, e)
        return []


# ── Facturas de proveedor (E2.5) ─────────────────────────────────────────────
def registrar_factura(id_proveedor=None, numero_factura=None, lineas=None,
                      id_pedido=None, id_recepcion=None, base=None, iva=None,
                      fecha_factura=None, observaciones=None, id_empresa=None) -> int | None:
    """Registra una factura recibida de proveedor (registro documental + trazabilidad).
    Si no se pasan base/iva, base = suma de líneas e iva = 0. Total = base + iva."""
    id_empresa = _empresa(id_empresa)
    lineas = lineas or []
    base_calc = round(sum(int(l.get("cantidad") or 0) * round(float(l.get("precio_unitario") or 0), 2)
                          for l in lineas), 2)
    base_f = round(float(base), 2) if base is not None else base_calc
    iva_f = round(float(iva or 0), 2)
    total_f = round(base_f + iva_f, 2)
    try:
        ensure_schema()
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO compras_facturas (id_empresa, id_proveedor, id_pedido, id_recepcion, "
                "numero_factura, fecha_factura, base, iva, total, observaciones) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, id_proveedor, id_pedido, id_recepcion, numero_factura,
                 fecha_factura, base_f, iva_f, total_f, observaciones))
            fid = cur.lastrowid
            for l in lineas:
                cant = int(l.get("cantidad") or 0)
                precio = round(float(l.get("precio_unitario") or 0), 2)
                cur.execute(
                    "INSERT INTO compras_facturas_lineas (id_factura, codigo_articulo, "
                    "descripcion, cantidad, precio_unitario, subtotal) VALUES (%s,%s,%s,%s,%s,%s)",
                    (fid, l.get("codigo") or l.get("codigo_articulo"), l.get("descripcion"),
                     cant, precio, round(cant * precio, 2)))
        # E6.5: encola el asiento de compra (no-op si la contabilidad está apagada).
        try:
            from src.services.contabilidad.posting import encolar_compra
            encolar_compra(fid, total_f, fecha_factura or _hoy(), id_empresa=id_empresa,
                           base=base_f, iva=iva_f)
        except Exception:
            pass
        return fid
    except Exception as e:
        logger.error("registrar_factura: %s", e)
        return None


def obtener_factura(id_factura, id_empresa=None) -> dict | None:
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM compras_facturas WHERE id_factura=%s AND id_empresa=%s",
                        (id_factura, id_empresa))
            cab = _fila_a_dict(cur, cur.fetchone())
            if not cab:
                return None
            cur.execute("SELECT * FROM compras_facturas_lineas WHERE id_factura=%s ORDER BY id",
                        (id_factura,))
            cab["lineas"] = _filas_a_dicts(cur, cur.fetchall())
            return cab
    except Exception as e:
        logger.error("obtener_factura(%s): %s", id_factura, e)
        return None


def listar_facturas(id_empresa=None, id_proveedor=None, id_pedido=None, limite=500) -> list:
    id_empresa = _empresa(id_empresa)
    filtros, params = ["id_empresa=%s"], [id_empresa]
    if id_proveedor:
        filtros.append("id_proveedor=%s"); params.append(id_proveedor)
    if id_pedido:
        filtros.append("id_pedido=%s"); params.append(id_pedido)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM compras_facturas WHERE " + " AND ".join(filtros)
                        + " ORDER BY id_factura DESC LIMIT %s", (*params, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_facturas: %s", e)
        return []


def validar_factura(id_factura, tolerancia=0.01, id_empresa=None) -> dict:
    """Valida la factura contra el total del pedido vinculado. Marca 'validada' si
    coincide (±tolerancia) o 'con_diferencias' si no. Devuelve el diagnóstico."""
    id_empresa = _empresa(id_empresa)
    fac = obtener_factura(id_factura, id_empresa)
    if not fac:
        return {"ok": False, "error": "factura inexistente"}
    referencia = None
    if fac.get("id_pedido"):
        ped = obtener_pedido(fac["id_pedido"], id_empresa)
        referencia = float(ped["total"]) if ped else None
    diff = None if referencia is None else round(float(fac["total"]) - referencia, 2)
    coincide = referencia is not None and abs(diff) <= tolerancia
    estado = "validada" if coincide else ("con_diferencias" if referencia is not None else "registrada")
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE compras_facturas SET estado=%s WHERE id_factura=%s AND id_empresa=%s",
                        (estado, id_factura, id_empresa))
            conn.commit()
    except Exception as e:
        logger.error("validar_factura(%s): %s", id_factura, e)
    return {"ok": coincide, "estado": estado, "total_factura": float(fac["total"]),
            "total_pedido": referencia, "diferencia": diff}


# ── Informes de compras (E2.6) ───────────────────────────────────────────────
def _rango(cur_sql, params, desde, hasta, campo):
    if desde:
        cur_sql.append(f"{campo}>=%s"); params.append(desde)
    if hasta:
        cur_sql.append(f"{campo}<=%s"); params.append(hasta)


def compras_por_proveedor(desde=None, hasta=None, id_empresa=None) -> list:
    """Gasto facturado por proveedor (facturas registradas). [{id_proveedor, proveedor,
    facturas, total}]."""
    id_empresa = _empresa(id_empresa)
    filtros, params = ["f.id_empresa=%s"], [id_empresa]
    _rango(filtros, params, desde, hasta, "f.fecha_factura")
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT f.id_proveedor, COALESCE(p.razon_social,'(sin proveedor)') AS proveedor, "
                "COUNT(*) AS facturas, COALESCE(SUM(f.total),0) AS total "
                "FROM compras_facturas f LEFT JOIN proveedores p ON p.id_proveedor=f.id_proveedor "
                "WHERE " + " AND ".join(filtros) + " GROUP BY f.id_proveedor, proveedor "
                "ORDER BY total DESC", tuple(params))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("compras_por_proveedor: %s", e)
        return []


def compras_por_periodo(desde=None, hasta=None, id_empresa=None) -> list:
    """Gasto facturado agrupado por mes (AAAA-MM). [{periodo, facturas, total}]."""
    id_empresa = _empresa(id_empresa)
    filtros, params = ["id_empresa=%s", "fecha_factura IS NOT NULL"], [id_empresa]
    _rango(filtros, params, desde, hasta, "fecha_factura")
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT DATE_FORMAT(fecha_factura,'%%Y-%%m') AS periodo, COUNT(*) AS facturas, "
                "COALESCE(SUM(total),0) AS total FROM compras_facturas WHERE "
                + " AND ".join(filtros) + " GROUP BY periodo ORDER BY periodo", tuple(params))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("compras_por_periodo: %s", e)
        return []


def costes_por_articulo(id_empresa=None, limite=500) -> list:
    """Compras por artículo (líneas de factura): unidades, gasto y precio medio.
    [{codigo_articulo, unidades, gasto, precio_medio}]."""
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT l.codigo_articulo, COALESCE(SUM(l.cantidad),0) AS unidades, "
                "COALESCE(SUM(l.subtotal),0) AS gasto FROM compras_facturas_lineas l "
                "JOIN compras_facturas f ON f.id_factura=l.id_factura "
                "WHERE f.id_empresa=%s AND l.codigo_articulo IS NOT NULL "
                "GROUP BY l.codigo_articulo ORDER BY gasto DESC LIMIT %s",
                (id_empresa, int(limite)))
            filas = _filas_a_dicts(cur, cur.fetchall())
        for r in filas:
            u = float(r.get("unidades") or 0)
            r["precio_medio"] = round(float(r.get("gasto") or 0) / u, 2) if u else 0.0
        return filas
    except Exception as e:
        logger.error("costes_por_articulo: %s", e)
        return []


def historico_pedidos(id_empresa=None, id_proveedor=None, limite=500) -> list:
    """Histórico de pedidos con nombre de proveedor."""
    id_empresa = _empresa(id_empresa)
    filtros, params = ["c.id_empresa=%s"], [id_empresa]
    if id_proveedor:
        filtros.append("c.id_proveedor=%s"); params.append(id_proveedor)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT c.id_pedido, c.numero, c.estado, c.total, c.fecha, "
                "COALESCE(p.razon_social,'') AS proveedor FROM compras_pedidos c "
                "LEFT JOIN proveedores p ON p.id_proveedor=c.id_proveedor "
                "WHERE " + " AND ".join(filtros) + " ORDER BY c.id_pedido DESC LIMIT %s",
                (*params, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("historico_pedidos: %s", e)
        return []


def crear_pedido_desde_propuestas(propuesta_ids=None, id_proveedor=None, usuario=None,
                                  id_empresa=None) -> int | None:
    """E2.7 — Convierte sugerencias de reabastecimiento (estado 'pendiente') en un
    pedido de compra BORRADOR. Reutiliza `reabastecimiento.listar_propuestas` y los
    costes del artículo como precio estimado; marca las propuestas como 'pedido'.
    Si `propuesta_ids` es None, toma todas las pendientes."""
    try:
        from src.db import reabastecimiento as R
    except Exception as e:
        logger.error("reabastecimiento no disponible: %s", e)
        return None
    pendientes = R.listar_propuestas(("pendiente",))
    if propuesta_ids is not None:
        ids = set(propuesta_ids)
        pendientes = [p for p in pendientes if p["id"] in ids]
    if not pendientes:
        return None
    lineas = []
    for p in pendientes:
        costes = obtener_costes(p["codigo"]) or {}
        precio = costes.get("coste_actual") or costes.get("ultimo_coste") or 0
        lineas.append({"codigo": p["codigo"], "descripcion": p.get("nombre"),
                       "cantidad": int(p.get("cantidad") or 0), "precio_unitario": precio})
    pid = crear_pedido(id_proveedor=id_proveedor, lineas=lineas, usuario=usuario,
                       observaciones="Generado desde reabastecimiento", id_empresa=id_empresa)
    if pid:
        for p in pendientes:
            R.cambiar_estado_propuesta(p["id"], "pedido")
    return pid


def proveedores_mas_utilizados(id_empresa=None, limite=20) -> list:
    """Ranking de proveedores por nº de pedidos (excluye CANCELADO)."""
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT c.id_proveedor, COALESCE(p.razon_social,'(sin proveedor)') AS proveedor, "
                "COUNT(*) AS pedidos, COALESCE(SUM(c.total),0) AS total FROM compras_pedidos c "
                "LEFT JOIN proveedores p ON p.id_proveedor=c.id_proveedor "
                "WHERE c.id_empresa=%s AND c.estado<>'CANCELADO' "
                "GROUP BY c.id_proveedor, proveedor ORDER BY pedidos DESC, total DESC LIMIT %s",
                (id_empresa, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("proveedores_mas_utilizados: %s", e)
        return []
