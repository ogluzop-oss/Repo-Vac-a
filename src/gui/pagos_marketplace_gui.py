"""
GUI del Marketplace + Pagos (F5) — capa fina que SOLO orquesta `services.pagos_marketplace.operaciones`.

- `ConectarCobrosDialog`: onboarding KYB de una parte (proveedor/vendedor) en el PSP + estado (banco/últimos4).
- `EscrowPagosDialog`: transacciones de la Lonja con su estado de escrow + acciones (confirmar recepción,
  abrir disputa, liberar [step-up MFA], ver ledger).

Reutiliza los helpers visuales de `catalogo_gestion` y `mostrar_mensaje`. Ninguna lógica de negocio vive aquí.
"""

import logging

from PyQt6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QTableWidgetItem,
                             QVBoxLayout)

from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _TEXT, _btn, _dialogo_frameless, _inp, _tabla)
from src.services.pagos_marketplace import operaciones as OP

logger = logging.getLogger("gui.pagos_marketplace")


def _puede(usuario, permiso) -> bool:
    try:
        from src.services import autorizacion
        return autorizacion.puede(usuario or {}, permiso)
    except Exception:
        return False

try:
    from assets.estilo_global import mostrar_mensaje
except Exception:  # pragma: no cover
    mostrar_mensaje = None


def _aviso(parent, titulo, mensaje, nivel="info"):
    if mostrar_mensaje is not None:
        try:
            mostrar_mensaje(parent, titulo, mensaje, nivel=nivel); return
        except Exception:
            pass
    from PyQt6.QtWidgets import QMessageBox
    (QMessageBox.information if nivel in ("info", "success") else QMessageBox.warning)(
        parent, titulo, mensaje)


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


class ConectarCobrosDialog(QDialog):
    """Onboarding KYB de una parte en el PSP + estado de la cuenta conectada."""

    def __init__(self, tipo_parte, id_parte, nombre="", parent=None):
        super().__init__(parent)
        self._tipo = tipo_parte
        self._id = id_parte
        self.setFixedSize(560, 420)
        v = _dialogo_frameless(self, titulo=f"Conectar cobros (KYB) · {nombre}".strip(" ·"), ancho=560)
        self.lbl = QLabel("")
        self.lbl.setStyleSheet(f"color:{_TEXT};background:transparent;font-size:13px;")
        self.lbl.setWordWrap(True)
        v.addWidget(self.lbl)
        self.txt_url = _inp("Enlace de onboarding del PSP")
        self.txt_url.setReadOnly(True)
        v.addWidget(self.txt_url)
        nota = QLabel("El proveedor/vendedor completa sus datos bancarios en el flujo seguro del PSP "
                      "(KYB). Smart Manager solo guarda un token y el banco + últimos 4 dígitos.")
        nota.setStyleSheet(f"color:{_DIM};background:transparent;font-size:11px;")
        nota.setWordWrap(True)
        v.addWidget(nota)
        v.addStretch()
        bar = QHBoxLayout()
        bar.addWidget(_btn("Conectar cobros (KYB)", self._conectar, primary=True))
        bar.addWidget(_btn("Actualizar estado", self._refrescar))
        bar.addStretch()
        bar.addWidget(_btn("Cerrar", self.reject))
        v.addLayout(bar)
        self._pintar(OP.estado_cobros(self._tipo, self._id))

    def _pintar(self, resumen):
        if not resumen or not resumen.get("account_id"):
            self.lbl.setText("Estado: sin conectar. Pulsa «Conectar cobros (KYB)» para empezar.")
            self.txt_url.clear()
            return
        est = resumen.get("status", "pending")
        payouts = "sí" if resumen.get("payouts_enabled") else "no"
        etiqueta = resumen.get("etiqueta") or "Cuenta bancaria"
        self.lbl.setText(f"Estado KYB: <b>{est}</b> · payouts habilitados: <b>{payouts}</b><br>"
                         f"{etiqueta}")
        if resumen.get("onboarding_url"):
            self.txt_url.setText(resumen["onboarding_url"])

    def _conectar(self):
        r = OP.conectar_cobros(self._tipo, self._id)
        if not r.get("ok"):
            _aviso(self, "Cobros", r.get("error", "No se pudo iniciar el onboarding."), "error"); return
        if r.get("onboarding_url"):
            self.txt_url.setText(r["onboarding_url"])
            _aviso(self, "Cobros", "Onboarding creado. Abre el enlace para completar el KYB.", "success")
        else:
            _aviso(self, "Cobros",
                   "Cuenta creada en modo simulado (sin PSP configurado): sin custodia real de fondos.",
                   "info")
        self._pintar(OP.estado_cobros(self._tipo, self._id))

    def _refrescar(self):
        self._pintar(OP.estado_cobros(self._tipo, self._id, refrescar=True))


