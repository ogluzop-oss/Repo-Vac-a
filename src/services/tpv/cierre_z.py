"""
Cierre Z formal de caja (F2.2) — resumen diario, arqueo, trazabilidad y documento.

Lee las ventas/devoluciones REALES del día (sin tocar TPV ni contabilidad), calcula
el resumen (ventas brutas, devoluciones, base/IVA vía `utils.fiscalidad`, desglose de
cobros), realiza el arqueo (esperado/declarado/diferencia) y persiste un cierre
INMUTABLE y AUDITABLE en `cierres_z` (nº correlativo por empresa+tienda + hash
encadenado, mismo patrón que los asientos). Genera un PDF y lo indexa en el centro
documental. NO crea asientos: la contabilidad ya agrega el día vía `posting`.
"""

import datetime as _dt
import hashlib
import json
import logging
import os

from src.db.conexion import (EMPRESA_DEFAULT_ID, _fila_a_dict, _filas_a_dicts,
                             ensure_schema, obtener_conexion, transaccion)

logger = logging.getLogger("tpv.cierre_z")

# Buckets de medios de cobro soportados (resto → 'otros').
_MEDIOS = ("efectivo", "tarjeta", "transferencia")
_EPS = 0.01


def _empresa(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def _bucket(forma):
    f = (forma or "efectivo").strip().lower()
    return f if f in _MEDIOS else "otros"


def _fecha_str(fecha):
    if isinstance(fecha, (_dt.date, _dt.datetime)):
        return fecha.strftime("%Y-%m-%d")
    return str(fecha)[:10]


# ── Resumen del día (solo lectura) ───────────────────────────────────────────
def resumen_dia(fecha, id_empresa=None, caja=None) -> dict:
    """Agrega ventas y devoluciones del día (por caja si se indica). No persiste.

    `ventas` no tiene id_empresa (producto mono-empresa); el filtro real es por
    fecha [+ caja], coherente con `facturacion_diaria_log`."""
    id_empresa = _empresa(id_empresa)
    fecha = _fecha_str(fecha)
    cobros = {"efectivo": 0.0, "tarjeta": 0.0, "transferencia": 0.0, "otros": 0.0}
    reembolsos = dict(cobros)
    ventas_brutas = devoluciones = 0.0
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            fv, pv = ["DATE(fecha)=%s"], [fecha]
            if caja is not None:
                fv.append("numero_caja=%s"); pv.append(int(caja))
            cur.execute("SELECT forma_pago, COALESCE(SUM(total),0) tot FROM ventas WHERE "
                        + " AND ".join(fv) + " GROUP BY forma_pago", tuple(pv))
            for r in _filas_a_dicts(cur, cur.fetchall()):
                imp = round(float(r["tot"] or 0), 2)
                cobros[_bucket(r["forma_pago"])] += imp; ventas_brutas += imp
            fd, pd = ["DATE(fecha)=%s"], [fecha]
            if caja is not None:
                fd.append("numero_caja=%s"); pd.append(int(caja))
            cur.execute("SELECT forma_reembolso, COALESCE(SUM(total_reembolso),0) tot "
                        "FROM devoluciones WHERE " + " AND ".join(fd) + " GROUP BY forma_reembolso",
                        tuple(pd))
            for r in _filas_a_dicts(cur, cur.fetchall()):
                imp = round(float(r["tot"] or 0), 2)
                reembolsos[_bucket(r["forma_reembolso"])] += imp; devoluciones += imp
    except Exception as e:
        logger.error("resumen_dia(%s): %s", fecha, e)
    ventas_brutas = round(ventas_brutas, 2); devoluciones = round(devoluciones, 2)
    neto = round(ventas_brutas - devoluciones, 2)
    # Cobros netos por medio (ventas - devoluciones del mismo medio).
    cobros_netos = {k: round(cobros[k] - reembolsos.get(k, 0.0), 2) for k in cobros}
    # IVA del neto (mismo origen que el posting). `ventas` no guarda base/IVA.
    base = cuota = 0.0; desglose_iva = []
    try:
        from src.utils import fiscalidad
        d = fiscalidad.desglose_iva(neto, id_empresa=id_empresa)
        base, cuota = d["base"], d["cuota"]
        if abs(neto) > _EPS:
            desglose_iva = [{"tipo": d["tipo"], "base": base, "cuota": cuota}]
    except Exception as e:
        logger.error("resumen_dia desglose IVA: %s", e)
    return {
        "fecha": fecha, "caja": caja, "ventas_brutas": ventas_brutas,
        "devoluciones": devoluciones, "descuentos": 0.0,   # no disponible en `ventas`
        "total_cobrado": neto, "base": base, "iva": cuota,
        "cobros": cobros_netos, "desglose_iva": desglose_iva,
    }


# ── Generación del cierre Z (persistente, inmutable, documental) ─────────────
def _hash(numero, fecha, total, prev):
    base = f"{numero}|{fecha}|{round(float(total), 2)}|{prev or ''}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def existe_cierre(fecha, id_empresa=None, id_tienda="", caja=1) -> dict | None:
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM cierres_z WHERE id_empresa=%s AND id_tienda=%s "
                        "AND caja=%s AND fecha=%s", (id_empresa, id_tienda or "", int(caja),
                                                     _fecha_str(fecha)))
            return _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        logger.error("existe_cierre: %s", e); return None


