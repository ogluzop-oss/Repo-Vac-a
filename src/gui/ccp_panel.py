"""
Panel de la Corporate Communication Platform (CCP Fase II) — GUI mínima.

SOLO consume los servicios de `src.services.ccp` (API-First: cero lógica de negocio aquí). Tres
pestañas: Analítica (KPIs), Timeline (cronología unificada por contacto) y Campañas (lista + procesar).
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from src.gui._neon_ui import _RoundTableCorners, _ss_tabla_neon
from src.services import ccp

logger = logging.getLogger("gui.ccp_panel")

_BG = "#0E1117"; _BG2 = "#161B22"; _CIAN = "#00FFC6"; _ROJO = "#FF4C4C"
_BORDE = "#30363D"; _TEXT = "#E6EDF3"; _DIM = "#8B949E"


def _tabla(cols):
    t = QTableWidget(0, len(cols)); t.setHorizontalHeaderLabels(cols)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    t.horizontalHeader().setHighlightSections(False)
    t.setFrameShape(QTableWidget.Shape.NoFrame)
    t.setStyleSheet(_ss_tabla_neon())                 # contorno neón + cabeceras redondeadas + hover swap
    t._mask = _RoundTableCorners(t, radius=10)         # máscara → el contorno no se corta
    return t


class CCPPanelDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Plataforma de Comunicaciones (CCP)")
        self.setMinimumSize(820, 600)
        # SIN barra negra de Windows: ventana sin marco con contorno neón propio (se cierra con "Cerrar").
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setStyleSheet(f"QDialog{{background:{_BG};border:2px solid {_CIAN};border-radius:14px;}}"
                           f"QLabel{{color:{_TEXT};font-family:'Segoe UI';border:none;}}")
        self._drag = None
        self._build()

    # Arrastre de la ventana sin marco (no hay barra de título de Windows).
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e):
        if self._drag is not None and (e.buttons() & Qt.MouseButton.LeftButton):
            self.move(e.globalPosition().toPoint() - self._drag)
            e.accept()

    def mouseReleaseEvent(self, e):
        self._drag = None
        super().mouseReleaseEvent(e)

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(16, 14, 16, 14); root.setSpacing(10)
        t = QLabel("📡  PLATAFORMA CORPORATIVA DE COMUNICACIONES")
        t.setStyleSheet(f"color:{_CIAN};font-weight:900;font-size:16px;")
        root.addWidget(t)
        tabs = QTabWidget()
        tabs.setStyleSheet(f"QTabBar::tab{{background:{_BG2};color:{_DIM};padding:8px 16px;}}"
                           f"QTabBar::tab:selected{{color:{_CIAN};border-bottom:2px solid {_CIAN};}}"
                           "QTabWidget::pane{border:none;}")
        tabs.addTab(self._tab_analitica(), "Analítica")
        tabs.addTab(self._tab_timeline(), "Timeline")
        tabs.addTab(self._tab_campanas(), "Campañas")
        root.addWidget(tabs, 1)
        b = QPushButton("Cerrar"); b.setFixedHeight(36); b.clicked.connect(self.accept)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(f"QPushButton{{background:transparent;color:{_CIAN};border:2px solid {_CIAN};"
                        f"border-radius:10px;font-weight:900;padding:6px 18px;}}"
                        f"QPushButton:hover{{background:{_CIAN};color:{_BG};}}")     # hover swap
        root.addWidget(b, 0, Qt.AlignmentFlag.AlignRight)

    # ── Analítica ────────────────────────────────────────────────────────────
    def _tab_analitica(self):
        w = QWidget(); ly = QVBoxLayout(w)
        self.lbl_kpi = QLabel(); self.lbl_kpi.setStyleSheet("font-size:13px;"); self.lbl_kpi.setWordWrap(True)
        ly.addWidget(self.lbl_kpi)
        self.tbl_canal = _tabla(["Canal", "Nº comunicaciones"]); ly.addWidget(self.tbl_canal, 1)
        try:
            r = ccp.analitica.resumen()
            self.lbl_kpi.setText(
                f"Total: <b>{r['total']}</b>  ·  Enviados: <b>{r['enviados']}</b>  ·  Fallidos: "
                f"<b>{r['fallidos']}</b>  ·  No operativos: <b>{r['no_operativos']}</b>  ·  Cola: "
                f"<b>{r['cola_pendiente']}</b>  ·  Tasa éxito: <b>{r['tasa_exito']}%</b>")
            self.tbl_canal.setRowCount(len(r["por_canal"]))
            for i, (k, v) in enumerate(sorted(r["por_canal"].items(), key=lambda x: -x[1])):
                self.tbl_canal.setItem(i, 0, QTableWidgetItem(str(k)))
                self.tbl_canal.setItem(i, 1, QTableWidgetItem(str(v)))
        except Exception as e:
            logger.debug("analitica: %s", e)
        return w

    # ── Timeline ─────────────────────────────────────────────────────────────
    def _tab_timeline(self):
        w = QWidget(); ly = QVBoxLayout(w)
        fila = QHBoxLayout()
        self.inp_tl = QLineEdit(); self.inp_tl.setPlaceholderText("Correo del contacto…")
        self.inp_tl.setStyleSheet(f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_CIAN};"
                                  "border-radius:10px;padding:6px 12px;}}")
        bb = QPushButton("Ver"); bb.clicked.connect(self._cargar_timeline)
        bb.setStyleSheet(f"QPushButton{{background:{_CIAN};color:{_BG};border-radius:10px;"
                         "font-weight:900;padding:6px 16px;}}")
        fila.addWidget(self.inp_tl, 1); fila.addWidget(bb); ly.addLayout(fila)
        self.tbl_tl = _tabla(["Fecha", "Sentido", "Canal", "Asunto", "Contraparte", "Estado"])
        ly.addWidget(self.tbl_tl, 1)
        return w

    def _cargar_timeline(self):
        try:
            ev = ccp.timeline.timeline(correo=self.inp_tl.text().strip() or None, limite=200)
        except Exception as e:
            logger.debug("timeline: %s", e); ev = []
        self.tbl_tl.setRowCount(len(ev))
        for i, e in enumerate(ev):
            for j, k in enumerate(("fecha", "sentido", "canal", "asunto", "contraparte", "estado")):
                self.tbl_tl.setItem(i, j, QTableWidgetItem(str(e.get(k) or "")))

    # ── Campañas ─────────────────────────────────────────────────────────────
    def _tab_campanas(self):
        w = QWidget(); ly = QVBoxLayout(w)
        self.tbl_camp = _tabla(["ID", "Nombre", "Tipo", "Estado", "Total", "Enviados", "Fallidos"])
        ly.addWidget(self.tbl_camp, 1)
        b = QPushButton("Procesar seleccionada"); b.clicked.connect(self._procesar_campana)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(f"QPushButton{{background:transparent;color:{_CIAN};border:2px solid {_CIAN};"
                        f"border-radius:10px;font-weight:900;padding:6px 16px;}}"
                        f"QPushButton:hover{{background:{_CIAN};color:{_BG};}}")     # hover swap
        ly.addWidget(b, 0, Qt.AlignmentFlag.AlignRight)
        self._cargar_campanas()
        return w

    def _cargar_campanas(self):
        try:
            camps = ccp.campanas.listar_campanas()
        except Exception as e:
            logger.debug("campanas: %s", e); camps = []
        self.tbl_camp.setRowCount(len(camps))
        for i, c in enumerate(camps):
            for j, k in enumerate(("id", "nombre", "tipo", "estado", "total", "enviados", "fallidos")):
                self.tbl_camp.setItem(i, j, QTableWidgetItem(str(c.get(k) or "")))

    def _procesar_campana(self):
        r = self.tbl_camp.currentRow()
        if r < 0:
            return
        try:
            cid = int(self.tbl_camp.item(r, 0).text())
            ccp.campanas.procesar_campana(cid)
            self._cargar_campanas()
        except Exception as e:
            logger.debug("procesar campaña: %s", e)


def abrir_ccp_panel(parent=None):
    CCPPanelDialog(parent).exec()
