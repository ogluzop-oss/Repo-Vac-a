"""
Gastos de viaje / notas de gastos (petición explícita, migr. 0324) — motor NUEVO (auditoría previa:
no existía ningún concepto de gasto de empleado en el repo). Flujo: empleado registra un gasto
(opcionalmente con foto de ticket, extraído por `ticket_ocr`) → pendiente → aprobado/rechazado por
RRHH → reembolso inyectado en la PRÓXIMA nómina del empleado (concepto `dietas` ya existente del
motor de nómina, vía `services.rrhh.nominas_pro` — NUNCA un motor de pago paralelo). Multiempresa.
"""

import logging

logger = logging.getLogger("gastos_viaje")

CATEGORIAS = ("transporte", "alojamiento", "dietas", "otros")
ESTADOS = ("pendiente", "aprobado", "rechazado", "reembolsado")


class GastoViajeError(Exception):
    """Validación de negocio fallida (importe/categoría/estado inválidos, transición no permitida)."""


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _siguiente_codigo(cur, id_empresa) -> str:
    cur.execute("SELECT codigo FROM gastos_viaje WHERE id_empresa=%s ORDER BY id DESC LIMIT 1",
               (id_empresa,))
    row = cur.fetchone()
    ultimo = 0
    if row:
        try:
            ultimo = int(str(row[0]).split("-")[-1])
        except (ValueError, IndexError):
            ultimo = 0
    return f"GV-{ultimo + 1:05d}"


def crear_gasto(id_empleado, fecha_gasto, categoria, importe, *, concepto=None, id_proyecto=None,
                moneda="EUR", ruta_ticket=None, ocr_origen=False, id_empresa=None) -> dict:
    if categoria not in CATEGORIAS:
        raise GastoViajeError(f"Categoría no válida: {categoria!r}")
    try:
        importe = round(float(importe), 2)
    except (TypeError, ValueError):
        raise GastoViajeError("El importe no es un número válido.") from None
    if importe <= 0:
        raise GastoViajeError("El importe debe ser mayor que cero.")
    if not id_empleado:
        raise GastoViajeError("Falta el empleado.")
    id_empresa = _emp(id_empresa)
    try:
        from src.db.conexion import transaccion
        with transaccion() as conn, conn.cursor() as cur:
            codigo = _siguiente_codigo(cur, id_empresa)
            cur.execute(
                "INSERT INTO gastos_viaje (id_empresa, codigo, id_empleado, id_proyecto, "
                "fecha_gasto, categoria, concepto, importe, moneda, ruta_ticket, ocr_origen) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, codigo, id_empleado, id_proyecto, fecha_gasto, categoria,
                 (concepto or "").strip() or None, importe, moneda, ruta_ticket, bool(ocr_origen)))
            id_gasto = cur.lastrowid
    except Exception as e:
        logger.error("crear_gasto: %s", e)
        raise GastoViajeError("No se pudo registrar el gasto.") from e

    try:
        from src.services import eventos as _EV
        _EV.publicar("GASTO_VIAJE_CREADO", id_empresa=id_empresa, origen="gastos_viaje",
                     ref_entidad="gasto_viaje", ref_id=id_gasto,
                     payload={"codigo": codigo, "importe": importe, "categoria": categoria})
    except Exception:
        pass
    return {"ok": True, "id": id_gasto, "codigo": codigo}


def obtener_gasto(id_gasto, id_empresa=None) -> dict | None:
    id_empresa = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM gastos_viaje WHERE id=%s AND id_empresa=%s",
                       (id_gasto, id_empresa))
            cols = [d[0] for d in cur.description]
            row = cur.fetchone()
            return dict(zip(cols, row)) if row else None
    except Exception as e:
        logger.error("obtener_gasto(%s): %s", id_gasto, e)
        return None


