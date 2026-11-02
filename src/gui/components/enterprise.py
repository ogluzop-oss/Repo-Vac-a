"""
Librería visual Enterprise (Components). Widgets reutilizables con identidad única, construidos sobre
`gui/foundation` (tokens/iconos/export). Ningún widget implementa lógica de negocio: solo presentan
datos ya calculados por los servicios.

Componentes: EnterpriseCard · EnterpriseStatusBadge · EnterpriseRiskIndicator · EnterpriseSearch ·
EnterpriseFilter · EnterpriseToolbar · EnterpriseTable · EnterpriseDashboardGrid · EnterpriseTimeline ·
EnterpriseInlineBanner · EnterpriseHelpTooltip.
"""

import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
                             QLineEdit, QMenu, QPushButton, QScrollArea,
                             QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from src.gui.foundation import export as _export
from src.gui.foundation import icons as _icons
from src.gui.foundation import tokens as T

try:
    # Repinta las esquinas + redibuja el contorno neón encima → la scrollbar y las cabeceras dejan
    # de cortar el borde redondeado de la tabla (mismo mecanismo que las tablas de catalogo_gestion).
    from assets.estilo_global import instalar_corner_cover as _corner_cover
except Exception:
    _corner_cover = None

logger = logging.getLogger("gui.components")


# ── EnterpriseCard — tarjeta ÚNICA configurable ───────────────────────────────
class EnterpriseCard(QFrame):
    """Tarjeta configurable por modo: 'kpi' · 'riesgo' · 'estado' · 'ia' · 'prediccion' · 'accion'.
    Sustituye a cualquier KPICard/MetricCard."""

    clicked = pyqtSignal()

    _ACENTO = {"kpi": T.INFO, "estado": T.ANALISIS, "ia": T.INFO, "prediccion": T.ANALISIS,
               "accion": T.OK}

    def __init__(self, titulo, valor="", *, modo="kpi", concepto=None, subtitulo=None,
                 riesgo=None, on_click=None, parent=None):
        super().__init__(parent)
        acento = T.color_riesgo(riesgo) if (modo == "riesgo" and riesgo) else self._ACENTO.get(modo, T.INFO)
        self.setStyleSheet(T.qss_tarjeta(acento))
        self.setMinimumWidth(180)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(4)

        cab = _icons.etiqueta(concepto, titulo) if concepto else titulo
        lt = QLabel(cab)
        lt.setStyleSheet(f"color:{T.DIM};font-size:14px;font-weight:700;background:transparent;border:none;")
        lay.addWidget(lt)

        lv = QLabel(str(valor))
        lv.setStyleSheet(f"color:{acento};font-size:22px;font-weight:900;background:transparent;border:none;")
        lay.addWidget(lv)
        self._valor = lv

        if subtitulo:
            ls = QLabel(str(subtitulo))
            ls.setStyleSheet(f"color:{T.TEXT};font-size:11px;background:transparent;border:none;")
            ls.setWordWrap(True)
            lay.addWidget(ls)

        if modo == "accion" and on_click:
            b = QPushButton(str(valor) or titulo)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"QPushButton{{background:{T.BG2};color:{acento};border:2px solid {acento};"
                            f"border-radius:8px;font-weight:900;padding:6px 12px;}}"
                            f"QPushButton:hover{{background:{acento};color:{T.BG};}}")
            b.clicked.connect(on_click)
            lv.setVisible(False)
            lay.addWidget(b)

        self._on_click = on_click

    def set_valor(self, valor):
        self._valor.setText(str(valor))

    def mousePressEvent(self, e):
        self.clicked.emit()
        if self._on_click and self._valor.isVisible():
            try:
                self._on_click()
            except Exception:
                pass
        super().mousePressEvent(e)


# ── EnterpriseStatusBadge — pastilla de estado ────────────────────────────────
class EnterpriseStatusBadge(QLabel):
    def __init__(self, texto, *, rol="neutro", parent=None):
        super().__init__(texto, parent)
        c = T.color(rol)
        self.setStyleSheet(f"color:{c};background:{T.BG2};border:1px solid {c};border-radius:10px;"
                           f"padding:3px 12px;font-weight:800;font-size:13px;")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_estado(self, texto, rol="neutro"):
        c = T.color(rol)
        self.setStyleSheet(f"color:{c};background:{T.BG2};border:1px solid {c};border-radius:10px;"
                           f"padding:3px 12px;font-weight:800;font-size:13px;")
        self.setText(texto)


