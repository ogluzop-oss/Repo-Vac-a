"""
Alta del PRIMER perfil SUPERADMIN — pantalla de ONBOARDING (primera ejecución de la instalación).

Se muestra UNA vez, justo después de elegir el tipo de comercio (`SelectorEdicionWindow`) y solo si
la empresa activa todavía no tiene NINGÚN perfil de empleado registrado (instalación nueva). Los
perfiles con rol SUPERADMIN son los únicos que pueden dar de alta más perfiles de empleado
(`ConfiguracionWindow` → "Generar perfil empleado"), así que sin este paso una instalación nueva no
tendría forma de crear su primer usuario. Emite `cuenta_creada(nombre)` al terminar.

`db.usuario.crear_perfil` normalmente exige una sesión de administrador activa para dar de alta un
perfil — aquí no puede haber ninguna todavía. Tiene una excepción de arranque: se permite crear el
primer perfil SIN sesión activa únicamente si la empresa no tiene aún ningún perfil (deja de aplicar
en cuanto exista el primero), así que este flujo sigue pasando por la MISMA función y la MISMA
política de contraseñas que el resto de altas — no se crea un camino paralelo.
"""

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


def _input(placeholder="", *, password=False, max_length=None):
    e = QLineEdit()
    e.setPlaceholderText(placeholder)
    e.setFixedHeight(42)
    if password:
        e.setEchoMode(QLineEdit.EchoMode.Password)
    if max_length:
        e.setMaxLength(max_length)
    e.setStyleSheet(
        f"QLineEdit{{background:{_BG};color:#E6EDF3;border:2px solid {_BORDE};border-radius:9px;"
        f"padding:0 12px;font-family:'{_FONT}';font-size:14px;}}"
        f"QLineEdit:focus{{border-color:{_CIAN};}}")
    return e


class PrimerSuperadminWindow(QWidget):
    """Onboarding de alta del primer SUPERADMIN. Emite `cuenta_creada(nombre)` al terminar."""

    cuenta_creada = pyqtSignal(str)

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

        titulo = QLabel(tr("primer_admin.titulo", default="Crea tu primer perfil de administración"))
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        titulo.setWordWrap(True)
        titulo.setStyleSheet(f"color:{_CIAN};font-size:26px;font-weight:900;letter-spacing:1px;")
        root.addWidget(titulo)

        sub = QLabel(tr(
            "primer_admin.subtitulo",
            default="Este perfil tendrá el rol SUPERADMIN: es el único que puede dar de alta al resto "
            "de perfiles de empleado más adelante desde Configuración.",
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

        pl.addWidget(self._lbl_campo(tr("primer_admin.nombre", default="Nombre de usuario")))
        self.inp_nombre = _input(tr("primer_admin.nombre_ph", default="p. ej. ADMIN"))
        pl.addWidget(self.inp_nombre)

        pl.addWidget(self._lbl_campo(tr("primer_admin.password", default="PIN (4 dígitos)")))
        self.inp_password = _input(
            tr("primer_admin.password_ph", default="Código de 4 dígitos"),
            password=True, max_length=4,
        )
        pl.addWidget(self.inp_password)

        pl.addWidget(self._lbl_campo(tr("primer_admin.password2", default="Repetir PIN")))
        self.inp_password2 = _input(
            tr("primer_admin.password2_ph", default="Repite el PIN de 4 dígitos"),
            password=True, max_length=4,
        )
        pl.addWidget(self.inp_password2)

        self.lbl_error = QLabel("")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.setStyleSheet(f"color:{_ROJO};font-size:12px;font-weight:700;")
        self.lbl_error.hide()
        pl.addWidget(self.lbl_error)

        from src.gui.catalogo_gestion import _btn
        pl.addSpacing(6)
        self.btn_crear = _btn(
            tr("primer_admin.crear", default="CREAR CUENTA Y CONTINUAR"),
            self._crear,
            primary=True,
        )
        self.btn_crear.setFixedHeight(46)
        pl.addWidget(self.btn_crear)

        root.addWidget(panel, alignment=Qt.AlignmentFlag.AlignCenter)
        root.addStretch(2)

        self.inp_password.returnPressed.connect(self._crear)
        self.inp_password2.returnPressed.connect(self._crear)

    def _lbl_campo(self, texto):
        lb = QLabel(texto)
        lb.setStyleSheet(f"color:#E6EDF3;font-size:12px;font-weight:700;")
        return lb

    def _error(self, msg):
        self.lbl_error.setText(msg)
        self.lbl_error.show()

    def _crear(self):
        self.lbl_error.hide()
        nombre = self.inp_nombre.text().strip()
        pw1 = self.inp_password.text()
        pw2 = self.inp_password2.text()
        if not nombre:
            self._error(tr("primer_admin.err_nombre", default="Indica un nombre de usuario."))
            return
        if pw1 != pw2:
            self._error(tr("primer_admin.err_no_coincide", default="Las contraseñas no coinciden."))
            return
        from src.seguridad import politica
        ok_pol, motivo = politica.validar_pin(pw1)
        if not ok_pol:
            self._error(motivo)
            return
        from src.db.usuario import crear_perfil
        self.btn_crear.setEnabled(False)
        try:
            ok = crear_perfil(nombre, pw1, perfil_tipo="SUPERADMIN")
        finally:
            self.btn_crear.setEnabled(True)
        if not ok:
            self._error(tr(
                "primer_admin.err_creacion",
                default="No se pudo crear la cuenta. Puede que el nombre ya esté en uso.",
            ))
            return
        self.cuenta_creada.emit(nombre.strip().upper())
