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
    QDialog,
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

from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _btn, _btn_cargando, _chk,
                                      _dialogo_frameless, _inp, _lbl, _tabla)

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


class _DestinatarioDialog(QDialog):
    """Alta/edición de un destinatario B2G (Facturae/DIR3) — `facturae_destinatarios`. Este archivo no
    tenía diálogo propio; se reutiliza el patrón frameless más simple ya existente en
    `catalogo_gestion` (`_dialogo_frameless`/`_inp`/`_lbl`/`_chk`) en vez de duplicar uno nuevo."""

    def __init__(self, parent=None, datos=None):
        super().__init__(parent)
        datos = datos or {}
        v = _dialogo_frameless(self, "Destinatario B2G (Facturae)", ancho=460)

        def _fila(etiqueta, campo):
            v.addWidget(_lbl(etiqueta))
            v.addWidget(campo)

        self.in_nif = _inp("NIF"); self.in_nif.setText(str(datos.get("nif") or ""))
        _fila("NIF", self.in_nif)
        self.in_cliente_id = _inp("Cliente ID (opcional, vincula con clientes)")
        self.in_cliente_id.setText(str(datos.get("cliente_id") or ""))
        _fila("Cliente ID (opcional)", self.in_cliente_id)
        self.in_razon = _inp("Razón social"); self.in_razon.setText(str(datos.get("razon_social") or ""))
        _fila("Razón social", self.in_razon)
        self.in_tipo = _inp("F = física, J = jurídica")
        self.in_tipo.setText(str(datos.get("tipo_persona") or "J"))
        _fila("Tipo de persona", self.in_tipo)
        self.in_residencia = _inp("R = residente, U = UE, E = extranjero")
        self.in_residencia.setText(str(datos.get("residencia") or "R"))
        _fila("Residencia", self.in_residencia)
        self.in_direccion = _inp("Dirección"); self.in_direccion.setText(str(datos.get("direccion") or ""))
        _fila("Dirección", self.in_direccion)
        self.in_cp = _inp("Código postal"); self.in_cp.setText(str(datos.get("cp") or ""))
        _fila("CP", self.in_cp)
        self.in_municipio = _inp("Municipio"); self.in_municipio.setText(str(datos.get("municipio") or ""))
        _fila("Municipio", self.in_municipio)
        self.in_provincia = _inp("Provincia"); self.in_provincia.setText(str(datos.get("provincia") or ""))
        _fila("Provincia", self.in_provincia)
        self.in_pais = _inp("Código país (ISO-3)"); self.in_pais.setText(str(datos.get("cod_pais") or "ESP"))
        _fila("País", self.in_pais)
        self.chk_aapp = _chk("Es Administración Pública (AAPP) — obliga a DIR3",
                             bool(datos.get("es_aapp")))
        v.addWidget(self.chk_aapp)
        self.in_dir3_oc = _inp("DIR3 oficina contable")
        self.in_dir3_oc.setText(str(datos.get("dir3_oficina_contable") or ""))
        _fila("DIR3 · Oficina contable", self.in_dir3_oc)
        self.in_dir3_og = _inp("DIR3 órgano gestor")
        self.in_dir3_og.setText(str(datos.get("dir3_organo_gestor") or ""))
        _fila("DIR3 · Órgano gestor", self.in_dir3_og)
        self.in_dir3_ut = _inp("DIR3 unidad tramitadora")
        self.in_dir3_ut.setText(str(datos.get("dir3_unidad_tramitadora") or ""))
        _fila("DIR3 · Unidad tramitadora", self.in_dir3_ut)
        self.in_dir3_op = _inp("DIR3 órgano proponente (opcional)")
        self.in_dir3_op.setText(str(datos.get("dir3_organo_proponente") or ""))
        _fila("DIR3 · Órgano proponente", self.in_dir3_op)

        botones = QHBoxLayout()
        botones.addStretch()
        botones.addWidget(_btn("Cancelar", self.reject))
        botones.addWidget(_btn("Guardar", self.accept, primary=True))
        v.addLayout(botones)

    def valores(self) -> dict:
        cid = self.in_cliente_id.text().strip()
        return {
            "nif": self.in_nif.text().strip(),
            "cliente_id": int(cid) if cid.isdigit() else None,
            "razon_social": self.in_razon.text().strip() or None,
            "tipo_persona": self.in_tipo.text().strip() or "J",
            "residencia": self.in_residencia.text().strip() or "R",
            "direccion": self.in_direccion.text().strip() or None,
            "cp": self.in_cp.text().strip() or None,
            "municipio": self.in_municipio.text().strip() or None,
            "provincia": self.in_provincia.text().strip() or None,
            "cod_pais": self.in_pais.text().strip() or "ESP",
            "es_aapp": self.chk_aapp.isChecked(),
            "dir3_oficina_contable": self.in_dir3_oc.text().strip() or None,
            "dir3_organo_gestor": self.in_dir3_og.text().strip() or None,
            "dir3_unidad_tramitadora": self.in_dir3_ut.text().strip() or None,
            "dir3_organo_proponente": self.in_dir3_op.text().strip() or None,
        }


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
        self.pagina_facturae = self._crear_pagina_facturae()
        self.recargar()

    def _p(self):
        return self._host or self.pagina_certificados

    def _crear_pagina_certificados(self) -> QWidget:
        self.tbl_cert = _tabla(["ID", "Alias", "Titular NIF", "Válido hasta", "Estado"])
        page = QWidget(); cl = QVBoxLayout(page)
        cbar = QHBoxLayout()
        cbar.addWidget(_btn("Importar certificado (.p12/.pfx)", self._importar_cert, primary=True))
        cbar.addWidget(_btn("Activar", self._activar_cert, primary=True))
        cbar.addWidget(_btn("Revocar", self._revocar_cert, danger=True))
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

    def _crear_pagina_facturae(self) -> QWidget:
        self.tbl_facturae = _tabla(["ID", "Venta", "Nº factura", "Canal", "Estado", "Intentos"])
        page = QWidget(); fl = QVBoxLayout(page)
        fbar = QHBoxLayout()
        fbar.addWidget(_btn("Procesar envíos Facturae (FACe)", self._procesar_facturae, primary=True))
        fbar.addStretch()
        fl.addLayout(fbar)
        self.fb_facturae = QLabel(""); self.fb_facturae.setStyleSheet(f"color:{_DIM};")  # feedback
        fl.addWidget(self.fb_facturae)
        self.lbl_facturae = QLabel(""); self.lbl_facturae.setStyleSheet(f"color:{_CIAN};")  # resumen
        fl.addWidget(self.lbl_facturae)
        fl.addWidget(self.tbl_facturae)

        sep = QLabel("Destinatarios B2G (datos fiscales/DIR3)")
        sep.setStyleSheet(f"color:{_CIAN};font-weight:bold;margin-top:10px;")
        fl.addWidget(sep)
        dbar = QHBoxLayout()
        dbar.addWidget(_btn("＋ Nuevo/editar destinatario", self._nuevo_destinatario, primary=True))
        dbar.addStretch()
        fl.addLayout(dbar)
        self.tbl_dest = _tabla(["NIF", "Razón social", "AAPP", "DIR3 oficina", "DIR3 órgano",
                               "DIR3 unidad", "Estado B2G"])
        fl.addWidget(self.tbl_dest)
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
        # Envíos Facturae (FACe) — `envios.listar` filtra por un único estado; se combinan los
        # tres estados reales del ciclo (pendiente/enviado/error) para una vista completa.
        try:
            from src.services.fiscal.facturae import envios as FE
            envs = []
            for estado in ("pendiente", "enviado", "error"):
                envs.extend(FE.listar(estado, id_empresa=eid, limite=200))
            self.tbl_facturae.setRowCount(len(envs))
            for i, r in enumerate(envs):
                for j, v in enumerate([r.get("id"), r.get("venta_id"), r.get("numero_factura"),
                                       r.get("canal"), r.get("estado"), r.get("intentos")]):
                    self.tbl_facturae.setItem(i, j, _it(v))
            pend_fe = [r for r in envs if r.get("estado") == "pendiente"]
            self.lbl_facturae.setText(f"Envíos Facturae: {len(envs)} · pendientes: {len(pend_fe)}. "
                                      "Estados: pendiente · enviado · error.")
        except Exception as e:
            logger.error("load envios facturae: %s", e)
            self.lbl_facturae.setText(f"Error envíos Facturae: {e}")
        # Destinatarios B2G
        try:
            from src.services.fiscal.facturae import destinatarios as D
            dests = D.listar(id_empresa=eid)
            self.tbl_dest.setRowCount(len(dests))
            for i, d in enumerate(dests):
                faltan = D.validar_para_b2g(d)
                estado_b2g = "Listo" if not faltan else f"Faltan: {', '.join(faltan)}"
                for j, v in enumerate([d.get("nif"), d.get("razon_social"),
                                       "Sí" if d.get("es_aapp") else "No",
                                       d.get("dir3_oficina_contable"), d.get("dir3_organo_gestor"),
                                       d.get("dir3_unidad_tramitadora"), estado_b2g]):
                    self.tbl_dest.setItem(i, j, _it(v))
        except Exception as e:
            logger.error("load destinatarios facturae: %s", e)

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

    # ── Envío Facturae (FACe) ─────────────────────────────────────────────────
    def _procesar_facturae(self):
        if not _puede(self.usuario, "aeat.presentar"):
            self.fb_facturae.setText("Permiso requerido: aeat.presentar"); return
        r = QMessageBox.question(
            self._p(), "Envío Facturae (FACe)",
            "Se procesarán los envíos Facturae PENDIENTES (reconstrucción + firma + entrega por FACe).\n"
            "Requiere un certificado ACTIVO válido y datos DIR3 completos del destinatario. Sin ellos, "
            "los envíos permanecen en 'pendiente' y NO se marcan como enviados.\n\n¿Continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return
        try:
            from src.services.fiscal.facturae import servicio as F
            res = F.procesar_envios_facturae(id_empresa=_empresa())
            self.fb_facturae.setText(f"Cola procesada → enviados: {res.get('enviados', 0)} · en espera: "
                                     f"{res.get('en_espera', 0)} · errores: {res.get('errores', 0)}.")
        except Exception as e:
            logger.error("procesar_envios_facturae: %s", e)
            self.fb_facturae.setText(f"Error al procesar la cola de envío Facturae: {e}")
        self.recargar()

    # ── Destinatarios B2G ─────────────────────────────────────────────────────
    def _dest_sel_nif(self):
        row = self.tbl_dest.currentRow()
        if row < 0:
            return None
        it = self.tbl_dest.item(row, 0)
        return it.text() if it and it.text() else None

    def _nuevo_destinatario(self):
        if not _puede(self.usuario, "aeat.presentar"):
            self.fb_facturae.setText("Permiso requerido: aeat.presentar"); return
        from src.services.fiscal.facturae import destinatarios as D
        nif_sel = self._dest_sel_nif()
        datos = D.obtener(nif_sel, id_empresa=_empresa()) if nif_sel else None
        dlg = _DestinatarioDialog(self._p(), datos=datos)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        vals = dlg.valores()
        nif = vals.pop("nif", None)
        if not nif:
            self.fb_facturae.setText("El NIF es obligatorio."); return
        ok = D.guardar(nif, id_empresa=_empresa(), **vals)
        self.fb_facturae.setText(f"Destinatario {nif} guardado." if ok else
                                 f"No se pudo guardar el destinatario {nif}.")
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
        cab.addWidget(_btn_cargando("Actualizar", self._load, primary=True))
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)
        self.panels = FiscalPanels(usuario=self.usuario, host=self)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.panels.pagina_certificados, "Certificados")
        self.tabs.addTab(self.panels.pagina_verifactu, "Registros Verifactu")
        self.tabs.addTab(self.panels.pagina_facturae, "Facturae (FACe)")
        root.addWidget(self.tabs)

    def _load(self):
        self.panels.recargar()
