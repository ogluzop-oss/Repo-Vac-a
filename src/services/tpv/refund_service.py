"""
Refund Service — Smart Manager AI TPV Enterprise
Handles returns: deadline validation, authorization, DB recording,
stock reversion and payment method enforcement.
"""
from __future__ import annotations

import logging
from datetime import datetime

from src.utils import divisas

logger = logging.getLogger("tpv.refund")

# Default return window in days (overridden by configuraciones if available)
DEFAULT_PLAZO_DIAS = 30


# ─── DB helpers ───────────────────────────────────────────────────────────────

def _conn():
    from src.db.conexion import obtener_conexion
    return obtener_conexion()


def _emp():
    """Empresa de la sesión (tenant). Tras la PK compuesta de `articulos` (migr 0181), las mutaciones de stock
    por código deben filtrar por empresa; por defecto se usa la de la sesión."""
    from src.db.conexion import EMPRESA_DEFAULT_ID
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id() or EMPRESA_DEFAULT_ID
    except Exception:
        return EMPRESA_DEFAULT_ID


def _get_plazo_dias() -> int:
    """Plazo de devolución VIGENTE (usado solo como fallback para ventas anteriores a la
    migr. 0232, que no tienen `fecha_limite_devolucion` propia congelada). Lee de
    `config_ticket.devol_dias` — la MISMA tabla que edita Configuración → Plazo de
    devolución (`gestion_usuarios._guardar_devol`); antes leía de `configuraciones.
    plazo_devoluciones_dias`, una columna que ninguna pantalla llega a escribir nunca,
    así que cambiar el plazo en Configuración no tenía ningún efecto real."""
    try:
        from src.db.config_ticket import obtener_config_ticket
        return int(obtener_config_ticket()["devol_dias"])
    except Exception:
        return DEFAULT_PLAZO_DIAS


# ─── Ticket lookup ────────────────────────────────────────────────────────────

def buscar_venta(venta_id: int) -> dict | None:
    """
    Returns full sale dict with its items or None if not found.
    """
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, fecha, total, forma_pago, empleado, numero_caja,
                           fecha_limite_devolucion, cliente_id, id_empresa
                    FROM ventas WHERE id = %s
                """, (venta_id,))
                row = cur.fetchone()
                if not row:
                    return None
                venta = {
                    "id": row[0], "fecha": row[1],
                    "total": float(row[2] or 0),
                    "forma_pago": row[3], "empleado": row[4],
                    "numero_caja": row[5],
                    "fecha_limite_devolucion": row[6],
                    # Fidelización (PWA Fase 3): necesario para revertir puntos al devolver — la
                    # EMPRESA REAL de la venta, no la ambiente del proceso (mismo bug multi-tenant
                    # ya corregido antes en online_orders_service/circulares/remote_scan: una
                    # devolución procesada fuera de la sesión de escritorio normal, p.ej. desde un
                    # test o un futuro flujo sin sesión, resolvía `empresa_actual_id()` en vez de
                    # la empresa REAL de ESTA venta, y la reversión de puntos no encontraba fila).
                    "cliente_id": row[7],
                    "id_empresa": row[8],
                }

                cur.execute("""
                    SELECT codigo_articulo, nombre, cantidad, precio_unitario, subtotal,
                           peso_vendido, precio_kg, modo_venta
                    FROM venta_items WHERE venta_id = %s
                """, (venta_id,))
                cols = [c[0] for c in cur.description]
                venta["items"] = [dict(zip(cols, r, strict=False)) for r in cur.fetchall()]
                return venta
    except Exception as e:
        logger.error(f"buscar_venta {venta_id}: {e}")
        return None


# ─── Deadline validation ──────────────────────────────────────────────────────

def descuento_pct_efectivo(item: dict) -> float:
    """% de descuento REAL aplicado a esta línea vendida. `venta_items` nunca guardó un % de
    descuento como columna propia, pero sí `precio_unitario` (precio ORIGINAL, sin descontar) y
    `subtotal` (ya con el descuento aplicado) — de ahí se reconstruye el % exacto, sin necesitar
    ninguna columna/migración nueva ni tocar ningún INSERT de venta existente."""
    try:
        precio = float(item.get("precio_unitario", 0) or 0)
        cantidad = float(item.get("cantidad", 0) or 0)
        subtotal = float(item.get("subtotal", 0) or 0)
        bruto = precio * cantidad
        if bruto <= 0:
            return 0.0
        return max(0.0, round((1 - subtotal / bruto) * 100, 2))
    except Exception:
        return 0.0


def umbral_bloqueo_descuento(id_empresa=None) -> float | None:
    """% mínimo de descuento configurado en Configuración → Plazo devolución → "Artículos con
    descuento". None = función desactivada (nunca bloquea por este motivo)."""
    try:
        from src.db.config_ticket import obtener_config_ticket
        umbral = obtener_config_ticket(id_empresa).get("descuento_min_bloqueo")
        return float(umbral) if umbral else None
    except Exception as e:
        logger.error("umbral_bloqueo_descuento: %s", e)
        return None


