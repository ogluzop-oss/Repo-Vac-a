"""
Fidelización (VTA.3) — puntos, monedero y cupones.

Acumulación/canje de puntos y saldo de monedero del cliente, y emisión/validación/redención
de cupones con caducidad. `clientes.saldo_puntos`/`saldo_monedero` son la caché de saldo;
`fidelizacion_movimientos` el libro. Best-effort, multiempresa. Sin Qt.
"""

import datetime as _dt
import logging

from src.db.conexion import _fila_a_dict, _filas_a_dicts, ensure_schema, obtener_conexion, transaccion

logger = logging.getLogger("ventas.fidelizacion")

PUNTOS_POR_EURO = 1   # 1 punto por € (configurable a futuro)


def _emp(id_empresa=None):
    # IOC v3 (Bloque V): seam de identidad delegado en la fachada de datos (db -> db).
    try:
        from src.db.identidad_contexto import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        try:
            from src.db.empresa import empresa_actual_id
            return id_empresa or empresa_actual_id()
        except Exception:
            from src.db.conexion import EMPRESA_DEFAULT_ID
            return id_empresa or EMPRESA_DEFAULT_ID


def _mov(cur, id_empresa, id_cliente, tipo, puntos=0, importe=0, id_venta=None, desc=None):
    cur.execute("INSERT INTO fidelizacion_movimientos (id_empresa, id_cliente, tipo, puntos, "
                "importe, id_venta, descripcion) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, id_cliente, tipo, int(puntos), float(importe), id_venta, desc))


def saldo_puntos(id_cliente, id_empresa=None) -> int:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COALESCE(saldo_puntos,0) FROM clientes WHERE id=%s AND id_empresa=%s",
                        (id_cliente, id_empresa))
            r = cur.fetchone()
            return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) if r else 0
    except Exception as e:
        logger.error("saldo_puntos: %s", e); return 0


def acumular_puntos(id_cliente, importe_venta, id_venta=None, id_empresa=None) -> int:
    """Acumula puntos por una venta (PUNTOS_POR_EURO). Devuelve puntos añadidos."""
    id_empresa = _emp(id_empresa)
    pts = int(float(importe_venta or 0) * PUNTOS_POR_EURO)
    if pts <= 0 or not id_cliente:
        return 0
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE clientes SET saldo_puntos=COALESCE(saldo_puntos,0)+%s "
                        "WHERE id=%s AND id_empresa=%s", (pts, id_cliente, id_empresa))
            _mov(cur, id_empresa, id_cliente, "acumular", puntos=pts, importe=importe_venta,
                 id_venta=id_venta, desc="Acumulación por venta")
        return pts
    except Exception as e:
        logger.error("acumular_puntos: %s", e); return 0


def canjear_puntos(id_cliente, puntos, id_empresa=None) -> bool:
    """Canjea puntos (resta del saldo). Falla si no hay saldo suficiente."""
    id_empresa = _emp(id_empresa)
    puntos = int(puntos)
    if puntos <= 0:
        return False
    if saldo_puntos(id_cliente, id_empresa) < puntos:
        return False
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE clientes SET saldo_puntos=saldo_puntos-%s WHERE id=%s AND id_empresa=%s",
                        (puntos, id_cliente, id_empresa))
            _mov(cur, id_empresa, id_cliente, "canjear", puntos=-puntos, desc="Canje de puntos")
        return True
    except Exception as e:
        logger.error("canjear_puntos: %s", e); return False


def revertir_puntos(id_cliente, importe_venta, id_venta=None, id_empresa=None) -> int:
    """Revierte la acumulación de una venta devuelta. Devuelve puntos retirados."""
    id_empresa = _emp(id_empresa)
    pts = int(float(importe_venta or 0) * PUNTOS_POR_EURO)
    if pts <= 0 or not id_cliente:
        return 0
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE clientes SET saldo_puntos=GREATEST(0,COALESCE(saldo_puntos,0)-%s) "
                        "WHERE id=%s AND id_empresa=%s", (pts, id_cliente, id_empresa))
            _mov(cur, id_empresa, id_cliente, "revertir", puntos=-pts, id_venta=id_venta,
                 desc="Reversión por devolución")
        return pts
    except Exception as e:
        logger.error("revertir_puntos: %s", e); return 0