def generar_cierre_z(fecha, importe_declarado, usuario=None, id_empresa=None,
                     id_tienda="", caja=1, fondo_inicial=0.0, generar_pdf=True) -> dict | None:
    """Genera (o devuelve si ya existe) el cierre Z del día/caja. Inmutable y auditable.

    importe_esperado = fondo_inicial + efectivo neto (ventas - devoluciones en efectivo).
    """
    id_empresa = _empresa(id_empresa)
    id_tienda = id_tienda or ""
    fecha = _fecha_str(fecha)
    prev = existe_cierre(fecha, id_empresa, id_tienda, caja)
    if prev:
        prev["duplicado"] = True
        return prev

    res = resumen_dia(fecha, id_empresa=id_empresa, caja=caja)
    esperado = round(float(fondo_inicial or 0) + res["cobros"].get("efectivo", 0.0), 2)
    declarado = round(float(importe_declarado or 0), 2)
    diferencia = round(declarado - esperado, 2)
    estado = "CUADRADO" if abs(diferencia) < _EPS else "DESCUADRE"

    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COALESCE(MAX(numero),0) FROM cierres_z WHERE id_empresa=%s "
                        "AND id_tienda=%s FOR UPDATE", (id_empresa, id_tienda))
            r = cur.fetchone()
            numero = int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) + 1
            cur.execute("SELECT hash_audit FROM cierres_z WHERE id_empresa=%s AND id_tienda=%s "
                        "ORDER BY numero DESC LIMIT 1", (id_empresa, id_tienda))
            rp = cur.fetchone()
            prev_hash = (rp[0] if rp and not isinstance(rp, dict) else rp.get("hash_audit") if rp else None)
            h = _hash(numero, fecha, res["total_cobrado"], prev_hash)
            cur.execute(
                "INSERT INTO cierres_z (id_empresa, id_tienda, numero, fecha, caja, usuario, "
                "ventas_brutas, devoluciones, descuentos, base, iva, total_cobrado, "
                "desglose_cobros, desglose_iva, importe_esperado, importe_declarado, diferencia, "
                "estado, hash_audit) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, id_tienda, numero, fecha, int(caja), usuario,
                 res["ventas_brutas"], res["devoluciones"], res["descuentos"], res["base"],
                 res["iva"], res["total_cobrado"], json.dumps(res["cobros"], ensure_ascii=False),
                 json.dumps(res["desglose_iva"], ensure_ascii=False), esperado, declarado,
                 diferencia, estado, h))
            cid = cur.lastrowid
    except Exception as e:
        logger.error("generar_cierre_z: %s", e)
        return None

    ruta_pdf = None
    if generar_pdf:
        try:
            ruta_pdf = _generar_pdf(cid, numero, fecha, res, esperado, declarado, diferencia,
                                    estado, usuario, id_tienda, caja)
            if ruta_pdf:
                with obtener_conexion() as conn, conn.cursor() as cur:
                    cur.execute("UPDATE cierres_z SET ruta_pdf=%s WHERE id=%s", (ruta_pdf, cid))
                    conn.commit()
                _indexar_documento(ruta_pdf, cid, numero, fecha, res["total_cobrado"],
                                   usuario, id_empresa, id_tienda)
        except Exception as e:
            logger.error("generar_cierre_z PDF/indexado: %s", e)

    # H6: procesa la cola contable al cerrar el día (contabilización automática; best-effort).
    try:
        from src.services.contabilidad.posting import procesar_cola
        procesar_cola(id_empresa)
    except Exception as e:
        logger.debug("cierre_z procesar_cola: %s", e)

    return obtener_cierre_z(cid, id_empresa)


def obtener_cierre_z(cid, id_empresa=None) -> dict | None:
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM cierres_z WHERE id=%s AND id_empresa=%s", (cid, id_empresa))
            return _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        logger.error("obtener_cierre_z(%s): %s", cid, e); return None


