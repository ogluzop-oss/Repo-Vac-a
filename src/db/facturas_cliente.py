"""
Facturación comercial de cliente (VTA.8) — capa COMERCIAL, no fiscal.

`facturas_cliente(+lineas)` con estados (borrador/emitida/cobrada/parcial/vencida/anulada),
conciliación factura↔cobro↔venta↔cliente e informes de ventas/márgenes. NO sustituye
Verifactu/Facturae (la factura fiscal se sigue emitiendo por el núcleo fiscal); esta capa
da trazabilidad comercial y rentabilidad. Multiempresa. Sin Qt.
"""

import datetime as _dt
import logging

from src.db.conexion import _fila_a_dict, _filas_a_dicts, ensure_schema, obtener_conexion, transaccion

logger = logging.getLogger("ventas.facturas_cliente")

ESTADOS = ("borrador", "emitida", "cobrada", "parcial", "vencida", "anulada",
           # FASE 3.6 — ciclo financiero / impagos
           "proforma", "impagada", "reclamada", "judicial",
           # FASE 4.5 — workflow de aprobación
           "pendiente_aprobacion", "aprobada", "rechazada")


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


def _iva_empresa(id_empresa=None) -> float:
    try:
        from src.utils import fiscalidad
        return float(fiscalidad.iva_empresa(id_empresa))
    except Exception:
        return 21.0


def _serie_factura(id_empresa, id_tienda=None, id_caja=None) -> str:
    """Serie efectiva de la factura según la estrategia fiscal (serie/serie_por:
    empresa/tienda/caja). Reutiliza el núcleo fiscal; degrada a 'A' si no disponible."""
    try:
        from src.db import fiscal as F
        if id_tienda in (None, ""):
            try:
                from src.db.empresa import tienda_actual_id
                id_tienda = tienda_actual_id()
            except Exception:
                id_tienda = None
        return F.serie_efectiva(F.obtener_config(id_empresa), id_tienda, id_caja)
    except Exception:
        return "A"


