"""
Badges de notificación por PESTAÑA (círculo rojo, número blanco) — extiende a nivel de pestaña/sección
el mismo criterio ya usado en el menú principal para las tarjetas de módulo
(`gui/menu_principal.py::MenuCardButton.set_badge`, Fase 3 del Centro de Actividad): el número se
CALCULA al vuelo desde `services.actividad.badges` (motor de eventos), nunca se almacena aquí.

Sin precedente previo en la app (no existe ninguna subclase de `QTabBar` ni un `paintEvent` que
dibuje un badge sobre una pestaña) — se construye aquí por primera vez, reutilizando la MISMA paleta/
técnica que `MenuCardButton` (un `QLabel` hijo posicionado con `move()`).

Dos variantes, según cómo navegue cada ventana (auditado: bastantes módulos usan un sidebar de
botones + `QStackedWidget` en vez de un `QTabWidget` real):
- `instalar_badges` — sobre un `QTabWidget` real, posicionando cada badge sobre el `tabRect()`.
- `instalar_badges_sidebar` — sobre una lista de botones de un sidebar (cada botón es su propio
  padre del badge, igual que `MenuCardButton`), para las ventanas con navegación de botón+`QStackedWidget`.
"""

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtWidgets import QLabel, QTabWidget, QWidget

_COLOR_BADGE = "#FF3B30"
_COLOR_TEXTO = "#FFFFFF"


class GestorBadgesPestanas(QObject):
    """Gestiona un `QLabel`-badge por índice de pestaña de un `QTabWidget`, reposicionándolos sobre
    el `tabRect()` real de cada pestaña. `obtener_counts()` debe devolver `{indice: n}`;
    `al_entrar(indice)` (opcional) se invoca al cambiar a esa pestaña, para que el llamador marque
    esa pestaña como vista (`services.actividad.badges.marcar_visto`) y refresque.

    Hereda de `QObject` (no un objeto Python plano): `installEventFilter(self)` exige un `QObject`
    real — sin esto, PyQt6 rechaza la instalación del filtro con `TypeError` en el propio
    constructor, tumbando cualquier ventana que instale badges (bug real detectado al cablear la
    variante sidebar en RRHH/Reposición: sin esta herencia, `QTabWidget.tabBar().installEventFilter`
    y `QWidget.installEventFilter` fallan igual en ambas variantes)."""

    def __init__(self, tabs: QTabWidget, obtener_counts, al_entrar=None, color_fondo="#0D1117"):
        super().__init__(tabs)
        self.tabs = tabs
        self._obtener_counts = obtener_counts
        self._al_entrar = al_entrar
        self._color_fondo = color_fondo
        self._labels = {}
        tabs.currentChanged.connect(self._on_cambio)
        tabs.tabBar().installEventFilter(self)
        self.refrescar()

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.Resize, QEvent.Type.LayoutRequest, QEvent.Type.Show):
            self._reposicionar()
        return False

    def _on_cambio(self, indice):
        if self._al_entrar and indice >= 0:
            try:
                self._al_entrar(indice)
            except Exception:
                pass
        self._reposicionar()

    def refrescar(self):
        """Recalcula los contadores (llama a `obtener_counts`) y repinta los badges."""
        try:
            counts = self._obtener_counts() or {}
        except Exception:
            counts = {}
        for i in range(self.tabs.count()):
            n = 0
            try:
                n = int(counts.get(i, 0) or 0)
            except (TypeError, ValueError):
                n = 0
            lbl = self._label_de(i)
            if n <= 0:
                lbl.hide()
                continue
            txt = "99+" if n > 99 else str(n)
            w = 22 if len(txt) <= 2 else 30
            lbl.setText(txt)
            lbl.setFixedSize(w, 22)
            lbl.show()
            lbl.raise_()
        self._reposicionar()

    def _label_de(self, indice):
        lbl = self._labels.get(indice)
        if lbl is None:
            lbl = QLabel("", self.tabs.tabBar())
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                f"background-color:{_COLOR_BADGE};color:{_COLOR_TEXTO};"
                f"border:2px solid {self._color_fondo};border-radius:11px;"
                "font-family:'Segoe UI';font-weight:900;font-size:11px;")
            lbl.hide()
            self._labels[indice] = lbl
        return lbl

    def _reposicionar(self):
        bar = self.tabs.tabBar()
        for i, lbl in self._labels.items():
            if not lbl.isVisible() or i >= self.tabs.count():
                continue
            rect = bar.tabRect(i)
            lbl.move(rect.right() - lbl.width() - 4, rect.top() + 2)


