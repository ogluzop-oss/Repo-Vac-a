"""
Sugerencias de artículos — autocompletado reutilizable para CUALQUIER barra de búsqueda de
artículos de la app (código o nombre). El patrón (QCompleter + QStringListModel +
estilizar_completer + precarga desde `db.articulos.listar_codigo_nombre`) estaba duplicado ~4 veces
solo dentro de `info_articulo.py`; al extenderlo a todas las barras de búsqueda de artículo de la
app, se centraliza aquí — UNA sola implementación (regla de CLAUDE.md: "un solo motor", nada de
copiar el mismo boilerplate en cada pantalla).

Uso (código) — se AÑADE junto a cualquier QLineEdit existente, sin tocar su lógica de búsqueda
(`textChanged`/`returnPressed`/botón de búsqueda quedan intactos):

    from src.gui.components.completer_articulos import instalar_sugerencias_articulo
    self.completer = instalar_sugerencias_articulo(self.search_bar)

Vive en `gui/components/` (mismo criterio que `remote_scan.py`: widget/comportamiento compartido
NUEVO va aquí, no copiado en cada pantalla ni en `catalogo_gestion.py`).
"""

import logging

from PyQt6.QtCore import QPointF, QStringListModel, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

try:
    from assets.estilo_global import (COLOR_CIAN, COLOR_FONDO_APP, COLOR_FONDO_WIDGET,
                                      _blindar_tamano_fijo, estilizar_completer)
except Exception:  # pragma: no cover
    estilizar_completer = None
    _blindar_tamano_fijo = None
    COLOR_CIAN = "#00FFC6"
    COLOR_FONDO_APP = "#0E1117"
    COLOR_FONDO_WIDGET = "#161B22"

logger = logging.getLogger("gui.completer_articulos")

_EDICIONES_CON_FILTROS = ("RETAIL", "TEXTIL", "SUPERMARKET")


def datos_sugerencias_articulo() -> list:
    """Sugerencias en formato único 'CÓDIGO – NOMBRE' (sin duplicar código y nombre), para el
    tenant activo (el filtrado por empresa ya lo hace `listar_codigo_nombre` internamente)."""
    try:
        from src.db.articulos import listar_codigo_nombre
    except Exception as e:  # pragma: no cover
        logger.error("datos_sugerencias_articulo: %s", e)
        return []
    data = []
    try:
        filas = listar_codigo_nombre()
    except Exception as e:  # pragma: no cover
        logger.error("datos_sugerencias_articulo: %s", e)
        return []
    for cod, nom in filas:
        cod = str(cod or "").strip()
        nom = str(nom or "").strip()
        if cod or nom:
            data.append(f"{cod} – {nom}".strip(" –"))
    return data


def instalar_sugerencias_articulo(line_edit: QLineEdit) -> QCompleter:
    """Instala en `line_edit` el autocompletado estándar de artículos (código o nombre): case
    insensitive, `MatchContains`, estilizado vía `estilizar_completer` y precargado de inmediato
    desde `listar_codigo_nombre()`. Incluye el mismo reintento defensivo que ya tenía
    `info_articulo.py` (`_update_suggestions`): si la precarga llegó vacía (p. ej. la BD aún no
    estaba lista al construirse la ventana), se reintenta la primera vez que el usuario escribe.

    Devuelve el `QCompleter` ya instalado — su modelo es accesible vía `completer.model()`, o usa
    `refrescar_sugerencias_articulo(completer)` para forzar una recarga explícita (p. ej. tras dar
    de alta un artículo nuevo desde la misma pantalla)."""
    completer = QCompleter()
    model = QStringListModel()
    completer.setModel(model)
    completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    completer.setFilterMode(Qt.MatchFlag.MatchContains)
    line_edit.setCompleter(completer)
    if estilizar_completer:
        estilizar_completer(completer)
    model.setStringList(datos_sugerencias_articulo())  # precarga: sugerencias inmediatas

    def _refrescar_si_vacio(texto=""):
        if len(texto) >= 1 and not model.stringList():
            model.setStringList(datos_sugerencias_articulo())

    line_edit.textChanged.connect(_refrescar_si_vacio)
    return completer


def refrescar_sugerencias_articulo(completer: QCompleter) -> None:
    """Fuerza una recarga de las sugerencias de un completer ya instalado por
    `instalar_sugerencias_articulo` (p. ej. tras crear/editar un artículo en la misma pantalla)."""
    model = completer.model()
    if isinstance(model, QStringListModel):
        model.setStringList(datos_sugerencias_articulo())