def crear_factura(id_cliente=None, id_venta=None, lineas=None, base=None, iva=None,
                  serie=None, fecha_emision=None, fecha_vencimiento=None, id_empresa=None,
                  id_tienda=None, id_caja=None, tipo_documento="factura") -> int | None:
    """Crea una factura comercial con desglose MULTI-IVA por línea.

    Tipo de IVA por línea (orden de prioridad): explícito en la línea > ``articulos.iva``
    del artículo > IVA fiscal de la empresa. Persiste el tipo en cada línea y el resumen por
    tipo en ``factura_impuestos``. La cabecera (base/iva/total) se deriva del desglose por
    líneas cuando hay líneas (corrige el IVA de tipo único); si no, usa lo recibido. Captura
    coste_unitario por línea para márgenes."""
    id_empresa = _emp(id_empresa)
    lineas = lineas or []
    iva_emp = _iva_empresa(id_empresa)
    try:
        from src.utils import fiscalidad
    except Exception:
        fiscalidad = None
    try:
        ensure_schema()
        with transaccion() as conn, conn.cursor() as cur:
            # Tipo de IVA por artículo (una sola consulta) para resolver el tipo de cada línea.
            codigos = [c for c in ((l.get("codigo") or l.get("codigo_articulo")) for l in lineas) if c]
            mapa_iva = {}
            if codigos:
                marks = ",".join(["%s"] * len(codigos))
                try:
                    cur.execute(f"SELECT codigo, iva FROM articulos WHERE codigo IN ({marks})", codigos)
                    for r in (cur.fetchall() or []):
                        cod, ti = (r[0], r[1]) if not isinstance(r, dict) else (r["codigo"], r["iva"])
                        if ti is not None:
                            mapa_iva[cod] = float(ti)
                except Exception:
                    mapa_iva = {}
            # Normaliza líneas: cantidad, precio, código, tipo IVA, subtotal (PVP).
            calc = []
            for l in lineas:
                cod = l.get("codigo") or l.get("codigo_articulo")
                ti = l.get("iva")
                ti = float(ti) if ti is not None else mapa_iva.get(cod, iva_emp)
                # Granel (venta por peso): cantidad = peso (decimal), precio = precio/kg.
                es_granel = (str(l.get("modo_venta") or "").upper() in ("PESO", "GRANEL")
                             or l.get("peso_vendido") not in (None, "", 0))
                if es_granel:
                    cant = round(float(l.get("peso_vendido") or l.get("cantidad") or 0), 3)
                    precio = round(float(l.get("precio_kg") or l.get("precio_unitario") or 0), 2)
                else:
                    cant = round(float(l.get("cantidad") or 0), 3)
                    precio = round(float(l.get("precio_unitario") or 0), 2)
                # Subtotal REAL si se aporta (granel/descuentos); si no, cantidad×precio.
                sub = (round(float(l["subtotal"]), 2) if l.get("subtotal") is not None
                       else round(cant * precio, 2))
                calc.append({"cant": cant, "precio": precio, "cod": cod, "iva": ti,
                             "desc": l.get("descripcion"), "coste": l.get("coste_unitario"),
                             "subtotal": sub})
            # Perfil fiscal del cliente = ORIGEN ÚNICO de decisión (FASE 3.1/3.2).
            perfil = None
            if id_cliente:
                try:
                    from src.db import clientes as _CLI
                    perfil = _CLI.perfil_fiscal(id_cliente)
                except Exception:
                    perfil = None
            # Motor fiscal ÚNICO: IVA + recargo equiv. + ISP/intracom/exento + IRPF.
            por_tipo, base_f, iva_f, total_f = {}, None, None, None
            recargo_f, ret_pct, ret_imp, leyenda_f, regimen_f = 0.0, 0.0, 0.0, None, None
            if calc and fiscalidad is not None:
                fisc = fiscalidad.calcular_fiscalidad(
                    [{"subtotal": c["subtotal"], "iva": c["iva"]} for c in calc],
                    perfil=perfil, id_empresa=id_empresa)
                por_tipo = fisc.get("por_tipo") or {}
                base_f, iva_f, total_f = fisc["base"], fisc["cuota"], fisc["total"]
                recargo_f = fisc["cuota_recargo"]; ret_pct = fisc["retencion_pct"]
                ret_imp = fisc["retencion"]; leyenda_f = fisc["leyenda"]; regimen_f = fisc["regimen"]
            if base_f is None:   # sin líneas o sin fiscalidad → respeta lo recibido
                base_f = round(float(base), 2) if base is not None else round(
                    sum(c["subtotal"] for c in calc), 2)
                iva_f = round(float(iva or 0), 2)
                total_f = round(base_f + iva_f, 2)
            # Serie efectiva + número secuencial SIN HUECOS por (empresa, serie). Atómico:
            # FOR UPDATE sobre el último de la serie → numeración consistente bajo concurrencia.
            from src.services.facturacion import tipos_documento as _TD
            estado_doc = _TD.estado_inicial(tipo_documento)
            if not serie:
                serie = _TD.serie_para(tipo_documento, _serie_factura(id_empresa, id_tienda, id_caja))
            cur.execute("SELECT numero_serie FROM facturas_cliente WHERE id_empresa=%s AND serie=%s "
                        "AND numero_serie IS NOT NULL ORDER BY numero_serie DESC LIMIT 1 FOR UPDATE",
                        (id_empresa, serie))
            r = cur.fetchone()
            ult = (r[0] if not isinstance(r, dict) else r.get("numero_serie")) if r else None
            num_serie = int(ult or 0) + 1
            numero_fmt = f"{serie}-{num_serie:06d}"
            cur.execute("INSERT INTO facturas_cliente (id_empresa, id_cliente, id_venta, serie, "
                        "numero, numero_serie, tipo_documento, estado, base, iva, total, "
                        "regimen_fiscal, cuota_recargo, retencion_pct, retencion_importe, "
                        "leyenda_fiscal, fecha_emision, fecha_vencimiento) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (id_empresa, id_cliente, id_venta, serie, numero_fmt, num_serie,
                         tipo_documento, estado_doc, base_f, iva_f, total_f, regimen_f, recargo_f,
                         ret_pct, ret_imp, leyenda_f, fecha_emision, fecha_vencimiento))
            fid = cur.lastrowid
            for c in calc:
                coste = c["coste"]
                if coste is None:   # toma coste medio del artículo si no se indica
                    try:
                        from src.db import compras
                        coste = float((compras.obtener_costes(c["cod"]) or {}).get("coste_medio") or 0)
                    except Exception:
                        coste = 0
                cur.execute("INSERT INTO facturas_cliente_lineas (id_factura, id_empresa, "
                            "codigo_articulo, descripcion, cantidad, precio_unitario, coste_unitario, "
                            "subtotal, iva) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                            (fid, id_empresa, c["cod"], c["desc"], c["cant"], c["precio"],
                             round(float(coste or 0), 2), c["subtotal"], c["iva"]))
            # Resumen de impuestos por tipo (id_linea NULL = fila resumen).
            for tipo, acc in por_tipo.items():
                cur.execute("INSERT INTO factura_impuestos (id_empresa, id_factura, id_linea, "
                            "tipo_iva, base, cuota, total, tipo_recargo, cuota_recargo) "
                            "VALUES (%s,%s,NULL,%s,%s,%s,%s,%s,%s)",
                            (id_empresa, fid, round(float(tipo), 2), acc["base"], acc["cuota"],
                             acc["total"], acc.get("tipo_recargo", 0), acc.get("cuota_recargo", 0)))
            nuevo_fid = fid
        # Enlace fiscal (best-effort, POST-commit): SOLO si el tipo es elegible Verifactu
        # (una proforma NUNCA genera registro fiscal).
        try:
            from src.services.facturacion import tipos_documento as _TD
            if _TD.es_verifactu(tipo_documento):
                vincular_fiscal(nuevo_fid, id_venta, id_empresa)
        except Exception:
            pass
        registrar_evento(nuevo_fid, "generada", detalle=f"{tipo_documento}:{numero_fmt}",
                         id_empresa=id_empresa)
        # AR (cuentas a cobrar): solo facturas A CRÉDITO (con vencimiento o condiciones
        # aplazadas). Las ventas retail al contado NO generan vencimiento (evita doble cómputo).
        try:
            from src.services.facturacion import tipos_documento as _TD2
            _cond = str((perfil or {}).get("condiciones_pago") or "").lower()
            a_credito = bool(fecha_vencimiento) or (_cond and _cond not in ("contado", "0"))
            if a_credito and _TD2.genera_fiscal(tipo_documento):
                crear_vencimiento_ar(nuevo_fid, fecha_vencimiento, id_empresa)
        except Exception:
            pass
        # Fase 1 (motor de eventos): publicacion OBSERVACIONAL, aditiva y bulletproof.
        try:
            from src.services import eventos as _EV
            _EV.publicar("FACTURA_GENERADA", id_empresa=id_empresa, origen="facturacion",
                         prioridad=_EV.prioridades.ALTA, ref_entidad="factura", ref_id=nuevo_fid,
                         payload={"id_cliente": id_cliente, "id_venta": id_venta, "serie": serie})
        except Exception:
            pass
        return nuevo_fid
    except Exception as e:
        logger.error("crear_factura: %s", e); return None


