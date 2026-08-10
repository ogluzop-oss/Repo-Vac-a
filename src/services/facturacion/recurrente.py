"""
FASE 4.1 — Facturación RECURRENTE (alquileres, mantenimiento, cuotas, servicios periódicos).

Genera facturas periódicas reutilizando EL MOTOR ACTUAL (facturas_cliente.crear_factura): cada
generación crea factura + snapshot(*) + auditoría + numeración + (si procede) vencimiento, sin
duplicar lógica. (*) El snapshot/PDF se construye con el mismo flujo de la factura comercial.
"""

import datetime as _dt
import logging

logger = logging.getLogger("facturacion.recurrente")

FRECUENCIAS = ("diaria", "semanal", "mensual", "trimestral", "semestral", "anual")
_DIAS = {"diaria": 1, "semanal": 7}
_MESES = {"mensual": 1, "trimestral": 3, "semestral": 6, "anual": 12}


def _emp(id_empresa=None):
    # IOC v2 (Bloque III): resolución de empresa vía capa de identidad (Strangler).
    try:
        from src.services.facturacion.identidad_facturacion import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        from src.db.empresa import empresa_actual_id
        return id_empresa or empresa_actual_id()


def _suma_meses(fecha: _dt.date, meses: int) -> _dt.date:
    m = fecha.month - 1 + meses
    y = fecha.year + m // 12
    m = m % 12 + 1
    import calendar
    d = min(fecha.day, calendar.monthrange(y, m)[1])
    return _dt.date(y, m, d)


def avanzar(fecha: _dt.date, frecuencia: str) -> _dt.date:
    if frecuencia in _DIAS:
        return fecha + _dt.timedelta(days=_DIAS[frecuencia])
    return _suma_meses(fecha, _MESES.get(frecuencia, 1))


def crear(id_cliente, importe, *, frecuencia="mensual", concepto=None, iva=None, divisa=None,
          tipo_documento="factura", fecha_inicio=None, fecha_fin=None, dia_facturacion=1,
          id_tienda=None, id_empresa=None) -> int | None:
    id_empresa = _emp(id_empresa)
    if frecuencia not in FRECUENCIAS:
        frecuencia = "mensual"
    ini = fecha_inicio or _dt.date.today().isoformat()
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO facturacion_recurrente (id_empresa, id_cliente, id_tienda, concepto, "
                "estado, fecha_inicio, fecha_fin, frecuencia, dia_facturacion, importe, iva, divisa, "
                "tipo_documento, proxima_generacion) "
                "VALUES (%s,%s,%s,%s,'activa',%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, id_cliente, id_tienda, concepto, ini, fecha_fin, frecuencia,
                 int(dia_facturacion or 1), round(float(importe or 0), 2),
                 iva, divisa, tipo_documento, ini))
            rid = cur.lastrowid
            conn.commit()
            return rid
    except Exception as e:
        logger.error("recurrente.crear: %s", e); return None


def listar(id_empresa=None, estado=None) -> list:
    id_empresa = _emp(id_empresa)
    from src.db.conexion import _filas_a_dicts, obtener_conexion
    cond, params = ["id_empresa=%s"], [id_empresa]
    if estado:
        cond.append("estado=%s"); params.append(estado)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT * FROM facturacion_recurrente WHERE {' AND '.join(cond)} "
                        "ORDER BY proxima_generacion", params)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("recurrente.listar: %s", e); return []


def generar_una(rec, id_empresa=None) -> int | None:
    """Genera UNA factura a partir de una plantilla recurrente (dict). Devuelve id_factura."""
    id_empresa = _emp(id_empresa)
    from src.db import facturas_cliente as FC
    lineas = [{"descripcion": rec.get("concepto") or "Servicio recurrente", "cantidad": 1,
               "precio_unitario": float(rec.get("importe") or 0),
               "subtotal": float(rec.get("importe") or 0),
               "iva": float(rec["iva"]) if rec.get("iva") is not None else None}]
    fid = FC.crear_factura(id_cliente=rec.get("id_cliente"), lineas=lineas,
                           tipo_documento=rec.get("tipo_documento") or "factura",
                           id_tienda=rec.get("id_tienda"), id_empresa=id_empresa)
    if fid:
        try:
            from src.db.conexion import obtener_conexion
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("UPDATE facturas_cliente SET origen='recurrente', id_recurrente=%s "
                            "WHERE id_factura=%s", (rec.get("id"), fid))
                conn.commit()
            FC.registrar_evento(fid, "FACTURA_RECURRENTE", detalle=str(rec.get("id")),
                                id_empresa=id_empresa)
        except Exception:
            pass
    return fid


def generar_pendientes(hoy=None, id_empresa=None) -> dict:
    """Genera todas las facturas recurrentes vencidas (proxima_generacion <= hoy). Idempotente
    por avance de fecha. Devuelve {generadas, ids}."""
    id_empresa = _emp(id_empresa)
    hoy = _dt.date.fromisoformat(hoy) if isinstance(hoy, str) else (hoy or _dt.date.today())
    from src.db.conexion import obtener_conexion
    ids = []
    for rec in listar(id_empresa, estado="activa"):
        prox = rec.get("proxima_generacion")
        if isinstance(prox, str):
            try: prox = _dt.date.fromisoformat(prox[:10])
            except Exception: prox = None
        fin = rec.get("fecha_fin")
        if isinstance(fin, str):
            try: fin = _dt.date.fromisoformat(fin[:10])
            except Exception: fin = None
        if not prox or prox > hoy or (fin and prox > fin):
            continue
        fid = generar_una(rec, id_empresa)
        if fid:
            ids.append(fid)
            nueva = avanzar(prox, rec.get("frecuencia") or "mensual")
            estado = "finalizada" if (fin and nueva > fin) else "activa"
            try:
                with obtener_conexion() as conn, conn.cursor() as cur:
                    cur.execute("UPDATE facturacion_recurrente SET ultima_generacion=%s, "
                                "proxima_generacion=%s, estado=%s WHERE id=%s",
                                (prox.isoformat(), nueva.isoformat(), estado, rec.get("id")))
                    conn.commit()
            except Exception as e:
                logger.error("recurrente avanzar(%s): %s", rec.get("id"), e)
    return {"generadas": len(ids), "ids": ids}
