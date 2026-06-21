"""
Inventario físico / recuento auditado (INV.2).

Cabecera `inventarios` + líneas `inventario_lineas`. El cierre genera AJUSTES reales de
stock con trazabilidad completa y registra el movimiento en el kárdex (INV.1). No modifica
TPV/compras/logística. Multiempresa/multitienda por id_empresa/id_tienda.

Estados: BORRADOR → ABIERTO → CERRADO; ANULADO desde BORRADOR/ABIERTO. Un inventario
CERRADO o ANULADO no es editable.
"""

import logging

from src.db.conexion import (_fila_a_dict, _filas_a_dicts, ensure_schema,
                             obtener_conexion, transaccion)

logger = logging.getLogger("inventario.fisico")

BORRADOR, ABIERTO, CERRADO, ANULADO = "BORRADOR", "ABIERTO", "CERRADO", "ANULADO"
_EDITABLES = (BORRADOR, ABIERTO)


class InventarioError(Exception):
    """Operación de inventario no permitida (estado, artículo o inventario inválido)."""


def _tenant(id_empresa=None, id_tienda=None):
    try:
        from src.db.empresa import empresa_actual_id, tienda_actual_id
        return (id_empresa or empresa_actual_id(),
                id_tienda if id_tienda is not None else tienda_actual_id())
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return (id_empresa or EMPRESA_DEFAULT_ID), id_tienda


def _stock_actual(cur, codigo, id_empresa):
    """Stock disponible del artículo (Stock_total + Stock_tienda). None si no existe."""
    cur.execute("SELECT COALESCE(Stock_total,0) AS t, COALESCE(Stock_tienda,0) AS ti "
                "FROM articulos WHERE codigo=%s AND id_empresa=%s", (codigo, id_empresa))
    r = cur.fetchone()
    if not r:
        return None
    if isinstance(r, dict):
        return int(r["t"]) + int(r["ti"]), int(r["t"]), int(r["ti"])
    return int(r[0]) + int(r[1]), int(r[0]), int(r[1])


def _cabecera(cur, id_inv, id_empresa):
    cur.execute("SELECT * FROM inventarios WHERE id=%s AND id_empresa=%s", (id_inv, id_empresa))
    return _fila_a_dict(cur, cur.fetchone())


# ── Ciclo de vida ─────────────────────────────────────────────────────────────
def crear_inventario(nombre, id_empresa=None, id_tienda=None, usuario=None, id_almacen=None) -> int | None:
    """Crea un inventario. Si `id_almacen` se indica (INV.4.8), el recuento/cierre operan
    sobre stock_almacen de ese almacén; si es NULL, se comporta como INV.2 (agregado)."""
    id_empresa, id_tienda = _tenant(id_empresa, id_tienda)
    try:
        ensure_schema()
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO inventarios (id_empresa, id_tienda, id_almacen, nombre, estado, "
                        "usuario_creacion) VALUES (%s,%s,%s,%s,%s,%s)",
                        (id_empresa, id_tienda, id_almacen, nombre or "Inventario", BORRADOR, usuario))
            return cur.lastrowid
    except Exception as e:
        logger.error("crear_inventario: %s", e)
        return None


def _transicion(id_inv, id_empresa, desde, hacia, **sets):
    id_empresa, _ = _tenant(id_empresa)
    with transaccion() as conn, conn.cursor() as cur:
        cab = _cabecera(cur, id_inv, id_empresa)
        if not cab:
            raise InventarioError("Inventario no encontrado.")
        if cab["estado"] not in (desde if isinstance(desde, (tuple, list)) else (desde,)):
            raise InventarioError(f"No se puede pasar de '{cab['estado']}' a '{hacia}'.")
        cols = ["estado=%s"]; params = [hacia]
        for k, v in sets.items():
            cols.append(f"{k}=%s"); params.append(v)
        params += [id_inv, id_empresa]
        cur.execute(f"UPDATE inventarios SET {', '.join(cols)} WHERE id=%s AND id_empresa=%s",
                    params)
    return True