# ============================================================
# BLOQUE FILTROS DE BÚSQUEDA DE ARTÍCULOS (talla/color/precio/género)
# ============================================================
# SOLO para las ediciones Retail/Textil/Supermarket (petición explícita) — en el resto de
# ediciones (Pharmacy/Bakery) esta función no aparece: `crear_boton_filtros_articulo` devuelve
# None y el llamador simplemente no añade nada a su layout (ni rompe nada si no comprueba el
# resultado, ya que None no se puede añadir a un QLayout y cada llamador ya hace `if boton:`).

def edicion_admite_filtros_articulo() -> bool:
    try:
        from src.services import verticales
        return verticales.vertical_actual() in _EDICIONES_CON_FILTROS
    except Exception as e:
        logger.debug("edicion_admite_filtros_articulo: %s", e)
        return False


class _BotonCerrarX(QPushButton):
    """Botón circular rojo "✕" con el aspa pintada A MANO (centrado por geometría pura) — mismo
    criterio que `gui/tpv.py::_BotonCerrarX`, copiado aquí (no importado) para no acoplar este
    componente ligero y muy reutilizado al módulo gigante del TPV."""

    def __init__(self, size: int = 30, parent=None):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"QPushButton{{background:transparent;border:none;border-radius:{size // 2}px;"
            "padding:0;}}"
            "QPushButton:hover{background:#F85149;}")
        # SIN esto, un layout/contenedor padre con su propio padding/stretch puede estirar el botón
        # más allá de `size x size` (se veía como una "píldora" roja ancha en vez de un círculo —
        # el bug real reportado: el hover ya no era circular y se comía el título de al lado).
        if _blindar_tamano_fijo:
            _blindar_tamano_fijo(self, size, size)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor("#0D1117") if self.underMouse() else QColor("#F85149")
        pen = QPen(color)
        pen.setWidthF(max(1.6, self._size * 0.07))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        m = self._size * 0.3
        n = self._size - m
        p.drawLine(QPointF(m, m), QPointF(n, n))
        p.drawLine(QPointF(n, m), QPointF(m, n))
        p.end()


class _IconoFiltros(QPushButton):
    """Icono de filtros (3 líneas horizontales con un "nodo" circular en cada una, a distinta
    posición) pintado a mano — mismo diseño que el icono de referencia, en turquesa."""

    def __init__(self, size: int = 40, parent=None):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Filtros de búsqueda (talla, color, precio, género)")
        self.setStyleSheet(
            f"QPushButton{{background:{COLOR_FONDO_WIDGET};border:2px solid {COLOR_CIAN};"
            "border-radius:10px;padding:0;}}"
            f"QPushButton:hover{{background:{COLOR_CIAN};}}")
        if _blindar_tamano_fijo:
            _blindar_tamano_fijo(self, size, size)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor("#0D1117") if self.underMouse() else QColor(COLOR_CIAN)
        s = self._size
        pen = QPen(color)
        pen.setWidthF(max(1.4, s * 0.045))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        margen = s * 0.22
        x0, x1 = margen, s - margen
        ys = (s * 0.32, s * 0.5, s * 0.68)
        nodos = (s * 0.62, s * 0.38, s * 0.55)  # posición del nodo en cada línea (distinta a propósito)
        radio = s * 0.07
        for y, nx in zip(ys, nodos, strict=False):
            p.drawLine(QPointF(x0, y), QPointF(x1, y))
            p.setBrush(color)
            p.drawEllipse(QPointF(nx, y), radio, radio)
            p.setBrush(Qt.BrushStyle.NoBrush)
        p.end()