# ── EnterpriseRiskIndicator — indicador de riesgo ─────────────────────────────
class EnterpriseRiskIndicator(EnterpriseStatusBadge):
    _ROL = {"BAJO": "ok", "MEDIO": "advertencia", "ALTO": "critico"}

    def __init__(self, nivel="BAJO", parent=None):
        nivel = str(nivel).upper()
        super().__init__(_icons.etiqueta("riesgo", nivel), rol=self._ROL.get(nivel, "neutro"), parent=parent)

    def set_nivel(self, nivel):
        nivel = str(nivel).upper()
        self.set_estado(_icons.etiqueta("riesgo", nivel), self._ROL.get(nivel, "neutro"))


# ── EnterpriseSearch / EnterpriseFilter ───────────────────────────────────────
class EnterpriseSearch(QLineEdit):
    def __init__(self, placeholder="Buscar…", parent=None):
        super().__init__(parent)
        self.setFixedHeight(32)
        self.setPlaceholderText(_icons.etiqueta("buscar", placeholder))
        self.setStyleSheet(f"QLineEdit{{background:{T.BG2};color:{T.TEXT};border:2px solid {T.BORDE};"
                           f"border-radius:8px;padding:0 10px;font-size:12px;font-family:'{T.FONT}';}}"
                           f"QLineEdit:focus{{border-color:{T.INFO};}}")


class EnterpriseFilter(QComboBox):
    def __init__(self, opciones=None, parent=None):
        super().__init__(parent)
        self.setFixedHeight(32)
        self.setMinimumWidth(200)
        # Popup con anchura suficiente para no cortar el texto de las opciones.
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        try:
            self.view().setMinimumWidth(220)
        except Exception:
            pass
        self.setStyleSheet(f"QComboBox{{background:{T.BG2};color:{T.TEXT};border:2px solid {T.BORDE};"
                           f"border-radius:8px;padding:0 10px;font-size:12px;font-family:'{T.FONT}';}}"
                           f"QComboBox:hover,QComboBox:on{{border-color:{T.INFO};}}"
                           # ::drop-down explícito (no confiar en la herencia del QSS global): el
                           # botón de la flecha debe fundirse con el fondo del propio combo, sin
                           # parche de tono distinto — mismo tratamiento que el resto de combos
                           # locales de la app (ver `assets/estilo_global.py::QComboBox::drop-down`).
                           f"QComboBox::drop-down{{border:none;width:22px;background:transparent;}}"
                           f"QComboBox QAbstractItemView{{background:{T.BG2};color:{T.TEXT};"
                           f"border:1px solid {T.INFO};selection-background-color:{T.INFO};"
                           f"selection-color:{T.BG};outline:none;}}")
        for op in (opciones or []):
            if isinstance(op, (list, tuple)):
                self.addItem(str(op[0]), op[1] if len(op) > 1 else op[0])
            else:
                self.addItem(str(op), op)


