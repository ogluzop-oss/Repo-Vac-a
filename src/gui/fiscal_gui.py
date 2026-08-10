"""
GUI Fiscal · Certificados + Verifactu (cierre de brecha — EXPOSICIÓN operativa del núcleo fiscal C3).

El motor fiscal ya es REAL y está certificado (no es un mock): `services/fiscal/emisores/verifactu_aeat.py`
envía por SOAP a los endpoints OFICIALES de la AEAT (`www1.agenciatributaria.gob.es` / preproducción),
`emisores/tls.py` hace mTLS real con el certificado del contribuyente, `certificados.py` gestiona el
PKCS#12 cifrado, y `worker.procesar_cola` transmite con máquina de estados (generado→firmado→enviado→
rechazado/anulado). Lo que faltaba era EXPONERLO: gestionar el certificado (habilitador de la transmisión
real) y monitorizar/enviar los registros. Esta ventana NO toca el motor; solo orquesta.

HONESTIDAD: sin un certificado de PRODUCCIÓN válido y una empresa dada de alta en la AEAT, la transmisión
no puede aceptarse — los registros quedan en 'generado' (o el proveedor `simulado` encadena hash sin valor
legal). NUNCA se marca 'enviado/aceptado' sin el acuse REAL de la AEAT (lo fija el worker con el certificado
activo). El estado se distingue siempre: generado · firmado · enviado · rechazado · anulado.
"""

import logging

from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.gui.catalogo_gestion import _BG, _CIAN, _DIM, _btn, _tabla

logger = logging.getLogger("gui.fiscal")


def _it(v):
    from PyQt6.QtWidgets import QTableWidgetItem
    return QTableWidgetItem("" if v is None else str(v))


def _empresa():
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID


def _usuario_sesion(fallback=None):
    try:
        from src.db.usuario import sesion_global
        return sesion_global.usuario_actual or fallback or {}
    except Exception:
        return fallback or {}


def _puede(usuario, permiso) -> bool:
    try:
        from src.services import autorizacion
        return autorizacion.puede(usuario or {}, permiso, id_empresa=_empresa())
    except Exception:
        return True


