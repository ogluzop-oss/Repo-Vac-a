"""
Multialmacén — servicio de stock por almacén (INV.4.2). Fuente única de verdad.

`stock_almacen` (cantidad por almacén+artículo) es la fuente de verdad; las columnas
`articulos.Stock_central/Stock_total/Stock_tienda` quedan como CACHÉ derivada, recalculada
automáticamente tras cada movimiento mediante `recalcular_cache_articulo`:

  Stock_central = Σ existencias en almacenes tipo 'central'
  Stock_total   = Σ existencias en almacenes NO tipo 'tienda'  (incluye central)
  Stock_tienda  = Σ existencias en el almacén de la TIENDA ACTIVA

Mapeo de almacenes por empresa: un 'central', un 'GENERAL' (logistico, resto no-tienda) y
un almacén tipo 'tienda' por cada tienda. No rompe TPV/compras/logística: la caché conserva
exactamente los valores previos tras el sembrado (reseed). Multiempresa/multitienda.
"""

import logging

from src.db.conexion import (_fila_a_dict, _filas_a_dicts, ensure_schema,
                             obtener_conexion, transaccion)

logger = logging.getLogger("inventario.stock_almacen")


def _tenant(id_empresa=None):
    try:
        from src.db.empresa import empresa_actual_id
        return id_empresa or empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return id_empresa or EMPRESA_DEFAULT_ID


def _tienda_activa():
    try:
        from src.db.empresa import tienda_actual_id
        return tienda_actual_id()
    except Exception:
        return None


# ── Catálogo de almacenes ─────────────────────────────────────────────────────
def _almacen_unico(cur, id_empresa, **filtros):
    cond = ["id_empresa=%s"]; params = [id_empresa]
    for k, v in filtros.items():
        cond.append(f"{k}=%s"); params.append(v)
    cur.execute(f"SELECT id FROM almacen WHERE {' AND '.join(cond)} ORDER BY id LIMIT 1", params)
    r = cur.fetchone()
    return (r[0] if not isinstance(r, dict) else r["id"]) if r else None


def _crear_almacen(cur, id_empresa, nombre, codigo, tipo, id_tienda=None):
    cur.execute("INSERT INTO almacen (nombre, activo, id_empresa, codigo_almacen, tipo_almacen, "
                "estado, id_tienda) VALUES (%s,1,%s,%s,%s,'activo',%s)",
                (nombre, id_empresa, codigo, tipo, id_tienda))
    return cur.lastrowid


def ensure_almacenes_empresa(id_empresa=None) -> dict:
    """Garantiza central + general + un almacén por tienda. Devuelve ids por rol."""
    id_empresa = _tenant(id_empresa)
    suf = str(id_empresa)[:8]
    with transaccion() as conn, conn.cursor() as cur:
        central = _almacen_unico(cur, id_empresa, tipo_almacen="central")
        if not central:
            central = _crear_almacen(cur, id_empresa, f"ALMACÉN CENTRAL {suf}", "ALM-CENTRAL", "central")
        general = _almacen_unico(cur, id_empresa, tipo_almacen="logistico", codigo_almacen="ALM-GENERAL")
        if not general:
            general = _crear_almacen(cur, id_empresa, f"ALMACÉN GENERAL {suf}", "ALM-GENERAL", "logistico")
        tiendas = {}
        cur.execute("SELECT id, codigo_tienda FROM tiendas WHERE id_empresa=%s", (id_empresa,))
        for row in _filas_a_dicts(cur, cur.fetchall()):
            tid = row["id"]
            alm = _almacen_unico(cur, id_empresa, tipo_almacen="tienda", id_tienda=tid)
            if not alm:
                alm = _crear_almacen(cur, id_empresa, f"ALMACÉN TIENDA {tid} {suf}",
                                     f"ALM-T{tid}", "tienda", id_tienda=tid)
            tiendas[tid] = alm
    return {"central": central, "general": general, "tiendas": tiendas}