# ── EnterpriseToolbar — barra de herramientas (título + búsqueda + acciones + export) ──
class EnterpriseToolbar(QWidget):
    def __init__(self, titulo="", *, con_busqueda=False, con_export=False, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(T.SPACING_S)
        if titulo:
            lt = QLabel(titulo)
            lt.setStyleSheet(f"color:{T.INFO};font-size:14px;font-weight:900;background:transparent;")
            self._lay.addWidget(lt)
        self._lay.addStretch(1)
        self.search = None
        if con_busqueda:
            self.search = EnterpriseSearch()
            self.search.setFixedWidth(240)
            self._lay.addWidget(self.search)
            # Disparador explícito: reaplica el mismo filtro en vivo (textChanged) que ya conecte
            # quien use esta barra de herramientas — no hay lógica de filtro propia que duplicar aquí.
            btn_buscar = QPushButton("🔍")
            btn_buscar.setCursor(Qt.CursorShape.PointingHandCursor)
            # 44x44 (no 32x32): un cuadro más pequeño recorta visualmente el glifo emoji — mismo bug
            # ya visto y corregido en `catalogo_gestion._btn`/`remote_scan.py` (ahí a 46x46).
            btn_buscar.setFixedSize(48, 48)
            btn_buscar.setStyleSheet(
                f"QPushButton{{background:{T.BG2};color:{T.INFO};border:2px solid {T.INFO};"
                f"border-radius:8px;font-weight:900;font-size:14px;padding:0;}}"
                f"QPushButton:hover{{background:{T.INFO};color:{T.BG};}}")
            btn_buscar.clicked.connect(lambda: self.search.textChanged.emit(self.search.text()))
            self._lay.addWidget(btn_buscar)
            self.btn_buscar = btn_buscar
        if con_export:
            self._lay.addWidget(self._boton(_icons.etiqueta("exportar", "Excel"), self._export, T.ANALISIS))
        self._on_export_datos = None

    def _boton(self, txt, slot, color):
        b = QPushButton(txt)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFixedHeight(32)
        b.setStyleSheet(f"QPushButton{{background:{T.BG2};color:{color};border:2px solid {color};"
                        f"border-radius:8px;font-weight:800;padding:0 12px;}}"
                        f"QPushButton:hover{{background:{color};color:{T.BG};}}")
        b.clicked.connect(slot)
        return b

    def add_action(self, texto, slot, *, concepto=None, color=None):
        b = self._boton(_icons.etiqueta(concepto, texto) if concepto else texto, slot, color or T.INFO)
        self._lay.addWidget(b)
        return b

    def add_widget(self, w):
        self._lay.addWidget(w)

    def set_export(self, proveedor_datos, nombre_base):
        """proveedor_datos: callable → lista de dicts. nombre_base: nombre del fichero."""
        self._on_export_datos = (proveedor_datos, nombre_base)

    def _export(self):
        if not self._on_export_datos:
            return
        proveedor, nombre = self._on_export_datos
        try:
            _export.exportar_excel(proveedor() or [], nombre)
        except Exception as e:
            logger.debug("export toolbar: %s", e)


# ── EnterpriseTable — tabla única (búsqueda + paginación + menú contextual) ────
class EnterpriseTable(QWidget):
    def __init__(self, columnas=None, *, con_busqueda=True, pagina=0, con_actualizar=None,
                 contador_abajo=False, actualizar_pos="busqueda", mostrar_contador=True, parent=None):
        super().__init__(parent)
        self._cols = list(columnas or [])
        self._datos = []           # lista de listas (todas las filas)
        self._pagina = 0
        self._por_pagina = int(pagina) if pagina else 0   # 0 = sin paginación
        self._contador_abajo = bool(contador_abajo)
        self._mostrar_contador = bool(mostrar_contador)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(T.SPACING_S)

        self.lbl_pag = QLabel("")
        self.lbl_pag.setStyleSheet(f"color:{T.DIM};font-size:11px;")
        self.search = None
        # Barra superior de la tabla. `actualizar_pos`: "busqueda" = Actualizar pegado a la barra de
        # búsqueda (defecto); "derecha" = Actualizar en el extremo derecho (esquina superior derecha).
        if con_busqueda or con_actualizar:
            barra = QHBoxLayout()
            if con_busqueda:
                self.search = EnterpriseSearch()
                self.search.textChanged.connect(self._aplicar_filtro)
                barra.addWidget(self.search)
                # Disparador explícito de búsqueda (antes solo filtraba en vivo al teclear): mismo
                # contorno cian compacto que `_nav_btn`, ajustado a un único glifo junto al campo.
                btn_buscar = QPushButton("🔍")
                btn_buscar.setCursor(Qt.CursorShape.PointingHandCursor)
                # 44x44 (no 32x32): mismo ajuste anti-recorte de glifo que en `EnterpriseToolbar`.
                btn_buscar.setFixedSize(48, 48)
                btn_buscar.setStyleSheet(
                    f"QPushButton{{background:{T.BG2};color:{T.INFO};border:2px solid {T.INFO};"
                    f"border-radius:8px;font-weight:900;font-size:14px;padding:0;}}"
                    f"QPushButton:hover{{background:{T.INFO};color:{T.BG};}}")
                btn_buscar.clicked.connect(self._aplicar_filtro)
                barra.addWidget(btn_buscar)
                self.btn_buscar = btn_buscar
            if con_actualizar and actualizar_pos == "busqueda":
                barra.addWidget(self._btn_actualizar(con_actualizar))
            barra.addStretch(1)
            if not self._contador_abajo and self._mostrar_contador:
                barra.addWidget(self.lbl_pag)
            if con_actualizar and actualizar_pos == "derecha":
                barra.addWidget(self._btn_actualizar(con_actualizar))
            lay.addLayout(barra)

        self.tabla = QTableWidget()
        self.tabla.setColumnCount(len(self._cols))
        self.tabla.setHorizontalHeaderLabels(self._cols)
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabla.customContextMenuRequested.connect(self._menu_contextual)
        # Diseño ESTÁNDAR de la app: contorno neón + hover swap en cabeceras + esquinas redondeadas +
        # anchura equitativa (columnas Stretch → ocupa todo el ancho).
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setStyleSheet(T.qss_tabla())
        from PyQt6.QtWidgets import QHeaderView
        hh = self.tabla.horizontalHeader()
        hh.setHighlightSections(False)
        for c in range(len(self._cols)):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.tabla, 1)
        # Tapa de esquinas: evita que la scrollbar y las cabeceras corten el contorno neón.
        if _corner_cover is not None:
            _corner_cover(self.tabla, 12, bg=T.BG)

        # Fila inferior: contador abajo-izquierda (opcional) + navegación abajo-derecha (paginación).
        if (self._contador_abajo and self._mostrar_contador) or self._por_pagina:
            pie = QHBoxLayout()
            if self._contador_abajo and self._mostrar_contador:
                pie.addWidget(self.lbl_pag)
            pie.addStretch(1)
            if self._por_pagina:
                self._b_prev = self._nav_btn("◀", lambda: self._cambiar_pagina(-1))
                self._b_next = self._nav_btn("▶", lambda: self._cambiar_pagina(1))
                pie.addWidget(self._b_prev); pie.addWidget(self._b_next)
            lay.addLayout(pie)

    def _btn_actualizar(self, slot):
        b = QPushButton("🔄 Actualizar")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(T.qss_boton(T.INFO))

        def _run():
            orig = b.text()
            b.setText("⏳ Actualizando…"); b.setEnabled(False)
            try:
                from PyQt6.QtWidgets import QApplication
                QApplication.processEvents()   # fuerza el repintado del estado de carga
                slot()
            finally:
                b.setText(orig); b.setEnabled(True)
        b.clicked.connect(_run)
        return b

    def _nav_btn(self, txt, slot):
        # Glifos geométricos (◀ ▶) que renderizan de forma fiable, a diferencia de ‹ › (se veían
        # en blanco). Botón amplio y con padding para que el icono se vea completo (no recortado).
        b = QPushButton(txt); b.setMinimumSize(52, 36); b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(f"QPushButton{{background:{T.BG2};color:{T.INFO};border:2px solid {T.INFO};"
                        f"border-radius:8px;font-weight:900;font-size:16px;padding:2px 8px;}}"
                        f"QPushButton:hover{{background:{T.INFO};color:{T.BG};}}")
        b.clicked.connect(slot); return b

    def set_columnas(self, columnas):
        self._cols = list(columnas)
        self.tabla.setColumnCount(len(self._cols))
        self.tabla.setHorizontalHeaderLabels(self._cols)
        from PyQt6.QtWidgets import QHeaderView
        hh = self.tabla.horizontalHeader()
        for c in range(len(self._cols)):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch)

    def set_datos(self, filas):
        """filas: lista de dicts (usa columnas) o lista de listas/tuplas."""
        norm = []
        for f in (filas or []):
            if isinstance(f, dict):
                norm.append([f.get(c, "") for c in self._cols])
            else:
                norm.append(list(f))
        self._datos = norm
        self._pagina = 0
        self._render()

    def _filtradas(self):
        txt = (self.search.text().strip().lower() if self.search else "")
        if not txt:
            return self._datos
        return [row for row in self._datos if any(txt in str(v).lower() for v in row)]

    def _aplicar_filtro(self):
        self._pagina = 0
        self._render()

    def _cambiar_pagina(self, d):
        self._pagina = max(0, self._pagina + d)
        self._render()

    def _render(self):
        filas = self._filtradas()
        total = len(filas)
        if self._por_pagina:
            ini = self._pagina * self._por_pagina
            filas_pag = filas[ini:ini + self._por_pagina]
            paginas = max(1, (total + self._por_pagina - 1) // self._por_pagina)
            self.lbl_pag.setText(f"{total} filas · pág. {self._pagina + 1}/{paginas}")
        else:
            filas_pag = filas
            self.lbl_pag.setText(f"{total} filas")
        self.tabla.setRowCount(len(filas_pag))
        for i, row in enumerate(filas_pag):
            for j, v in enumerate(row):
                self.tabla.setItem(i, j, QTableWidgetItem(str(v)))
        # Nota: no se llama a resizeColumnsToContents() a propósito — rompería el modo Stretch
        # (anchura equitativa) que da el diseño estándar de la app.

    def _menu_contextual(self, pos):
        m = QMenu(self)
        a_copiar = QAction("Copiar fila", self)
        a_copiar.triggered.connect(self._copiar_fila)
        a_export = QAction(_icons.etiqueta("exportar", "Exportar a Excel"), self)
        a_export.triggered.connect(self._exportar)
        m.addAction(a_copiar); m.addAction(a_export)
        m.exec(self.tabla.viewport().mapToGlobal(pos))

    def _copiar_fila(self):
        r = self.tabla.currentRow()
        if r < 0:
            return
        vals = [self.tabla.item(r, c).text() if self.tabla.item(r, c) else "" for c in range(self.tabla.columnCount())]
        try:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText("\t".join(vals))
        except Exception:
            pass

    def _exportar(self):
        datos = [dict(zip(self._cols, row)) for row in self._filtradas()]
        _export.exportar_excel(datos, "Tabla", columnas=self._cols)


# ── EnterpriseDashboardGrid — rejilla de tarjetas ─────────────────────────────
class EnterpriseDashboardGrid(QWidget):
    def __init__(self, columnas=4, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        self._cols = max(1, int(columnas))
        self._grid = QGridLayout(self)
        self._grid.setSpacing(T.SPACING_M)
        self._n = 0

    def add_card(self, card: EnterpriseCard):
        r, c = divmod(self._n, self._cols)
        self._grid.addWidget(card, r, c)
        self._n += 1
        return card

    def limpiar(self):
        while self._grid.count():
            it = self._grid.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        self._n = 0


# ── EnterpriseTimeline — línea temporal vertical ──────────────────────────────
class EnterpriseTimeline(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setStyleSheet(f"QScrollArea{{background:{T.BG};border:1px solid {T.BORDE};border-radius:8px;}}")
        self._cont = QWidget()
        self._cont.setStyleSheet("background:transparent;")
        self._lay = QVBoxLayout(self._cont)
        self._lay.setContentsMargins(T.SPACING_M, T.SPACING_M, T.SPACING_M, T.SPACING_M)
        self._lay.setSpacing(T.SPACING_S)
        self._lay.addStretch(1)
        self.setWidget(self._cont)

    def add_item(self, texto, *, fecha="", rol="info", concepto=None):
        fila = QFrame()
        fila.setStyleSheet(f"background:{T.BG2};border:1px solid {T.BORDE};"
                           f"border-left:3px solid {T.color(rol)};border-radius:8px;")
        fl = QHBoxLayout(fila); fl.setContentsMargins(10, 6, 10, 6)
        lbl = QLabel(_icons.etiqueta(concepto, texto) if concepto else texto)
        lbl.setStyleSheet(f"color:{T.TEXT};background:transparent;border:none;font-size:12px;")
        lbl.setWordWrap(True)
        fl.addWidget(lbl, 1)
        if fecha:
            lf = QLabel(str(fecha))
            lf.setStyleSheet(f"color:{T.DIM};background:transparent;border:none;font-size:10px;")
            fl.addWidget(lf)
        self._lay.insertWidget(self._lay.count() - 1, fila)

    def limpiar(self):
        while self._lay.count() > 1:
            it = self._lay.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()


# ── EnterpriseInlineBanner — aviso inline de ancho completo, NO modal ─────────
class EnterpriseInlineBanner(QFrame):
    """Aviso inline de ancho completo, no-modal: un frame más dentro del layout de la pantalla, con
    fondo oscuro + acento de color de borde según rol semántico (`T.color(rol)`), mensaje en negrita
    del mismo color y un botón de acción opcional (relleno con el color del rol, texto en `T.BG`).

    DISTINTO de `assets/estilo_global.mostrar_mensaje`/`mostrar_confirmacion`: esos son DIÁLOGOS
    MODALES (bloquean la ventana hasta que el usuario los cierra). `EnterpriseInlineBanner` es un
    widget normal que se inserta en un layout — no interrumpe el flujo, no bloquea el resto de la
    UI, y puede convivir con otros widgets en la misma pantalla (p. ej. varios avisos a la vez).

    Roles: 'info' · 'analisis' · 'advertencia' · 'critico' · 'ok' (mismo catálogo semántico que
    `tokens.color`/el resto de la librería — `EnterpriseStatusBadge`, `EnterpriseRiskIndicator`).
    """

    accion_pulsada = pyqtSignal()

    def __init__(self, mensaje, *, rol="info", texto_accion=None, concepto=None, parent=None):
        super().__init__(parent)
        acento = T.color(rol)
        self.setStyleSheet(f"background:{T.BG2};border:1px solid {T.BORDE};"
                           f"border-left:4px solid {acento};border-radius:{T.RADIO}px;")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(T.SPACING_M)

        self._lbl = QLabel(_icons.etiqueta(concepto, mensaje) if concepto else str(mensaje))
        self._lbl.setStyleSheet(f"color:{acento};font-size:13px;font-weight:800;"
                                f"background:transparent;border:none;")
        self._lbl.setWordWrap(True)
        lay.addWidget(self._lbl, 1)

        self._btn = None
        if texto_accion:
            b = QPushButton(str(texto_accion))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"QPushButton{{background:{acento};color:{T.BG};border:none;"
                            f"border-radius:8px;font-weight:900;padding:6px 14px;}}"
                            f"QPushButton:hover{{background:{T.BG2};color:{acento};"
                            f"border:2px solid {acento};}}")
            b.clicked.connect(self.accion_pulsada.emit)
            lay.addWidget(b)
            self._btn = b

    def set_mensaje(self, mensaje):
        self._lbl.setText(str(mensaje))


# ── EnterpriseHelpTooltip — icono "?" con popover de ayuda en lenguaje claro ──
def _ensamblar_texto_ayuda(texto_o_partes) -> str:
    """Ensambla un dict tipo SOMA (`resumen`/`por_que`/`datos`/`ejemplo`/`consecuencias`) en un
    párrafo legible en lenguaje claro — mismo patrón de ensamblado que
    `soma/direccion/iniciativas.py::explicar` (por_qué/datos/consecuencias → texto), aquí generalizado
    como plantilla reutilizable por cualquier pantalla, no una llamada a esa función SOMA-específica.
    Una cadena plana se devuelve tal cual."""
    if isinstance(texto_o_partes, dict):
        partes = []
        if texto_o_partes.get("resumen"):
            partes.append(str(texto_o_partes["resumen"]))
        if texto_o_partes.get("por_que"):
            partes.append(f"¿Por qué? {texto_o_partes['por_que']}")
        datos = texto_o_partes.get("datos")
        if datos:
            if isinstance(datos, dict):
                datos = ", ".join(f"{k}: {v}" for k, v in datos.items())
            partes.append(f"Datos: {datos}.")
        if texto_o_partes.get("ejemplo"):
            partes.append(f"Ejemplo: {texto_o_partes['ejemplo']}")
        if texto_o_partes.get("consecuencias"):
            partes.append(f"Consecuencias: {texto_o_partes['consecuencias']}")
        return " ".join(partes) or "Sin información adicional."
    return str(texto_o_partes)


class _HelpPopover(QFrame):
    """Popover NO MODAL (`Qt.WindowType.Popup`): Qt lo cierra solo al pulsar fuera de él (o al perder
    el foco), sin bloquear el resto de la ventana — incluye además una 'X' explícita para cerrarlo
    sin depender de acertar el clic fuera (accesibilidad/teclado)."""

    def __init__(self, texto, *, titulo=None, parent=None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Sin esto, `close()` solo OCULTA el popup (no destruye el objeto C++) — el padre
        # (`EnterpriseHelpTooltip`) necesita la señal `destroyed` real para saber que ya no hay
        # popover abierto y permitir reabrirlo con un clic normal.
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFixedWidth(320)
        self.setStyleSheet(f"background:{T.BG2};border:2px solid {T.INFO};border-radius:{T.RADIO}px;")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 12)
        lay.setSpacing(6)

        cab = QHBoxLayout()
        lt = QLabel(titulo or "Ayuda")
        lt.setStyleSheet(f"color:{T.INFO};font-size:13px;font-weight:900;"
                         f"background:transparent;border:none;")
        cab.addWidget(lt, 1)
        btn_cerrar = QPushButton("✕")
        btn_cerrar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cerrar.setFixedSize(20, 20)
        btn_cerrar.setStyleSheet(
            f"QPushButton{{background:transparent;color:{T.DIM};border:none;font-weight:900;}}"
            f"QPushButton:hover{{color:{T.CRITICO};}}")
        btn_cerrar.clicked.connect(self.close)
        cab.addWidget(btn_cerrar)
        lay.addLayout(cab)

        lbl = QLabel(str(texto))
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color:{T.TEXT};font-size:12px;background:transparent;border:none;")
        lay.addWidget(lbl)

    def mostrar_en(self, punto_global):
        self.move(punto_global)
        self.show()


class EnterpriseHelpTooltip(QWidget):
    """Icono "?" pequeño (18-20px) que, al PULSARLO (no al pasar el ratón — interacción explícita y
    predecible, mismo criterio que el resto de la librería: nada se dispara solo por hover), muestra
    un popover NO MODAL (`_HelpPopover`) con una explicación en lenguaje claro, sin jerga. Mismo
    espíritu no-modal que `EnterpriseInlineBanner`: no bloquea el resto de la pantalla y se cierra
    solo (pulsar fuera) o con su 'X'.

    `texto_o_partes`: una cadena plana YA redactada, o un dict `{resumen, por_que, datos,
    ejemplo, consecuencias}` que se ensambla en un párrafo legible (`_ensamblar_texto_ayuda`) — pensado
    para reutilizarse en cualquier pantalla que necesite ayuda contextual (Calculadora Fiscal, SOMA,
    o cualquier futura), no solo el caso que lo originó."""

    def __init__(self, texto_o_partes, *, titulo=None, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        self._titulo = titulo
        self._texto = _ensamblar_texto_ayuda(texto_o_partes)
        self._popover = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._btn = QPushButton("?")
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setFixedSize(19, 19)
        self._btn.setStyleSheet(
            f"QPushButton{{background:{T.BG2};color:{T.INFO};border:1px solid {T.INFO};"
            f"border-radius:9px;font-weight:900;font-size:11px;padding:0;}}"
            f"QPushButton:hover{{background:{T.INFO};color:{T.BG};}}")
        self._btn.clicked.connect(self._alternar)
        lay.addWidget(self._btn)

    def _alternar(self):
        # `esta_abierto()` (no un simple `is not None`): un clic FUERA del popover lo oculta solo
        # (dismissal automático de `Qt.WindowType.Popup`) sin pasar por `_cerrar()`/`closeEvent` — la
        # referencia puede seguir viva pero OCULTA. Comprobar visibilidad real evita que un segundo
        # clic en "?" se interprete como "cerrar" cuando en realidad ya estaba cerrado.
        if self.esta_abierto():
            self._cerrar()
            return
        self._abrir()

    def _abrir(self):
        if self._popover is not None:
            # Referencia previa OCULTA (dismissal automático por clic fuera) que nunca pasó por
            # `closeEvent` — se cierra explícitamente para no dejarla viva sin motivo antes de crear
            # la nueva instancia.
            self._popover.close()
        self._popover = _HelpPopover(self._texto, titulo=self._titulo)
        self._popover.destroyed.connect(self._on_popover_destruido)
        punto = self._btn.mapToGlobal(self._btn.rect().bottomLeft())
        self._popover.mostrar_en(punto)

    def _on_popover_destruido(self, *_args):
        self._popover = None

    def _cerrar(self):
        if self._popover is not None:
            self._popover.close()

    def esta_abierto(self) -> bool:
        return self._popover is not None and self._popover.isVisible()

    def set_texto(self, texto_o_partes):
        self._texto = _ensamblar_texto_ayuda(texto_o_partes)
