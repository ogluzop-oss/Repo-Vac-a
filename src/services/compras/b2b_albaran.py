"""
Albarán automático de pedido B2B (Smart Suppliers). Reutiliza EXACTAMENTE el mismo generador de PDF
que ya usa el módulo de Logística (`services.logistics.logistics_pdf_service.generar_albaran_traspaso`)
— no se crea un motor de documentos paralelo. Se genera en cuanto el pedido queda CONFIRMADA (el único
evento real de "tramitado por completo y visible/recibido en el portal del proveedor": no existe en
este ecosistema ningún paso separado de "el proveedor acepta la orden").

El PROVEEDOR figura como emisor (ORIGEN/SALIDA, membrete) y la EMPRESA compradora + su tienda destino
como receptor (DESTINO/RECEPCIÓN) — al revés que un traspaso interno entre almacenes propios.
"""

import logging
from datetime import datetime

from src.db.conexion import obtener_conexion

logger = logging.getLogger("compras.b2b_albaran")


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def _leer_transaccion(id_tx):
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM transaccion_comercial WHERE id_tx=%s", (id_tx,))
        row = cur.fetchone()
        if not row:
            return None, []
        tx = _fila(cur, row)
        cur.execute("SELECT * FROM transaccion_lineas WHERE id_tx=%s ORDER BY id", (id_tx,))
        lineas = [_fila(cur, r) for r in cur.fetchall()]
        return tx, lineas