def almacen_central(id_empresa=None) -> int | None:
    return ensure_almacenes_empresa(id_empresa)["central"]


def almacen_de_tienda(id_tienda, id_empresa=None) -> int | None:
    return ensure_almacenes_empresa(id_empresa)["tiendas"].get(id_tienda)


def listar_almacenes(id_empresa=None, solo_activos=True) -> list:
    id_empresa = _tenant(id_empresa)
    try:
        ensure_schema()
        cond = ["id_empresa=%s"]; params = [id_empresa]
        if solo_activos:
            cond.append("activo=1")
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT * FROM almacen WHERE {' AND '.join(cond)} ORDER BY tipo_almacen, nombre",
                        params)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_almacenes: %s", e); return []


# ── Lectura de existencias ────────────────────────────────────────────────────
def obtener_stock_almacen(codigo, id_almacen, id_empresa=None) -> int:
    id_empresa = _tenant(id_empresa)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT cantidad FROM stock_almacen WHERE id_empresa=%s AND id_almacen=%s "
                        "AND codigo_articulo=%s", (id_empresa, id_almacen, codigo))
            r = cur.fetchone()
            return int((r[0] if not isinstance(r, dict) else r["cantidad"]) or 0) if r else 0
    except Exception as e:
        logger.error("obtener_stock_almacen: %s", e); return 0


def obtener_stock_articulo(codigo, id_empresa=None) -> dict:
    """Existencias del artículo desglosadas por almacén + total global."""
    id_empresa = _tenant(id_empresa)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT s.id_almacen, a.nombre, a.tipo_almacen, a.id_tienda, s.cantidad "
                        "FROM stock_almacen s JOIN almacen a ON a.id=s.id_almacen "
                        "WHERE s.id_empresa=%s AND s.codigo_articulo=%s ORDER BY a.tipo_almacen, a.nombre",
                        (id_empresa, codigo))
            filas = _filas_a_dicts(cur, cur.fetchall())
        return {"detalle": filas, "total": sum(int(f["cantidad"]) for f in filas)}
    except Exception as e:
        logger.error("obtener_stock_articulo: %s", e); return {"detalle": [], "total": 0}


def stock_total_global(codigo, id_empresa=None) -> int:
    return obtener_stock_articulo(codigo, id_empresa)["total"]


# ── Recálculo de la caché ─────────────────────────────────────────────────────
def esta_gestionado(codigo, id_empresa=None, cur=None) -> bool:
    """True si el artículo ya tiene existencias registradas en stock_almacen."""
    id_empresa = _tenant(id_empresa)

    def _q(c):
        c.execute("SELECT 1 FROM stock_almacen WHERE id_empresa=%s AND codigo_articulo=%s LIMIT 1",
                  (id_empresa, codigo))
        return c.fetchone() is not None
    try:
        if cur is not None:
            return _q(cur)
        with obtener_conexion() as conn, conn.cursor() as c:
            return _q(c)
    except Exception:
        return False


