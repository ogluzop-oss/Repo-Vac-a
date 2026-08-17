"""
GUI del Marketplace + Pagos (F5) — capa fina que SOLO orquesta `services.pagos_marketplace.operaciones`.

- `ConectarCobrosDialog`: onboarding KYB de una parte (proveedor/vendedor) en el PSP + estado (banco/últimos4).
- `EscrowPagosDialog`: transacciones de la Lonja con su estado de escrow + acciones (confirmar recepción,
  abrir disputa, liberar [step-up MFA], ver ledger).

Reutiliza los helpers visuales de `catalogo_gestion` y `mostrar_mensaje`. Ninguna lógica de negocio vive aquí.
"""

import logging

from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QTableWidgetItem, QVBoxLayout)

from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _TEXT, _btn, _dialogo_frameless, _inp, _tabla)
from src.services.pagos_marketplace import operaciones as OP

logger = logging.getLogger("gui.pagos_marketplace")

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
