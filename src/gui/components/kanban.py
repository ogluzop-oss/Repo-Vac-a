"""
EnterpriseKanbanBoard — tablero Kanban genérico (arrastrar-y-soltar) por columnas con color propio.

JUSTIFICACIÓN DE COMPONENTE NUEVO (CLAUDE.md, regla 1: "Prohibido crear tablas, tarjetas, buscadores,
filtros, toolbars, badges o indicadores fuera de la librería, salvo justificación técnica
documentada"): no existía ningún primitivo de arrastre multi-columna en `gui/components/enterprise.py`
— `EnterpriseTable` es una tabla plana y `EnterpriseDashboardGrid` es una rejilla ESTÁTICA de tarjetas
KPI (sin drag&drop ni columnas por estado). Un Kanban reutilizable (pipeline CRM hoy; cualquier flujo
por etapas en el futuro — OF de Producción, tickets SAT, OT de GMAO — todos ya modelan un "estado"/
"etapa" por el que una entidad avanza) necesita un widget de columnas enlazadas con arrastre entre
ellas que ningún componente existente cubre ni puede extender sin romper su contrato. Se añade como
componente de librería (no ad-hoc dentro de `crm_dashboard.py`) para que sea reutilizable.

Patrón de implementación (estándar PyQt para Kanban multi-columna): N `QListWidget` hermanos, cada uno
con `setAcceptDrops(True)` + `setDragDropMode(DragDrop)`, con `dropEvent` SOBRESCRITO a mano (no se
delega en el `dropEvent` por defecto de `QAbstractItemView`): el mecanismo interno de Qt para mover
`QListWidgetItem` entre vistas NO conserva el widget puesto con `setItemWidget` en el ítem movido (bug
conocido de Qt/PyQt) — por eso aquí se saca el ítem de la lista origen a mano (`takeItem`) y se
reconstruye la tarjeta en la lista destino con los mismos datos, es la vía robusta para arrastre
entre columnas. El reordenamiento DENTRO de una misma columna se ignora a propósito (no tiene
significado de negocio en el pipeline — el orden de las etapas lo fija `crm_etapas.orden`, no el
orden de las tarjetas dentro de una etapa).

Ningún widget de aquí contiene lógica de negocio: solo presenta tarjetas y notifica el gesto de
arrastre vía la señal `cartaMovida(id_tarjeta, columna_origen, columna_destino)` — quien use este
componente decide qué hacer (p.ej. llamar a `services.crm.oportunidades.mover_etapa`).
"""

import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout, QLabel, QListWidget,
                             QListWidgetItem, QScrollArea, QVBoxLayout, QWidget)

from src.gui.components.enterprise import EnterpriseStatusBadge
from src.gui.foundation import tokens as T

logger = logging.getLogger("gui.components.kanban")


# ── Tarjeta individual (visual, calca el estilo de EnterpriseCard) ───────────
class _TarjetaKanbanWidget(QFrame):
    def __init__(self, dato, acento, parent=None):
        super().__init__(parent)
        dato = dato or {}
        self.setStyleSheet(T.qss_tarjeta(acento))
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(3)

        titulo = QLabel(str(dato.get("titulo") or f"#{dato.get('id', '')}"))
        titulo.setWordWrap(True)
        titulo.setStyleSheet(f"color:{T.TEXT};font-weight:900;font-size:13px;background:transparent;"
                             f"border:none;")
        lay.addWidget(titulo)

        if dato.get("cliente"):
            cli = QLabel(f"👤 {dato['cliente']}")
            cli.setWordWrap(True)
            cli.setStyleSheet(f"color:{T.DIM};font-size:11px;background:transparent;border:none;")
            lay.addWidget(cli)

        fila = QHBoxLayout()
        fila.setContentsMargins(0, 2, 0, 0)
        valor = dato.get("valor")
        try:
            txt_valor = f"{float(valor):,.2f} €" if valor is not None else "—"
        except (TypeError, ValueError):
            txt_valor = str(valor)
        lv = QLabel(txt_valor)
        lv.setStyleSheet(f"color:{acento};font-weight:800;font-size:12px;background:transparent;"
                         f"border:none;")
        fila.addWidget(lv)
        fila.addStretch(1)
        prob = dato.get("probabilidad")
        if prob is not None:
            try:
                badge = EnterpriseStatusBadge(f"{int(prob)}%", rol="analisis")
                badge.setStyleSheet(badge.styleSheet() + "padding:1px 8px;font-size:11px;")
                fila.addWidget(badge)
            except Exception:
                pass
        lay.addLayout(fila)

        if dato.get("responsable"):
            r = QLabel(f"🧑‍💼 {dato['responsable']}")
            r.setStyleSheet(f"color:{T.DIM};font-size:11px;background:transparent;border:none;")
            lay.addWidget(r)

        if dato.get("proxima_actividad"):
            act = QLabel(f"📋 {dato['proxima_actividad']}")
            act.setWordWrap(True)
            act.setStyleSheet(f"color:{T.INFO};font-size:11px;background:transparent;border:none;")
            lay.addWidget(act)


