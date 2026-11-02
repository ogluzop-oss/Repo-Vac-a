"""
Proveedor fiscal TICKETBAI (C3.4-TBAI) — régimen foral del País Vasco (Araba/
Bizkaia/Gipuzkoa): tres Diputaciones con su propio servicio de envío (LROE)
pero una misma especificación de factura/encadenamiento (TicketBAI).

EXTIENDE el núcleo congelado (C3.1/C3.2) EXACTAMENTE como Verifactu: reutiliza
la numeración, el encadenado atómico y la cola de `src.db.fiscal` (misma tabla
`fiscal_registros`, mismo mecanismo `insertar_registro`/`cadena_valida`); solo
aporta el FORMATO LEGAL (huella interna, identificador TBAI, QR de cotejo) vía
los puntos de extensión `campos_hash`/`huella_fn`. El registro aquí es
síncrono y ligero (apto para caja); el XML firmado (XAdES-BES, OBLIGATORIO en
TicketBAI, a diferencia de Verifactu) y el ENVÍO a la LROE de la diputación
correspondiente viven en `EmisorTicketBAI` (`emisores/ticketbai_lroe.py`),
procesado por el worker (`worker.procesar_cola`), igual que Verifactu.

HONESTIDAD: TicketBAI exige firma XAdES de la factura; sin un certificado
ACTIVO de la empresa no existe identificador TBAI legal posible. En ese caso
el registro se crea igualmente (encadenado de auditoría intacto, estado
'generado') pero el QR/identificador quedan con el marcador explícito
`SIN-CERTIFICADO` — NUNCA se inventa un identificador o un envío aceptado sin
el acuse REAL de la Diputación Foral (lo fija el worker vía `EmisorTicketBAI`).
"""

import datetime
import json
import logging

from src.db import fiscal as fdb
from src.services.fiscal import ticketbai_legal as legal
from src.services.fiscal.base import ProveedorFiscal, RegistroFiscal
from src.services.fiscal.registry import registrar_proveedor

logger = logging.getLogger("fiscal.ticketbai")


@registrar_proveedor("ticketbai", territorios=("araba", "bizkaia", "gipuzkoa"))
class ProveedorTicketBAI(ProveedorFiscal):
    nombre = "ticketbai"

    # ── datos legales no derivables (NIF emisor, fechas, desglose IVA) ──────────
    def _meta(self, tipo, total, id_empresa, territorio) -> dict:
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
        return {
            "regimen": "ticketbai", "kind": "alta", "territorio": territorio,
            "tipo_factura": "F1" if tipo == "factura" else "F2",   # ⚠️[verificar tipos TBAI]
            "nif_emisor": info.get("cif") or "",
            "nombre_emisor": info.get("razon_social") or info.get("nombre") or "",
            "descripcion": "Venta",
            "fecha_expedicion": ahora.strftime("%d-%m-%Y"),         # consistente con Verifactu
            "fecha_expedicion_corta": ahora.strftime("%d%m%y"),     # usada en el identificador TBAI
            "hora_expedicion": ahora.strftime("%H:%M:%S"),
            "fecha_gen": ahora.isoformat(),
            "cuota_total": cuota,
            "importe_total": f"{round(float(total or 0), 2):.2f}",
            "base_total": base,
            "tipo_iva": tipo_iva,
            "desglose": [{"tipo": f"{float(tipo_iva):.2f}" if tipo_iva is not None else None,
                          "base": base, "cuota": cuota}],
        }

    def _identificador_y_qr(self, meta: dict, reg: dict):
        """Identificador TBAI + QR reales SOLO si hay un certificado ACTIVO
        (TicketBAI exige firma). Sin certificado: marcador honesto
        `SIN-CERTIFICADO` — nunca un identificador inventado como válido."""
        territorio = meta.get("territorio") or "araba"
        try:
            from src.services.fiscal import certificados as C
            activo = C.obtener_activo(id_empresa=reg.get("id_empresa"))
        except Exception as e:
            logger.debug("certificados.obtener_activo no disponible: %s", e)
            activo = None
        if not activo:
            marcador = (f"{legal.MARCADOR_SIN_CERTIFICADO}|serie={reg['serie']}|"
                       f"numero={reg['numero']}|total={meta.get('importe_total')}")
            return None, marcador
        ident = legal.identificador_tbai(meta.get("nif_emisor"),
                                         meta.get("fecha_expedicion_corta"),
                                         activo.get("num_serie"))
        qr = legal.contenido_qr(territorio, ident, reg["serie"], reg["numero"],
                                meta.get("importe_total"))
        return ident, qr

    def _guardar_qr(self, id_registro, qr):
        try:
            from src.db.conexion import obtener_conexion
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("UPDATE fiscal_registros SET qr=%s WHERE id=%s", (qr, id_registro))
                conn.commit()
        except Exception as e:
            logger.debug("No se pudo guardar el QR TicketBAI: %s", e)

    def registrar(self, tipo, referencia=None, total=0.0, payload=None,
                  id_caja=None) -> RegistroFiscal:
        eid = fdb._empresa(None)
        cfg = self.config or fdb.obtener_config(eid)
        territorio = cfg.get("territorio") if cfg.get("territorio") in legal.TERRITORIOS else "araba"
        meta = self._meta(tipo, total, eid, territorio)
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
        # NOTA: `meta` ya quedó serializado en el `payload` por `insertar_registro`
        # ANTES de que el identificador/QR existan (dependen del nº/serie
        # definitivos, resueltos atómicamente dentro de esa llamada) — por eso el
        # identificador NO se guarda como un campo de payload aparte; viaja dentro
        # del propio QR (parámetro `id`), que SÍ se persiste a continuación. Única
        # fuente de verdad para el render (`ticket.py._info_ticketbai`).
        _ident, qr = self._identificador_y_qr(meta, reg)
        self._guardar_qr(reg["id"], qr)
        reg["qr"] = qr
        return RegistroFiscal.desde_fila(reg)

    def anular(self, registro: RegistroFiscal) -> RegistroFiscal:
        eid = fdb._empresa(None)
        cfg = self.config or fdb.obtener_config(eid)
        territorio = cfg.get("territorio") if cfg.get("territorio") in legal.TERRITORIOS else "araba"
        meta = self._meta("anulacion", -(registro.total or 0), eid, territorio)
        meta["kind"] = "anulacion"
        meta["serie_anulada"] = registro.serie
        meta["num_anulada"] = str(registro.numero)
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