def abrir_inventario(id_inv, id_empresa=None) -> bool:
    return _transicion(id_inv, id_empresa, BORRADOR, ABIERTO,
                       fecha_apertura=_now())


def anular_inventario(id_inv, id_empresa=None) -> bool:
    return _transicion(id_inv, id_empresa, _EDITABLES, ANULADO)


def _now():
    import datetime as _dt
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ── Recuento ──────────────────────────────────────────────────────────────────
def registrar_recuento(id_inv, codigo, contado, observaciones=None, id_empresa=None) -> bool:
    """Registra/actualiza el recuento de un artículo. Captura el stock esperado y calcula
    la diferencia. Rechaza inventarios no editables y artículos inexistentes."""
    id_empresa, _ = _tenant(id_empresa)
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cab = _cabecera(cur, id_inv, id_empresa)
            if not cab:
                raise InventarioError("Inventario no encontrado.")
            if cab["estado"] not in _EDITABLES:
                raise InventarioError(f"Inventario '{cab['estado']}' no editable.")
            st = _stock_actual(cur, codigo, id_empresa)
            if st is None:
                raise InventarioError(f"Artículo '{codigo}' inexistente en la empresa.")
            if cab.get("id_almacen"):       # INV.4.8: esperado por almacén concreto
                cur.execute("SELECT COALESCE(cantidad,0) FROM stock_almacen WHERE id_empresa=%s "
                            "AND id_almacen=%s AND codigo_articulo=%s",
                            (id_empresa, cab["id_almacen"], codigo))
                rr = cur.fetchone()
                esperado = int((rr[0] if not isinstance(rr, dict) else list(rr.values())[0]) or 0) if rr else 0
            else:
                esperado = st[0]
            contado = int(contado)
            diferencia = contado - esperado
            cur.execute(
                "INSERT INTO inventario_lineas (id_inventario, id_empresa, codigo_articulo, "
                "stock_esperado, stock_contado, diferencia, observaciones) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE stock_esperado=VALUES(stock_esperado), "
                "stock_contado=VALUES(stock_contado), diferencia=VALUES(diferencia), "
                "observaciones=VALUES(observaciones)",
                (id_inv, id_empresa, codigo, esperado, contado, diferencia, observaciones))
        return True
    except InventarioError:
        raise
    except Exception as e:
        logger.error("registrar_recuento(%s,%s): %s", id_inv, codigo, e)
        return False


def recalcular_diferencias(id_inv, id_empresa=None) -> int:
    """Recalcula la diferencia de cada línea contada (defensivo). Devuelve nº de líneas."""
    id_empresa, _ = _tenant(id_empresa)
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE inventario_lineas SET diferencia = COALESCE(stock_contado,0) - "
                        "stock_esperado WHERE id_inventario=%s AND id_empresa=%s "
                        "AND stock_contado IS NOT NULL", (id_inv, id_empresa))
            return cur.rowcount
    except Exception as e:
        logger.error("recalcular_diferencias: %s", e)
        return 0


