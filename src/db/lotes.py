"""
Lotes, caducidades y consumo FEFO (INV.3).

Sub-ledger de existencias por lote (`lotes`) con trazabilidad propia (`lotes_movimientos`),
paralelo al stock agregado. El consumo es FEFO (First-Expired, First-Out): primero los lotes
con caducidad más próxima (los sin caducidad, al final). Pensado para invocarse como
complemento best-effort de las operaciones de stock: si un artículo no tiene lotes, las
funciones de consumo son no-op y nunca bloquean la operación. Multiempresa/multitienda
(id_tienda 0 = global). Sin Qt.
"""

import datetime as _dt
import logging

from src.db.conexion import (_fila_a_dict, _filas_a_dicts, ensure_schema,
                             obtener_conexion, transaccion)

logger = logging.getLogger("inventario.lotes")

ACTIVO, AGOTADO = "activo", "agotado"
TIPOS_SALIDA = ("SALIDA_VENTA", "MERMA", "TRASPASO", "AJUSTE", "DEVOLUCION_PROVEEDOR")


def _tenant(id_empresa=None, id_tienda=None):
    try:
        from src.db.empresa import empresa_actual_id, tienda_actual_id
        emp = id_empresa or empresa_actual_id()
        tnd = id_tienda if id_tienda is not None else tienda_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        emp = id_empresa or EMPRESA_DEFAULT_ID
        tnd = id_tienda
    return emp, int(tnd or 0)


def _mov(cur, id_empresa, id_lote, codigo, tipo, cantidad, id_documento=None,
         usuario=None, observaciones=None):
    cur.execute(
        "INSERT INTO lotes_movimientos (id_empresa, id_lote, codigo_articulo, tipo, cantidad, "
        "id_documento, usuario, observaciones) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (id_empresa, id_lote, codigo, tipo, int(cantidad),
         str(id_documento) if id_documento is not None else None, usuario, observaciones))


# ── Entrada ───────────────────────────────────────────────────────────────────
def registrar_entrada(codigo, lote, cantidad, fecha_caducidad=None, id_empresa=None,
                      id_tienda=None, origen="manual", id_documento=None, usuario=None,
                      id_almacen=None) -> int | None:
    """Crea o incrementa un lote y registra el movimiento ENTRADA. Devuelve id del lote.
    id_almacen (INV.4) localiza el lote por almacén (opcional, retrocompatible)."""
    id_empresa, id_tienda = _tenant(id_empresa, id_tienda)
    cantidad = int(cantidad or 0)
    if not codigo or not lote or cantidad <= 0:
        return None
    try:
        ensure_schema()
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, cantidad FROM lotes WHERE id_empresa=%s AND id_tienda=%s "
                        "AND codigo_articulo=%s AND lote=%s",
                        (id_empresa, id_tienda, codigo, lote))
            row = cur.fetchone()
            if row:
                id_lote = row[0] if not isinstance(row, dict) else row["id"]
                cur.execute("UPDATE lotes SET cantidad=cantidad+%s, cantidad_inicial=cantidad_inicial+%s, "
                            "estado=%s, fecha_caducidad=COALESCE(%s, fecha_caducidad), "
                            "id_almacen=COALESCE(%s, id_almacen) WHERE id=%s",
                            (cantidad, cantidad, ACTIVO, fecha_caducidad, id_almacen, id_lote))
            else:
                cur.execute(
                    "INSERT INTO lotes (id_empresa, id_tienda, codigo_articulo, lote, "
                    "fecha_caducidad, cantidad, cantidad_inicial, origen, id_documento, estado, "
                    "id_almacen) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (id_empresa, id_tienda, codigo, lote, fecha_caducidad, cantidad, cantidad,
                     origen, str(id_documento) if id_documento is not None else None, ACTIVO,
                     id_almacen))
                id_lote = cur.lastrowid
            _mov(cur, id_empresa, id_lote, codigo, "ENTRADA", cantidad,
                 id_documento=id_documento, usuario=usuario, observaciones=origen)
        return id_lote
    except Exception as e:
        logger.error("registrar_entrada(%s,%s): %s", codigo, lote, e)
        return None