# ── Columna (QListWidget con drag&drop manual entre hermanas) ────────────────
class _KanbanColumnList(QListWidget):
    tarjetaMovida = pyqtSignal(object, str, str)  # id_tarjeta, columna_origen, columna_destino

    def __init__(self, codigo_columna, acento, parent=None):
        super().__init__(parent)
        self.codigo_columna = codigo_columna
        self.acento = acento
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSpacing(8)
        self.setStyleSheet(
            f"QListWidget{{background:{T.BG};border:1px solid {T.BORDE};border-radius:{T.RADIO}px;"
            f"outline:none;}}"
            f"QListWidget::item{{border:none;background:transparent;}}"
            f"QListWidget::item:selected{{background:transparent;}}" + T.qss_scrollbar(acento))

    def agregar_tarjeta(self, dato):
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, dato.get("id"))
        item.setData(Qt.ItemDataRole.UserRole + 1, dato)
        widget = _TarjetaKanbanWidget(dato, self.acento)
        self.addItem(item)
        item.setSizeHint(widget.sizeHint())
        self.setItemWidget(item, widget)

    # -- drag & drop ----------------------------------------------------------
    def dragEnterEvent(self, event):
        if isinstance(event.source(), _KanbanColumnList):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if isinstance(event.source(), _KanbanColumnList):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        source = event.source()
        if not isinstance(source, _KanbanColumnList):
            event.ignore()
            return
        item = source.currentItem()
        if item is None:
            event.ignore()
            return
        if source is self:
            # Reordenar DENTRO de la misma columna: sin significado de negocio en este pipeline
            # (el orden de las etapas lo fija `crm_etapas.orden`) — no-op deliberado, evita además
            # el bug de Qt que pierde el `setItemWidget` del ítem al reordenar internamente.
            event.ignore()
            return
        fila = source.row(item)
        id_tarjeta = item.data(Qt.ItemDataRole.UserRole)
        dato = item.data(Qt.ItemDataRole.UserRole + 1) or {}
        source.takeItem(fila)
        nuevo = QListWidgetItem()
        nuevo.setData(Qt.ItemDataRole.UserRole, id_tarjeta)
        nuevo.setData(Qt.ItemDataRole.UserRole + 1, dato)
        widget = _TarjetaKanbanWidget(dato, self.acento)
        self.addItem(nuevo)
        nuevo.setSizeHint(widget.sizeHint())
        self.setItemWidget(nuevo, widget)
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()
        self.tarjetaMovida.emit(id_tarjeta, source.codigo_columna, self.codigo_columna)


