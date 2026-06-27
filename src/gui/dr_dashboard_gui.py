"""
DR-E (GUI) — Panel de Disaster Recovery. Muestra ultimo backup, RPO/RTO, replicacion,
almacenamiento, ultimo restore test e incidentes DR. Permite crear snapshot, drill y runbook.
"""

import logging

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QVBoxLayout, QWidget

from src.gui.catalogo_gestion import _BG, _CIAN, _DIM, _btn, _tabla

logger = logging.getLogger("gui.dr")


def _it(v):
    from PyQt6.QtWidgets import QTableWidgetItem
    return QTableWidgetItem("" if v is None else str(v))


class DRDashboardWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("Disaster Recovery · Panel")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        cab.addWidget(_btn("Actualizar", self._load, primary=True))
        cab.addWidget(_btn("Crear snapshot", self._snapshot))
        cab.addWidget(_btn("Drill verify", self._drill))
        cab.addWidget(_btn("Runbook PDF", self._runbook))
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)

        self.lbl = QLabel(""); self.lbl.setStyleSheet(f"color:{_DIM};")
        root.addWidget(self.lbl)
        self.tbl = _tabla(["Indicador", "Valor"])
        root.addWidget(self.tbl)
        self._load()

    def _load(self):
        try:
            from src.services.dr import dr_dashboard
            p = dr_dashboard.panel()
            filas = [
                ("Último backup (horas)", p.get("ultimo_backup_horas")),
                ("RPO (horas)", (p.get("rpo") or {}).get("rpo_horas")),
                ("RTO estimado (min)", (p.get("rto") or {}).get("rto_min")),
                ("Replicación", (p.get("replicacion") or {}).get("estado")),
                ("Almacenamiento", (p.get("almacenamiento") or {}).get("backend")),
                ("Último restore test", (p.get("ultimo_restore_test") or {}).get("estado")),
                ("Incidentes DR", len(p.get("incidentes_dr") or [])),
            ]
            self.tbl.setRowCount(len(filas))
            for i, (k, v) in enumerate(filas):
                self.tbl.setItem(i, 0, _it(k)); self.tbl.setItem(i, 1, _it(v))
            self.lbl.setText("Panel DR actualizado.")
        except Exception as e:
            logger.error("load DR: %s", e)
            self.lbl.setText(f"Error: {e}")

    def _snapshot(self):
        from src.services.dr import dr_pitr
        r = dr_pitr.crear_snapshot(motivo="manual_gui")
        QMessageBox.information(self, "Snapshot", "OK" if r.get("ok") else f"Error: {r.get('error')}")
        self._load()

    def _drill(self):
        from src.services.dr import dr_drills
        r = dr_drills.verify_diario()
        QMessageBox.information(self, "Drill", "OK" if r.get("ok") else "Fallido")
        self._load()

    def _runbook(self):
        from src.services.dr import dr_dashboard
        r = dr_dashboard.runbook("pdf")
        QMessageBox.information(self, "Runbook", r.get("ruta") if r.get("ok") else "Error")