class FiltrosArticuloDialog(QDialog):
    """Popup "Filtros": talla, color, rango de precio y género/segmento. Al aplicar, llama a
    `db.familias.buscar_articulos_con_filtros` y entrega la lista resultante al callback
    `on_resultados` del llamador — cada pantalla decide cómo mostrar esos resultados (tabla,
    lista, etc.), este diálogo no impone ninguna vista de resultados."""

    def __init__(self, on_resultados, texto_actual="", parent=None):
        super().__init__(parent)
        self._on_resultados = on_resultados
        self._texto_actual = texto_actual
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(380)
        self._drag_pos = None
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QFrame(); frame.setObjectName("filtrosArt")
        frame.setStyleSheet(
            f"QFrame#filtrosArt{{background:{COLOR_FONDO_APP};border:2px solid {COLOR_CIAN};"
            "border-radius:16px;}}")
        outer.addWidget(frame)
        v = QVBoxLayout(frame)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(12)

        cab = QHBoxLayout(); cab.setSpacing(8)
        titulo = QLabel("FILTROS DE BÚSQUEDA")
        titulo.setStyleSheet(f"color:{COLOR_CIAN};font-weight:900;font-size:15px;background:transparent;border:none;")
        titulo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        cab.addWidget(titulo, 1)
        btn_x = _BotonCerrarX(30)
        btn_x.clicked.connect(self.reject)
        cab.addWidget(btn_x, 0, Qt.AlignmentFlag.AlignTop)
        v.addLayout(cab)

        from src.db import familias as F
        try:
            tallas = F.tallas_disponibles()
            colores = F.colores_disponibles()
        except Exception:
            tallas, colores = [], []

        # Los títulos de cada campo (+2pt, 12→14) son el texto que se pidió agrandar; el contenido
        # de los propios desplegables/barras (combos/spinboxes) vuelve a su tamaño original (13px).
        _ss_lbl = "color:white;font-weight:700;font-size:14px;background:transparent;border:none;"
        _ss_combo = (
            f"QComboBox{{background:{COLOR_FONDO_WIDGET};color:white;border:2px solid {COLOR_CIAN};"
            "border-radius:8px;padding:6px 10px;font-size:13px;}}")
        _ss_spin = _ss_combo.replace("QComboBox", "QDoubleSpinBox")

        v.addWidget(QLabel("Talla", styleSheet=_ss_lbl))
        self.cmb_talla = QComboBox(); self.cmb_talla.setStyleSheet(_ss_combo)
        self.cmb_talla.addItem("(Todas)", None)
        for t in tallas:
            self.cmb_talla.addItem(str(t), t)
        v.addWidget(self.cmb_talla)

        v.addWidget(QLabel("Color", styleSheet=_ss_lbl))
        self.cmb_color = QComboBox(); self.cmb_color.setStyleSheet(_ss_combo)
        self.cmb_color.addItem("(Todos)", None)
        for c in colores:
            self.cmb_color.addItem(str(c), c)
        v.addWidget(self.cmb_color)

        v.addWidget(QLabel("Género / segmento", styleSheet=_ss_lbl))
        self.cmb_genero = QComboBox(); self.cmb_genero.setStyleSheet(_ss_combo)
        self.cmb_genero.addItem("(Todos)", None)
        for g, etiqueta in (("HOMBRE", "Hombre"), ("MUJER", "Mujer"),
                           ("NINO", "Niño"), ("NINA", "Niña"), ("UNISEX", "Unisex")):
            self.cmb_genero.addItem(etiqueta, g)
        v.addWidget(self.cmb_genero)

        v.addWidget(QLabel("Rango de precio", styleSheet=_ss_lbl))
        fila_precio = QHBoxLayout(); fila_precio.setSpacing(8)
        self.spin_precio_min = QDoubleSpinBox(); self.spin_precio_min.setStyleSheet(_ss_spin)
        self.spin_precio_min.setRange(0, 999999); self.spin_precio_min.setPrefix("mín. ")
        self.spin_precio_max = QDoubleSpinBox(); self.spin_precio_max.setStyleSheet(_ss_spin)
        self.spin_precio_max.setRange(0, 999999); self.spin_precio_max.setValue(999999)
        self.spin_precio_max.setPrefix("máx. ")
        fila_precio.addWidget(self.spin_precio_min)
        fila_precio.addWidget(self.spin_precio_max)
        v.addLayout(fila_precio)

        self.lbl_error = QLabel(""); self.lbl_error.setWordWrap(True)
        self.lbl_error.setStyleSheet("color:#F85149;font-weight:700;font-size:11px;background:transparent;border:none;")
        v.addWidget(self.lbl_error)

        botones = QHBoxLayout(); botones.setSpacing(12)
        btn_aplicar = QPushButton("Aplicar filtros")
        btn_aplicar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_aplicar.setStyleSheet(
            f"QPushButton{{background:#0D1117;color:{COLOR_CIAN};border:2px solid {COLOR_CIAN};"
            f"border-radius:8px;font-weight:900;padding:8px 14px;}}"
            f"QPushButton:hover{{background:{COLOR_CIAN};color:#0D1117;}}")
        btn_aplicar.clicked.connect(self._aplicar)
        botones.addStretch()
        botones.addWidget(btn_aplicar)
        v.addLayout(botones)

    def _aplicar(self):
        precio_min = self.spin_precio_min.value()
        precio_max = self.spin_precio_max.value()
        if precio_min > precio_max:
            self.lbl_error.setText("El precio mínimo no puede ser mayor que el máximo.")
            return
        try:
            from src.db import familias as F
            resultados = F.buscar_articulos_con_filtros(
                self._texto_actual, talla=self.cmb_talla.currentData(),
                color=self.cmb_color.currentData(),
                precio_min=precio_min or None,
                precio_max=precio_max if precio_max < 999999 else None,
                genero=self.cmb_genero.currentData())
        except Exception as e:
            logger.error("FiltrosArticuloDialog._aplicar: %s", e)
            self.lbl_error.setText("No se pudo aplicar el filtro. Inténtalo de nuevo.")
            return
        if self._on_resultados:
            self._on_resultados(resultados)
        self.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)