def listar_cierres_z(id_empresa=None, id_tienda=None, limite=200) -> list:
    id_empresa = _empresa(id_empresa)
    filtros, params = ["id_empresa=%s"], [id_empresa]
    if id_tienda is not None:
        filtros.append("id_tienda=%s"); params.append(id_tienda)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM cierres_z WHERE " + " AND ".join(filtros)
                        + " ORDER BY fecha DESC, numero DESC LIMIT %s", (*params, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_cierres_z: %s", e); return []


def cadena_z_valida(id_empresa=None, id_tienda="") -> bool:
    """Re-deriva el hash encadenado de los cierres Z y verifica integridad."""
    id_empresa = _empresa(id_empresa)
    prev = None
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT numero, fecha, total_cobrado, hash_audit FROM cierres_z "
                        "WHERE id_empresa=%s AND id_tienda=%s ORDER BY numero",
                        (id_empresa, id_tienda or ""))
            for r in _filas_a_dicts(cur, cur.fetchall()):
                esperado = _hash(r["numero"], _fecha_str(r["fecha"]), r["total_cobrado"], prev)
                if r.get("hash_audit") and r["hash_audit"] != esperado:
                    return False
                prev = r.get("hash_audit") or prev
    except Exception as e:
        logger.error("cadena_z_valida: %s", e); return False
    return True


# ── Documento PDF + indexado ─────────────────────────────────────────────────
def _ruta_documentos():
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                        "documentos", "cierres_z")
    os.makedirs(base, exist_ok=True)
    return base


def _generar_pdf(cid, numero, fecha, res, esperado, declarado, diferencia, estado,
                 usuario, id_tienda, caja) -> str | None:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
    except Exception as e:
        logger.warning("reportlab no disponible para PDF de cierre Z: %s", e)
        return None
    ruta = os.path.join(_ruta_documentos(), f"cierre_z_{numero:05d}_{fecha}.pdf")
    c = canvas.Canvas(ruta, pagesize=A4)
    w, h = A4
    y = h - 25 * mm
    c.setFont("Helvetica-Bold", 15); c.drawString(20 * mm, y, f"CIERRE Z Nº {numero:05d}")
    c.setFont("Helvetica", 9); y -= 8 * mm
    for et, val in (("Fecha", fecha), ("Tienda", id_tienda or "-"), ("Caja", caja),
                    ("Responsable", usuario or "-")):
        c.drawString(20 * mm, y, f"{et}: {val}"); y -= 5 * mm
    y -= 4 * mm; c.setFont("Helvetica-Bold", 11); c.drawString(20 * mm, y, "RESUMEN DEL DÍA")
    c.setFont("Helvetica", 9); y -= 6 * mm
    for et, val in (("Ventas brutas", res["ventas_brutas"]), ("Devoluciones", res["devoluciones"]),
                    ("Descuentos", res["descuentos"]), ("Base imponible", res["base"]),
                    ("IVA", res["iva"]), ("Total cobrado", res["total_cobrado"])):
        c.drawString(24 * mm, y, f"{et}: {val:.2f} €"); y -= 5 * mm
    y -= 4 * mm; c.setFont("Helvetica-Bold", 11); c.drawString(20 * mm, y, "DESGLOSE DE COBROS")
    c.setFont("Helvetica", 9); y -= 6 * mm
    for medio, imp in res["cobros"].items():
        c.drawString(24 * mm, y, f"{medio.capitalize()}: {imp:.2f} €"); y -= 5 * mm
    y -= 4 * mm; c.setFont("Helvetica-Bold", 11); c.drawString(20 * mm, y, "ARQUEO")
    c.setFont("Helvetica", 9); y -= 6 * mm
    for et, val in (("Esperado", esperado), ("Declarado", declarado), ("Diferencia", diferencia)):
        c.drawString(24 * mm, y, f"{et}: {val:.2f} €"); y -= 5 * mm
    c.setFont("Helvetica-Bold", 10); c.drawString(24 * mm, y, f"Estado: {estado}"); y -= 8 * mm
    c.setFont("Helvetica-Oblique", 7)
    c.drawString(20 * mm, 15 * mm, f"Documento auditable · ID {cid} · generado {_dt.datetime.now():%Y-%m-%d %H:%M}")
    c.showPage(); c.save()
    return ruta


def _indexar_documento(ruta, cid, numero, fecha, total, usuario, id_empresa, id_tienda):
    try:
        from src.db import documentos
        documentos.registrar_documento(
            ruta, tipo="informe", nombre=f"Cierre Z {numero:05d} ({fecha})",
            referencia=f"cierre_z:{cid}", importe=total, trabajador=usuario,
            id_empresa=id_empresa, id_tienda=id_tienda or None, estado="generado")
    except Exception as e:
        logger.error("_indexar_documento cierre Z: %s", e)