def bloqueado_por_descuento(item: dict, id_empresa=None) -> tuple[bool, float, float | None]:
    """(bloqueado, descuento_real_pct, umbral_configurado). Política de empresa: cualquier
    artículo (sea cual sea su EAN — complementa, no sustituye, el bloqueo por lista de
    `devoluciones_baneados`) vendido con un descuento IGUAL O SUPERIOR al umbral configurado
    nunca admite devolución."""
    umbral = umbral_bloqueo_descuento(id_empresa)
    if not umbral:
        return False, 0.0, None
    pct = descuento_pct_efectivo(item)
    return pct >= umbral, pct, umbral


def validar_plazo(fecha_venta: datetime, fecha_limite: datetime | None = None) -> tuple[bool, int, int]:
    """
    Returns (dentro_plazo, dias_transcurridos, plazo_maximo).

    `fecha_limite`: la fecha límite CONGELADA de `ventas.fecha_limite_devolucion` (migr. 0232),
    si la venta la tiene — se respeta el plazo que se le comunicó al cliente EN SU TICKET, aunque
    la empresa haya cambiado el plazo de devolución después. Solo para ventas anteriores a esa
    migración (`fecha_limite is None`) se recalcula con el plazo VIGENTE ahora mismo.
    """
    dias = (datetime.now() - fecha_venta).days
    if fecha_limite is not None:
        plazo = (fecha_limite - fecha_venta).days
        return datetime.now() <= fecha_limite, dias, plazo
    plazo = _get_plazo_dias()
    return dias <= plazo, dias, plazo


# ─── Authorization check ──────────────────────────────────────────────────────

def verificar_autorizacion(nombre: str, pin: str) -> tuple[bool, str]:
    """
    Checks that the employee exists, has ADMINISTRADOR profile (SUPERADMIN also
    authorizes: rango jerárquico igual o superior, mismo criterio que
    `_PinDialog._roles_permitidos` en gestion_usuarios.py) and the PIN matches.
    Returns (authorized, message).
    """
    try:
        from src.db.usuario import validar_login_empleado
        user = validar_login_empleado(nombre, pin)
        if not user:
            return False, "Credenciales incorrectas."
        perfil = user.get("perfil", "").upper()
        if perfil not in ("ADMINISTRADOR", "SUPERADMIN"):
            return False, f"{nombre} no tiene permiso para autorizar devoluciones."
        return True, nombre
    except Exception as e:
        logger.error(f"verificar_autorizacion: {e}")
        return False, f"Error al verificar: {e}"


# ─── Refund enforcement ───────────────────────────────────────────────────────