def instalar_badges(tabs: QTabWidget, obtener_counts, al_entrar=None,
                    color_fondo="#0D1117") -> GestorBadgesPestanas:
    """Instala badges de notificación (círculo rojo + nº blanco) en la esquina superior derecha de
    cada pestaña de `tabs`. `obtener_counts()` -> `{indice_pestaña: n}`. `al_entrar(indice)` opcional,
    se invoca al cambiar a esa pestaña (para marcar-como-visto). Devuelve el gestor; llamar a
    `.refrescar()` para repintar tras recalcular los contadores (p. ej. en un timer periódico o al
    volver a mostrar la ventana)."""
    return GestorBadgesPestanas(tabs, obtener_counts, al_entrar, color_fondo)


class GestorBadgesSidebar(QObject):
    """Igual que `GestorBadgesPestanas`, pero para una lista de BOTONES de un sidebar (patrón
    botón+`QStackedWidget`, sin `QTabWidget`): cada badge se parenta directamente al botón
    correspondiente (misma técnica que `MenuCardButton._badge`), no a una `tabBar` compartida.

    Hereda de `QObject` por el mismo motivo que `GestorBadgesPestanas`: `btn.installEventFilter(self)`
    exige un `QObject` real (sin ello, `TypeError` en el propio constructor)."""

    def __init__(self, botones: list[QWidget], obtener_counts, al_entrar=None, color_fondo="#0D1117"):
        super().__init__(botones[0] if botones else None)
        self.botones = list(botones)
        self._obtener_counts = obtener_counts
        self._al_entrar = al_entrar
        self._color_fondo = color_fondo
        self._labels = {}
        for i, btn in enumerate(self.botones):
            btn.installEventFilter(self)
            if al_entrar is not None:
                btn.clicked.connect(lambda checked=False, idx=i: self._on_click(idx))
        self.refrescar()

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self._reposicionar()
        return False

    def _on_click(self, indice):
        try:
            self._al_entrar(indice)
        except Exception:
            pass
        self._reposicionar()

    def refrescar(self):
        """Recalcula los contadores (llama a `obtener_counts`) y repinta los badges."""
        try:
            counts = self._obtener_counts() or {}
        except Exception:
            counts = {}
        for i, btn in enumerate(self.botones):
            n = 0
            try:
                n = int(counts.get(i, 0) or 0)
            except (TypeError, ValueError):
                n = 0
            lbl = self._label_de(i, btn)
            if n <= 0:
                lbl.hide()
                continue
            txt = "99+" if n > 99 else str(n)
            w = 22 if len(txt) <= 2 else 30
            lbl.setFixedSize(w, 22)
            lbl.setText(txt)
            lbl.show()
            lbl.raise_()
        self._reposicionar()

    def _label_de(self, indice, boton):
        lbl = self._labels.get(indice)
        if lbl is None:
            lbl = QLabel("", boton)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                f"background-color:{_COLOR_BADGE};color:{_COLOR_TEXTO};"
                f"border:2px solid {self._color_fondo};border-radius:11px;"
                "font-family:'Segoe UI';font-weight:900;font-size:11px;")
            lbl.hide()
            self._labels[indice] = lbl
        return lbl

    def _reposicionar(self):
        for i, lbl in self._labels.items():
            if not lbl.isVisible() or i >= len(self.botones):
                continue
            btn = self.botones[i]
            lbl.move(btn.width() - lbl.width() - 4, 4)


def instalar_badges_sidebar(botones: list[QWidget], obtener_counts, al_entrar=None,
                            color_fondo="#0D1117") -> GestorBadgesSidebar:
    """Instala badges de notificación (círculo rojo + nº blanco) en la esquina superior derecha de
    cada botón de un sidebar. `obtener_counts()` -> `{indice_boton: n}` (el índice corresponde a la
    posición del botón en la lista `botones`). `al_entrar(indice)` opcional, se invoca al pulsar ese
    botón (para marcar-como-visto) — se conecta ADEMÁS del `clicked` que ya tenga el botón, sin
    sustituirlo. Devuelve el gestor; llamar a `.refrescar()` para repintar tras recalcular los
    contadores (p. ej. en un timer periódico o al volver a mostrar la ventana)."""
    return GestorBadgesSidebar(botones, obtener_counts, al_entrar, color_fondo)
