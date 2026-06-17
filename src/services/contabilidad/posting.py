"""
Posting contable asíncrono (E6.4/E6.5) — cola + generación de asientos.

DC2: COLA ASÍNCRONA + AGREGACIÓN DIARIA. Los eventos del ERP (ventas, compras,
devoluciones) se ENCOLAN (best-effort, sin bloquear la operación) y un procesador
genera los asientos: tickets de TPV → 1 asiento resumen por día; facturas → 1 por
documento. Idempotente; nunca rompe la venta/compra.
"""

import datetime as _dt
import json
import logging

from src.db.conexion import (EMPRESA_DEFAULT_ID, _filas_a_dicts, ensure_schema,
                             obtener_conexion)
from src.services.contabilidad import asientos as A
from src.services.contabilidad import cuentas as K
from src.services.contabilidad import mapeo as M

logger = logging.getLogger("contab.posting")


def _empresa(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def _fecha(f):
    if isinstance(f, (_dt.date, _dt.datetime)):
        return f.strftime("%Y-%m-%d")
    return str(f)[:10]


def _desglose(total, id_empresa):
    """(base, cuota, tipo_iva) IVA-incluido, usando la MISMA fuente fiscal."""
    try:
        from src.utils import fiscalidad
        d = fiscalidad.desglose_iva(total, id_empresa=id_empresa)
        return round(d["base"], 2), round(d["cuota"], 2), d["tipo"]
    except Exception:
        base = round(float(total or 0), 2)
        return base, 0.0, 0.0


# ── Encolado (desde hooks del ERP) ────────────────────────────────────────────
def encolar(evento, ref, total, fecha, subtipo=None, extra=None, id_empresa=None) -> int | None:
    """Encola un evento económico SOLO si la contabilidad está activa. Best-effort."""
    id_empresa = _empresa(id_empresa)
    if not K.contabilidad_activa(id_empresa):
        return None
    payload = {"total": round(float(total or 0), 2)}
    if extra:
        payload.update(extra)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO contab_cola (id_empresa, evento, subtipo, ref, fecha_evento, "
                        "payload) VALUES (%s,%s,%s,%s,%s,%s)",
                        (id_empresa, evento, subtipo, str(ref), _fecha(fecha),
                         json.dumps(payload, ensure_ascii=False)))
            cid = cur.lastrowid
            conn.commit()
            return cid
    except Exception as e:
        logger.warning("encolar(%s,%s): %s", evento, ref, e)
        return None


def encolar_venta(ref, total, fecha, forma_pago="efectivo", subtipo="ticket", id_empresa=None):
    return encolar("venta", ref, total, fecha, subtipo=subtipo,
                   extra={"forma_pago": forma_pago}, id_empresa=id_empresa)


def encolar_compra(ref, total, fecha, id_empresa=None, base=None, iva=None, subtipo="factura"):
    extra = {}
    if base is not None:
        extra["base"] = round(float(base), 2)
    if iva is not None:
        extra["iva"] = round(float(iva), 2)
    return encolar("compra", ref, total, fecha, subtipo=subtipo, extra=extra, id_empresa=id_empresa)


def encolar_devolucion(ref, total, fecha, tipo="venta", forma_pago="efectivo", id_empresa=None):
    """Devolución de venta (o de compra) → contraflujo del importe."""
    return encolar("devolucion", ref, total, fecha, subtipo=tipo,
                   extra={"forma_pago": forma_pago}, id_empresa=id_empresa)


# ── Procesado de la cola → asientos ──────────────────────────────────────────
def _pendientes(cur, id_empresa, evento):
    cur.execute("SELECT * FROM contab_cola WHERE id_empresa=%s AND evento=%s AND estado='pendiente' "
                "ORDER BY fecha_evento, id", (id_empresa, evento))
    return _filas_a_dicts(cur, cur.fetchall())


def _marcar(cur, ids, id_asiento):
    if not ids:
        return
    marks = ",".join(["%s"] * len(ids))
    cur.execute(f"UPDATE contab_cola SET estado='hecho', id_asiento=%s WHERE id IN ({marks})",
                (id_asiento, *ids))


def procesar_cola(id_empresa=None) -> dict:
    """Genera asientos de los eventos pendientes. Tickets → 1 asiento/día; facturas
    (venta/compra) → 1 por documento. Devuelve {asientos, eventos}."""
    id_empresa = _empresa(id_empresa)
    res = {"asientos": 0, "eventos": 0}
    if not K.contabilidad_activa(id_empresa):
        return res
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            ventas = _pendientes(cur, id_empresa, "venta")
            compras = _pendientes(cur, id_empresa, "compra")
            devoluciones = _pendientes(cur, id_empresa, "devolucion")
    except Exception as e:
        logger.error("procesar_cola/listar: %s", e)
        return res

    # ── Ventas ──
    tickets_por_fecha = {}
    for ev in ventas:
        p = _payload(ev)
        if ev.get("subtipo") == "factura":
            aid = _asiento_venta_factura(ev, p, id_empresa)
            if aid:
                _cerrar(id_empresa, [ev["id"]], aid); res["asientos"] += 1; res["eventos"] += 1
        else:
            tickets_por_fecha.setdefault(ev["fecha_evento"], []).append(ev)
    for fecha, evs in tickets_por_fecha.items():
        aid = _asiento_tickets_dia(fecha, evs, id_empresa)
        if aid:
            _cerrar(id_empresa, [e["id"] for e in evs], aid)
            res["asientos"] += 1; res["eventos"] += len(evs)

    # ── Compras ── (1 asiento por factura) — E6.5
    for ev in compras:
        p = _payload(ev)
        aid = _asiento_compra(ev, p, id_empresa)
        if aid:
            _cerrar(id_empresa, [ev["id"]], aid); res["asientos"] += 1; res["eventos"] += 1

    # ── Devoluciones ── (1 asiento por devolución) — E6.5
    for ev in devoluciones:
        p = _payload(ev)
        aid = _asiento_devolucion(ev, p, id_empresa)
        if aid:
            _cerrar(id_empresa, [ev["id"]], aid); res["asientos"] += 1; res["eventos"] += 1
    return res


def _payload(ev) -> dict:
    try:
        return json.loads(ev.get("payload") or "{}")
    except Exception:
        return {}


def _cerrar(id_empresa, ids, id_asiento):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            _marcar(cur, ids, id_asiento)
            conn.commit()
    except Exception as e:
        logger.error("_cerrar: %s", e)


def _asiento_tickets_dia(fecha, eventos, id_empresa):
    """1 asiento resumen del día: Debe formas de pago · Haber 700 (base) + 477 (cuota)."""
    por_fp, total = {}, 0.0
    for ev in eventos:
        p = _payload(ev)
        t = round(float(p.get("total") or 0), 2)
        fp = (p.get("forma_pago") or "efectivo")
        por_fp[fp] = round(por_fp.get(fp, 0.0) + t, 2); total += t
    total = round(total, 2)
    base, cuota, tipo = _desglose(total, id_empresa)
    lineas = [{"codigo_cuenta": M.cuenta_forma_pago(fp, id_empresa), "debe": imp,
               "descripcion": f"Ventas {fp} {fecha}"} for fp, imp in por_fp.items()]
    lineas.append({"codigo_cuenta": M.cuenta("venta", id_empresa=id_empresa), "haber": base,
                   "descripcion": "Ventas del día"})
    if cuota:
        lineas.append({"codigo_cuenta": M.cuenta("iva_rep", id_empresa=id_empresa), "haber": cuota,
                       "tipo_iva": tipo, "descripcion": "IVA repercutido"})
    r = A.crear_asiento(fecha, lineas, concepto=f"Ventas TPV {fecha}", origen="venta",
                        ref_origen=f"tickets:{fecha}", id_empresa=id_empresa)
    return r["id"] if r else None


def _asiento_venta_factura(ev, p, id_empresa):
    total = round(float(p.get("total") or 0), 2)
    base, cuota, tipo = _desglose(total, id_empresa)
    fp = p.get("forma_pago") or "factura"
    lineas = [{"codigo_cuenta": M.cuenta_forma_pago(fp, id_empresa), "debe": total,
               "descripcion": "Cobro/cliente"},
              {"codigo_cuenta": M.cuenta("venta", id_empresa=id_empresa), "haber": base}]
    if cuota:
        lineas.append({"codigo_cuenta": M.cuenta("iva_rep", id_empresa=id_empresa), "haber": cuota,
                       "tipo_iva": tipo})
    r = A.crear_asiento(ev["fecha_evento"], lineas, concepto=f"Factura venta {ev['ref']}",
                        origen="venta", ref_origen=f"factura:{ev['ref']}", id_empresa=id_empresa)
    return r["id"] if r else None


def _asiento_compra(ev, p, id_empresa):
    total = round(float(p.get("total") or 0), 2)
    base = p.get("base"); iva = p.get("iva")
    if base is None:
        base, iva, _ = _desglose(total, id_empresa)
    base = round(float(base), 2); iva = round(float(iva or (total - base)), 2)
    tipo_iva = round(iva / base * 100, 2) if base else 0.0
    lineas = [{"codigo_cuenta": M.cuenta("compra", id_empresa=id_empresa), "debe": base,
               "descripcion": "Compra"}]
    if iva:
        lineas.append({"codigo_cuenta": M.cuenta("iva_sop", id_empresa=id_empresa), "debe": iva,
                       "tipo_iva": tipo_iva, "descripcion": "IVA soportado"})
    lineas.append({"codigo_cuenta": M.cuenta("proveedor", id_empresa=id_empresa), "haber": round(base + iva, 2),
                   "descripcion": "Proveedor"})
    r = A.crear_asiento(ev["fecha_evento"], lineas, concepto=f"Factura compra {ev['ref']}",
                        origen="compra", ref_origen=f"compra:{ev['ref']}", id_empresa=id_empresa)
    return r["id"] if r else None


def _asiento_devolucion(ev, p, id_empresa):
    """Devolución de venta: contraflujo (Debe 708 base + 477 cuota / Haber forma_pago).
    Devolución de compra: (Debe 400 / Haber 608 base + 472 cuota)."""
    total = round(float(p.get("total") or 0), 2)
    base, cuota, tipo = _desglose(total, id_empresa)
    if ev.get("subtipo") == "compra":
        lineas = [{"codigo_cuenta": M.cuenta("proveedor", id_empresa=id_empresa), "debe": total},
                  {"codigo_cuenta": M.cuenta("devolucion_compra", id_empresa=id_empresa), "haber": base}]
        if cuota:
            lineas.append({"codigo_cuenta": M.cuenta("iva_sop", id_empresa=id_empresa), "haber": cuota,
                           "tipo_iva": tipo})
        concepto = f"Devolución de compra {ev['ref']}"
    else:
        fp = p.get("forma_pago") or "efectivo"
        lineas = [{"codigo_cuenta": M.cuenta("devolucion_venta", id_empresa=id_empresa), "debe": base},
                  {"codigo_cuenta": M.cuenta_forma_pago(fp, id_empresa), "haber": total}]
        if cuota:
            lineas.insert(1, {"codigo_cuenta": M.cuenta("iva_rep", id_empresa=id_empresa),
                              "debe": cuota, "tipo_iva": tipo})
        concepto = f"Devolución de venta {ev['ref']}"
    r = A.crear_asiento(ev["fecha_evento"], lineas, concepto=concepto, origen="devolucion",
                        ref_origen=f"devolucion:{ev['ref']}", id_empresa=id_empresa)
    return r["id"] if r else None
