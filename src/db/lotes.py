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

ACTIVO, AGOTADO, BLOQUEADO = "activo", "agotado", "bloqueado"
TIPOS_SALIDA = ("SALIDA_VENTA", "MERMA", "TRASPASO", "AJUSTE", "DEVOLUCION_PROVEEDOR",
                "SALIDA_PRODUCCION")  # SALIDA_PRODUCCION: consumo de componentes (MRP, BLOQUE 3)


def _tnd_int(tnd) -> int:
    """Coerciona el id de tienda a INT (la columna lotes.id_tienda es INT, 0 = global).
    El contexto de tienda puede ser un código alfanumérico (p. ej. un almacén 'ALMC');
    en ese caso se trata como 0 (global) en lugar de reventar."""
    try:
        return int(tnd or 0)
    except (TypeError, ValueError):
        return 0


def _tenant(id_empresa=None, id_tienda=None):
    try:
        from src.db.empresa import empresa_actual_id, tienda_actual_id
        emp = id_empresa or empresa_actual_id()
        tnd = id_tienda if id_tienda is not None else tienda_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        emp = id_empresa or EMPRESA_DEFAULT_ID
        tnd = id_tienda
    return emp, _tnd_int(tnd)


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
                      id_almacen=None, id_recepcion_origen=None, id_tx_origen=None,
                      propiedad=None, id_suministrador=None) -> int | None:
    """Crea o incrementa un lote y registra el movimiento ENTRADA. Devuelve id del lote.
    id_almacen (INV.4) localiza el lote por almacén (opcional, retrocompatible).

    `id_recepcion_origen`/`id_tx_origen` (Fase B — Landed Cost, migración 0266): referencia a la
    recepción de compra o transacción B2B que originó la entrada — `prorratear_costes_recepcion()`
    los usa para localizar qué lotes actualizar con el snapshot de coste landed. Ambos opcionales
    y retrocompatibles (cero cambio para el resto de llamadores); si el lote ya existía (se
    incrementa, no se crea), NUNCA se sobreescribe un origen ya fijado por una entrada anterior
    (COALESCE) — el snapshot landed es por definición un best-effort ligado a la PRIMERA entrada
    de ese lote, documentado en `0266_lotes_coste_landed.py`.

    `propiedad`/`id_suministrador` (Fase C — Stock en Consignación, migración 0267): marca el lote
    como `'consignacion'` (propiedad del proveedor hasta que se consume, ver `consumir_fefo`) en vez
    del `'propio'` por defecto de la columna. Ambos opcionales/retrocompatibles — `None` deja la
    columna en su DEFAULT ('propio')/NULL para el resto de llamadores (~15 call sites existentes,
    cero cambio de comportamiento). Igual que `id_recepcion_origen`/`id_tx_origen`, en un
    incremento sobre un lote ya existente NUNCA se sobreescribe una propiedad/suministrador ya
    fijados por una entrada anterior (COALESCE) — un lote de consignación no puede "volverse propio"
    por una entrada posterior sin marcar, y viceversa."""
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
                            "id_almacen=COALESCE(%s, id_almacen), "
                            "id_recepcion_origen=COALESCE(id_recepcion_origen,%s), "
                            "id_tx_origen=COALESCE(id_tx_origen,%s), "
                            "propiedad=COALESCE(%s, propiedad), "
                            "id_suministrador=COALESCE(id_suministrador,%s) WHERE id=%s",
                            (cantidad, cantidad, ACTIVO, fecha_caducidad, id_almacen,
                             id_recepcion_origen, id_tx_origen, propiedad, id_suministrador, id_lote))
            else:
                cur.execute(
                    "INSERT INTO lotes (id_empresa, id_tienda, codigo_articulo, lote, "
                    "fecha_caducidad, cantidad, cantidad_inicial, origen, id_documento, estado, "
                    "id_almacen, id_recepcion_origen, id_tx_origen, propiedad, id_suministrador) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (id_empresa, id_tienda, codigo, lote, fecha_caducidad, cantidad, cantidad,
                     origen, str(id_documento) if id_documento is not None else None, ACTIVO,
                     id_almacen, id_recepcion_origen, id_tx_origen, propiedad or "propio",
                     id_suministrador))
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
                  idempotente=False, orden=None) -> dict:
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
            # Política de consumo: por defecto FEFO (caducidad). `orden` permite FIFO/LIFO reutilizando
            # exactamente esta misma lógica (solo cambia el criterio de selección de lotes).
            _orden = orden or "(fecha_caducidad IS NULL), fecha_caducidad, fecha_entrada, id"
            cur.execute(
                "SELECT id, lote, cantidad, propiedad, id_suministrador FROM lotes WHERE "
                "id_empresa=%s AND id_tienda=%s AND codigo_articulo=%s AND estado=%s AND "
                "cantidad>0" + cond_alm + f" ORDER BY {_orden} FOR UPDATE",
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
                detalle.append({"id_lote": ln["id"], "lote": ln["lote"], "consumido": toma,
                                "propiedad": ln.get("propiedad"),
                                "id_suministrador": ln.get("id_suministrador")})
                restante -= toma
        _liquidar_consumo_consignacion(detalle, tipo, codigo, id_documento, id_empresa, usuario)
        return {"consumido": cantidad - restante, "faltante": restante, "detalle": detalle}
    except Exception as e:
        logger.error("consumir_fefo(%s,%s): %s", codigo, cantidad, e)
        return {"consumido": 0, "faltante": cantidad, "detalle": detalle}


def _liquidar_consumo_consignacion(detalle, tipo, codigo, id_documento, id_empresa, usuario):
    """Fase C — Stock en Consignación: dispara la liquidación (auto-factura idempotente) del stock de
    consignación consumido por ESTE `consumir_fefo`, tras el commit de la salida real. Best-effort
    ABSOLUTO (mismo espíritu que el resto del módulo, ver docstring de cabecera): esta función NUNCA
    puede hacer que `consumir_fefo` falle ni se comporte distinto para el llamador — cualquier fallo
    aquí queda solo logueado. `DEVOLUCION_PROVEEDOR` se excluye a propósito (Fase C, punto 5): esa
    salida es la devolución de mercancía en consignación al proveedor, no una venta/consumo real, así
    que estructuralmente NUNCA debe generar factura. Import perezoso tras el commit — mismo patrón que
    `db/compras.py::recibir()` (sync multialmacén/lotes) para evitar un ciclo de imports en frío
    (`b2b_pedidos` → ... → `db.lotes`)."""
    if tipo == "DEVOLUCION_PROVEEDOR":
        return
    consignacion = [d for d in detalle if d.get("propiedad") == "consignacion" and d.get("consumido")]
    if not consignacion:
        return
    try:
        from src.services.compras import b2b_pedidos as _B2B
        por_suministrador: dict = {}
        for d in consignacion:
            por_suministrador[d["id_suministrador"]] = (
                por_suministrador.get(d["id_suministrador"], 0) + int(d["consumido"]))
        for id_sum, cant in por_suministrador.items():
            if not id_sum or cant <= 0:
                continue
            _B2B.registrar_consumo_consignacion(id_sum, codigo, cant, id_documento, id_empresa,
                                                usuario=usuario)
    except Exception as e:
        logger.error("_liquidar_consumo_consignacion(%s): %s", codigo, e)


# ── Bloqueo/desbloqueo (calidad: NC sobre un lote) ─────────────────────────────
def bloquear_lote(id_lote, motivo, usuario=None, id_empresa=None) -> bool:
    """Bloquea un lote (estado='bloqueado'). `consumir_fefo` filtra explícitamente
    `WHERE estado=ACTIVO`, así que un lote bloqueado queda automáticamente excluido de FEFO/
    FIFO/LIFO sin tocar esa función. No modifica la cantidad (el stock sigue existiendo, solo
    deja de ser consumible). El motivo es obligatorio y se registra como movimiento 'BLOQUEO'
    en `lotes_movimientos` (auditoría, sin columna nueva)."""
    id_empresa, _ = _tenant(id_empresa)
    motivo = (motivo or "").strip()
    if not motivo:
        return False
    try:
        ensure_schema()
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("SELECT codigo_articulo FROM lotes WHERE id=%s AND id_empresa=%s",
                        (id_lote, id_empresa))
            row = cur.fetchone()
            if not row:
                return False
            codigo = row[0] if not isinstance(row, dict) else row["codigo_articulo"]
            cur.execute("UPDATE lotes SET estado=%s WHERE id=%s AND id_empresa=%s",
                        (BLOQUEADO, id_lote, id_empresa))
            _mov(cur, id_empresa, id_lote, codigo, "BLOQUEO", 0, usuario=usuario,
                 observaciones=motivo)
        return True
    except Exception as e:
        logger.error("bloquear_lote(%s): %s", id_lote, e)
        return False


def desbloquear_lote(id_lote, usuario=None, id_empresa=None) -> bool:
    """Desbloquea un lote (estado vuelve a 'activo'): vuelve a ser elegible por FEFO/FIFO/LIFO.
    No-op (False) si el lote no está bloqueado."""
    id_empresa, _ = _tenant(id_empresa)
    try:
        ensure_schema()
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("SELECT codigo_articulo, estado FROM lotes WHERE id=%s AND id_empresa=%s",
                        (id_lote, id_empresa))
            row = cur.fetchone()
            if not row:
                return False
            codigo = row[0] if not isinstance(row, dict) else row["codigo_articulo"]
            estado = row[1] if not isinstance(row, dict) else row["estado"]
            if estado != BLOQUEADO:
                return False
            cur.execute("UPDATE lotes SET estado=%s WHERE id=%s AND id_empresa=%s",
                        (ACTIVO, id_lote, id_empresa))
            _mov(cur, id_empresa, id_lote, codigo, "DESBLOQUEO", 0, usuario=usuario)
        return True
    except Exception as e:
        logger.error("desbloquear_lote(%s): %s", id_lote, e)
        return False


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
            cond.append("id_tienda=%s"); params.append(_tnd_int(id_tienda))
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
            cond.append("id_tienda=%s"); params.append(_tnd_int(id_tienda))
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


def consumir_fifo(codigo, cantidad, **kw) -> dict:
    """Consume por FIFO (primero en entrar, primero en salir). Reutiliza consumir_fefo cambiando
    solo el criterio de selección de lotes (fecha de entrada ascendente)."""
    return consumir_fefo(codigo, cantidad, orden="fecha_entrada, id", **kw)


def consumir_lifo(codigo, cantidad, **kw) -> dict:
    """Consume por LIFO (último en entrar, primero en salir). Reutiliza consumir_fefo con el criterio
    de fecha de entrada descendente."""
    return consumir_fefo(codigo, cantidad, orden="fecha_entrada DESC, id DESC", **kw)


def consumir_por_politica(codigo, cantidad, politica="FEFO", **kw) -> dict:
    """Punto único: aplica la política de consumo indicada (FEFO/FIFO/LIFO). No duplica lógica."""
    p = str(politica or "FEFO").upper()
    if p == "FIFO":
        return consumir_fifo(codigo, cantidad, **kw)
    if p == "LIFO":
        return consumir_lifo(codigo, cantidad, **kw)
    return consumir_fefo(codigo, cantidad, **kw)
