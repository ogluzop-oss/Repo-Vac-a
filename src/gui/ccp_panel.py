"""
Panel de la Corporate Communication Platform (CCP Fase II) — GUI mínima.

SOLO consume los servicios de `src.services.ccp` (API-First: cero lógica de negocio aquí). Tres
pestañas: Analítica (KPIs), Timeline (cronología unificada por contacto) y Campañas (lista + procesar).
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from src.gui._neon_ui import (_BotonCerrarX, _RoundTableCorners,
                              _ss_tabla_neon, instalar_columnas_equitativas)
from src.gui.components import EnterpriseTabs
from src.gui.transiciones import abrir_dialogo_deslizante
from src.services import ccp

try:
    from assets.estilo_global import mostrar_mensaje
except Exception:  # pragma: no cover
    mostrar_mensaje = None

logger = logging.getLogger("gui.ccp_panel")

_BG = "#0E1117"; _BG2 = "#161B22"; _CIAN = "#00FFC6"; _ROJO = "#FF4C4C"
_BORDE = "#30363D"; _TEXT = "#E6EDF3"; _DIM = "#8B949E"


def _aviso(parent, titulo, msg, nivel="info"):
    if mostrar_mensaje is not None:
        mostrar_mensaje(parent, titulo, msg, nivel=nivel)
    else:  # pragma: no cover
        logger.info("%s: %s", titulo, msg)


def _tabla(cols):
    t = QTableWidget(0, len(cols)); t.setHorizontalHeaderLabels(cols)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    # Reparto equitativo del ancho visible entre columnas por defecto (petición explícita, mismo
    # criterio que `catalogo_gestion._tabla`): una columna solo crece más que su reparto si su
    # cabecera/celda no cabe, y eso ensancha la TABLA (scrollbar horizontal, `_ss_tabla_neon` ya
    # la estiliza) en vez de robarle espacio a las demás — ver `_neon_ui._ColumnasEquitativas`.
    t.horizontalHeader().setHighlightSections(False)
    instalar_columnas_equitativas(t)
    t.setFrameShape(QTableWidget.Shape.NoFrame)
    t.setStyleSheet(_ss_tabla_neon())                 # contorno neón + cabeceras redondeadas + hover swap
    t._mask = _RoundTableCorners(t, radius=10)         # máscara → el contorno no se corta
    return t


class CCPPanelDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Plataforma de Comunicaciones (CCP)")
        self.setMinimumSize(820, 600)
        # SIN barra negra de Windows: ventana sin marco (se cierra con la X). Petición explícita:
        # se abre a PANTALLA COMPLETA, sin el contorno turquesa que antes rodeaba la ventana, y con
        # la misma animación de deslizamiento que el resto de diálogos a pantalla completo de la
        # app — ver `abrir_ccp_panel`/`abrir_dialogo_deslizante`, que es quien de verdad fija la
        # geometría a pantalla completa de forma fiable (fijarla aquí en `__init__` no basta: el
        # HWND frameless puede asentarse con una geometría menor DESPUÉS de este punto en Windows).
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        # "border:none" EXPLÍCITO (no basta con omitirlo): la hoja de estilos global de la app
        # pone `border:2px solid CIAN` a TODO QDialog por defecto (`assets/estilo_global.py`,
        # QSS_DIALOGS) y, como esta hoja local no redeclaraba esa propiedad, seguía colándose por
        # debajo pese a quitar el contorno de aquí — el contorno turquesa que rodeaba la ventana
        # seguía viéndose tras pasar a pantalla completa.
        self.setStyleSheet(f"QDialog{{background:{_BG};border:none;}}"
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

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # Reafirma el contorno de las 3 tablas (petición explícita: al abrirse a pantalla completa
        # con `abrir_dialogo_deslizante`, podía quedar un contorno más pequeño "flotando" dentro —
        # ver `_RoundTableCorners.refrescar`).
        for _nombre in ("tbl_canal", "tbl_tl", "tbl_camp"):
            _tbl = getattr(self, _nombre, None)
            if _tbl is not None and hasattr(_tbl, "_mask"):
                _tbl._mask.refrescar()

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(16, 14, 16, 14); root.setSpacing(10)
        cab = QHBoxLayout()
        t = QLabel("📡  PLATAFORMA CORPORATIVA DE COMUNICACIONES")
        t.setStyleSheet(f"color:{_CIAN};font-weight:900;font-size:16px;")
        cab.addWidget(t); cab.addStretch()
        btn_x = _BotonCerrarX(32); btn_x.clicked.connect(self.accept)
        cab.addWidget(btn_x)
        root.addLayout(cab)
        tabs = EnterpriseTabs()  # estilo + deslizamiento ya incluidos (petición explícita, 2026-11-23:
                                 # CCP es la referencia de diseño de subpestañas de toda la app — ahora
                                 # usa el propio componente compartido, en vez de fijar su hoja de
                                 # estilos a mano, para que de verdad sea una única fuente).
        tabs.addTab(self._tab_analitica(), "Analítica")
        tabs.addTab(self._tab_timeline(), "Cronología")
        tabs.addTab(self._tab_campanas(), "Campañas")
        root.addWidget(tabs, 1)

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
        self.inp_tl = QLineEdit(); self.inp_tl.setPlaceholderText("🔍 Correo del contacto…")
        self.inp_tl.setStyleSheet(f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_CIAN};"
                                  "border-radius:10px;padding:6px 12px;}}")
        bb = QPushButton("🔍"); bb.clicked.connect(self._cargar_timeline)
        bb.setStyleSheet(f"QPushButton{{background:{_BG};color:{_CIAN};border:2px solid {_CIAN};border-radius:10px;"
                         "font-weight:900;padding:6px 16px;}"
                         f"QPushButton:hover{{background:{_CIAN};color:{_BG};}}")
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
        titulo = "Campañas"
        r = self.tbl_camp.currentRow()
        if r < 0:
            _aviso(self, titulo, "Selecciona antes una campaña de la tabla.", "info")
            return
        try:
            cid = int(self.tbl_camp.item(r, 0).text())
            n = ccp.campanas.procesar_campana(cid)
            self._cargar_campanas()
            if n > 0:
                _aviso(self, titulo, f"Campaña procesada: {n} comunicación(es) encolada(s).", "success")
            else:
                _aviso(self, titulo,
                      "La campaña no tenía comunicaciones pendientes que procesar.", "info")
        except Exception as e:
            logger.debug("procesar campaña: %s", e)
            _aviso(self, titulo, "No se pudo procesar la campaña.", "error")


def abrir_ccp_panel(parent=None):
    abrir_dialogo_deslizante(CCPPanelDialog(parent), parent)
