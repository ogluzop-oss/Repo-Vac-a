"""
Activación de la instalación contra el servidor CENTRAL de licencias (Fase 3, ver plan
`hazy-riding-aurora`) — pantalla de ONBOARDING, se muestra justo después de crear el primer
perfil SUPERADMIN (`gui/primer_superadmin_wizard.py`) y SOLO si hay un servidor central
configurado (`SMART_MANAGER_LICENCIA_URL`) y esta instalación todavía no está activada
(`services.licencia_central.identidad.activado()`). Sin esa variable de entorno, esta pantalla ni
siquiera se construye — instalaciones sin licenciamiento central (legacy) no ven nada nuevo.

Toda la lógica vive en `services.licencia_central.cliente.activar` (llamada HTTP real al servidor
central, ya verificada de extremo a extremo) — esta GUI solo la orquesta. Emite `activada()` al
terminar, tanto si se activó con éxito como si el usuario decide omitir el paso (se puede activar
más adelante desde Configuración — no bloquea el arranque de la app)."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QLineEdit, QVBoxLayout, QWidget

from src.utils.i18n import tr

_BG = "#0E1117"
_BG2 = "#161B22"
_CIAN = "#00FFC6"
_BORDE = "#30363D"
_DIM = "#8B949E"
_ROJO = "#FF5C70"
_FONT = "Segoe UI"


def _input(placeholder=""):
    e = QLineEdit()
    e.setPlaceholderText(placeholder)
    e.setFixedHeight(42)
    e.setStyleSheet(
        f"QLineEdit{{background:{_BG};color:#E6EDF3;border:2px solid {_BORDE};border-radius:9px;"
        f"padding:0 12px;font-family:'{_FONT}';font-size:14px;}}"
        f"QLineEdit:focus{{border-color:{_CIAN};}}")
    return e


class ActivacionLicenciaWindow(QWidget):
    """Onboarding de activación de licencia. Emite `activada()` al terminar (con o sin éxito —
    ver `_omitir`), nunca bloquea el arranque de la app."""

    activada = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel_raiz")
        self.setStyleSheet(f"background:{_BG};")
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(48, 40, 48, 40)
        root.setSpacing(14)
        root.addStretch(1)

        titulo = QLabel(tr("activacion.titulo", default="Activa tu licencia"))
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        titulo.setWordWrap(True)
        titulo.setStyleSheet(f"color:{_CIAN};font-size:26px;font-weight:900;letter-spacing:1px;")
        root.addWidget(titulo)

        sub = QLabel(tr(
            "activacion.subtitulo",
            default="Introduce el código de activación que recibiste al contratar Smart Manager. "
            "Puedes omitir este paso ahora y activarla más tarde desde Configuración.",
        ))
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color:{_DIM};font-size:13px;")
        sub.setMaximumWidth(520)
        root.addWidget(sub, alignment=Qt.AlignmentFlag.AlignCenter)
        root.addSpacing(18)

        panel = QWidget()
        panel.setObjectName("panel_form")
        panel.setStyleSheet(
            f"QWidget#panel_form{{background:{_BG2};border:1px solid {_BORDE};border-radius:16px;}}"
        )
        panel.setFixedWidth(420)
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(28, 26, 28, 26)
        pl.setSpacing(12)

        pl.addWidget(self._lbl_campo(tr("activacion.codigo", default="Código de activación")))
        self.inp_codigo = _input(tr("activacion.codigo_ph", default="p. ej. SM-XXXX-XXXX-XXXX"))
        pl.addWidget(self.inp_codigo)

        pl.addWidget(self._lbl_campo(tr("activacion.empresa", default="Nombre de la empresa")))
        self.inp_empresa = _input(tr("activacion.empresa_ph", default="Razón social"))
        pl.addWidget(self.inp_empresa)

        self.lbl_error = QLabel("")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.setStyleSheet(f"color:{_ROJO};font-size:12px;font-weight:700;")
        self.lbl_error.hide()
        pl.addWidget(self.lbl_error)

        from src.gui.catalogo_gestion import _btn
        pl.addSpacing(6)
        self.btn_activar = _btn(
            tr("activacion.activar", default="ACTIVAR"),
            self._activar,
            primary=True,
        )
        self.btn_activar.setFixedHeight(46)
        pl.addWidget(self.btn_activar)

        self.btn_omitir = _btn(
            tr("activacion.omitir", default="Omitir por ahora"),
            self._omitir,
        )
        self.btn_omitir.setFixedHeight(38)
        pl.addWidget(self.btn_omitir)

        root.addWidget(panel, alignment=Qt.AlignmentFlag.AlignCenter)
        root.addStretch(2)

        self.inp_empresa.returnPressed.connect(self._activar)

    def _lbl_campo(self, texto):
        lb = QLabel(texto)
        lb.setStyleSheet("color:#E6EDF3;font-size:12px;font-weight:700;")
        return lb

    def _error(self, msg):
        self.lbl_error.setText(msg)
        self.lbl_error.show()

    def _omitir(self):
        self.activada.emit()

    def _activar(self):
        self.lbl_error.hide()
        codigo = self.inp_codigo.text().strip()
        empresa = self.inp_empresa.text().strip()
        if not codigo or not empresa:
            self._error(tr("activacion.err_datos", default="Indica el código de activación y el nombre de la empresa."))
            return
        from src.services.licencia_central import cliente
        self.btn_activar.setEnabled(False)
        self.btn_omitir.setEnabled(False)
        try:
            r = cliente.activar(codigo, empresa)
        finally:
            self.btn_activar.setEnabled(True)
            self.btn_omitir.setEnabled(True)
        if not r.get("ok"):
            self._error(r.get("error") or tr("activacion.err_generico", default="No se pudo activar la licencia."))
            return
        self.activada.emit()