class EscrowPagosDialog(QDialog):
    """Transacciones de la Lonja con su estado de escrow + acciones."""

    def __init__(self, usuario=None, parent=None):
        super().__init__(parent)
        self.usuario = usuario or {}
        self.setFixedSize(920, 600)
        v = _dialogo_frameless(self, titulo="Pagos del mercado · Escrow", ancho=920)
        cab = QHBoxLayout()
        cab.addWidget(_btn("💳  Cobros de mi empresa (KYB)", self._cobros_empresa, primary=True))
        cab.addStretch()
        if _puede(self.usuario, "pagos.pasarela.configurar"):
            cab.addWidget(_btn("⚙  Credenciales de la plataforma", self._credenciales_plataforma))
        v.addLayout(cab)
        self.tbl = _tabla(["ID", "Vendedor", "Importe", "Divisa", "Estado de pago", "Comisión"])
        v.addWidget(self.tbl, 1)
        bar = QHBoxLayout()
        bar.addWidget(_btn("Confirmar recepción", self._confirmar, primary=True))
        bar.addWidget(_btn("Abrir disputa", self._disputa))
        bar.addWidget(_btn("Liberar fondos", self._liberar))
        bar.addWidget(_btn("Ver ledger", self._ledger))
        bar.addStretch()
        bar.addWidget(_btn("Actualizar", self._cargar))
        bar.addWidget(_btn("Cerrar", self.reject))
        v.addLayout(bar)
        self._cargar()

    def _cobros_empresa(self):
        """KYB de la cuenta de cobros de la PROPIA empresa (para recibir sus ventas del mercado)."""
        ConectarCobrosDialog("empresa", 0, "Mi empresa", self).exec()

    def _credenciales_plataforma(self):
        """Admin: alta de las credenciales Connect de la plataforma (RBAC + step-up en el diálogo)."""
        PlataformaCobrosDialog(self.usuario, self).exec()

    def _cargar(self):
        filas = OP.transacciones((self.usuario or {}).get("id_empresa"))
        self.tbl.setRowCount(len(filas))
        for i, f in enumerate(filas):
            for j, val in enumerate([f.get("id"), f.get("id_vendedor"),
                                     round(float(f.get("importe") or 0), 2), f.get("divisa"),
                                     f.get("estado_pago") or "—", f.get("comision_importe")]):
                self.tbl.setItem(i, j, _it(val))

    def _sel_id(self):
        row = self.tbl.currentRow()
        if row < 0:
            return None
        it = self.tbl.item(row, 0)
        try:
            return int(it.text()) if it and it.text() else None
        except ValueError:
            return None

    def _confirmar(self):
        tid = self._sel_id()
        if not tid:
            _aviso(self, "Escrow", "Selecciona una transacción.", "info"); return
        r = OP.confirmar_recepcion(tid)
        if r.get("ok"):
            _aviso(self, "Escrow", f"Recepción confirmada. Estado: {r.get('estado_pago')}.", "success")
        else:
            _aviso(self, "Escrow", f"No se pudo confirmar: {r.get('error')}", "error")
        self._cargar()

    def _disputa(self):
        tid = self._sel_id()
        if not tid:
            _aviso(self, "Escrow", "Selecciona una transacción.", "info"); return
        motivo, ok = _pedir_texto(self, "Abrir disputa", "Motivo de la disputa:")
        if not ok:
            return
        r = OP.abrir_disputa(tid, motivo=motivo or None)
        if r.get("ok"):
            _aviso(self, "Escrow", "Disputa abierta.", "success")
        else:
            _aviso(self, "Escrow", f"No se pudo abrir la disputa: {r.get('error')}", "error")
        self._cargar()

    def _liberar(self):
        tid = self._sel_id()
        if not tid:
            _aviso(self, "Escrow", "Selecciona una transacción.", "info"); return
        # Acción crítica (movimiento de fondos): step-up MFA ANTES de ejecutar (después de RBAC).
        try:
            from src.gui.mfa_gui import step_up_sesion
            if not step_up_sesion("finanzas.critica", parent=self):
                _aviso(self, "Escrow", "Verificación MFA requerida para liberar fondos.", "warning"); return
        except Exception as e:
            logger.debug("step_up_sesion: %s", e)
        r = OP.liberar(tid)
        if r.get("ok"):
            _aviso(self, "Escrow", f"Fondos liberados. Estado: {r.get('estado_pago')}.", "success")
        else:
            _aviso(self, "Escrow", f"No se pudo liberar: {r.get('error')}", "error")
        self._cargar()

    def _ledger(self):
        tid = self._sel_id()
        if not tid:
            _aviso(self, "Escrow", "Selecciona una transacción.", "info"); return
        LedgerDialog(tid, self).exec()


