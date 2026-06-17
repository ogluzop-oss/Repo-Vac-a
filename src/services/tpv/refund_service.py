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


def _get_plazo_dias() -> int:
    """Read return window from configuraciones, fall back to DEFAULT."""
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT plazo_devoluciones_dias FROM configuraciones LIMIT 1"
                )
                row = cur.fetchone()
                if row and row[0]:
                    return int(row[0])
    except Exception:
        pass
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
                    SELECT id, fecha, total, forma_pago, empleado, numero_caja
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

def validar_plazo(fecha_venta: datetime) -> tuple[bool, int, int]:
    """
    Returns (dentro_plazo, dias_transcurridos, plazo_maximo).
    """
    plazo = _get_plazo_dias()
    dias = (datetime.now() - fecha_venta).days
    return dias <= plazo, dias, plazo


# ─── Authorization check ──────────────────────────────────────────────────────

def verificar_autorizacion(nombre: str, pin: str) -> tuple[bool, str]:
    """
    Checks that the employee exists, has GERENTE/ADMINISTRADOR profile
    and the PIN matches. Returns (authorized, message).
    """
    try:
        from src.db.usuario import validar_login_empleado
        user = validar_login_empleado(nombre, pin)
        if not user:
            return False, "Credenciales incorrectas."
        perfil = user.get("perfil", "").upper()
        if perfil not in ("GERENTE", "ADMINISTRADOR"):
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
                                WHERE codigo = %s
                            """, (qty, cod))

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
        # E6.5: encola el asiento de devolución (no-op si la contabilidad está apagada).
        try:
            import datetime as _dt
            from src.services.contabilidad.posting import encolar_devolucion
            encolar_devolucion(dev_id, total_reembolso, _dt.date.today().strftime("%Y-%m-%d"),
                               tipo="venta", forma_pago=forma_reembolso)
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
