"""
Multi-Tenant Cloud Manager — GUI (Fase V · Bloque 7). Panel maestro SUPERADMIN de todas las empresas
SaaS. Consume SOLO `src.services.cloud_manager` (que reutiliza SaaS/Observabilidad/plataforma). Alta
inline de empresa, suspender/reactivar, backup y monitorización global. Feedback 100% INLINE (sin
QMessageBox/QDialog — lección del crash de audio de SOMA). Solo debe abrirse con perfil SUPERADMIN.
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QTableWidgetItem, QVBoxLayout,
                             QWidget)

from src.gui.catalogo_gestion import (_BG, _BG2, _CIAN, _DIM, _TEXT, _btn, _btn_x, _combo,
                                      _inp, _tabla)
from src.services import cloud_manager as cm

logger = logging.getLogger("cloud.gui")


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


class CloudManagerWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.main = main
        self._empresas = []
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)

        cab = QHBoxLayout()
        t = QLabel("☁ Multi-Tenant Cloud Manager")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        if callback_vuelta:
            cab.addWidget(_btn_x(self._volver))
        root.addLayout(cab)

        # Solo SUPERADMIN.
        perfil = str((self.usuario or {}).get("perfil", "")).upper()
        if perfil != "SUPERADMIN":
            aviso = QLabel("Acceso restringido: el Cloud Manager es exclusivo del perfil SUPERADMIN.")
            aviso.setStyleSheet(f"color:{_DIM};font-size:14px;padding:20px;")
            root.addWidget(aviso); root.addStretch()
            return

        # Panel de monitorización global (reutiliza servicios existentes).
        self.lbl_monit = QLabel("")
        self.lbl_monit.setWordWrap(True)
        self.lbl_monit.setStyleSheet(f"color:{_TEXT};font-size:12px;background:{_BG2};"
                                     "border-radius:10px;padding:12px;")
        root.addWidget(self.lbl_monit)

        # Alta inline de empresa.
        alta = QHBoxLayout()
        self.in_nombre = _inp("Nombre de la empresa"); self.in_nombre.setFixedWidth(240)
        self.cmb_plan = _combo([(p, p) for p in cm.licencias_cloud.PLANES])
        alta.addWidget(QLabel("Nueva empresa:")); alta.addWidget(self.in_nombre)
        alta.addWidget(QLabel("Plan:")); alta.addWidget(self.cmb_plan)
        alta.addWidget(_btn("Crear empresa", self._crear, primary=True))
        alta.addStretch()
        alta.addWidget(_btn("↻ Refrescar", self._recargar))
        root.addLayout(alta)

        self.tabla = _tabla(["ID Empresa", "Nombre", "Estado operativo"])
        root.addWidget(self.tabla)

        acc = QHBoxLayout()
        acc.addWidget(_btn("Suspender", self._suspender, danger=True))
        acc.addWidget(_btn("Reactivar", self._reactivar))
        acc.addWidget(_btn("Backup", self._backup))
        acc.addStretch()
        root.addLayout(acc)

        self.lbl_feedback = QLabel(""); self.lbl_feedback.setWordWrap(True)
        self.lbl_feedback.setStyleSheet(f"color:{_CIAN};font-size:12px;")
        root.addWidget(self.lbl_feedback)

        self._recargar()

    # ── helpers ──
    def _usuario(self):
        return (self.usuario or {}).get("nombre")

    def _feedback(self, msg, color=_CIAN):
        self.lbl_feedback.setStyleSheet(f"color:{color};font-size:12px;")
        self.lbl_feedback.setText(msg)

    def _emp_sel(self):
        fila = self.tabla.currentRow()
        if fila < 0 or fila >= len(self._empresas):
            return None
        e = self._empresas[fila]
        return e.get("id") or e.get("id_empresa")

    def _recargar(self, *_):
        self._empresas = cm.tenants.listar()
        self.tabla.setRowCount(len(self._empresas))
        for i, e in enumerate(self._empresas):
            for j, v in enumerate([e.get("id") or e.get("id_empresa"),
                                   e.get("nombre_empresa") or e.get("nombre"),
                                   e.get("estado_operativo")]):
                self.tabla.setItem(i, j, _it(v))
        self._pintar_monitorizacion()

    def _pintar_monitorizacion(self):
        try:
            g = cm.monitorizacion.global_()
            sis = g.get("sistema", {})
            plat = g.get("plataforma", {})
            self.lbl_monit.setText(
                f"<b>Monitorización global</b> · Empresas: {len(self._empresas)} · "
                f"CPU: {sis.get('cpu_pct')}% · RAM: {sis.get('ram_pct')}% · "
                f"Disco: {sis.get('disco_pct')}% · "
                f"Servicios plataforma: {len(plat.get('servicios', []) if isinstance(plat, dict) else [])} · "
                f"Salud: {g.get('salud', {}).get('status', '—') if isinstance(g.get('salud'), dict) else '—'}")
        except Exception as e:
            self.lbl_monit.setText(f"Monitorización no disponible: {e}")

    # ── acciones (inline) ──
    def _crear(self):
        nombre = self.in_nombre.text().strip()
        if not nombre:
            self._feedback("⚠️ Escribe el nombre de la empresa.", "#F0A020"); return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            r = cm.tenants.crear(nombre, plan=self.cmb_plan.currentData(), usuario=self._usuario())
        finally:
            QApplication.restoreOverrideCursor()
        if r.get("ok"):
            self.in_nombre.clear()
            self._feedback(f"✅ Empresa «{nombre}» creada (plan {r.get('plan')}).")
            self._recargar()
        else:
            self._feedback(f"⚠️ No se pudo crear: {r.get('error')}", "#F0A020")

    def _accion(self, fn, ok_msg):
        emp = self._emp_sel()
        if not emp:
            self._feedback("Selecciona una empresa en la tabla.", "#F0A020"); return
        r = fn(emp)
        if isinstance(r, dict) and r.get("ok"):
            self._feedback(ok_msg(r)); self._recargar()
        else:
            self._feedback(f"⚠️ {r}", "#F0A020")

    def _suspender(self):
        self._accion(lambda e: cm.tenants.suspender(e, usuario=self._usuario()),
                     lambda r: f"⏸ Empresa {r['id_empresa']} suspendida.")

    def _reactivar(self):
        self._accion(lambda e: cm.tenants.reactivar(e, usuario=self._usuario()),
                     lambda r: f"▶ Empresa {r['id_empresa']} reactivada.")

    def _backup(self):
        emp = self._emp_sel()
        if not emp:
            self._feedback("Selecciona una empresa.", "#F0A020"); return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            r = cm.tenants.backup(emp)
        finally:
            QApplication.restoreOverrideCursor()
        self._feedback(f"💾 Backup empresa {emp}: {r}" if r else "Backup no disponible.")
