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
    # IOC v2 (Bloque III): resolución de empresa vía capa de identidad (Strangler).
    try:
        from src.services.tpv.identidad_tpv import empresa_id
        return empresa_id(id_empresa)
    except Exception:
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
    num_tickets = 0
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
            # Nº de tickets de compra del día (= clientes atendidos en caja; `ventas` no tiene
            # cliente, cada fila es un ticket). Reemplaza el concepto de nóminas en el cierre diario.
            cur.execute("SELECT COUNT(*) FROM ventas WHERE " + " AND ".join(fv), tuple(pv))
            rc = cur.fetchone()
            num_tickets = int((rc[0] if not isinstance(rc, dict) else list(rc.values())[0]) or 0) if rc else 0
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
    ticket_medio = round(neto / num_tickets, 2) if num_tickets else 0.0
    return {
        "fecha": fecha, "caja": caja, "ventas_brutas": ventas_brutas,
        "devoluciones": devoluciones, "descuentos": 0.0,   # no disponible en `ventas`
        "total_cobrado": neto, "base": base, "iva": cuota,
        "cobros": cobros_netos, "desglose_iva": desglose_iva,
        "num_tickets": num_tickets, "num_clientes": num_tickets, "ticket_medio": ticket_medio,
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
    # caja=None → CIERRE DIARIO de tienda (agrega TODAS las cajas del día); se persiste con caja 0.
    caja_alm = int(caja) if caja is not None else 0
    prev = existe_cierre(fecha, id_empresa, id_tienda, caja_alm)
    if prev:
        # REIMPRESIÓN: el cierre ya existe (inmutable). No se duplica la fila ni se recontabiliza;
        # se REGENERA su mismo ticket (mismo nº y hash) por si hubo un error humano al imprimir.
        prev["duplicado"] = True
        prev["posting"] = {}
        if generar_pdf:
            try:
                res_prev = resumen_dia(fecha, id_empresa=id_empresa, caja=caja)
                ruta = _generar_pdf(prev.get("id"), prev.get("numero"), fecha, res_prev,
                                    prev.get("importe_esperado"), prev.get("importe_declarado"),
                                    prev.get("diferencia"), prev.get("estado", ""),
                                    prev.get("usuario"), id_tienda,
                                    caja if caja is not None else "TODAS", posting=None)
                if ruta:
                    prev["ruta_pdf"] = ruta
            except Exception as e:
                logger.error("reimpresión cierre diario: %s", e)
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
                (id_empresa, id_tienda, numero, fecha, caja_alm, usuario,
                 res["ventas_brutas"], res["devoluciones"], res["descuentos"], res["base"],
                 res["iva"], res["total_cobrado"], json.dumps(res["cobros"], ensure_ascii=False),
                 json.dumps(res["desglose_iva"], ensure_ascii=False), esperado, declarado,
                 diferencia, estado, h))
            cid = cur.lastrowid
    except Exception as e:
        logger.error("generar_cierre_z: %s", e)
        return None

    # CIERRE DIARIO: recopila y CONTABILIZA los hechos económicos del día encolados EXCEPTO las
    # nóminas (no son un hecho de caja; las procesa la contabilidad general). Best-effort.
    posting = {}
    try:
        from src.services.contabilidad.posting import procesar_cola
        posting = procesar_cola(id_empresa, incluir_nominas=False)
    except Exception as e:
        logger.debug("cierre_z procesar_cola: %s", e)

    ruta_pdf = None
    if generar_pdf:
        try:
            ruta_pdf = _generar_pdf(cid, numero, fecha, res, esperado, declarado, diferencia,
                                    estado, usuario, id_tienda,
                                    caja if caja is not None else "TODAS", posting)
            if ruta_pdf:
                with obtener_conexion() as conn, conn.cursor() as cur:
                    cur.execute("UPDATE cierres_z SET ruta_pdf=%s WHERE id=%s", (ruta_pdf, cid))
                    conn.commit()
                _indexar_documento(ruta_pdf, cid, numero, fecha, res["total_cobrado"],
                                   usuario, id_empresa, id_tienda)
        except Exception as e:
            logger.error("generar_cierre_z PDF/indexado: %s", e)

    resultado = obtener_cierre_z(cid, id_empresa)
    if resultado is not None:
        resultado["posting"] = posting
    return resultado


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


def _e(v) -> str:
    try:
        return f"{float(v):.2f} €"
    except Exception:
        return str(v)


def _generar_pdf(cid, numero, fecha, res, esperado, declarado, diferencia, estado,
                 usuario, id_tienda, caja, posting=None) -> str | None:
    """Ticket de CIERRE DIARIO en el MISMO formato recibo que el ticket de compra (documento interno
    de empresa: logo, cabecera fiscal, tienda, nº ticket único, empleado, fecha/hora, sin QR/barras,
    margen izquierdo ampliado). Reutiliza el generador único `utils.impresion`."""
    try:
        from src.utils.impresion import generar_ticket_operacion_pdf
        from src.utils.ticket_data import construir_datos_operacion
    except Exception as e:
        logger.warning("Ticket de cierre diario no disponible: %s", e)
        return None

    es_todas = caja is None or str(caja) == "TODAS"
    secciones = [
        ("RESUMEN DEL DÍA", [
            ("Fecha contable", _fecha_str(fecha)),
            ("Ventas brutas", _e(res["ventas_brutas"])),
            ("Devoluciones", _e(res["devoluciones"])),
            ("Base imponible", _e(res["base"])),
            ("IVA", _e(res["iva"])),
            ("Facturación (total cobrado)", _e(res["total_cobrado"])),
            ("Nº de tickets (clientes)", res.get("num_tickets", 0)),
            ("Ticket medio", _e(res.get("ticket_medio", 0.0))),
        ]),
        ("DESGLOSE DE COBROS", [(str(k).capitalize(), _e(v)) for k, v in (res.get("cobros") or {}).items()]),
        ("ARQUEO", [
            ("Esperado", _e(esperado)), ("Declarado", _e(declarado)),
            ("Diferencia", _e(diferencia)), ("Estado", estado),
        ]),
    ]
    if posting:
        secciones.append(("ASIENTOS CONTABILIZADOS (excl. nóminas)", [
            ("Ventas", posting.get("ventas", 0)),
            ("Compras", posting.get("compras", 0)),
            ("Devoluciones", posting.get("devoluciones", 0)),
            ("Total asientos", posting.get("asientos", 0)),
        ]))

    ticket_num = f"CD-{_fecha_str(fecha).replace('-', '')}-{int(numero or 0):05d}"
    datos = construir_datos_operacion(
        "CIERRE DIARIO", usuario, prefijo="CD", ticket_num=ticket_num,
        subtitulo=("Todas las cajas" if es_todas else f"Caja {caja}"),
        caja=(None if es_todas else str(caja)), secciones=secciones,
        total=("FACTURACIÓN DEL DÍA", res.get("total_cobrado", 0)),
        pie=f"Documento auditable · ID {cid} · conservar para archivo")

    ruta = os.path.join(_ruta_documentos(), f"cierre_z_{int(numero or 0):05d}_{_fecha_str(fecha)}.pdf")
    try:
        generar_ticket_operacion_pdf(datos, ruta)
    except Exception as e:
        logger.warning("PDF cierre diario: %s", e)
        return None
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