def obtener_factura(fid, id_empresa=None) -> dict | None:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM facturas_cliente WHERE id_factura=%s AND id_empresa=%s",
                        (fid, id_empresa))
            cab = _fila_a_dict(cur, cur.fetchone())
            if not cab:
                return None
            cur.execute("SELECT * FROM facturas_cliente_lineas WHERE id_factura=%s ORDER BY id", (fid,))
            cab["lineas"] = _filas_a_dicts(cur, cur.fetchall())
            return cab
    except Exception as e:
        logger.error("obtener_factura: %s", e); return None


def obtener_impuestos(fid, id_empresa=None) -> list:
    """Desglose de IVA por tipo de una factura (filas resumen, id_linea NULL).
    Cada item: {tipo_iva, base, cuota, total}. Vacío si no hay desglose registrado."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT tipo_iva, base, cuota, total, tipo_recargo, cuota_recargo "
                        "FROM factura_impuestos "
                        "WHERE id_factura=%s AND id_empresa=%s AND id_linea IS NULL "
                        "ORDER BY tipo_iva", (fid, id_empresa))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("obtener_impuestos(%s): %s", fid, e); return []


def vincular_fiscal(id_factura, id_venta=None, id_empresa=None) -> dict:
    """Enlaza la factura comercial con el registro fiscal (fiscal_registros) de su venta,
    si existe. Rellena ``factura_fiscal`` (serie/numero/hash/estado AEAT) y ``factura_qr``
    (QR de cotejo). Idempotente (UPSERT por factura). Best-effort: si no hay registro o
    falla, no rompe nada. Devuelve el registro fiscal vinculado o {}."""
    id_empresa = _emp(id_empresa)
    if not id_venta:
        return {}
    try:
        from src.db import fiscal as F
        reg = F.obtener_por_referencia(id_venta, id_empresa=id_empresa, tipo="ticket")
        if not reg:
            return {}
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO factura_fiscal (id_empresa, id_factura, id_registro_fiscal, "
                "serie_fiscal, numero_fiscal, hash, hash_anterior, estado_fiscal, estado_aeat, "
                "csv_aeat) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE id_registro_fiscal=VALUES(id_registro_fiscal), "
                "serie_fiscal=VALUES(serie_fiscal), numero_fiscal=VALUES(numero_fiscal), "
                "hash=VALUES(hash), hash_anterior=VALUES(hash_anterior), "
                "estado_fiscal=VALUES(estado_fiscal), estado_aeat=VALUES(estado_aeat), "
                "csv_aeat=VALUES(csv_aeat)",
                (id_empresa, id_factura, reg.get("id"), reg.get("serie"), reg.get("numero"),
                 reg.get("hash"), reg.get("hash_anterior"), reg.get("estado") or "generado",
                 reg.get("estado_aeat"), reg.get("csv_aeat")))
            if reg.get("qr"):
                cur.execute(
                    "INSERT INTO factura_qr (id_empresa, id_factura, contenido, formato) "
                    "VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE contenido=VALUES(contenido), "
                    "formato=VALUES(formato)",
                    (id_empresa, id_factura, reg.get("qr"), reg.get("proveedor") or "verifactu"))
        return reg
    except Exception as e:
        logger.error("vincular_fiscal(%s): %s", id_factura, e)
        return {}


def guardar_snapshot(id_factura, snapshot: dict, id_empresa=None) -> bool:
    """Congela el documento (JSON inmutable) en facturas_cliente.snapshot + snapshot_fecha."""
    import json as _json
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE facturas_cliente SET snapshot=%s, snapshot_fecha=NOW() "
                        "WHERE id_factura=%s AND id_empresa=%s",
                        (_json.dumps(snapshot, ensure_ascii=False, default=str), id_factura, id_empresa))
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error("guardar_snapshot(%s): %s", id_factura, e); return False


def obtener_snapshot(id_factura, id_empresa=None) -> dict | None:
    """Snapshot documental congelado de la factura (o None si no tiene)."""
    import json as _json
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT snapshot FROM facturas_cliente WHERE id_factura=%s AND id_empresa=%s",
                        (id_factura, id_empresa))
            r = cur.fetchone()
            raw = (r[0] if not isinstance(r, dict) else r.get("snapshot")) if r else None
            return _json.loads(raw) if raw else None
    except Exception as e:
        logger.error("obtener_snapshot(%s): %s", id_factura, e); return None


def obtener_fiscal(id_factura, id_empresa=None) -> dict | None:
    """Vínculo fiscal de una factura (factura_fiscal) o None si no está enlazada."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM factura_fiscal WHERE id_factura=%s AND id_empresa=%s",
                        (id_factura, id_empresa))
            r = cur.fetchone()
            return _fila_a_dict(cur, r) if r else None
    except Exception as e:
        logger.error("obtener_fiscal(%s): %s", id_factura, e); return None


