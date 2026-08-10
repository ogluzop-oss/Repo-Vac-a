"""
Autocompletado de destinatarios para campos de correo (capa GUI).

Consume EXCLUSIVAMENTE el Servicio Corporativo de Resolución de Destinatarios (punto único oficial):
al escribir en un `QLineEdit`, muestra un popup con sugerencias enriquecidas (nombre, correo,
etiqueta de tipo, aviso de estado, favorito/reciente) resueltas por `destinatarios.buscar_
destinatarios(...)`, con multiempresa y contexto de módulo. Al elegir, coloca el correo en el campo.

Reutilizable por cualquier pantalla que redacte correos (o, a futuro, otros canales). NO implementa
lógica de resolución: solo presenta lo que devuelve el servicio.
"""

import logging

from PyQt6.QtCore import QObject, QPoint, Qt, QTimer
from PyQt6.QtWidgets import QListWidget, QListWidgetItem

from src.services import destinatarios as _dest

logger = logging.getLogger("gui.destinatarios.autocomplete")

_SS_POPUP = (
    "QListWidget{background:#161B22;color:#E6EDF3;border:2px solid #00FFC6;border-radius:10px;"
    "font-family:'Segoe UI';font-size:13px;outline:none;padding:4px;}"
    "QListWidget::item{padding:7px 10px;border-radius:6px;}"
    "QListWidget::item:selected{background:rgba(0,255,198,0.18);color:#00FFC6;}"
    "QListWidget::item:hover{background:rgba(0,255,198,0.10);}"
)


def _empresa_actual():
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _usuario_actual():
    try:
        from src.db.usuario import sesion_global
        u = sesion_global.usuario_actual or {}
        return str(u.get("nombre") or u.get("usuario") or u.get("id") or "") or None
    except Exception:
        return None


class AutocompletadoDestinatarios(QObject):
    """Controlador que engancha un popup de sugerencias a un `QLineEdit`."""

    def __init__(self, line_edit, *, contexto=None, id_empresa_getter=None, limite=8, parent=None):
        super().__init__(parent or line_edit)
        self.le = line_edit
        self.contexto = contexto
        self._id_emp = id_empresa_getter or _empresa_actual
        self.limite = limite

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(180)   # debounce
        self._timer.timeout.connect(self._buscar)

        self.popup = QListWidget()
        self.popup.setWindowFlags(Qt.WindowType.Popup)
        self.popup.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.popup.setStyleSheet(_SS_POPUP)
        self.popup.setMouseTracking(True)
        self.popup.itemClicked.connect(self._elegir)

        self.le.textEdited.connect(self._on_text)
        self.le.installEventFilter(self)

    # ── Eventos del campo ────────────────────────────────────────────────────
    def eventFilter(self, obj, ev):
        if obj is self.le and ev.type() == ev.Type.FocusIn and not self.le.text().strip():
            self._timer.start()   # al enfocar vacío: muestra favoritos/recientes
        if obj is self.le and ev.type() == ev.Type.KeyPress and self.popup.isVisible():
            k = ev.key()
            if k in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                fila = self.popup.currentRow()
                fila += 1 if k == Qt.Key.Key_Down else -1
                self.popup.setCurrentRow(max(0, min(self.popup.count() - 1, fila)))
                return True
            if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                it = self.popup.currentItem() or (self.popup.item(0) if self.popup.count() else None)
                if it:
                    self._elegir(it)
                    return True
            if k == Qt.Key.Key_Escape:
                self.popup.hide()
                return True
        return super().eventFilter(obj, ev)

    def _on_text(self, _txt):
        self._timer.start()

    # ── Búsqueda + popup ─────────────────────────────────────────────────────
    def _buscar(self):
        texto = self.le.text().strip()
        # Si el usuario ya escribió un correo completo, no molestamos con sugerencias.
        if texto and "@" in texto and " " not in texto and texto.endswith((".com", ".es", ".org",
                                                                            ".net")):
            self.popup.hide()
            return
        try:
            res = _dest.buscar_destinatarios(self._id_emp(), texto, contexto=self.contexto,
                                             usuario=_usuario_actual(), limite=self.limite)
        except Exception as e:
            logger.debug("autocompletado buscar: %s", e)
            res = []
        if not res:
            self.popup.hide()
            return
        self.popup.clear()
        for d in res:
            self.popup.addItem(self._item(d))
        self.popup.setCurrentRow(0)
        self._posicionar()
        self.popup.show()

    def _item(self, d) -> QListWidgetItem:
        marca = "★ " if d.favorito else ("🕘 " if (d.reciente and not d.favorito) else "")
        nombre = d.nombre_mostrado or d.correo
        texto = f"{marca}{nombre}  ·  {d.correo}   [{d.etiqueta}]"
        if d.avisos:
            texto += "   ⚠ " + "; ".join(d.avisos)
        it = QListWidgetItem(texto)
        it.setData(Qt.ItemDataRole.UserRole, d)
        if d.avisos:
            from PyQt6.QtGui import QColor
            it.setForeground(QColor("#F0A050"))   # ámbar: hay aviso (no impide enviar)
        return it

    def _posicionar(self):
        pos = self.le.mapToGlobal(QPoint(0, self.le.height() + 2))
        self.popup.setGeometry(pos.x(), pos.y(), max(self.le.width(), 320),
                               min(self.popup.count(), 8) * 40 + 10)

    def _elegir(self, item):
        d = item.data(Qt.ItemDataRole.UserRole)
        if d is not None:
            self.le.setText(d.correo)
        self.popup.hide()
        self.le.setFocus()


def instalar_autocompletado(line_edit, *, contexto=None, id_empresa_getter=None, limite=8):
    """Instala el autocompletado de destinatarios en un `QLineEdit` y devuelve el controlador
    (mantener una referencia mientras viva el campo). `contexto` = módulo desde el que se redacta
    (prioriza fuentes afines)."""
    return AutocompletadoDestinatarios(line_edit, contexto=contexto,
                                       id_empresa_getter=id_empresa_getter, limite=limite)
