"""
GUIs SAT/Helpdesk (BLOQUE 4): SATDashboardWindow, TicketsWindow, ContratosSATWindow,
IntervencionesWindow, KnowledgeBaseWindow, PortalSATWindow. Reutilizan estilo global + servicios SAT.
"""

import logging

from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QMessageBox, QTabWidget, QTextEdit,
                             QVBoxLayout, QWidget)

from src.gui.catalogo_gestion import _BG, _CIAN, _DIM, _btn, _tabla

logger = logging.getLogger("gui.sat")


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


class SATDashboardWindow(QWidget):
    """Cuadro de mando de soporte: Tickets, Intervenciones, KB, KPIs."""
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("SAT / Helpdesk")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        cab.addWidget(_btn("Actualizar", self._load, primary=True))
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)
        self.lbl = QLabel(""); self.lbl.setStyleSheet(f"color:{_DIM};")
        root.addWidget(self.lbl)
        self.tabs = QTabWidget()
        self.tbl_tk = _tabla(["ID", "Codigo", "Asunto", "Prioridad", "Estado", "Tecnico"])
        self.tbl_kpi = _tabla(["KPI", "Valor"])
        self.tabs.addTab(self.tbl_tk, "Tickets")
        self.tabs.addTab(self.tbl_kpi, "KPIs")
        root.addWidget(self.tabs)
        self._load()

    def _load(self):
        eid = _empresa()
        try:
            from src.services.sat import analitica, tickets
            tks = tickets.listar(id_empresa=eid)
            self.tbl_tk.setRowCount(len(tks))
            for i, x in enumerate(tks):
                for j, v in enumerate([x.get("id"), x.get("codigo"), x.get("asunto"),
                                       x.get("prioridad"), x.get("estado"), x.get("tecnico")]):
                    self.tbl_tk.setItem(i, j, _it(v))
            k = analitica.kpis(id_empresa=eid)
            self.tbl_kpi.setRowCount(len(k))
            for i, (nombre, val) in enumerate(k.items()):
                self.tbl_kpi.setItem(i, 0, _it(nombre)); self.tbl_kpi.setItem(i, 1, _it(val))
            self.lbl.setText(f"Abiertos: {k.get('tickets_abiertos', 0)} · SLA: {k.get('cumplimiento_sla_pct', 0)}%")
        except Exception as e:
            logger.error("load SAT: %s", e)
            self.lbl.setText(f"Error: {e}")


class TicketsWindow(SATDashboardWindow): """Vista de tickets (reutiliza dashboard)."""
class ContratosSATWindow(SATDashboardWindow): """Vista de contratos/SLA (reutiliza dashboard)."""
class IntervencionesWindow(SATDashboardWindow): """Vista de intervenciones (reutiliza dashboard)."""


class KnowledgeBaseWindow(QWidget):
    """Base de conocimiento: busqueda y lectura de articulos publicados."""
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("Base de conocimiento")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        self.txt = QLineEdit(); self.txt.setPlaceholderText("Buscar...")
        cab.addWidget(self.txt); cab.addWidget(_btn("Buscar", self._buscar, primary=True))
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)
        self.tbl = _tabla(["ID", "Titulo", "Etiquetas", "Vistas"])
        root.addWidget(self.tbl)
        self._buscar()

    def _buscar(self):
        try:
            from src.services.sat import kb
            arts = kb.buscar(self.txt.text(), id_empresa=_empresa())
            self.tbl.setRowCount(len(arts))
            for i, a in enumerate(arts):
                for j, v in enumerate([a.get("id"), a.get("titulo"), a.get("etiquetas"), a.get("vistas")]):
                    self.tbl.setItem(i, j, _it(v))
        except Exception as e:
            logger.error("buscar KB: %s", e)


class PortalSATWindow(QWidget):
    """SAT-G — Portal de cliente: crear ticket, consultar tickets/SLA/intervenciones."""
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, id_cliente=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.id_cliente = id_cliente or (usuario or {}).get("id_cliente")
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("Portal de soporte")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)
        # Alta de ticket
        root.addWidget(QLabel("Nuevo ticket"))
        self.asunto = QLineEdit(); self.asunto.setPlaceholderText("Asunto")
        self.desc = QTextEdit(); self.desc.setPlaceholderText("Describe tu incidencia...")
        self.desc.setMaximumHeight(90)
        root.addWidget(self.asunto); root.addWidget(self.desc)
        root.addWidget(_btn("Crear ticket", self._crear, primary=True))
        # Mis tickets
        self.tbl = _tabla(["Codigo", "Asunto", "Estado", "SLA"])
        root.addWidget(QLabel("Mis tickets")); root.addWidget(self.tbl)
        self._load()

    def _crear(self):
        if not self.asunto.text().strip():
            QMessageBox.warning(self, "Portal", "Indica un asunto."); return
        try:
            from src.services.sat import tickets
            tid = tickets.crear_ticket(self.asunto.text().strip(), descripcion=self.desc.toPlainText(),
                                       id_cliente=self.id_cliente, canal="portal", id_empresa=_empresa())
            QMessageBox.information(self, "Portal", f"Ticket creado: TK{tid:06d}" if tid else "Error")
            self.asunto.clear(); self.desc.clear(); self._load()
        except Exception as e:
            QMessageBox.critical(self, "Portal", str(e))

    def _load(self):
        try:
            from src.services.sat import tickets
            tks = tickets.listar(id_cliente=self.id_cliente, id_empresa=_empresa()) if self.id_cliente else []
            self.tbl.setRowCount(len(tks))
            for i, x in enumerate(tks):
                for j, v in enumerate([x.get("codigo"), x.get("asunto"), x.get("estado"),
                                       x.get("sla_vencimiento")]):
                    self.tbl.setItem(i, j, _it(v))
        except Exception as e:
            logger.error("portal load: %s", e)