def registrar_evento(id_factura, evento, detalle=None, usuario=None, id_usuario=None,
                     ip=None, id_empresa=None) -> bool:
    """Traza de auditoría de la factura (generada/vista/descargada/anulada/rectificada…).
    Resuelve el usuario activo si no se indica. Best-effort: nunca rompe el flujo."""
    id_empresa = _emp(id_empresa)
    if id_usuario is None and usuario is None:
        try:
            from src.db.usuario import sesion_global
            u = sesion_global.usuario_actual or {}
            id_usuario = u.get("id"); usuario = u.get("nombre") or u.get("usuario")
        except Exception:
            pass
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO factura_eventos (id_empresa, id_factura, evento, id_usuario, "
                        "usuario, detalle, ip) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (id_empresa, id_factura, str(evento)[:30], id_usuario,
                         (str(usuario)[:80] if usuario else None),
                         (str(detalle)[:500] if detalle else None), ip))
            conn.commit()
            return True
    except Exception as e:
        logger.error("registrar_evento(%s,%s): %s", id_factura, evento, e)
        return False


def listar_eventos(id_factura, id_empresa=None, limite=200) -> list:
    """Eventos de auditoría de una factura, más recientes primero."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT evento, usuario, id_usuario, detalle, ip, fecha FROM factura_eventos "
                        "WHERE id_factura=%s AND id_empresa=%s ORDER BY id DESC LIMIT %s",
                        (id_factura, id_empresa, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_eventos(%s): %s", id_factura, e); return []


def registrar_exportacion(id_factura, formato="pdf", ruta=None, hash=None, destino=None,
                          id_empresa=None) -> int | None:
    """Registra una exportación de la factura (PDF/Facturae/XML/CSV…) en factura_exportaciones
    + evento 'exportada'. Trazabilidad documental (FASE 3.8). Best-effort."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO factura_exportaciones (id_empresa, id_factura, formato, ruta, "
                        "hash, destino) VALUES (%s,%s,%s,%s,%s,%s)",
                        (id_empresa, id_factura, str(formato)[:20], (ruta or None),
                         (hash or None), (destino or None)))
            eid = cur.lastrowid
            conn.commit()
        registrar_evento(id_factura, "exportada", detalle=str(formato), id_empresa=id_empresa)
        return eid
    except Exception as e:
        logger.error("registrar_exportacion(%s): %s", id_factura, e); return None