def metodo_reembolso_permitido(forma_pago_original: str,
                                forma_reembolso: str) -> tuple[bool, str]:
    """
    Enforces refund method rules:
      - Card payment → must refund to card
      - Cash payment → can refund cash or store credit
    """
    orig = (forma_pago_original or "").lower()
    dest = (forma_reembolso or "").lower()

    if "tarjeta" in orig and "tarjeta" not in dest:
        return False, (
            "El pago original fue con tarjeta. "
            "La devolución debe realizarse sobre la misma tarjeta."
        )
    return True, ""


# ─── Core refund processing ───────────────────────────────────────────────────

def procesar_devolucion(
    venta_id: int,
    items_devolver: list[dict],       # [{codigo, nombre, cantidad, precio_unitario, subtotal}]
    forma_reembolso: str,
    forma_pago_original: str,
    empleado: str,
    numero_caja: int,
    motivo: str,
    autorizado_por: str | None = None,
    requirio_autorizacion: bool = False,
    observaciones: str = "",
) -> tuple[bool, str, int | None]:
    """
    Records the return in devoluciones + devolucion_items,
    reverts stock for each item, and logs the audit event.
    Returns (success, message, devolucion_id).
    """
    if not items_devolver:
        return False, "No hay artículos seleccionados para devolver.", None

    # Payment method enforcement
    ok, msg = metodo_reembolso_permitido(forma_pago_original, forma_reembolso)
    if not ok:
        return False, msg, None

    # Banned-article enforcement (re-validated here, at the service layer, not just in the GUI
    # dialog that disables the checkbox — a banned article must never be returnable regardless
    # of the caller: TPV, future API, self-checkout, etc.).
    try:
        from src.db import devoluciones_baneados as _ban
        for it in items_devolver:
            cod = it.get("codigo_articulo", "")
            if cod and cod != "GRANEL" and _ban.esta_baneado(cod):
                return False, f"El artículo {cod} está baneado para devoluciones y no puede procesarse.", None
    except Exception as e:
        logger.error(f"Error comprobando artículos baneados: {e}")

    # Bloqueo por política de descuento (re-validado aquí, a nivel de servicio — mismo criterio de
    # defensa en profundidad que el bloqueo por EAN de arriba): un artículo vendido con un
    # descuento igual o superior al umbral configurado nunca admite devolución, sea cual sea su EAN.
    try:
        for it in items_devolver:
            bloqueado, pct, umbral = bloqueado_por_descuento(it)
            if bloqueado:
                nombre = it.get("nombre") or it.get("codigo_articulo", "")
                return False, (
                    f"El artículo '{nombre}' se vendió con un {pct:.0f}% de descuento "
                    f"(≥ {umbral:.0f}% configurado) y no admite devolución por política de la empresa."
                ), None
    except Exception as e:
        logger.error(f"Error comprobando bloqueo por descuento: {e}")

    # Deadline enforcement (defense-in-depth, mirrors the GUI's hard block in
    # _DevolucionDialog._mostrar_alerta_caducado — an expired ticket is never returnable,
    # by design there is no manager-override for this).
    try:
        venta = buscar_venta(venta_id)
        if venta:
            fecha_venta = venta["fecha"]
            if isinstance(fecha_venta, str):
                fecha_venta = datetime.fromisoformat(fecha_venta)
            dentro, _dias, _plazo = validar_plazo(fecha_venta, venta.get("fecha_limite_devolucion"))
            if not dentro:
                return False, f"El ticket #{venta_id} ha superado el plazo de devolución y no se puede procesar.", None
    except Exception as e:
        logger.error(f"Error comprobando plazo de devolución: {e}")

    total_reembolso = round(sum(
        float(it.get("subtotal", 0)) for it in items_devolver
    ), 2)

    if total_reembolso <= 0:
        return False, "El importe de devolución no puede ser cero.", None

    try:
        from src.db.conexion import transaccion
        with transaccion() as conn:        # A2.3: devolución + ítems + stock atómicos
            with conn.cursor() as cur:
                # Insert devolucion header
                cur.execute("""
                    INSERT INTO devoluciones
                      (venta_original_id, total_reembolso, forma_reembolso,
                       forma_pago_original, empleado, numero_caja, motivo,
                       autorizado_por, requirio_autorizacion, observaciones)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    venta_id, total_reembolso, forma_reembolso,
                    forma_pago_original, empleado, numero_caja, motivo,
                    autorizado_por, 1 if requirio_autorizacion else 0,
                    observaciones
                ))
                dev_id = cur.lastrowid

                # Insert devolucion items + revert stock
                for it in items_devolver:
                    cur.execute("""
                        INSERT INTO devolucion_items
                          (devolucion_id, codigo_articulo, nombre,
                           cantidad, precio_unitario, subtotal)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        dev_id,
                        it.get("codigo_articulo", "GRANEL"),
                        it.get("nombre", ""),
                        float(it.get("cantidad", 1)),
                        float(it.get("precio_unitario", 0)),
                        float(it.get("subtotal", 0)),
                    ))
                    # Revert stock for unit-sold items (not bulk/granel)
                    cod = it.get("codigo_articulo", "")
                    if cod and cod != "GRANEL" and it.get("modo_venta", "UNIDAD") == "UNIDAD":
                        qty = int(it.get("cantidad", 0))
                        if qty > 0:
                            cur.execute("""
                                UPDATE articulos
                                SET Stock_tienda = Stock_tienda + %s
                                WHERE codigo = %s AND id_empresa = %s
                            """, (qty, cod, _emp()))

                # Audit log
                cur.execute("""
                    INSERT INTO auditoria_logs
                      (usuario, accion, tabla_afectada, detalles)
                    VALUES (%s, %s, %s, %s)
                """, (
                    empleado,
                    "DEVOLUCIÓN PROCESADA",
                    "devoluciones",
                    f"dev_id={dev_id} venta_id={venta_id} "
                    f"importe={divisas.formatear(total_reembolso)} "
                    f"forma={forma_reembolso} "
                    f"autorizado_por={autorizado_por or 'N/A'}"
                ))

            # commit gestionado por transaccion()
        logger.info(
            f"Devolución #{dev_id} procesada: {divisas.formatear(total_reembolso)} "
            f"venta={venta_id} forma={forma_reembolso}"
        )
        # INV.1: kárdex DEVOLUCION por ítem repuesto (best-effort, tras commit).
        try:
            from src.db import kardex
            for it in items_devolver:
                cod = it.get("codigo_articulo", "")
                if cod and cod != "GRANEL" and it.get("modo_venta", "UNIDAD") == "UNIDAD":
                    qty = int(it.get("cantidad", 0))
                    if qty > 0:
                        kardex.registrar_movimiento(
                            cod, "DEVOLUCION", qty, id_documento=dev_id, destino="TIENDA",
                            usuario=empleado,
                            observaciones=f"Devolución #{dev_id} de venta #{venta_id}")
        except Exception:
            pass
        # VTA.5: restituye al ALMACÉN y LOTE originales de la venta cuando existan.
        try:
            from src.db.conexion import obtener_conexion
            from src.db import stock_almacen as SA, lotes as L
            with obtener_conexion() as _c, _c.cursor() as _cur:
                for it in items_devolver:
                    cod = it.get("codigo_articulo", "")
                    qty = int(it.get("cantidad", 0))
                    if not cod or cod == "GRANEL" or qty <= 0:
                        continue
                    _cur.execute("SELECT id_almacen, id_lote FROM venta_items WHERE venta_id=%s "
                                 "AND codigo_articulo=%s LIMIT 1", (venta_id, cod))
                    row = _cur.fetchone()
                    if not row:
                        continue
                    id_alm = row[0] if not isinstance(row, dict) else row["id_almacen"]
                    id_lote = row[1] if not isinstance(row, dict) else row["id_lote"]
                    if id_alm:
                        SA.incrementar_stock(cod, id_alm, qty)
                    if id_lote:
                        lt = L.obtener_lote(id_lote)
                        if lt:
                            L.registrar_entrada(cod, lt["lote"], qty,
                                                fecha_caducidad=lt.get("fecha_caducidad"),
                                                id_almacen=id_alm, origen="devolucion",
                                                id_documento=f"DEV{dev_id}", usuario=empleado)
        except Exception:
            pass
        # E6.5: encola el asiento de devolución (no-op si la contabilidad está apagada).
        try:
            import datetime as _dt
            from src.services.contabilidad.posting import encolar_devolucion
            encolar_devolucion(dev_id, total_reembolso, _dt.date.today().strftime("%Y-%m-%d"),
                               tipo="venta", forma_pago=forma_reembolso)
        except Exception:
            pass
        # Fidelización (Generador de Apps Móviles PWA, Fase 3): revierte los puntos acumulados por
        # la venta original si estaba vinculada a un cliente (`venta` ya se obtuvo arriba para la
        # comprobación del plazo) — simétrico al gancho de acumulación en
        # `conexion.registrar_venta_con_items`. Best-effort, nunca rompe la devolución.
        try:
            cliente_id = (venta or {}).get("cliente_id")
            if cliente_id:
                from src.db import fidelizacion as _fid
                _fid.revertir_puntos(cliente_id, total_reembolso, id_venta=venta_id,
                                     id_empresa=(venta or {}).get("id_empresa"))
        except Exception:
            pass
        return True, f"Devolución #{dev_id} registrada. Importe: {divisas.formatear(total_reembolso)}", dev_id

    except Exception as e:
        logger.error(f"procesar_devolucion: {e}")
        return False, f"Error al procesar la devolución: {e}", None