# ── Tablero ────────────────────────────────────────────────────────────────
class EnterpriseKanbanBoard(QWidget):
    """Tablero Kanban: una columna por etapa (`codigo`/`titulo`/`color`), una tarjeta por entidad.

    Uso:
        board = EnterpriseKanbanBoard(columnas)   # [{codigo, titulo, color}, …]
        board.cartaMovida.connect(mi_callback)    # (id_tarjeta, columna_origen, columna_destino)
        board.establecer_tarjetas(tarjetas)       # [{id, columna, titulo, valor, ...}, …]
    """

    cartaMovida = pyqtSignal(object, str, str)

    def __init__(self, columnas=None, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{T.BG};")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(f"QScrollArea{{background:{T.BG};border:none;}}" +
                                   T.qss_scrollbar())
        self._inner = QWidget()
        self._inner.setStyleSheet(f"background:{T.BG};")
        self._lay = QHBoxLayout(self._inner)
        self._lay.setContentsMargins(4, 4, 4, 4)
        self._lay.setSpacing(T.SPACING_M)
        self._scroll.setWidget(self._inner)
        outer.addWidget(self._scroll)

        self._columnas = {}  # codigo -> (header_label, QListWidget)
        self.establecer_columnas(columnas or [])

    def establecer_columnas(self, columnas):
        """Reconstruye las columnas (lista de dicts {codigo, titulo, color}). Llamar cuando cambien
        las etapas del pipeline; para una simple recarga de tarjetas usar `establecer_tarjetas`."""
        while self._lay.count():
            item = self._lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._columnas = {}
        for col in columnas:
            codigo = col.get("codigo")
            if not codigo:
                continue
            color = col.get("color") or T.INFO
            contenedor = QWidget()
            contenedor.setMinimumWidth(230)
            v = QVBoxLayout(contenedor)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(6)
            header = QLabel(str(col.get("titulo") or codigo))
            header.setAlignment(Qt.AlignmentFlag.AlignCenter)
            header.setStyleSheet(
                f"background:{T.BG2};color:{color};border:1px solid {T.BORDE};"
                f"border-bottom:3px solid {color};border-radius:8px;padding:8px;"
                f"font-weight:900;font-size:13px;")
            v.addWidget(header)
            lista = _KanbanColumnList(codigo, color)
            lista.tarjetaMovida.connect(self.cartaMovida.emit)
            v.addWidget(lista, 1)
            self._lay.addWidget(contenedor, 1)
            self._columnas[codigo] = (header, lista)

    def establecer_tarjetas(self, tarjetas):
        """Repuebla todas las columnas desde cero con `tarjetas` (dicts con clave 'columna' = código
        de la columna/etapa de destino). Tarjetas cuya columna no existe se ignoran (etapa desconocida)."""
        for _h, lista in self._columnas.values():
            lista.clear()
        for t in (tarjetas or []):
            destino = self._columnas.get(t.get("columna"))
            if destino is None:
                logger.debug("establecer_tarjetas: columna desconocida %r (tarjeta %r)",
                            t.get("columna"), t.get("id"))
                continue
            _h, lista = destino
            lista.agregar_tarjeta(t)
        for header, lista in self._columnas.values():
            base = header.text().split("  (")[0]
            header.setText(f"{base}  ({lista.count()})")

    def tarjetas_de(self, codigo_columna):
        """IDs de tarjeta actualmente presentes en una columna (para verificación/tests)."""
        destino = self._columnas.get(codigo_columna)
        if destino is None:
            return []
        _h, lista = destino
        return [lista.item(i).data(Qt.ItemDataRole.UserRole) for i in range(lista.count())]

    def mover_tarjeta_programatico(self, id_tarjeta, columna_origen, columna_destino):
        """Simula el gesto de arrastre sin interacción real de ratón (tests/automatización):
        traslada la tarjeta `id_tarjeta` de `columna_origen` a `columna_destino` y emite
        `cartaMovida` exactamente igual que un drop real de usuario."""
        origen = self._columnas.get(columna_origen)
        destino = self._columnas.get(columna_destino)
        if origen is None or destino is None:
            return False
        _ho, lista_o = origen
        _hd, lista_d = destino
        for i in range(lista_o.count()):
            item = lista_o.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == id_tarjeta:
                dato = item.data(Qt.ItemDataRole.UserRole + 1) or {}
                lista_o.takeItem(i)
                lista_d.agregar_tarjeta(dato)
                self.cartaMovida.emit(id_tarjeta, columna_origen, columna_destino)
                return True
        return False