def registrar_envio(id_factura, canal="email", destinatario=None, estado="pendiente",
                    error=None, id_empresa=None) -> int | None:
    """Registra un envío de la factura (email/FACe/FACeB2B…) en factura_envios + evento.
    Trazabilidad documental (FASE 3.8). Best-effort."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO factura_envios (id_empresa, id_factura, canal, destinatario, "
                        "estado, ultimo_error) VALUES (%s,%s,%s,%s,%s,%s)",
                        (id_empresa, id_factura, str(canal)[:20], (destinatario or None),
                         str(estado)[:20], (error or None)))
            eid = cur.lastrowid
            conn.commit()
        registrar_evento(id_factura, "enviada", detalle=f"{canal}:{estado}", id_empresa=id_empresa)
        return eid
    except Exception as e:
        logger.error("registrar_envio(%s): %s", id_factura, e); return None


def listar_envios(id_factura, id_empresa=None) -> list:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT canal, destinatario, estado, ultimo_error, fecha FROM factura_envios "
                        "WHERE id_factura=%s AND id_empresa=%s ORDER BY id DESC", (id_factura, id_empresa))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_envios(%s): %s", id_factura, e); return []


def listar_exportaciones(id_factura, id_empresa=None) -> list:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT formato, ruta, hash, destino, fecha FROM factura_exportaciones "
                        "WHERE id_factura=%s AND id_empresa=%s ORDER BY id DESC", (id_factura, id_empresa))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_exportaciones(%s): %s", id_factura, e); return []


def emitir(fid, id_empresa=None) -> bool:
    return _set_estado(fid, "emitida", id_empresa)


def anular(fid, id_empresa=None) -> bool:
    return _set_estado(fid, "anulada", id_empresa)


def eliminar_factura(fid, id_empresa=None) -> bool:
    """Borrado físico SOLO de BORRADORES (nunca de documentos emitidos/anulados/rectificativos).
    Para facturas emitidas usar `anular_factura` (anulación + abono). Esto evita huecos de
    numeración en documentos ya emitidos (conformidad fiscal). No afecta a venta ni kárdex."""
    id_empresa = _emp(id_empresa)
    f = obtener_factura(fid, id_empresa)
    if not f or f.get("estado") != "borrador":
        return False
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM facturas_cliente_lineas WHERE id_factura=%s", (fid,))
            cur.execute("DELETE FROM facturas_cliente WHERE id_factura=%s AND id_empresa=%s "
                        "AND estado='borrador'", (fid, id_empresa))
            return cur.rowcount > 0
    except Exception as e:
        logger.error("eliminar_factura(%s): %s", fid, e)
        return False


def anular_factura(fid, motivo=None, generar_abono=True, id_empresa=None) -> dict:
    """Anula una factura emitida (estado='anulada') y, por defecto, genera una factura
    RECTIFICATIVA (abono) que la revierte con importes negativos y la misma estructura de
    líneas/impuestos, en la misma serie y con su propio número secuencial. NO borra nada:
    ambos documentos quedan registrados (conformidad fiscal). Devuelve
    {ok, numero, id_abono, numero_abono}."""
    id_empresa = _emp(id_empresa)
    orig = obtener_factura(fid, id_empresa)
    if not orig:
        return {"ok": False, "error": "no_existe"}
    if str(orig.get("estado")) == "anulada":
        return {"ok": False, "error": "ya_anulada"}
    imps = obtener_impuestos(fid, id_empresa)   # leído antes de la transacción
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE facturas_cliente SET estado='anulada', motivo_anulacion=%s "
                        "WHERE id_factura=%s AND id_empresa=%s",
                        ((str(motivo)[:255] if motivo else None), fid, id_empresa))
            id_abono = numero_abono = None
            if generar_abono:
                serie = orig.get("serie") or _serie_factura(id_empresa)
                cur.execute("SELECT numero_serie FROM facturas_cliente WHERE id_empresa=%s AND serie=%s "
                            "AND numero_serie IS NOT NULL ORDER BY numero_serie DESC LIMIT 1 FOR UPDATE",
                            (id_empresa, serie))
                r = cur.fetchone()
                ult = (r[0] if not isinstance(r, dict) else r.get("numero_serie")) if r else None
                num_serie = int(ult or 0) + 1
                numero_abono = f"{serie}-{num_serie:06d}"
                cur.execute("INSERT INTO facturas_cliente (id_empresa, id_cliente, id_venta, serie, "
                            "numero, numero_serie, estado, base, iva, total, tipo_documento, "
                            "id_factura_rectificada, fecha_emision) "
                            "VALUES (%s,%s,%s,%s,%s,%s,'emitida',%s,%s,%s,'rectificativa',%s,CURDATE())",
                            (id_empresa, orig.get("id_cliente"), orig.get("id_venta"), serie,
                             numero_abono, num_serie, -float(orig.get("base") or 0),
                             -float(orig.get("iva") or 0), -float(orig.get("total") or 0), fid))
                id_abono = cur.lastrowid
                for l in (orig.get("lineas") or []):
                    cur.execute("INSERT INTO facturas_cliente_lineas (id_factura, id_empresa, "
                                "codigo_articulo, descripcion, cantidad, precio_unitario, "
                                "coste_unitario, subtotal, iva) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                                (id_abono, id_empresa, l.get("codigo_articulo"), l.get("descripcion"),
                                 -round(float(l.get("cantidad") or 0), 3),
                                 float(l.get("precio_unitario") or 0),
                                 float(l.get("coste_unitario") or 0), -float(l.get("subtotal") or 0),
                                 l.get("iva")))
                for imp in imps:
                    cur.execute("INSERT INTO factura_impuestos (id_empresa, id_factura, id_linea, "
                                "tipo_iva, base, cuota, total) VALUES (%s,%s,NULL,%s,%s,%s,%s)",
                                (id_empresa, id_abono, float(imp.get("tipo_iva") or 0),
                                 -float(imp.get("base") or 0), -float(imp.get("cuota") or 0),
                                 -float(imp.get("total") or 0)))
            res = {"ok": True, "numero": orig.get("numero"), "id_abono": id_abono,
                   "numero_abono": numero_abono}
        # Auditoría (POST-commit): anulación de la original + emisión del abono.
        registrar_evento(fid, "anulada", detalle=(str(motivo)[:500] if motivo else None),
                         id_empresa=id_empresa)
        if id_abono:
            registrar_evento(id_abono, "generada",
                             detalle=f"abono de {orig.get('numero')}", id_empresa=id_empresa)
        return res
    except Exception as e:
        logger.error("anular_factura(%s): %s", fid, e)
        return {"ok": False, "error": str(e)}


def _set_estado(fid, estado, id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    if estado not in ESTADOS:
        return False
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE facturas_cliente SET estado=%s WHERE id_factura=%s AND id_empresa=%s",
                        (estado, fid, id_empresa))
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error("_set_estado: %s", e); return False


def crear_vencimiento_ar(id_factura, fecha_vencimiento=None, id_empresa=None) -> int | None:
    """Crea (idempotente) el vencimiento de COBRO (cuentas a cobrar) de la factura, usando el
    MOTOR ÚNICO de tesorería (`vencimientos`). No duplica nada. Devuelve el id del vencimiento."""
    id_empresa = _emp(id_empresa)
    f = obtener_factura(id_factura, id_empresa)
    if not f or float(f.get("total") or 0) <= 0:
        return None
    fv = fecha_vencimiento or f.get("fecha_vencimiento")
    if not fv:
        import datetime as _dt
        fv = (_dt.date.today() + _dt.timedelta(days=30)).isoformat()
    try:
        from src.db import vencimientos as V
        vid = V.crear_vencimiento(
            "COBRO", float(f.get("total") or 0), fv, origen="factura_cliente",
            id_documento=id_factura, concepto=f.get("numero"), id_empresa=id_empresa)
        if vid:
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("UPDATE facturas_cliente SET id_vencimiento=%s WHERE id_factura=%s "
                            "AND id_empresa=%s", (vid, id_factura, id_empresa))
                conn.commit()
        return vid
    except Exception as e:
        logger.error("crear_vencimiento_ar(%s): %s", id_factura, e)
        return None


def registrar_cobro(id_factura, importe, forma_pago=None, referencia=None, id_empresa=None) -> dict:
    """Registra un cobro (mixto/parcial: se puede llamar varias veces con distintas formas de
    pago) en `factura_cobros`, actualiza el estado de la factura (parcial/cobrada) y abona el
    vencimiento AR si existe. Devuelve {ok, cobrado, pendiente, estado}."""
    id_empresa = _emp(id_empresa)
    f = obtener_factura(id_factura, id_empresa)
    if not f:
        return {"ok": False}
    imp = round(float(importe or 0), 2)
    total = float(f.get("total") or 0)
    nuevo_cobrado = round(float(f.get("cobrado") or 0) + imp, 2)
    estado = "cobrada" if nuevo_cobrado >= total else "parcial"
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO factura_cobros (id_empresa, id_factura, importe, forma_pago, "
                        "referencia) VALUES (%s,%s,%s,%s,%s)",
                        (id_empresa, id_factura, imp, (forma_pago or None), (referencia or None)))
            cur.execute("UPDATE facturas_cliente SET cobrado=%s, estado=%s WHERE id_factura=%s "
                        "AND id_empresa=%s", (nuevo_cobrado, estado, id_factura, id_empresa))
        # Abona el vencimiento AR (motor único), best-effort.
        try:
            if f.get("id_vencimiento"):
                from src.db import vencimientos as V
                V.abonar(f["id_vencimiento"], imp, id_empresa=id_empresa)
        except Exception:
            pass
        registrar_evento(id_factura, "cobro", detalle=f"{imp} {forma_pago or ''}".strip(),
                         id_empresa=id_empresa)
        return {"ok": True, "cobrado": nuevo_cobrado, "estado": estado,
                "pendiente": round(total - nuevo_cobrado, 2)}
    except Exception as e:
        logger.error("registrar_cobro(%s): %s", id_factura, e)
        return {"ok": False}


def listar_cobros(id_factura, id_empresa=None) -> list:
    """Cobros (medios de pago) registrados de una factura."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT fecha, importe, forma_pago, referencia FROM factura_cobros "
                        "WHERE id_factura=%s AND id_empresa=%s ORDER BY id", (id_factura, id_empresa))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_cobros(%s): %s", id_factura, e); return []