def recalcular_cache_articulo(codigo, id_empresa=None, cur=None) -> bool:
    """Recalcula articulos.Stock_central/Stock_total/Stock_tienda desde stock_almacen.
    No-op si el artículo aún no está gestionado (preserva la caché legada intacta)."""
    id_empresa = _tenant(id_empresa)

    def _run(c):
        if not esta_gestionado(codigo, id_empresa, cur=c):
            return
        c.execute("SELECT COALESCE(SUM(CASE WHEN a.tipo_almacen='central' THEN s.cantidad END),0) AS central, "
                  "COALESCE(SUM(CASE WHEN a.tipo_almacen<>'tienda' THEN s.cantidad END),0) AS no_tienda "
                  "FROM stock_almacen s JOIN almacen a ON a.id=s.id_almacen "
                  "WHERE s.id_empresa=%s AND s.codigo_articulo=%s", (id_empresa, codigo))
        r = c.fetchone()
        central = int((r[0] if not isinstance(r, dict) else r["central"]) or 0)
        no_tienda = int((r[1] if not isinstance(r, dict) else r["no_tienda"]) or 0)
        c.execute("UPDATE articulos SET Stock_central=%s, Stock_total=%s WHERE codigo=%s AND id_empresa=%s",
                  (central, no_tienda, codigo, id_empresa))
        tid = _tienda_activa()
        if tid:
            c.execute("SELECT COALESCE(SUM(s.cantidad),0) FROM stock_almacen s JOIN almacen a ON a.id=s.id_almacen "
                      "WHERE s.id_empresa=%s AND s.codigo_articulo=%s AND a.tipo_almacen='tienda' AND a.id_tienda=%s",
                      (id_empresa, codigo, tid))
            rr = c.fetchone()
            t = int((rr[0] if not isinstance(rr, dict) else list(rr.values())[0]) or 0)
            c.execute("UPDATE articulos SET Stock_tienda=%s WHERE codigo=%s AND id_empresa=%s",
                      (t, codigo, id_empresa))

    try:
        if cur is not None:
            _run(cur)
        else:
            with transaccion() as conn, conn.cursor() as c:
                _run(c)
        return True
    except Exception as e:
        logger.error("recalcular_cache_articulo(%s): %s", codigo, e); return False


# ── Mutaciones (fuente de verdad) ─────────────────────────────────────────────
def _upsert(cur, id_empresa, id_almacen, codigo, delta=None, absoluto=None):
    if absoluto is not None:
        cur.execute("INSERT INTO stock_almacen (id_empresa, id_almacen, codigo_articulo, cantidad) "
                    "VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE cantidad=VALUES(cantidad)",
                    (id_empresa, id_almacen, codigo, max(0, int(absoluto))))
    else:
        cur.execute("INSERT INTO stock_almacen (id_empresa, id_almacen, codigo_articulo, cantidad) "
                    "VALUES (%s,%s,%s,GREATEST(0,%s)) "
                    "ON DUPLICATE KEY UPDATE cantidad=GREATEST(0, cantidad+%s)",
                    (id_empresa, id_almacen, codigo, int(delta), int(delta)))


def _asegurar_gestionado(codigo, id_empresa):
    """Onboarding: si el artículo aún no está en stock_almacen, lo siembra desde la caché
    (preservando el stock existente) antes de mutar. Transacción propia (no anidar)."""
    if not esta_gestionado(codigo, id_empresa):
        reseed_articulo(codigo, id_empresa)


def incrementar_stock(codigo, id_almacen, cantidad, id_empresa=None) -> bool:
    id_empresa = _tenant(id_empresa)
    try:
        _asegurar_gestionado(codigo, id_empresa)
        with transaccion() as conn, conn.cursor() as cur:
            _upsert(cur, id_empresa, id_almacen, codigo, delta=int(cantidad))
            recalcular_cache_articulo(codigo, id_empresa, cur=cur)
        return True
    except Exception as e:
        logger.error("incrementar_stock: %s", e); return False


def decrementar_stock(codigo, id_almacen, cantidad, id_empresa=None) -> bool:
    return incrementar_stock(codigo, id_almacen, -abs(int(cantidad)), id_empresa)


def ajustar_stock(codigo, id_almacen, nueva_cantidad, id_empresa=None) -> bool:
    id_empresa = _tenant(id_empresa)
    try:
        _asegurar_gestionado(codigo, id_empresa)
        with transaccion() as conn, conn.cursor() as cur:
            _upsert(cur, id_empresa, id_almacen, codigo, absoluto=int(nueva_cantidad))
            recalcular_cache_articulo(codigo, id_empresa, cur=cur)
        return True
    except Exception as e:
        logger.error("ajustar_stock: %s", e); return False