# ─── History ──────────────────────────────────────────────────────────────────

def historial_devoluciones(limit: int = 50) -> list[dict]:
    """Returns recent returns for audit/reporting."""
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, fecha, venta_original_id, total_reembolso,
                           forma_reembolso, empleado, autorizado_por,
                           requirio_autorizacion, estado
                    FROM devoluciones
                    ORDER BY fecha DESC
                    LIMIT %s
                """, (limit,))
                cols = [c[0] for c in cur.description]
                return [dict(zip(cols, r, strict=False)) for r in cur.fetchall()]
    except Exception as e:
        logger.error(f"historial_devoluciones: {e}")
        return []


def historial_devoluciones_anual(anio, id_empresa) -> dict:
    """Totales de devoluciones del ejercicio `anio` para la empresa `id_empresa`.

    `devoluciones` no tiene columna `id_empresa` propia (es una tabla histórica previa al
    modelo multiempresa) — se filtra uniendo con `ventas` por `venta_original_id`, que sí
    está aislada por empresa. Una devolución de una venta ya borrada (`venta_original_id`
    NULL tras el ON DELETE SET NULL del FK) queda fuera del cómputo por empresa: no hay forma
    honesta de atribuirla a una empresa sin la venta original.
    """
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) AS registros, COALESCE(SUM(d.total_reembolso),0) AS total
                    FROM devoluciones d
                    JOIN ventas v ON v.id = d.venta_original_id
                    WHERE v.id_empresa = %s AND YEAR(d.fecha) = %s
                """, (id_empresa, int(anio)))
                row = cur.fetchone()
                if not row:
                    return {"registros": 0, "total_reembolso": 0.0}
                registros = row[0] if not isinstance(row, dict) else row["registros"]
                total = row[1] if not isinstance(row, dict) else row["total"]
                return {"registros": int(registros or 0), "total_reembolso": round(float(total or 0), 2)}
    except Exception as e:
        logger.error(f"historial_devoluciones_anual({anio}): {e}")
        return {"registros": 0, "total_reembolso": 0.0}