def marcar_estado_cobro(id_factura, estado, id_empresa=None) -> bool:
    """Cambia el estado de cobro/impago (vencida/impagada/reclamada/judicial). FASE 3.6."""
    if estado not in ("vencida", "impagada", "reclamada", "judicial", "cobrada", "parcial"):
        return False
    ok = _set_estado(id_factura, estado, id_empresa)
    if ok:
        registrar_evento(id_factura, estado, id_empresa=id_empresa)
    return ok


def registrar_cobro_factura(fid, importe, id_empresa=None) -> dict:
    """Suma un cobro a la factura y actualiza el estado (parcial/cobrada)."""
    id_empresa = _emp(id_empresa)
    f = obtener_factura(fid, id_empresa)
    if not f:
        return {"ok": False}
    nuevo_cobrado = round(float(f["cobrado"] or 0) + float(importe or 0), 2)
    estado = "cobrada" if nuevo_cobrado >= float(f["total"]) else "parcial"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE facturas_cliente SET cobrado=%s, estado=%s WHERE id_factura=%s "
                        "AND id_empresa=%s", (nuevo_cobrado, estado, fid, id_empresa))
            conn.commit()
        return {"ok": True, "cobrado": nuevo_cobrado, "estado": estado,
                "pendiente": round(float(f["total"]) - nuevo_cobrado, 2)}
    except Exception as e:
        logger.error("registrar_cobro_factura: %s", e); return {"ok": False}