def traspasar_stock(codigo, almacen_origen, almacen_destino, cantidad, id_empresa=None,
                    id_documento=None, usuario=None) -> bool:
    """Descuenta del almacén origen e incrementa el destino (atómico) y recalcula caché.
    Registra el movimiento TRASPASO en el kárdex con almacén origen/destino."""
    id_empresa = _tenant(id_empresa)
    cantidad = int(cantidad)
    if cantidad <= 0 or almacen_origen == almacen_destino:
        return False
    try:
        _asegurar_gestionado(codigo, id_empresa)
        with transaccion() as conn, conn.cursor() as cur:
            _upsert(cur, id_empresa, almacen_origen, codigo, delta=-cantidad)
            _upsert(cur, id_empresa, almacen_destino, codigo, delta=cantidad)
            recalcular_cache_articulo(codigo, id_empresa, cur=cur)
        try:
            from src.db import kardex
            kardex.registrar_movimiento(codigo, "TRASPASO", cantidad, origen="ALMACEN",
                                        destino="ALMACEN", id_documento=id_documento, usuario=usuario,
                                        id_empresa=id_empresa, id_almacen_origen=almacen_origen,
                                        id_almacen_destino=almacen_destino,
                                        observaciones="Traspaso entre almacenes")
        except Exception:
            pass
        return True
    except Exception as e:
        logger.error("traspasar_stock: %s", e); return False


# ── Sembrado desde la caché (idempotente) ─────────────────────────────────────
def reseed_articulo(codigo, id_empresa=None) -> bool:
    """Siembra stock_almacen desde la caché actual preservando los valores:
    central←Stock_central, general←(Stock_total-Stock_central), tiendas←stock_tienda."""
    id_empresa = _tenant(id_empresa)
    alm = ensure_almacenes_empresa(id_empresa)
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COALESCE(Stock_central,0) c, COALESCE(Stock_total,0) t "
                        "FROM articulos WHERE codigo=%s AND id_empresa=%s", (codigo, id_empresa))
            r = cur.fetchone()
            if not r:
                return False
            central = int(r[0] if not isinstance(r, dict) else r["c"])
            total = int(r[1] if not isinstance(r, dict) else r["t"])
            _upsert(cur, id_empresa, alm["central"], codigo, absoluto=central)
            _upsert(cur, id_empresa, alm["general"], codigo, absoluto=max(0, total - central))
            cur.execute("SELECT id_tienda, stock FROM stock_tienda WHERE id_empresa=%s AND codigo_articulo=%s",
                        (id_empresa, codigo))
            for row in _filas_a_dicts(cur, cur.fetchall()):
                a = alm["tiendas"].get(row["id_tienda"])
                if a:
                    _upsert(cur, id_empresa, a, codigo, absoluto=int(row["stock"] or 0))
            # La tienda ACTIVA usa el Stock_tienda de trabajo (autoritativo sobre el snapshot).
            tid = _tienda_activa()
            if tid and alm["tiendas"].get(tid):
                cur.execute("SELECT COALESCE(Stock_tienda,0) FROM articulos WHERE codigo=%s AND id_empresa=%s",
                            (codigo, id_empresa))
                rr = cur.fetchone()
                if rr:
                    val = int(rr[0] if not isinstance(rr, dict) else list(rr.values())[0])
                    _upsert(cur, id_empresa, alm["tiendas"][tid], codigo, absoluto=val)
        return True
    except Exception as e:
        logger.error("reseed_articulo(%s): %s", codigo, e); return False


def reseed_todo(id_empresa=None) -> int:
    id_empresa = _tenant(id_empresa)
    n = 0
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT codigo FROM articulos WHERE id_empresa=%s", (id_empresa,))
            codigos = [(r[0] if not isinstance(r, dict) else r["codigo"]) for r in cur.fetchall()]
        for c in codigos:
            if reseed_articulo(c, id_empresa):
                n += 1
    except Exception as e:
        logger.error("reseed_todo: %s", e)
    return n