# Catálogo de recompensas (Generador de Apps Móviles PWA, Fase 3 — "Gamificación: 1€=1 punto,
# canje por cupones"): tramos fijos puntos->cupón de importe fijo. Reutiliza `emitir_cupon`
# (motor de cupones ya existente), no crea un sistema de descuentos paralelo.
TIERS_CANJE = ((100, 5.0), (200, 12.0), (500, 35.0))


def canjear_por_cupon(id_cliente, puntos, id_empresa=None) -> dict:
    """Canjea `puntos` (debe coincidir con uno de los tramos de `TIERS_CANJE`) por un cupón de
    importe fijo ligado a este cliente, con 30 días de validez. Nunca deja el saldo descontado
    sin emitir el cupón: si `emitir_cupon` falla, revierte el canje de puntos."""
    id_empresa = _emp(id_empresa)
    puntos = int(puntos)
    valor = next((v for p, v in TIERS_CANJE if p == puntos), None)
    if valor is None:
        return {"ok": False, "error": "tramo_invalido"}
    if not canjear_puntos(id_cliente, puntos, id_empresa=id_empresa):
        return {"ok": False, "error": "saldo_insuficiente"}
    import secrets
    codigo = f"FID-{secrets.token_hex(4).upper()}"
    caduca = (_dt.date.today() + _dt.timedelta(days=30)).isoformat()
    cid = emitir_cupon(codigo, tipo="importe_fijo", valor=valor, id_cliente=id_cliente,
                       fecha_caducidad=caduca, id_empresa=id_empresa)
    if not cid:
        # No se pudo emitir el cupón: revertir el gasto de puntos (nunca cobrar sin entregar).
        try:
            with transaccion() as conn, conn.cursor() as cur:
                cur.execute("UPDATE clientes SET saldo_puntos=COALESCE(saldo_puntos,0)+%s "
                            "WHERE id=%s AND id_empresa=%s", (puntos, id_cliente, id_empresa))
                _mov(cur, id_empresa, id_cliente, "ajuste", puntos=puntos,
                     desc="Reversión: fallo al emitir cupón de canje")
        except Exception as e:
            logger.error("canjear_por_cupon: fallo revirtiendo tras error de emisión: %s", e)
        return {"ok": False, "error": "emision_fallida"}
    return {"ok": True, "codigo": codigo, "valor": valor, "caduca": caduca}


def movimientos(id_cliente, id_empresa=None) -> list:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM fidelizacion_movimientos WHERE id_cliente=%s AND id_empresa=%s "
                        "ORDER BY fecha DESC, id DESC", (id_cliente, id_empresa))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("movimientos: %s", e); return []


# ── Cupones ───────────────────────────────────────────────────────────────────
TIPOS_CUPON = ("descuento_pct", "importe_fijo", "envio_gratis")


def emitir_cupon(codigo, tipo="descuento_pct", valor=0, id_cliente=None, fecha_caducidad=None,
                 fecha_inicio=None, uso_maximo=1, importe_minimo=None, id_empresa=None) -> int | None:
    """`uso_maximo` (Fase 2 e-commerce — "límite de usos totales" del encargo): por DEFECTO 1,
    preserva el comportamiento de siempre (un cupón = un solo uso) — subirlo es opt-in explícito,
    nunca retroactivo. `importe_minimo`: el cupón no se valida si el carrito no lo alcanza
    ("uso mínimo" del encargo, interpretado como importe mínimo de pedido — el estándar de
    Shopify/la mayoría de motores de cupón). `tipo="envio_gratis"` no descuenta el subtotal de
    productos (ver `comercio_digital.comercial.cotizar`, que expone `envio_gratis=True` en su
    resultado para que el motor de envíos lo aplique cuando exista — Fase 3)."""
    id_empresa = _emp(id_empresa)
    try:
        ensure_schema()
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO cupones (id_empresa, codigo, id_cliente, tipo, valor, fecha_caducidad, "
                "fecha_inicio, uso_maximo, importe_minimo) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, codigo, id_cliente, tipo, valor, fecha_caducidad, fecha_inicio,
                 int(uso_maximo or 1), importe_minimo))
            return cur.lastrowid
    except Exception as e:
        logger.error("emitir_cupon: %s", e); return None