def _direccion_proveedor(id_suministrador, id_empresa) -> str:
    """Dirección fiscal del proveedor SEGÚN la ficha de esta empresa compradora concreta
    (`proveedores.direccion_fiscal`, puente por `id_suministrador`) — `suministradores` (identidad
    única y transversal del proveedor) no tiene columna de dirección propia."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT direccion_fiscal FROM proveedores WHERE id_suministrador=%s AND id_empresa=%s "
                "LIMIT 1", (id_suministrador, id_empresa))
            row = cur.fetchone()
            if not row:
                return ""
            return (row[0] if not isinstance(row, dict) else row.get("direccion_fiscal")) or ""
    except Exception as e:
        logger.debug("_direccion_proveedor(%s,%s): %s", id_suministrador, id_empresa, e)
        return ""


def _emp_desde_proveedor(id_suministrador, id_empresa) -> dict:
    """Adapta `suministradores` al mismo shape reducido que ya usa `_empresa()` en
    `logistics_pdf_service.py` (nombre/razon_social/cif/direccion/telefono/email/codigo_local).
    Campos no disponibles se muestran honestamente como "—", nunca inventados."""
    from src.services.compras import suministradores as SUP
    sup = SUP.obtener(id_suministrador) or {}
    return {
        "nombre": sup.get("razon_social") or "—",
        "razon_social": sup.get("razon_social") or "—",
        "cif": sup.get("cif") or "—",
        "direccion": _direccion_proveedor(id_suministrador, id_empresa) or "—",
        "telefono": sup.get("telefono") or "—",
        "email": sup.get("email_login") or "—",
        "codigo_local": "PROVEEDOR",
    }


def generar_albaran_pedido(id_tx) -> dict:
    """Genera (o regenera, es idempotente por ruta) el albarán del pedido B2B `id_tx` y lo registra en
    el Centro Documental. No lanza — un fallo aquí nunca debe impedir que el pedido quede confirmado
    (el pedido es el artefacto principal; el documento se puede regenerar bajo demanda)."""
    try:
        tx, lineas_db = _leer_transaccion(id_tx)
        if not tx:
            return {"ok": False, "error": "transaccion_no_encontrada"}
        id_suministrador = tx.get("id_suministrador")
        id_empresa = tx.get("id_empresa")
        id_tienda_destino = tx.get("id_tienda_destino") or tx.get("id_tienda")
        if not id_suministrador or not id_empresa:
            return {"ok": False, "error": "pedido_incompleto"}

        from src.db import empresa as EMP
        from src.db import tiendas as TIENDAS

        emp_proveedor = _emp_desde_proveedor(id_suministrador, id_empresa)
        info_empresa = EMP.info_documento(id_empresa=id_empresa)
        tienda = TIENDAS.obtener_tienda(id_tienda_destino) or {}
        destino_codigo = tienda.get("codigo_tienda") or info_empresa.get("centro_codigo") or "—"

        metadata = tx.get("metadata") or {}
        if isinstance(metadata, str):
            import json
            try:
                metadata = json.loads(metadata)
            except Exception:
                metadata = {}
        usuario_tramito = metadata.get("usuario") or "—"

        articulos = [{
            "codigo": ln.get("codigo_articulo", "—"),
            "nombre": ln.get("nombre", "Sin nombre"),
            "cantidad": int(ln.get("cantidad") or 0),
            "es_logistico": False,
        } for ln in lineas_db]

        id_traspaso = f"B2B-{id_tx}"
        data = {
            "id_traspaso": id_traspaso,
            "tipo_documento": "ALBARÁN DE PEDIDO B2B",
            "fecha_envio": datetime.now().strftime("%d/%m/%Y"),
            "origen": emp_proveedor["razon_social"],
            "destino": destino_codigo,
            # Texto plano (no el dict de sesión): `generar_albaran_traspaso` ya formatea el usuario
            # responsable + el centro (vía `_fmt_responsable`, con `origen` como centro) — no se
            # pre-formatea aquí para no duplicar el "Centro: ..." en el PDF.
            "usuario": usuario_tramito,
            "agencia_transporte": "—",
            "observaciones": "Pedido generado automáticamente desde el Portal B2B.",
            "peso_total": "Pte.",
            "total_referencias": len(articulos),
            "pales": [{
                "pale_codigo": f"PEDIDO-{str(id_tx)[:8].upper()}",
                "peso_pale": None,
                "articulos": articulos,
            }],
            "terminos": {
                "firma_emisor": "FIRMA PROVEEDOR / EXPEDICIÓN",
                "firma_receptor": "FIRMA EMPRESA / RECEPCIÓN",
            },
        }

        from src.services.logistics.logistics_pdf_service import generar_albaran_traspaso
        ruta = generar_albaran_traspaso(data, emp=emp_proveedor)

        from src.db.documentos import registrar_documento
        id_documento = registrar_documento(
            ruta, tipo="albaran", referencia=f"B2B_TX:{id_tx}",
            id_empresa=id_empresa, id_tienda=id_tienda_destino)

        # Unificación de recepciones (rearquitectura del flujo de recepción B2B): además del PDF y el
        # registro en el Centro Documental (de siempre), el albarán se registra TAMBIÉN como documento
        # logístico ('B2B') con un palé sintético — así el operario de Logística puede recibir este
        # pedido desde la pestaña Recepciones, con el mismo escaneo que un traspaso interno, en vez de
        # confirmarlo desde el Portal Empresa. Un fallo aquí, igual que con el PDF, nunca debe impedir
        # que el pedido quede confirmado.
        try:
            from src.db import logistica as LOG
            LOG.registrar_documento_b2b(
                id_tx, origen=emp_proveedor["razon_social"], destino=destino_codigo,
                usuario=usuario_tramito, lineas=[
                    {"codigo": a["codigo"], "nombre": a["nombre"], "cantidad": a["cantidad"]}
                    for a in articulos
                ], id_empresa=id_empresa, id_tienda=id_tienda_destino)
        except Exception as e:
            logger.error("generar_albaran_pedido(%s): no se pudo registrar el documento logístico: %s",
                        id_tx, e)

        return {"ok": True, "id_documento": id_documento, "ruta": ruta}
    except Exception as e:
        logger.error("generar_albaran_pedido(%s): %s", id_tx, e)
        return {"ok": False, "error": "error_interno"}