class FiscalPanels:
    """Páginas fiscales REUTILIZABLES (Certificados + Registros Verifactu). Se pueden incrustar en cualquier
    `QTabWidget`: la ventana `FiscalWindow` (independiente) y la pestaña AEAT de Contabilidad las comparten,
    de modo que hay UNA sola implementación (N7, sin duplicar). No toca el motor fiscal; solo orquesta.

    Expone `pagina_certificados` y `pagina_verifactu` (QWidget) para añadir como tabs, y `recargar()`.
    `host` = widget padre para los diálogos (QFileDialog/QMessageBox/QInputDialog)."""

    def __init__(self, usuario=None, host=None):
        self.usuario = usuario or _usuario_sesion()
        self._host = host
        self.pagina_certificados = self._crear_pagina_certificados()
        self.pagina_verifactu = self._crear_pagina_verifactu()
        self.recargar()

    def _p(self):
        return self._host or self.pagina_certificados

    def _crear_pagina_certificados(self) -> QWidget:
        self.tbl_cert = _tabla(["ID", "Alias", "Titular NIF", "Válido hasta", "Estado"])
        page = QWidget(); cl = QVBoxLayout(page)
        cbar = QHBoxLayout()
        cbar.addWidget(_btn("Importar certificado (.p12/.pfx)", self._importar_cert, primary=True))
        cbar.addWidget(_btn("Activar", self._activar_cert))
        cbar.addWidget(_btn("Revocar", self._revocar_cert))
        cbar.addStretch()
        cl.addLayout(cbar)
        self.fb_cert = QLabel(""); self.fb_cert.setStyleSheet(f"color:{_DIM};")   # feedback de acción
        cl.addWidget(self.fb_cert)
        self.lbl_cert = QLabel(""); self.lbl_cert.setStyleSheet(f"color:{_CIAN};")  # resumen (estado)
        cl.addWidget(self.lbl_cert)
        cl.addWidget(self.tbl_cert)
        return page

    def _crear_pagina_verifactu(self) -> QWidget:
        self.tbl_reg = _tabla(["ID", "Tipo", "Referencia", "Total", "Serie", "Estado"])
        page = QWidget(); rl = QVBoxLayout(page)
        rbar = QHBoxLayout()
        rbar.addWidget(_btn("Procesar cola de envío a la AEAT", self._procesar_cola, primary=True))
        rbar.addStretch()
        rl.addLayout(rbar)
        self.fb_reg = QLabel(""); self.fb_reg.setStyleSheet(f"color:{_DIM};")     # feedback de acción
        rl.addWidget(self.fb_reg)
        self.lbl_reg = QLabel(""); self.lbl_reg.setStyleSheet(f"color:{_CIAN};")  # resumen (estado)
        rl.addWidget(self.lbl_reg)
        rl.addWidget(self.tbl_reg)
        return page

    def _set(self, msg):
        # Feedback de acción: certificados (por defecto). `_procesar_cola` usa su propia etiqueta.
        self.fb_cert.setText(msg)

    def recargar(self):
        eid = _empresa()
        # Certificados
        try:
            from src.services.fiscal import certificados
            certs = certificados.listar(id_empresa=eid)
            self.tbl_cert.setRowCount(len(certs))
            for i, c in enumerate(certs):
                for j, v in enumerate([c.get("id"), c.get("alias"), c.get("titular_nif"),
                                       c.get("valido_hasta"), c.get("estado")]):
                    self.tbl_cert.setItem(i, j, _it(v))
            activo = certificados.obtener_activo(id_empresa=eid)
            dias = certificados.dias_para_caducar(id_empresa=eid)
            if activo:
                self.lbl_cert.setText(f"✔ Certificado ACTIVO: {activo.get('titular_nif', '—')} · "
                                      f"caduca en {dias if dias is not None else '—'} días → "
                                      f"transmisión REAL a la AEAT habilitada.")
            else:
                self.lbl_cert.setText("⚠ Sin certificado activo → la transmisión legal a la AEAT NO está "
                                      "habilitada (los registros quedan en 'generado').")
        except Exception as e:
            logger.error("load certificados: %s", e)
            self.lbl_cert.setText(f"Error certificados: {e}")
        # Registros Verifactu
        try:
            from src.db import fiscal as F
            regs = F.listar_registros(id_empresa=eid, limite=500)
            self.tbl_reg.setRowCount(len(regs))
            for i, r in enumerate(regs):
                for j, v in enumerate([r.get("id"), r.get("tipo"), r.get("referencia"),
                                       r.get("total"), r.get("serie"), r.get("estado")]):
                    self.tbl_reg.setItem(i, j, _it(v))
            pend = F.listar_cola(estado="pendiente", id_empresa=eid, limite=500)
            self.lbl_reg.setText(f"Registros: {len(regs)} · pendientes de envío: {len(pend)}. "
                                 "Estados: generado · firmado · enviado · rechazado · anulado.")
        except Exception as e:
            logger.error("load registros: %s", e)
            self.lbl_reg.setText(f"Error registros: {e}")

    # ── Certificados ──────────────────────────────────────────────────────────
    def _importar_cert(self):
        if not _puede(self.usuario, "aeat.presentar"):
            self._set("Permiso requerido: aeat.presentar"); return
        ruta, _f = QFileDialog.getOpenFileName(self._p(), "Selecciona el certificado PKCS#12",
                                               "", "Certificados (*.p12 *.pfx)")
        if not ruta:
            return
        pwd, ok = QInputDialog.getText(self._p(), "Certificado", "Contraseña del certificado:",
                                       QLineEdit.EchoMode.Password)
        if not ok:
            return
        try:
            with open(ruta, "rb") as fh:
                p12 = fh.read()
            from src.services.fiscal import certificados
            info = certificados.inspeccionar_pkcs12(p12, pwd)   # valida + extrae titular/caducidad
            if not info:
                self._set("Certificado no válido o contraseña incorrecta."); return
            alias, ok = QInputDialog.getText(self._p(), "Certificado",
                                             f"Titular: {info.get('titular_nif', '—')}. Alias:")
            if not ok:
                return
            cid = certificados.importar(p12, pwd, id_empresa=_empresa(), alias=alias or None)
            # El material del certificado NUNCA se muestra ni se registra; solo el id/alias/titular.
            self._set(f"Certificado importado: {cid} (titular {info.get('titular_nif', '—')})."
                      if cid else "No se pudo importar el certificado.")
        except Exception as e:
            logger.error("importar cert: %s", e)
            self._set(f"Error al importar el certificado: {e}")
        finally:
            pwd = None   # no conservar la contraseña en memoria más de lo necesario
        self.recargar()

    def _cert_sel(self):
        row = self.tbl_cert.currentRow()
        if row < 0:
            return None
        it = self.tbl_cert.item(row, 0)
        try:
            return int(it.text()) if it and it.text() else None
        except ValueError:
            return None

    def _activar_cert(self):
        if not _puede(self.usuario, "aeat.presentar"):
            self._set("Permiso requerido: aeat.presentar"); return
        cid = self._cert_sel()
        if not cid:
            self._set("Selecciona un certificado."); return
        from src.services.fiscal import certificados
        ok = certificados.activar(cid, id_empresa=_empresa())
        self._set(f"Certificado {cid} activado." if ok else f"No se pudo activar el certificado {cid}.")
        self.recargar()

    def _revocar_cert(self):
        if not _puede(self.usuario, "aeat.presentar"):
            self._set("Permiso requerido: aeat.presentar"); return
        cid = self._cert_sel()
        if not cid:
            self._set("Selecciona un certificado."); return
        from src.services.fiscal import certificados
        ok = certificados.revocar(cid, id_empresa=_empresa())
        self._set(f"Certificado {cid} revocado." if ok else f"No se pudo revocar el certificado {cid}.")
        self.recargar()

    # ── Envío Verifactu ───────────────────────────────────────────────────────
    def _procesar_cola(self):
        if not _puede(self.usuario, "aeat.presentar"):
            self.fb_reg.setText("Permiso requerido: aeat.presentar"); return
        r = QMessageBox.question(
            self._p(), "Envío a la AEAT",
            "Se enviarán los registros PENDIENTES a la AEAT mediante el web service oficial (Verifactu).\n"
            "Requiere un certificado ACTIVO válido. Sin él, los registros permanecen en 'generado' y NO se "
            "marcan como enviados.\n\n¿Continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return
        try:
            from src.services.fiscal import worker
            res = worker.procesar_cola(id_empresa=_empresa())
            self.fb_reg.setText(f"Cola procesada → enviados: {res.get('enviados', 0)} · en espera: "
                      f"{res.get('en_espera', 0)} · errores: {res.get('errores', 0)}.")
        except Exception as e:
            logger.error("procesar_cola: %s", e)
            self.fb_reg.setText(f"Error al procesar la cola de envío: {e}")
        self.recargar()


class FiscalWindow(QWidget):
    """Ventana operativa fiscal INDEPENDIENTE (Certificados + Registros Verifactu). Reutiliza `FiscalPanels`
    (misma implementación que la pestaña AEAT de Contabilidad). Se conserva por compatibilidad de contrato
    (v_id 'fiscal'); el acceso principal está ahora dentro de Contabilidad → AEAT."""

    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or _usuario_sesion()
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("Fiscal · Certificados y Verifactu")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        cab.addWidget(_btn("Actualizar", self._load, primary=True))
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)
        self.panels = FiscalPanels(usuario=self.usuario, host=self)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.panels.pagina_certificados, "Certificados")
        self.tabs.addTab(self.panels.pagina_verifactu, "Registros Verifactu")
        root.addWidget(self.tabs)

    def _load(self):
        self.panels.recargar()