# ── Cierre con ajuste auditado ────────────────────────────────────────────────
def cerrar_inventario(id_inv, usuario=None, id_empresa=None) -> dict:
    """Cierra un inventario ABIERTO y aplica los AJUSTES reales de stock para cada línea
    contada con diferencia ≠ 0. Cada ajuste mantiene esperado/contado/diferencia y genera
    un movimiento AJUSTE en el kárdex (INV.1) con la referencia del inventario."""
    id_empresa, _ = _tenant(id_empresa)
    ajustes = []
    with transaccion() as conn, conn.cursor() as cur:
        cab = _cabecera(cur, id_inv, id_empresa)
        if not cab:
            raise InventarioError("Inventario no encontrado.")
        if cab["estado"] != ABIERTO:
            raise InventarioError(f"Solo se cierra un inventario ABIERTO (actual: {cab['estado']}).")
        id_almacen = cab.get("id_almacen")
        cur.execute("SELECT * FROM inventario_lineas WHERE id_inventario=%s AND id_empresa=%s "
                    "AND stock_contado IS NOT NULL AND diferencia<>0", (id_inv, id_empresa))
        lineas = _filas_a_dicts(cur, cur.fetchall())
        for ln in lineas:
            cod = ln["codigo_articulo"]
            nuevo = int(ln["stock_contado"])
            if id_almacen:                  # INV.4.8: ajuste sobre stock_almacen del almacén
                cur.execute("SELECT COALESCE(cantidad,0) FROM stock_almacen WHERE id_empresa=%s "
                            "AND id_almacen=%s AND codigo_articulo=%s", (id_empresa, id_almacen, cod))
                rr = cur.fetchone()
                anterior = int((rr[0] if not isinstance(rr, dict) else list(rr.values())[0]) or 0) if rr else 0
            else:
                st = _stock_actual(cur, cod, id_empresa)
                if st is None:
                    continue
                anterior, total, _tienda = st
                # Reparte el nuevo total entre Stock_total/Stock_tienda manteniendo la suma exacta.
                if nuevo >= total:
                    n_total, n_tienda = total, nuevo - total
                else:
                    n_total, n_tienda = nuevo, 0
                cur.execute("UPDATE articulos SET Stock_total=%s, Stock_tienda=%s WHERE codigo=%s "
                            "AND id_empresa=%s", (n_total, n_tienda, cod, id_empresa))
            ajustes.append({"codigo": cod, "anterior": anterior, "nuevo": nuevo,
                            "diferencia": nuevo - anterior, "id_tienda": cab.get("id_tienda"),
                            "id_almacen": id_almacen})
        cur.execute("UPDATE inventarios SET estado=%s, fecha_cierre=%s, usuario_cierre=%s "
                    "WHERE id=%s AND id_empresa=%s",
                    (CERRADO, _now(), usuario, id_inv, id_empresa))

    # INV.4.8: si el inventario es por almacén, aplica el ajuste sobre stock_almacen
    # (fuente de verdad) → recalcula la caché automáticamente.
    try:
        if cab.get("id_almacen"):
            from src.db import stock_almacen as SA
            for a in ajustes:
                SA.ajustar_stock(a["codigo"], cab["id_almacen"], a["nuevo"], id_empresa=id_empresa)
    except Exception as e:
        logger.warning("stock_almacen ajuste inventario %s: %s", id_inv, e)
    # Kárdex AJUSTE (best-effort, tras commit; no rompe el cierre) — INV.1.
    try:
        from src.db import kardex
        for a in ajustes:
            kardex.registrar_movimiento(
                a["codigo"], "AJUSTE", a["diferencia"], id_documento=f"INV-{id_inv}",
                origen="INVENTARIO", usuario=usuario, id_empresa=id_empresa,
                id_tienda=a["id_tienda"], stock_anterior=a["anterior"], stock_nuevo=a["nuevo"],
                id_almacen_destino=a.get("id_almacen"),
                observaciones=f"Ajuste por inventario #{id_inv}")
        try:
            from src.gui.mostrar_stock import stock_signals
            for a in ajustes:
                stock_signals.stock_actualizado.emit(str(a["codigo"]))
        except Exception:
            pass
    except Exception as e:
        logger.warning("kardex ajustes inventario %s: %s", id_inv, e)
    # INV.3: refleja el ajuste en los lotes (best-effort, solo si el artículo tiene lotes).
    try:
        from src.db import lotes
        for a in ajustes:
            tnd = a["id_tienda"]
            if a["diferencia"] < 0:
                lotes.consumir_fefo(a["codigo"], -a["diferencia"], tipo="AJUSTE",
                                    id_empresa=id_empresa, id_tienda=tnd,
                                    id_documento=f"INV-{id_inv}", usuario=usuario,
                                    observaciones=f"Ajuste inventario #{id_inv}")
            elif a["diferencia"] > 0 and lotes.stock_por_lote(a["codigo"], id_empresa, tnd):
                lotes.registrar_entrada(a["codigo"], f"INV-{id_inv}", a["diferencia"],
                                        id_empresa=id_empresa, id_tienda=tnd, origen="inventario",
                                        id_documento=f"INV-{id_inv}", usuario=usuario)
    except Exception as e:
        logger.warning("lotes ajustes inventario %s: %s", id_inv, e)
    return {"inventario": id_inv, "ajustes_aplicados": len(ajustes), "detalle": ajustes}