# ── Consumo FEFO ──────────────────────────────────────────────────────────────
def consumir_fefo(codigo, cantidad, tipo="SALIDA_VENTA", id_empresa=None, id_tienda=None,
                  id_documento=None, usuario=None, observaciones=None, id_almacen=None,
                  idempotente=False) -> dict:
    """Consume `cantidad` del artículo aplicando FEFO sobre los lotes con existencias.
    No-op si el artículo no tiene lotes. Devuelve {consumido, faltante, detalle:[...]}.
    No bloquea: si los lotes no cubren la cantidad, consume lo disponible y deja `faltante`.
    id_almacen (INV.4) acota el consumo a un almacén concreto (opcional). Si `idempotente`
    y ya existe un consumo de este tipo para (codigo, id_documento), no vuelve a consumir (H1)."""
    id_empresa, id_tienda = _tenant(id_empresa, id_tienda)
    cantidad = int(cantidad or 0)
    detalle = []
    if not codigo or cantidad <= 0:
        return {"consumido": 0, "faltante": cantidad, "detalle": detalle}
    if tipo not in TIPOS_SALIDA:
        tipo = "SALIDA_VENTA"
    if idempotente and id_documento is not None:
        try:
            with obtener_conexion() as _c, _c.cursor() as _cur:
                _cur.execute("SELECT 1 FROM lotes_movimientos WHERE id_empresa=%s AND codigo_articulo=%s "
                             "AND tipo=%s AND id_documento=%s LIMIT 1",
                             (id_empresa, codigo, tipo, str(id_documento)))
                if _cur.fetchone():
                    return {"consumido": cantidad, "faltante": 0, "detalle": detalle, "idempotente": True}
        except Exception:
            pass
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cond_alm = " AND id_almacen=%s" if id_almacen is not None else ""
            params = [id_empresa, id_tienda, codigo, ACTIVO]
            if id_almacen is not None:
                params.append(id_almacen)
            cur.execute(
                "SELECT id, lote, cantidad FROM lotes WHERE id_empresa=%s AND id_tienda=%s "
                "AND codigo_articulo=%s AND estado=%s AND cantidad>0" + cond_alm +
                " ORDER BY (fecha_caducidad IS NULL), fecha_caducidad, fecha_entrada, id FOR UPDATE",
                params)
            lotes = _filas_a_dicts(cur, cur.fetchall())
            restante = cantidad
            for ln in lotes:
                if restante <= 0:
                    break
                toma = min(restante, int(ln["cantidad"]))
                nuevo = int(ln["cantidad"]) - toma
                cur.execute("UPDATE lotes SET cantidad=%s, estado=%s WHERE id=%s",
                            (nuevo, ACTIVO if nuevo > 0 else AGOTADO, ln["id"]))
                _mov(cur, id_empresa, ln["id"], codigo, tipo, toma,
                     id_documento=id_documento, usuario=usuario, observaciones=observaciones)
                detalle.append({"id_lote": ln["id"], "lote": ln["lote"], "consumido": toma})
                restante -= toma
        return {"consumido": cantidad - restante, "faltante": restante, "detalle": detalle}
    except Exception as e:
        logger.error("consumir_fefo(%s,%s): %s", codigo, cantidad, e)
        return {"consumido": 0, "faltante": cantidad, "detalle": detalle}


# ── Consultas ─────────────────────────────────────────────────────────────────
def stock_por_lote(codigo, id_empresa=None, id_tienda=None, incluir_agotados=False) -> list:
    id_empresa, id_tienda = _tenant(id_empresa, id_tienda)
    try:
        ensure_schema()
        cond = ["id_empresa=%s", "id_tienda=%s", "codigo_articulo=%s"]
        params = [id_empresa, id_tienda, codigo]
        if not incluir_agotados:
            cond.append("cantidad>0")
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT * FROM lotes WHERE {' AND '.join(cond)} "
                        "ORDER BY (fecha_caducidad IS NULL), fecha_caducidad, id", params)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("stock_por_lote: %s", e); return []