def marcar_vencidas(id_empresa=None) -> int:
    id_empresa = _emp(id_empresa)
    hoy = _dt.date.today().isoformat()
    try:
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE facturas_cliente SET estado='vencida' WHERE id_empresa=%s "
                        "AND estado IN ('emitida','parcial') AND fecha_vencimiento IS NOT NULL "
                        "AND fecha_vencimiento < %s", (id_empresa, hoy))
            return cur.rowcount
    except Exception as e:
        logger.error("marcar_vencidas: %s", e); return 0


def listar_facturas(id_empresa=None, id_cliente=None, estado=None, limite=500) -> list:
    id_empresa = _emp(id_empresa)
    cond, params = ["id_empresa=%s"], [id_empresa]
    if id_cliente:
        cond.append("id_cliente=%s"); params.append(id_cliente)
    if estado:
        cond.append("estado=%s"); params.append(estado)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT * FROM facturas_cliente WHERE {' AND '.join(cond)} "
                        f"ORDER BY id_factura DESC LIMIT %s", (*params, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_facturas: %s", e); return []


# ── Informes de ventas / márgenes / rentabilidad ─────────────────────────────
def informe_margenes(desde=None, hasta=None, id_empresa=None) -> dict:
    """Margen = Σ(precio - coste)·cantidad sobre las líneas de venta del período."""
    id_empresa = _emp(id_empresa)
    cond, params = ["v.id_empresa=%s"], [id_empresa]
    if desde:
        cond.append("v.fecha>=%s"); params.append(desde)
    if hasta:
        cond.append("v.fecha<=%s"); params.append(str(hasta) + " 23:59:59" if len(str(hasta)) == 10 else hasta)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"""
                SELECT COALESCE(SUM(vi.subtotal),0) AS ventas,
                       COALESCE(SUM(vi.cantidad * COALESCE(a.coste_medio,0)),0) AS coste
                FROM venta_items vi JOIN ventas v ON v.id=vi.venta_id
                LEFT JOIN articulos a ON a.codigo=vi.codigo_articulo
                WHERE {' AND '.join(cond)}
            """, params)
            r = cur.fetchone()
            ventas = float((r[0] if not isinstance(r, dict) else r["ventas"]) or 0)
            coste = float((r[1] if not isinstance(r, dict) else r["coste"]) or 0)
        margen = round(ventas - coste, 2)
        pct = round(margen / ventas * 100, 2) if ventas else 0.0
        return {"ventas": round(ventas, 2), "coste": round(coste, 2), "margen": margen,
                "margen_pct": pct}
    except Exception as e:
        logger.error("informe_margenes: %s", e); return {"ventas": 0, "coste": 0, "margen": 0}


def ventas_por_cliente(desde=None, hasta=None, id_empresa=None, limite=50) -> list:
    id_empresa = _emp(id_empresa)
    cond, params = ["id_empresa=%s", "cliente_id IS NOT NULL"], [id_empresa]
    if desde:
        cond.append("fecha>=%s"); params.append(desde)
    if hasta:
        cond.append("fecha<=%s"); params.append(str(hasta) + " 23:59:59" if len(str(hasta)) == 10 else hasta)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT cliente_id, COALESCE(cliente_nombre,'') nombre, COUNT(*) n, "
                        f"COALESCE(SUM(total),0) total FROM ventas WHERE {' AND '.join(cond)} "
                        f"GROUP BY cliente_id, cliente_nombre ORDER BY total DESC LIMIT %s",
                        (*params, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("ventas_por_cliente: %s", e); return []