# ── Consultas / informes ──────────────────────────────────────────────────────
def obtener_inventario(id_inv, id_empresa=None) -> dict | None:
    id_empresa, _ = _tenant(id_empresa)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            return _cabecera(cur, id_inv, id_empresa)
    except Exception as e:
        logger.error("obtener_inventario: %s", e); return None


def listar_lineas(id_inv, id_empresa=None) -> list:
    id_empresa, _ = _tenant(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM inventario_lineas WHERE id_inventario=%s AND id_empresa=%s "
                        "ORDER BY codigo_articulo", (id_inv, id_empresa))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_lineas: %s", e); return []


def listar_inventarios(id_empresa=None, estado=None, id_tienda=None) -> list:
    id_empresa, _ = _tenant(id_empresa)
    try:
        ensure_schema()
        cond = ["id_empresa=%s"]; params = [id_empresa]
        if estado:
            cond.append("estado=%s"); params.append(estado)
        if id_tienda is not None:
            cond.append("id_tienda=%s"); params.append(id_tienda)
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT * FROM inventarios WHERE {' AND '.join(cond)} "
                        f"ORDER BY created_at DESC, id DESC", params)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_inventarios: %s", e); return []


def resumen(id_inv, id_empresa=None) -> dict:
    """Resumen del inventario: nº líneas, contadas, con diferencia, sumas +/−."""
    lineas = listar_lineas(id_inv, id_empresa)
    contadas = [l for l in lineas if l.get("stock_contado") is not None]
    difs = [l for l in contadas if l.get("diferencia")]
    return {
        "lineas": len(lineas), "contadas": len(contadas), "con_diferencia": len(difs),
        "sobrante": sum(l["diferencia"] for l in difs if l["diferencia"] > 0),
        "faltante": sum(l["diferencia"] for l in difs if l["diferencia"] < 0),
    }


def diferencias_por_inventario(id_inv, id_empresa=None) -> list:
    return [l for l in listar_lineas(id_inv, id_empresa)
            if l.get("stock_contado") is not None and l.get("diferencia")]


def diferencias_por_articulo(codigo, id_empresa=None) -> list:
    id_empresa, _ = _tenant(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT l.*, i.nombre AS inventario, i.estado, i.fecha_cierre "
                        "FROM inventario_lineas l JOIN inventarios i ON i.id=l.id_inventario "
                        "WHERE l.codigo_articulo=%s AND l.id_empresa=%s AND l.diferencia<>0 "
                        "ORDER BY i.created_at DESC", (codigo, id_empresa))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("diferencias_por_articulo: %s", e); return []


def diferencias_por_tienda(id_tienda, id_empresa=None) -> list:
    id_empresa, _ = _tenant(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT l.* FROM inventario_lineas l JOIN inventarios i ON i.id=l.id_inventario "
                        "WHERE i.id_tienda=%s AND l.id_empresa=%s AND l.diferencia<>0 "
                        "ORDER BY l.codigo_articulo", (id_tienda, id_empresa))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("diferencias_por_tienda: %s", e); return []


def inventarios_abiertos(id_empresa=None) -> list:
    a = listar_inventarios(id_empresa, estado=ABIERTO)
    return a + listar_inventarios(id_empresa, estado=BORRADOR)


def inventarios_cerrados(id_empresa=None) -> list:
    return listar_inventarios(id_empresa, estado=CERRADO)