def stock_total_en_lotes(codigo, id_empresa=None, id_tienda=None) -> int:
    return sum(int(l["cantidad"]) for l in stock_por_lote(codigo, id_empresa, id_tienda))


def listar_lotes(id_empresa=None, id_tienda=None, codigo=None, incluir_agotados=False) -> list:
    id_empresa, id_tienda = _tenant(id_empresa, id_tienda)
    try:
        ensure_schema()
        cond = ["id_empresa=%s"]; params = [id_empresa]
        if id_tienda:
            cond.append("id_tienda=%s"); params.append(id_tienda)
        if codigo:
            cond.append("codigo_articulo=%s"); params.append(codigo)
        if not incluir_agotados:
            cond.append("cantidad>0")
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT * FROM lotes WHERE {' AND '.join(cond)} "
                        "ORDER BY (fecha_caducidad IS NULL), fecha_caducidad, codigo_articulo",
                        params)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_lotes: %s", e); return []


# ── Alertas de caducidad ──────────────────────────────────────────────────────
def lotes_por_caducar(dias=30, id_empresa=None, id_tienda=None) -> list:
    """Lotes activos con existencias cuya caducidad ocurre dentro de `dias` (desde hoy)."""
    id_empresa, _ = _tenant(id_empresa)
    hoy = _dt.date.today()
    limite = (hoy + _dt.timedelta(days=int(dias))).isoformat()
    try:
        ensure_schema()
        cond = ["id_empresa=%s", "cantidad>0", "fecha_caducidad IS NOT NULL",
                "fecha_caducidad>=%s", "fecha_caducidad<=%s"]
        params = [id_empresa, hoy.isoformat(), limite]
        if id_tienda is not None:
            cond.append("id_tienda=%s"); params.append(int(id_tienda))
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT * FROM lotes WHERE {' AND '.join(cond)} ORDER BY fecha_caducidad",
                        params)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("lotes_por_caducar: %s", e); return []


def lotes_caducados(id_empresa=None, id_tienda=None) -> list:
    id_empresa, _ = _tenant(id_empresa)
    hoy = _dt.date.today().isoformat()
    try:
        ensure_schema()
        cond = ["id_empresa=%s", "cantidad>0", "fecha_caducidad IS NOT NULL", "fecha_caducidad<%s"]
        params = [id_empresa, hoy]
        if id_tienda is not None:
            cond.append("id_tienda=%s"); params.append(int(id_tienda))
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT * FROM lotes WHERE {' AND '.join(cond)} ORDER BY fecha_caducidad",
                        params)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("lotes_caducados: %s", e); return []


# ── Trazabilidad ──────────────────────────────────────────────────────────────
def obtener_lote(id_lote, id_empresa=None) -> dict | None:
    id_empresa, _ = _tenant(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM lotes WHERE id=%s AND id_empresa=%s", (id_lote, id_empresa))
            return _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        logger.error("obtener_lote: %s", e); return None


def trazabilidad_lote(id_lote, id_empresa=None) -> list:
    id_empresa, _ = _tenant(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM lotes_movimientos WHERE id_lote=%s AND id_empresa=%s "
                        "ORDER BY fecha, id", (id_lote, id_empresa))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("trazabilidad_lote: %s", e); return []


def trazabilidad_articulo(codigo, id_empresa=None) -> list:
    id_empresa, _ = _tenant(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT m.*, l.lote, l.fecha_caducidad FROM lotes_movimientos m "
                        "JOIN lotes l ON l.id=m.id_lote WHERE m.codigo_articulo=%s AND m.id_empresa=%s "
                        "ORDER BY m.fecha, m.id", (codigo, id_empresa))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("trazabilidad_articulo: %s", e); return []
