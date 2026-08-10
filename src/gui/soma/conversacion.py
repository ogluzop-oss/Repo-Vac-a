"""
Panel conversacional de SOMA (Fase 2). Interfaz DEFINITIVA de conversación dentro del overlay:
historial de mensajes + entrada de texto + botón de micrófono (infraestructura de voz). NO desarrolla
la inteligencia (eso es de una fase posterior): solo la interfaz y las señales. Estilo Enterprise
(Foundation tokens) para coherencia visual.
"""

import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QScrollArea, QVBoxLayout, QWidget)

from src.gui.foundation import tokens as T

logger = logging.getLogger("gui.soma.conversacion")


class SomaConversationPanel(QFrame):
    enviado = pyqtSignal(str)          # texto escrito por el usuario
    voz_solicitada = pyqtSignal()      # el usuario pulsa el micrófono
    usuario_escribe = pyqtSignal(bool)  # True mientras hay texto (el trabajador "está diciendo algo")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("soma_conv")
        self.setStyleSheet(
            f"#soma_conv{{background:{T.BG2}; border:1px solid {T.BORDE}; border-radius:16px;}}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        cab = QLabel("SOMA")
        cab.setStyleSheet(f"color:{T.INFO}; font-weight:900; font-size:13px; background:transparent; border:none;")
        lay.addWidget(cab)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._cont = QWidget(); self._cont.setStyleSheet("background:transparent;")
        self._msgs = QVBoxLayout(self._cont)
        self._msgs.setContentsMargins(0, 0, 0, 0); self._msgs.setSpacing(6)
        self._msgs.addStretch(1)
        self._scroll.setWidget(self._cont)
        lay.addWidget(self._scroll, 1)

        fila = QHBoxLayout(); fila.setSpacing(6)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Escribe a SOMA…")
        self._input.setFixedHeight(44)
        self._input.setStyleSheet(
            f"QLineEdit{{background:{T.BG}; color:{T.TEXT}; border:2px solid {T.BORDE};"
            f"border-radius:10px; padding:0 12px; font-size:13px; font-family:'{T.FONT}';}}"
            f"QLineEdit:focus{{border-color:{T.INFO};}}")
        self._input.returnPressed.connect(self._enviar)
        self._input.textChanged.connect(lambda t: self.usuario_escribe.emit(bool((t or "").strip())))
        fila.addWidget(self._input, 1)
        self._btn_mic = self._boton("🎤", self.voz_solicitada.emit, T.ANALISIS)
        fila.addWidget(self._btn_mic)
        self._btn_send = self._boton("➤", self._enviar, T.INFO)
        fila.addWidget(self._btn_send)
        lay.addLayout(fila)

    def _boton(self, txt, slot, color):
        # Botón cuadrado para el emoji (mic/enviar): tamaño suficiente para que el icono no se recorte.
        b = QPushButton(txt); b.setFixedSize(48, 44); b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(f"QPushButton{{background:{T.BG}; color:{color}; border:2px solid {color};"
                        f"border-radius:10px; font-size:18px; font-weight:900; padding:0;}}"
                        f"QPushButton:hover{{background:{color}; color:{T.BG};}}")
        b.clicked.connect(slot)
        return b

    def _enviar(self):
        texto = (self._input.text() or "").strip()
        if not texto:
            return
        self.agregar_usuario(texto)
        self._input.clear()
        self.enviado.emit(texto)

    # ── Render de mensajes ────────────────────────────────────────────────────
    def _burbuja(self, texto, *, de_soma):
        b = QLabel(texto); b.setWordWrap(True)
        color = T.INFO if de_soma else T.TEXT
        fondo = T.BG if de_soma else T.SIDEBAR
        b.setStyleSheet(f"QLabel{{background:{fondo}; color:{color}; border:1px solid {T.BORDE};"
                        f"border-radius:12px; padding:8px 12px; font-size:13px;}}")
        cont = QHBoxLayout()
        if de_soma:
            cont.addWidget(b, 1); cont.addStretch(0)
        else:
            cont.addStretch(0); cont.addWidget(b, 1)
        w = QWidget(); w.setStyleSheet("background:transparent;"); w.setLayout(cont)
        self._msgs.insertWidget(self._msgs.count() - 1, w)
        self._autoscroll()

    def agregar_usuario(self, texto):
        self._burbuja(texto, de_soma=False)

    def agregar_soma(self, texto):
        self._burbuja(texto, de_soma=True)

    def agregar_soma_rico(self, texto, *, fuentes=None, visual=None):
        """Respuesta enriquecida: texto + contenido VISUAL (tabla/KPIs/lista/cronología) con
        componentes Enterprise + REFERENCIAS (fuentes). Todo dentro del overlay; sin ventanas nuevas."""
        if texto:
            self._burbuja(texto, de_soma=True)
        try:
            w = self._widget_visual(visual)
            if w is not None:
                self._insertar_widget(w)
        except Exception as e:
            logger.debug("visual: %s", e)
        if fuentes:
            self._insertar_referencias(fuentes)

    def _insertar_widget(self, w):
        cont = QHBoxLayout(); cont.addWidget(w, 1)
        wrap = QWidget(); wrap.setStyleSheet("background:transparent;"); wrap.setLayout(cont)
        self._msgs.insertWidget(self._msgs.count() - 1, wrap)
        self._autoscroll()

    def _widget_visual(self, visual):
        if not isinstance(visual, dict):
            return None
        tipo = visual.get("tipo")
        if tipo == "tabla":
            from src.gui.components import EnterpriseTable
            t = EnterpriseTable(visual.get("columnas") or [], con_busqueda=False)
            t.set_datos(visual.get("filas") or [])
            t.setMaximumHeight(220)
            return t
        if tipo == "kpis":
            from src.gui.components import EnterpriseCard, EnterpriseDashboardGrid
            grid = EnterpriseDashboardGrid(columnas=3)
            for it in (visual.get("items") or []):
                modo = "riesgo" if it.get("riesgo") else "kpi"
                grid.add_card(EnterpriseCard(it.get("titulo", ""), it.get("valor", ""),
                                             modo=modo, riesgo=it.get("riesgo")))
            return grid
        if tipo == "timeline":
            from src.gui.components import EnterpriseTimeline
            tl = EnterpriseTimeline(); tl.setMaximumHeight(200)
            for it in (visual.get("items") or []):
                tl.add_item(it.get("texto", ""), fecha=it.get("fecha", ""), rol=it.get("rol", "info"))
            return tl
        if tipo == "lista":
            lbl = QLabel("\n".join(f"• {x}" for x in (visual.get("items") or [])))
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color:{T.TEXT};background:{T.SIDEBAR};border:1px solid {T.BORDE};"
                              f"border-radius:10px;padding:8px 12px;font-size:12px;")
            return lbl
        return None

    def _insertar_referencias(self, fuentes):
        from src.gui.components import EnterpriseStatusBadge
        fila = QHBoxLayout(); fila.setSpacing(4)
        lbl = QLabel("Fuentes:"); lbl.setStyleSheet(f"color:{T.DIM};font-size:10px;background:transparent;")
        fila.addWidget(lbl)
        for f in list(fuentes)[:6]:
            fila.addWidget(EnterpriseStatusBadge(str(f), rol="analisis"))
        fila.addStretch(1)
        wrap = QWidget(); wrap.setStyleSheet("background:transparent;"); wrap.setLayout(fila)
        self._msgs.insertWidget(self._msgs.count() - 1, wrap)
        self._autoscroll()

    def _autoscroll(self):
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(10, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()))

    def foco_entrada(self):
        self._input.setFocus()

    def hay_texto(self) -> bool:
        return bool((self._input.text() or "").strip())

    # ── Workspace de Misión (Fase 6): widget único, dentro del overlay ────────
    def mostrar_workspace(self, mision):
        """Inserta/actualiza el Workspace de Misión al principio del historial (sin ventanas nuevas)."""
        try:
            if getattr(self, "_workspace", None) is None:
                from src.gui.soma.workspace import MissionWorkspace
                self._workspace = MissionWorkspace()
                self._msgs.insertWidget(0, self._workspace)
            self._workspace.actualizar(mision)
        except Exception as e:
            logger.debug("workspace: %s", e)