class PlataformaCobrosDialog(QDialog):
    """Admin: credenciales Connect de la PLATAFORMA (Stripe). Write-only: nunca muestra la clave guardada.
    Exige permiso `pagos.pasarela.configurar` + step-up MFA para guardar."""

    def __init__(self, usuario=None, parent=None):
        super().__init__(parent)
        self.usuario = usuario or {}
        self.setFixedSize(600, 520)
        v = _dialogo_frameless(self, titulo="Credenciales Connect de la plataforma (admin)", ancho=600)

        self.lbl_estado = QLabel("")
        self.lbl_estado.setStyleSheet(f"color:{_TEXT};background:transparent;font-size:13px;")
        self.lbl_estado.setWordWrap(True)
        v.addWidget(self.lbl_estado)

        def _fila(texto):
            lab = QLabel(texto); lab.setStyleSheet(f"color:{_DIM};background:transparent;font-weight:700;")
            v.addWidget(lab)

        _fila("Stripe secret key (sk_live_… / sk_test_…)")
        self.in_key = _inp("Se guarda cifrada · déjalo vacío para no cambiarla")
        self.in_key.setEchoMode(QLineEdit.EchoMode.Password)
        v.addWidget(self.in_key)

        _fila("Connect webhook secret (whsec_…)")
        self.in_whsec = _inp("Se guarda cifrado · déjalo vacío para no cambiarlo")
        self.in_whsec.setEchoMode(QLineEdit.EchoMode.Password)
        v.addWidget(self.in_whsec)

        fila = QHBoxLayout()
        lab_m = QLabel("Modo"); lab_m.setStyleSheet(f"color:{_DIM};background:transparent;font-weight:700;")
        self.cmb_modo = QComboBox(); self.cmb_modo.addItems(["test", "live"])
        self.cmb_modo.setFixedHeight(34)
        lab_c = QLabel("Comisión %"); lab_c.setStyleSheet(f"color:{_DIM};background:transparent;font-weight:700;")
        self.in_com = _inp("0"); self.in_com.setFixedWidth(90)
        fila.addWidget(lab_m); fila.addWidget(self.cmb_modo, 1)
        fila.addSpacing(16); fila.addWidget(lab_c); fila.addWidget(self.in_com)
        v.addLayout(fila)

        nota = QLabel("Las credenciales son de la CUENTA de la plataforma (el operador), no de una empresa. "
                      "Nunca se muestran una vez guardadas. Si están fijadas por variables de entorno, "
                      "estas tienen prioridad y el formulario no surtirá efecto.")
        nota.setStyleSheet(f"color:{_DIM};background:transparent;font-size:11px;")
        nota.setWordWrap(True)
        v.addWidget(nota)
        v.addStretch()

        bar = QHBoxLayout()
        bar.addWidget(_btn("Guardar credenciales", self._guardar, primary=True))
        bar.addStretch()
        bar.addWidget(_btn("Cerrar", self.reject))
        v.addLayout(bar)
        self._pintar()

    def _pintar(self):
        from src.services.pagos_marketplace import psp
        e = psp.estado_plataforma()
        self.cmb_modo.setCurrentText(e.get("modo") or "test")
        self.in_com.setText(f"{e.get('comision_pct', 0):g}")
        origen = "variables de entorno" if e.get("origen") == "env" else "guardadas en la app"
        estado = "✓ configurada" if e.get("configurada") else "— sin configurar"
        whk = "✓" if e.get("webhook_configurado") else "—"
        self.lbl_estado.setText(f"Estado: <b>{estado}</b> · webhook: <b>{whk}</b> · modo: "
                                f"<b>{e.get('modo')}</b> · origen: <b>{origen}</b>")

    def _guardar(self):
        if not _puede(self.usuario, "pagos.pasarela.configurar"):
            _aviso(self, "Credenciales", "Permiso requerido: pagos.pasarela.configurar", "warning"); return
        # Acción crítica: step-up MFA (después de RBAC), como el resto de configuración de pasarela.
        try:
            from src.gui.mfa_gui import step_up_sesion
            if not step_up_sesion("pagos.pasarela.configurar", parent=self):
                _aviso(self, "Credenciales", "Verificación MFA requerida para guardar credenciales.",
                       "warning"); return
        except Exception as e:
            logger.debug("step_up_sesion: %s", e)
        try:
            com = float((self.in_com.text() or "0").replace(",", ".") or 0)
        except ValueError:
            _aviso(self, "Credenciales", "Comisión % no válida.", "warning"); return
        from src.services.pagos_marketplace import psp
        ok = psp.guardar_config_plataforma(
            api_key=(self.in_key.text().strip() or None),
            webhook_secret=(self.in_whsec.text().strip() or None),
            modo=self.cmb_modo.currentText(), comision_pct=com)
        if ok:
            self.in_key.clear(); self.in_whsec.clear()   # write-only: no retener en el formulario
            _aviso(self, "Credenciales", "Credenciales de la plataforma guardadas (cifradas).", "success")
            self._pintar()
        else:
            _aviso(self, "Credenciales", "No se pudieron guardar las credenciales.", "error")


