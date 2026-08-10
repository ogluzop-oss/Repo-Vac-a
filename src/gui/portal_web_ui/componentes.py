"""
Portal Web · Componentes de UI reutilizables (Fase WEB-09).

Widgets de presentación genéricos para el Back Office web: `KpiCard`, `TablaDatos`, `Buscador`, `Toolbar`,
`Breadcrumb`, `PanelSeccion`. Solo presentación (no lógica de negocio). Reutilizan las primitivas de estilo
neón compartidas (`gui/_neon_ui`). Pensados para reutilización en futuras secciones/fases.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout,
                             QHeaderView, QLabel, QLineEdit, QPushButton,
                             QSizePolicy, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget)

from src.gui._neon_ui import (_BG, _BG2, _BORDE, _CIAN, _FONT, _ROJO, _TEXT,
                              _TEXT2, _VERDE, _RoundTableCorners, _btn, _lbl,
                              _ss_tabla_neon)


def sesion():
    """Sesión activa (usuario/perfil) para pasar a los servicios que lo requieran. Degradable."""
    try:
        from src.db.usuario import sesion_global
        return sesion_global
    except Exception:
        return None


def usuario_actual():
    s = sesion()
    return getattr(s, "usuario_actual", None) if s else None


def perfil_actual():
    s = sesion()
    for attr in ("perfil_actual", "rol_actual", "perfil", "rol"):
        v = getattr(s, attr, None) if s else None
        if v:
            return v
    return None


class KpiCard(QFrame):
    """Tarjeta KPI: título + valor grande + subtítulo opcional. Color de acento configurable."""

    clicked = pyqtSignal()

    def __init__(self, titulo="", valor="—", sub="", color=_CIAN, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"QFrame{{background:{_BG2};border:1px solid {_BORDE};border-radius:12px;}}"
                           f"QFrame:hover{{border-color:{color};}}")
        self.setMinimumWidth(180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        ly = QVBoxLayout(self)
        ly.setContentsMargins(16, 12, 16, 12)
        ly.setSpacing(2)
        ly.addWidget(_lbl(titulo, size=11, color=_TEXT2))
        self._val = _lbl(str(valor), bold=True, size=26, color=color)
        ly.addWidget(self._val)
        self._sub = _lbl(sub, size=10, color=_TEXT2)
        ly.addWidget(self._sub)

    def set_valor(self, valor, sub=None):
        self._val.setText(str(valor))
        if sub is not None:
            self._sub.setText(sub)

    def mouseReleaseEvent(self, e):
        self.clicked.emit()
        super().mouseReleaseEvent(e)


class Buscador(QWidget):
    """Caja de búsqueda con placeholder. Emite `buscar(texto)` en Enter o botón."""

    buscar = pyqtSignal(str)

    def __init__(self, placeholder="Buscar…", parent=None):
        super().__init__(parent)
        ly = QHBoxLayout(self)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.setSpacing(8)
        self._inp = QLineEdit()
        self._inp.setPlaceholderText(placeholder)
        self._inp.setFixedHeight(36)
        self._inp.setStyleSheet(
            f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:0 12px;font-size:12px;font-family:'{_FONT}';}}"
            f"QLineEdit:focus{{border-color:{_CIAN};}}")
        self._inp.returnPressed.connect(self._emit)
        ly.addWidget(self._inp, 1)
        b = _btn("🔍  Buscar", color_fg=_CIAN, color_border=_CIAN, hover_bg=_CIAN, h=36)
        b.clicked.connect(self._emit)
        ly.addWidget(b)

    def texto(self) -> str:
        return self._inp.text().strip()

    def _emit(self):
        self.buscar.emit(self.texto())


class Toolbar(QFrame):
    """Barra de acciones horizontal. `add(texto, handler, prim=False)` añade un botón."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QFrame{background:transparent;border:none;}")
        self._ly = QHBoxLayout(self)
        self._ly.setContentsMargins(0, 0, 0, 0)
        self._ly.setSpacing(8)

    def add(self, texto, handler=None, prim=False):
        if prim:
            b = _btn(texto, color_bg=_CIAN, color_fg="#0D1117", color_border=_CIAN,
                     hover_bg="#FFF", hover_fg="#0D1117", h=36)
        else:
            b = _btn(texto, color_fg=_CIAN, color_border=_CIAN, hover_bg=_CIAN, h=36)
        if handler:
            b.clicked.connect(handler)
        self._ly.addWidget(b)
        return b

    def add_stretch(self):
        self._ly.addStretch()

    def add_widget(self, w):
        self._ly.addWidget(w)