def validar_cupon(codigo, id_empresa=None, *, id_cliente=None, importe_pedido=None) -> dict | None:
    """Devuelve el cupón si está activo, dentro de su ventana de fechas, con usos disponibles,
    restringido al cliente correcto (si lo está) y el pedido alcanza su importe mínimo (si lo
    tiene); None en cualquier otro caso. `id_cliente`/`importe_pedido` son opcionales (None =
    no se comprueba esa condición — mismo criterio best-effort que el resto del motor)."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM cupones WHERE codigo=%s AND id_empresa=%s", (codigo, id_empresa))
            c = _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        logger.error("validar_cupon: %s", e); return None
    if not c or c.get("estado") != "activo":
        return None
    hoy = _dt.date.today()
    if c.get("fecha_inicio") and hoy < c["fecha_inicio"]:
        return None
    if c.get("fecha_caducidad") and hoy > c["fecha_caducidad"]:
        return None
    if int(c.get("usos_actuales") or 0) >= int(c.get("uso_maximo") or 1):
        return None
    if c.get("id_cliente") and id_cliente and str(c["id_cliente"]) != str(id_cliente):
        return None
    if c.get("importe_minimo") and importe_pedido is not None \
            and float(importe_pedido) < float(c["importe_minimo"]):
        return None
    return c


def redimir_cupon(codigo, id_venta=None, id_empresa=None, *, id_cliente=None,
                  importe_pedido=None) -> bool:
    """Redime UN uso del cupón. Con `uso_maximo` > 1 el cupón sigue 'activo' mientras le queden
    usos (incrementa `usos_actuales`); al agotar el último uso pasa a 'usado' — mismo estado
    terminal de siempre, ahora alcanzado por contador en vez de por una única redención."""
    id_empresa = _emp(id_empresa)
    c = validar_cupon(codigo, id_empresa, id_cliente=id_cliente, importe_pedido=importe_pedido)
    if not c:
        return False
    try:
        with transaccion() as conn, conn.cursor() as cur:
            usos_tras = int(c.get("usos_actuales") or 0) + 1
            agotado = usos_tras >= int(c.get("uso_maximo") or 1)
            cur.execute(
                "UPDATE cupones SET usos_actuales=%s, id_venta_uso=%s"
                + (", estado='usado'" if agotado else "") + " WHERE id=%s AND id_empresa=%s",
                (usos_tras, id_venta, c["id"], id_empresa))
        return True
    except Exception as e:
        logger.error("redimir_cupon: %s", e); return False


def expirar_cupones(id_empresa=None) -> int:
    id_empresa = _emp(id_empresa)
    hoy = _dt.date.today().isoformat()
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE cupones SET estado='caducado' WHERE id_empresa=%s AND estado='activo' "
                        "AND fecha_caducidad IS NOT NULL AND fecha_caducidad < %s", (id_empresa, hoy))
            return cur.rowcount
    except Exception as e:
        logger.error("expirar_cupones: %s", e); return 0


def listar_cupones(id_empresa=None) -> list:
    """Todos los cupones de la empresa, más recientes primero — para la pantalla de gestión
    (Catálogo Web → Descuentos, Fase 2 e-commerce)."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM cupones WHERE id_empresa=%s ORDER BY fecha DESC, id DESC",
                        (id_empresa,))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_cupones: %s", e); return []


def desactivar_cupon(id_cupon, id_empresa=None) -> bool:
    """Cancela un cupón manualmente (p. ej. se publicó por error) — estado terminal distinto de
    'usado'/'caducado' para que el motivo quede claro en la gestión, aunque a `validar_cupon` le
    basta con que no sea 'activo'."""
    id_empresa = _emp(id_empresa)
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE cupones SET estado='cancelado' WHERE id=%s AND id_empresa=%s "
                        "AND estado='activo'", (id_cupon, id_empresa))
            return cur.rowcount > 0
    except Exception as e:
        logger.error("desactivar_cupon(%s): %s", id_cupon, e); return False
