"""
Proveedor fiscal VERIFACTU (C3.3) — régimen de remisión a AEAT.

EXTIENDE el núcleo congelado (C3.1/C3.2) sin tocarlo: reutiliza la numeración,
el encadenado atómico y la cola; solo aporta el FORMATO LEGAL (huella, nº de serie,
QR de cotejo, leyenda) vía los puntos de extensión `campos_hash` + `huella_fn`.

C3.3.1: genera el registro de alta/anulación con huella legal y QR (síncrono y
ligero → apto para caja). La construcción del XML y el ENVÍO a AEAT viven en el
worker (C3.3.2/C3.3.3). La firma/certificado real y producción → C3.5.
"""

import datetime
import json
import logging

from src.db import fiscal as fdb
from src.services.fiscal import verifactu_legal as legal
from src.services.fiscal.base import ProveedorFiscal, RegistroFiscal
from src.services.fiscal.registry import registrar_proveedor

logger = logging.getLogger("fiscal.verifactu")


@registrar_proveedor("verifactu", territorios=("comun",))
class ProveedorVerifactu(ProveedorFiscal):
    nombre = "verifactu"

    # ── datos legales no derivables (NIF emisor, fechas, desglose IVA) ──────────
    def _meta(self, tipo, total, id_empresa) -> dict:
        info, desg = {}, {"base": 0.0, "cuota": 0.0, "tipo": 0.0}
        try:
            from src.db import empresa as emp_db
            info = emp_db.info_documento(id_empresa) or {}
        except Exception as e:
            logger.debug("info_documento no disponible: %s", e)
        try:
            from src.utils import fiscalidad
            desg = fiscalidad.desglose_iva(total, id_empresa=id_empresa)
        except Exception as e:
            logger.debug("desglose_iva no disponible: %s", e)
        ahora = datetime.datetime.now().astimezone().replace(microsecond=0)
        base = f"{float(desg.get('base') or 0):.2f}"
        cuota = f"{float(desg.get('cuota') or 0):.2f}"
        tipo_iva = desg.get("tipo")
        # Desglose conforme al XSD (mono-tipo a partir del IVA de la empresa;
        # multi-tipo → extensión futura con datos de línea). CalificacionOperacion
        # S1 = sujeta y no exenta. ⚠️[ClaveRegimen/Calificacion a confirmar fiscal]
        desglose = [{
            "clave_regimen": "01",            # ⚠️ régimen general; confirmar por empresa
            "calificacion": "S1",
            "tipo": f"{float(tipo_iva):.2f}" if tipo_iva is not None else None,
            "base": base,
            "cuota": cuota,
        }]
        return {
            "regimen": "verifactu", "kind": "alta",
            "tipo_factura": "F1" if tipo == "factura" else "F2",  # ⚠️[verificar tipos]
            "nif_emisor": info.get("cif") or "",
            "nombre_emisor": info.get("razon_social") or info.get("nombre") or "",
            "descripcion": "Venta",                               # ⚠️ texto por defecto
            "fecha_expedicion": ahora.strftime("%d-%m-%Y"),       # XSD: dd-mm-yyyy
            "fecha_gen": ahora.isoformat(),                       # XSD: dateTime con huso
            "cuota_total": cuota,
            "importe_total": f"{round(float(total or 0), 2):.2f}",
            "base_total": base,
            "tipo_iva": tipo_iva,
            "desglose": desglose,
        }

    def _guardar_qr(self, id_registro, qr):
        try:
            from src.db.conexion import obtener_conexion
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("UPDATE fiscal_registros SET qr=%s WHERE id=%s", (qr, id_registro))
                conn.commit()
        except Exception as e:
            logger.debug("No se pudo guardar el QR Verifactu: %s", e)

    def registrar(self, tipo, referencia=None, total=0.0, payload=None,
                  id_caja=None) -> RegistroFiscal:
        eid = fdb._empresa(None)
        cfg = self.config or fdb.obtener_config(eid)
        meta = self._meta(tipo, total, eid)
        if payload:
            meta["extra"] = payload
        reg = fdb.insertar_registro(
            tipo=tipo, referencia=referencia, total=total, payload=meta,
            proveedor=self.nombre, estado="generado", id_caja=id_caja,
            campos_hash=lambda s, n, t, r, tot: legal.campos_alta(s, n, meta),
            huella_fn=legal.huella_alta)
        if not reg:
            return RegistroFiscal(tipo=tipo, referencia=referencia, total=total,
                                  proveedor=self.nombre, estado="error")
        ns = legal.num_serie(reg["serie"], reg["numero"])
        qr = legal.contenido_qr(meta["nif_emisor"], ns, meta["fecha_expedicion"],
                                meta["importe_total"],
                                entorno=cfg.get("entorno", "preproduccion"))
        self._guardar_qr(reg["id"], qr)
        reg["qr"] = qr
        return RegistroFiscal.desde_fila(reg)

    def anular(self, registro: RegistroFiscal) -> RegistroFiscal:
        eid = fdb._empresa(None)
        meta = self._meta("anulacion", -(registro.total or 0), eid)
        meta["kind"] = "anulacion"
        meta["num_serie_anulada"] = (legal.num_serie(registro.serie, registro.numero)
                                     if registro.serie else str(registro.referencia or registro.id))
        reg = fdb.insertar_registro(
            tipo="anulacion", referencia=str(registro.referencia or registro.id),
            total=-(registro.total or 0), payload=meta, proveedor=self.nombre,
            estado="generado",
            campos_hash=lambda s, n, t, r, tot: legal.campos_anulacion(s, n, meta),
            huella_fn=legal.huella_anulacion)
        return RegistroFiscal.desde_fila(reg) if reg else registro

    # ── verificación de cadena: re-deriva con el formato legal desde el payload ──
    def recalcular_huella(self, fila: dict, hash_anterior):
        meta = {}
        try:
            meta = json.loads(fila.get("payload") or "{}")
        except Exception:
            pass
        serie, numero = fila.get("serie"), fila.get("numero")
        if meta.get("kind") == "anulacion":
            return legal.huella_anulacion(legal.campos_anulacion(serie, numero, meta), hash_anterior)
        return legal.huella_alta(legal.campos_alta(serie, numero, meta), hash_anterior)

    def leyenda(self) -> str:
        return legal.LEYENDA