def crear_boton_filtros_articulo(parent, line_edit: QLineEdit, on_resultados) -> _IconoFiltros | None:
    """Botón de icono "filtros" (3 líneas con nodos, pintado a mano) que abre
    `FiltrosArticuloDialog` (talla/color/precio/género) — SOLO si la edición activa es
    Retail/Textil/Supermarket (`edicion_admite_filtros_articulo`); en cualquier otra edición
    devuelve `None` sin crear nada, para que el llamador lo añada a su layout con un simple
    `if boton: layout.addWidget(boton)` sin necesitar ninguna comprobación de edición propia.
    `on_resultados(lista_dicts | None)` se llama al aplicar."""
    if not edicion_admite_filtros_articulo():
        return None
    boton = _IconoFiltros(40, parent)

    def _abrir():
        dlg = FiltrosArticuloDialog(on_resultados, line_edit.text(), parent=parent)
        dlg.exec()
    boton.clicked.connect(_abrir)
    return boton


class _ResultadosFiltroDialog(QDialog):
    """Lista simple de resultados del popup "Filtros" cuando hay más de una coincidencia — doble
    clic (o "Elegir") para cargar ese artículo en la pantalla que abrió el filtro."""

    def __init__(self, resultados: list, on_elegido, parent=None):
        super().__init__(parent)
        self._on_elegido = on_elegido
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(420)
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        frame = QFrame(); frame.setObjectName("resFiltro")
        frame.setStyleSheet(
            f"QFrame#resFiltro{{background:{COLOR_FONDO_APP};border:2px solid {COLOR_CIAN};border-radius:16px;}}")
        outer.addWidget(frame)
        v = QVBoxLayout(frame); v.setContentsMargins(20, 16, 20, 16); v.setSpacing(10)
        v.addWidget(QLabel(f"🎚  {len(resultados)} resultados — elige uno",
                           styleSheet=f"color:{COLOR_CIAN};font-weight:900;font-size:14px;background:transparent;border:none;"))
        self._lista = QListWidget()
        self._lista.setStyleSheet(
            f"QListWidget{{background:{COLOR_FONDO_WIDGET};color:white;border:1px solid {COLOR_CIAN};"
            "border-radius:8px;padding:4px;}QListWidget::item{padding:8px;}"
            f"QListWidget::item:selected{{background:{COLOR_CIAN};color:#0D1117;}}")
        self._lista.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        for r in resultados:
            texto = f"{r.get('codigo')} — {r.get('nombre') or ''}"
            if r.get("precio") is not None:
                texto += f"  ({r.get('precio')})"
            item = QListWidgetItem(texto)
            item.setData(Qt.ItemDataRole.UserRole, r.get("codigo"))
            self._lista.addItem(item)
        self._lista.itemDoubleClicked.connect(self._elegir)
        v.addWidget(self._lista)
        bl = QHBoxLayout(); bl.setSpacing(10)
        b_cerrar = QPushButton("Cerrar")
        b_cerrar.setStyleSheet("QPushButton{background:#0D1117;color:#F85149;border:2px solid #F85149;"
                               "border-radius:8px;font-weight:900;padding:8px 14px;}")
        b_cerrar.clicked.connect(self.reject)
        b_elegir = QPushButton("Elegir")
        b_elegir.setStyleSheet(
            f"QPushButton{{background:#0D1117;color:{COLOR_CIAN};border:2px solid {COLOR_CIAN};"
            "border-radius:8px;font-weight:900;padding:8px 14px;}}")
        b_elegir.clicked.connect(self._elegir_seleccionado)
        bl.addWidget(b_cerrar); bl.addStretch(); bl.addWidget(b_elegir)
        v.addLayout(bl)

    def _elegir_seleccionado(self):
        item = self._lista.currentItem()
        if item:
            self._elegir(item)

    def _elegir(self, item):
        codigo = item.data(Qt.ItemDataRole.UserRole)
        self.accept()
        if self._on_elegido and codigo:
            self._on_elegido(codigo)


def manejar_resultados_filtro(parent, resultados, on_elegido, mostrar_mensaje_fn=None) -> None:
    """Patrón compartido de qué hacer con los resultados de `FiltrosArticuloDialog`: 0 → avisa que
    no hay coincidencias; 1 → carga ese artículo directamente; 2+ → lista para elegir. Cada
    pantalla pasa su propio `on_elegido(codigo)` (normalmente el mismo método que ya usa para
    renderizar el resultado de una búsqueda manual)."""
    if resultados is None:
        return  # "Limpiar filtros": no hay nada que mostrar
    if not resultados:
        if mostrar_mensaje_fn:
            mostrar_mensaje_fn("Sin resultados", "Ningún artículo coincide con esos filtros.", "info")
        return
    if len(resultados) == 1:
        on_elegido(resultados[0]["codigo"])
        return
    _ResultadosFiltroDialog(resultados, on_elegido, parent=parent).exec()