class Breadcrumb(QLabel):
    """Migas de pan: `set_ruta(["Portal Web", "Clientes", "Ficha"])`."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"color:{_TEXT2};font-size:12px;font-family:'{_FONT}';background:transparent;")

    def set_ruta(self, partes):
        self.setText("  ›  ".join(str(p) for p in partes if p))


class TablaDatos(QTableWidget):
    """Tabla neón reutilizable. `cargar(cols, filas)` donde filas = lista de listas/tuplas de celdas.
    Soporta ORDENACIÓN por cabecera y SELECCIÓN MÚLTIPLE (WEB-10). Sin lógica de negocio."""

    def __init__(self, multiseleccion=False, ordenable=True, parent=None):
        super().__init__(0, 0, parent)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection if multiseleccion
                              else QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(40)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(ordenable)
        self._ordenable = ordenable
        self.setStyleSheet(_ss_tabla_neon())
        _RoundTableCorners(self)

    def cargar(self, cols, filas):
        self.setSortingEnabled(False)          # evita reordenar durante la carga
        self.clear()
        self.setColumnCount(len(cols))
        self.setHorizontalHeaderLabels([str(c) for c in cols])
        hh = self.horizontalHeader()
        for i in range(len(cols)):
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        self.setRowCount(0)
        for fila in filas:
            r = self.rowCount()
            self.insertRow(r)
            for c, val in enumerate(fila):
                it = QTableWidgetItem("" if val is None else str(val))
                self.setItem(r, c, it)
        self.setSortingEnabled(self._ordenable)

    def fila_actual_valor(self, col=0):
        r = self.currentRow()
        if r < 0:
            return None
        it = self.item(r, col)
        return it.text() if it else None

    def filas_seleccionadas(self) -> list:
        """Índices de fila seleccionados (selección múltiple)."""
        return sorted({i.row() for i in self.selectedIndexes()})


class PanelTabla(QWidget):
    """Tabla enriquecida reutilizable (WEB-10): búsqueda + ordenación + paginación + exportación +
    selección múltiple sobre `TablaDatos`. Trabaja con `list[dict]`. Solo presentación — la EXPORTACIÓN
    reutiliza `gui.foundation.export.exportar_excel` (no crea lógica ni formato nuevo)."""

    def __init__(self, nombre_export="portal_web", page_size=25, multiseleccion=True, parent=None):
        super().__init__(parent)
        self._nombre = nombre_export
        self._page = 0
        self._page_size = page_size
        self._cols = []
        self._all = []       # list[dict] completo
        self._filtrado = []  # list[dict] tras búsqueda
        ly = QVBoxLayout(self)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.setSpacing(8)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self._buscador = Buscador("Filtrar en la tabla…")
        self._buscador.buscar.connect(self._filtrar)
        bar.addWidget(self._buscador, 1)
        b_exp = _btn("⭳  Exportar", color_fg=_CIAN, color_border=_CIAN, hover_bg=_CIAN, h=36)
        b_exp.clicked.connect(self._exportar)
        bar.addWidget(b_exp)
        ly.addLayout(bar)

        self.tabla = TablaDatos(multiseleccion=multiseleccion)
        ly.addWidget(self.tabla, 1)

        pie = QHBoxLayout()
        self._lbl_total = QLabel("")
        self._lbl_total.setStyleSheet(f"color:{_TEXT2};font-size:11px;")
        pie.addWidget(self._lbl_total)
        pie.addStretch()
        self._b_prev = _btn("◀", color_fg=_CIAN, color_border=_BORDE, hover_bg=_CIAN, h=30)
        self._b_prev.clicked.connect(lambda: self._ir(self._page - 1))
        self._lbl_pag = QLabel("")
        self._lbl_pag.setStyleSheet(f"color:{_TEXT};font-size:11px;")
        self._b_next = _btn("▶", color_fg=_CIAN, color_border=_BORDE, hover_bg=_CIAN, h=30)
        self._b_next.clicked.connect(lambda: self._ir(self._page + 1))
        pie.addWidget(self._b_prev)
        pie.addWidget(self._lbl_pag)
        pie.addWidget(self._b_next)
        ly.addLayout(pie)

    def cargar(self, cols, filas):
        """`cols` = lista de claves; `filas` = list[dict]."""
        self._cols = list(cols)
        self._all = list(filas or [])
        self._filtrar(self._buscador.texto())

    def _filtrar(self, texto):
        texto = (texto or "").strip().lower()
        if not texto:
            self._filtrado = list(self._all)
        else:
            self._filtrado = [r for r in self._all
                              if any(texto in str(r.get(c, "")).lower() for c in self._cols)]
        self._page = 0
        self._render()

    def _paginas(self):
        n = max(1, (len(self._filtrado) + self._page_size - 1) // self._page_size)
        return n

    def _ir(self, page):
        self._page = max(0, min(page, self._paginas() - 1))
        self._render()

    def _render(self):
        ini = self._page * self._page_size
        pagina = self._filtrado[ini:ini + self._page_size]
        self.tabla.cargar([str(c).capitalize() for c in self._cols],
                          [[r.get(c) for c in self._cols] for r in pagina])
        self._lbl_total.setText(f"{len(self._filtrado)} de {len(self._all)} registro(s)")
        self._lbl_pag.setText(f"Página {self._page + 1} / {self._paginas()}")

    def filas_seleccionadas(self) -> list:
        """Dicts seleccionados en la página actual."""
        ini = self._page * self._page_size
        return [self._filtrado[ini + i] for i in self.tabla.filas_seleccionadas()
                if ini + i < len(self._filtrado)]

    def fila_actual(self):
        ini = self._page * self._page_size
        r = self.tabla.currentRow()
        return self._filtrado[ini + r] if 0 <= r and ini + r < len(self._filtrado) else None

    def _exportar(self):
        try:
            from src.gui.foundation.export import exportar_excel
            exportar_excel(self._filtrado, self._nombre, columnas=self._cols or None)
        except Exception:
            pass


class FormPanel(QFrame):
    """Formulario INLINE reutilizable (WEB-10): campos etiqueta→valor + Guardar/Cancelar. Se muestra
    DENTRO de la sección (no modal — respeta la lección SOMA: evitar modales en módulos con audio).
    Emite `guardado(dict)` y `cancelado()`. Solo captura de datos; la persistencia la hace la sección
    llamando a los servicios."""

    guardado = pyqtSignal(dict)
    cancelado = pyqtSignal()

    def __init__(self, titulo="", parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"QFrame{{background:{_BG2};border:1px solid {_CIAN};border-radius:12px;}}")
        self._campos = {}
        self._ly = QVBoxLayout(self)
        self._ly.setContentsMargins(16, 12, 16, 12)
        self._ly.setSpacing(6)
        self._titulo = QLabel(titulo)
        self._titulo.setStyleSheet(f"color:{_CIAN};font-weight:800;font-size:14px;")
        self._ly.addWidget(self._titulo)
        self._cont = QVBoxLayout()
        self._cont.setSpacing(6)
        self._ly.addLayout(self._cont)
        self._msg = QLabel("")
        self._msg.setStyleSheet(f"color:{_TEXT2};font-size:11px;")
        self._ly.addWidget(self._msg)
        botones = QHBoxLayout()
        botones.addStretch()
        b_cancel = _btn("Cancelar", color_fg=_TEXT2, color_border=_BORDE, hover_bg=_ROJO, h=34)
        b_cancel.clicked.connect(self.cancelado.emit)
        b_guardar = _btn("Guardar", color_bg=_VERDE, color_fg="#0D1117", color_border=_VERDE,
                         hover_bg="#FFF", hover_fg="#0D1117", h=34)
        b_guardar.clicked.connect(self._emit)
        botones.addWidget(b_cancel)
        botones.addWidget(b_guardar)
        self._ly.addLayout(botones)
        self.setVisible(False)

    def configurar(self, titulo, campos, valores=None):
        """`campos` = lista de (clave, etiqueta). `valores` = dict opcional para edición."""
        self._titulo.setText(titulo)
        self._msg.setText("")
        while self._cont.count():
            it = self._cont.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
        self._campos = {}
        valores = valores or {}
        for clave, etiqueta in campos:
            self._cont.addWidget(_lbl(etiqueta, size=11, color=_TEXT2))
            e = QLineEdit(str(valores.get(clave, "") or ""))
            e.setFixedHeight(34)
            e.setStyleSheet(
                f"QLineEdit{{background:{_BG};color:{_TEXT};border:2px solid {_BORDE};"
                f"border-radius:8px;padding:0 10px;font-size:12px;font-family:'{_FONT}';}}"
                f"QLineEdit:focus{{border-color:{_CIAN};}}")
            self._cont.addWidget(e)
            self._campos[clave] = e

    def mensaje(self, texto):
        self._msg.setText(texto)

    def _emit(self):
        self.guardado.emit({k: e.text().strip() for k, e in self._campos.items()})


class PanelSeccion(QWidget):
    """Base de una sección: cabecera (título + breadcrumb + toolbar opcional) + cuerpo. Las secciones
    concretas añaden su contenido a `self.cuerpo` (un QVBoxLayout)."""

    def __init__(self, titulo="", icono="", parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)
        self.breadcrumb = Breadcrumb()
        root.addWidget(self.breadcrumb)
        cab = QHBoxLayout()
        cab.setSpacing(10)
        cab.addWidget(_lbl(f"{icono}  {titulo}".strip(), bold=True, size=20, color=_CIAN))
        cab.addStretch()
        self.toolbar = Toolbar()
        cab.addWidget(self.toolbar)
        root.addLayout(cab)
        self.cuerpo = QVBoxLayout()
        self.cuerpo.setSpacing(10)
        root.addLayout(self.cuerpo, 1)

    def estado_vacio(self, texto="Sin datos disponibles."):
        w = QLabel("📭  " + texto)
        w.setWordWrap(True)
        w.setStyleSheet(f"color:{_TEXT2};background:{_BG2};border:1px dashed {_BORDE};"
                        f"border-radius:10px;padding:16px;font-size:12px;")
        return w