class LedgerDialog(QDialog):
    """Historial inmutable (append-only) de movimientos de una transacción."""

    def __init__(self, id_transaccion, parent=None):
        super().__init__(parent)
        self.setFixedSize(720, 460)
        v = _dialogo_frameless(self, titulo=f"Ledger · transacción {id_transaccion}", ancho=720)
        tbl = _tabla(["Fecha", "Tipo", "Importe", "Comisión", "Divisa", "Ref. pago"])
        v.addWidget(tbl, 1)
        eventos = OP.ledger(id_transaccion)
        tbl.setRowCount(len(eventos))
        for i, e in enumerate(eventos):
            for j, val in enumerate([str(e.get("creado_en") or "")[:19], e.get("tipo"),
                                     e.get("importe"), e.get("comision"), e.get("divisa"),
                                     e.get("payment_ref") or e.get("transfer_ref") or ""]):
                tbl.setItem(i, j, _it(val))
        bar = QHBoxLayout(); bar.addStretch(); bar.addWidget(_btn("Cerrar", self.reject))
        v.addLayout(bar)


def _pedir_texto(parent, titulo, etiqueta):
    """Input de texto frameless (evita el QInputDialog con barra nativa). Devuelve (texto, ok)."""
    dlg = QDialog(parent)
    dlg.setFixedSize(440, 220)
    v = _dialogo_frameless(dlg, titulo=titulo, ancho=440)
    lab = QLabel(etiqueta); lab.setStyleSheet(f"color:{_DIM};background:transparent;font-weight:700;")
    v.addWidget(lab)
    inp = _inp("")
    v.addWidget(inp)
    v.addStretch()
    estado = {"ok": False}
    bar = QHBoxLayout()
    bar.addWidget(_btn("Cancelar", dlg.reject))

    def _ok():
        estado["ok"] = True; dlg.accept()
    bar.addWidget(_btn("Aceptar", _ok, primary=True))
    v.addLayout(bar)
    dlg.exec()
    return (inp.text().strip(), estado["ok"])
