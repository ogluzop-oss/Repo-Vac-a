"""
GUI Resiliencia (BLOQUE 7): ResilienciaDashboardWindow — estado online/offline, colas, conflictos,
circuit breakers, RPO/RTO, edge nodes. Permite sincronizar, ejecutar watchdog y lanzar chaos.
Reutiliza el estilo global. Aditivo.
"""

import logging

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QTabWidget, QVBoxLayout, QWidget

from src.gui.catalogo_gestion import _BG, _CIAN, _DIM, _btn, _tabla

logger = logging.getLogger("gui.resiliencia")


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


class ResilienciaDashboardWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("Resiliencia · Continuidad operativa")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        cab.addWidget(_btn("Actualizar", self._load, primary=True))
        cab.addWidget(_btn("Sincronizar", self._sync))
        cab.addWidget(_btn("Watchdog", self._watchdog))
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)
        self.lbl = QLabel(""); self.lbl.setStyleSheet(f"color:{_DIM};")
        root.addWidget(self.lbl)
        self.tabs = QTabWidget()
        self.tbl_estado = _tabla(["Indicador", "Valor"])
        self.tbl_breakers = _tabla(["Servicio", "Estado", "Fallos"])
        self.tbl_edge = _tabla(["Tienda", "Modo", "Pendientes", "Salud"])
        self.tabs.addTab(self.tbl_estado, "Estado")
        self.tabs.addTab(self.tbl_breakers, "Circuit breakers")
        self.tabs.addTab(self.tbl_edge, "Edge nodes")
        root.addWidget(self.tabs)
        self._load()

    def _load(self):
        try:
            from src.services.resiliencia import resilience_dashboard
            p = resilience_dashboard.panel(id_empresa=_empresa())
            rr = p.get("rpo_rto", {})
            filas = [
                ("Salud general", p.get("salud")),
                ("Sync pendientes", p.get("sync_pendientes")),
                ("Conflictos", p.get("conflictos")),
                ("Breakers abiertos", ", ".join(p.get("breakers_abiertos", [])) or "0"),
                ("Tiendas offline/degradado", p.get("tiendas_offline")),
                ("RPO backup (h)", rr.get("rpo_backup")),
                ("RTO backup (min)", rr.get("rto_backup")),
                ("Última sincronización", p.get("ultima_sincronizacion")),
            ]
            self.tbl_estado.setRowCount(len(filas))
            for i, (k, v) in enumerate(filas):
                self.tbl_estado.setItem(i, 0, _it(k)); self.tbl_estado.setItem(i, 1, _it(v))
            br = p.get("circuit_breakers", [])
            self.tbl_breakers.setRowCount(len(br))
            for i, b in enumerate(br):
                for j, v in enumerate([b.get("servicio"), b.get("estado"), b.get("fallos")]):
                    self.tbl_breakers.setItem(i, j, _it(v))
            edge = p.get("edge_nodes", [])
            self.tbl_edge.setRowCount(len(edge))
            for i, n in enumerate(edge):
                for j, v in enumerate([n.get("id_tienda"), n.get("modo"), n.get("eventos_pendientes"),
                                       n.get("salud")]):
                    self.tbl_edge.setItem(i, j, _it(v))
            self.lbl.setText(f"Salud: {p.get('salud')} · Sync pendientes: {p.get('sync_pendientes')}")
        except Exception as e:
            logger.error("load resiliencia: %s", e)
            self.lbl.setText(f"Error: {e}")

    def _sync(self):
        try:
            from src.services.resiliencia import sync_engine
            r = sync_engine.push_offline_a_central(id_empresa=_empresa())
            QMessageBox.information(self, "Sync", f"Sincronizado: {r['resumen']}")
            self._load()
        except Exception as e:
            QMessageBox.critical(self, "Sync", str(e))

    def _watchdog(self):
        try:
            from src.services.resiliencia import resilience_watchdog
            r = resilience_watchdog.ejecutar(id_empresa=_empresa())
            QMessageBox.information(self, "Watchdog", f"Acciones: {r['acciones']}")
            self._load()
        except Exception as e:
            QMessageBox.critical(self, "Watchdog", str(e))