def listar_gastos(*, id_empresa=None, id_empleado=None, estado=None, limite=1000) -> list:
    id_empresa = _emp(id_empresa)
    filtros, params = ["id_empresa=%s"], [id_empresa]
    if id_empleado is not None:
        filtros.append("id_empleado=%s"); params.append(id_empleado)
    if estado:
        filtros.append("estado=%s"); params.append(estado)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM gastos_viaje WHERE " + " AND ".join(filtros) +
                " ORDER BY fecha_creacion DESC LIMIT %s", (*params, int(limite)))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_gastos: %s", e)
        return []


def aprobar(id_gasto, *, usuario=None, id_empresa=None) -> dict:
    id_empresa = _emp(id_empresa)
    g = obtener_gasto(id_gasto, id_empresa)
    if not g:
        raise GastoViajeError("Gasto no encontrado.")
    if g["estado"] != "pendiente":
        raise GastoViajeError(f"No se puede aprobar desde el estado '{g['estado']}'.")
    try:
        from src.db.conexion import transaccion
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE gastos_viaje SET estado='aprobado', aprobado_por=%s, "
                       "fecha_aprobacion=NOW() WHERE id=%s AND id_empresa=%s",
                       (usuario, id_gasto, id_empresa))
        return {"ok": True}
    except Exception as e:
        logger.error("aprobar(%s): %s", id_gasto, e)
        return {"ok": False, "error": "error_interno"}


def rechazar(id_gasto, motivo, *, usuario=None, id_empresa=None) -> dict:
    id_empresa = _emp(id_empresa)
    g = obtener_gasto(id_gasto, id_empresa)
    if not g:
        raise GastoViajeError("Gasto no encontrado.")
    if g["estado"] != "pendiente":
        raise GastoViajeError(f"No se puede rechazar desde el estado '{g['estado']}'.")
    try:
        from src.db.conexion import transaccion
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE gastos_viaje SET estado='rechazado', aprobado_por=%s, "
                       "fecha_aprobacion=NOW(), motivo_rechazo=%s WHERE id=%s AND id_empresa=%s",
                       (usuario, (motivo or "").strip() or None, id_gasto, id_empresa))
        return {"ok": True}
    except Exception as e:
        logger.error("rechazar(%s): %s", id_gasto, e)
        return {"ok": False, "error": "error_interno"}


# ── Reembolso en nómina (petición explícita: "flujo de aprobación para su reembolso en nómina") ──
def total_pendiente_reembolso(id_empleado, *, id_empresa=None) -> float:
    """Importe total APROBADO (no reembolsado todavía) de un empleado — se inyecta en el concepto
    `dietas` de su próxima nómina, ver `services.rrhh.nominas_pro.preparar_datos_nomina`."""
    id_empresa = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COALESCE(SUM(importe),0) FROM gastos_viaje WHERE id_empresa=%s "
                       "AND id_empleado=%s AND estado='aprobado'", (id_empresa, id_empleado))
            fila = cur.fetchone()
            return round(float(fila[0] or 0), 2) if fila else 0.0
    except Exception as e:
        logger.error("total_pendiente_reembolso(%s): %s", id_empleado, e)
        return 0.0


def marcar_reembolsados(id_empleado, *, id_nomina=None, id_empresa=None) -> dict:
    """Marca todos los gastos APROBADOS del empleado como `reembolsado` (al confirmar la nómina que
    ya incluyó su importe) — mismo gesto explícito/no-automático que `nominas_pro.amortizar_anticipos`
    (se pide confirmación al humano antes de llamarlo, nunca se dispara solo)."""
    id_empresa = _emp(id_empresa)
    try:
        from src.db.conexion import transaccion
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE gastos_viaje SET estado='reembolsado', id_nomina_reembolso=%s "
                       "WHERE id_empresa=%s AND id_empleado=%s AND estado='aprobado'",
                       (id_nomina, id_empresa, id_empleado))
            total = cur.rowcount
        return {"ok": True, "marcados": total}
    except Exception as e:
        logger.error("marcar_reembolsados(%s): %s", id_empleado, e)
        return {"ok": False, "error": "error_interno"}
