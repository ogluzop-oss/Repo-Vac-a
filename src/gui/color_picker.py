"""
Selector de color unificado (estilo Smart Manager).

Reutilizado por la configuración de colores (Smart Config) y por el asistente de Canal Web para elegir
el color corporativo sin tener que escribir el código HEX a mano. Frente al `QColorDialog` nativo:

  * Sin la barra de título negra de Windows (marco propio con borde neón turquesa).
  * Botones Aceptar / Cancelar SIEMPRE legibles (texto visible sobre el fondo) — el botón por defecto
    (Aceptar) se pinta en verde con texto oscuro; el resto en oscuro con borde/hover turquesa.

Devuelve el color elegido como cadena HEX (#RRGGBB) o None si el usuario cancela.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QColorDialog, QDialogButtonBox, QPushButton

from src.utils.i18n import tr

_CIAN = "#00FFC6"
_VERDE = "#3FB950"
_BG = "#0E1117"
_BG2 = "#161B22"
_TEXT = "#E6EDF3"
_BORDE = "#30363D"

# Verde/rojo "GUARDAR HORARIOS" (src/gui/horarios_gui.py): mismo diseño exacto (fondo oscuro +
# contorno de color + texto de color, hover = relleno de color) reutilizado aquí para Aceptar
# (verde) y Cancelar (mismo diseño, rojo estándar de la app — COLOR_ROJO_ERROR en
# assets/estilo_global.py, ya usado en todos los botones semanticRole="danger").
_ROJO_ERROR = "#F85149"

_QSS_ACEPTAR = """
QPushButton {
    background: #161B22; border: 2px solid #22C55E; border-radius: 10px;
    color: #22C55E;
    font-family: 'Segoe UI'; font-weight: bold; font-size: 13px;
    padding: 0 28px;
}
QPushButton:hover { background: #22C55E; color: #0E1117; border-color: #22C55E; }
"""

_QSS_CANCELAR = f"""
QPushButton {{
    background: #161B22; border: 2px solid {_ROJO_ERROR}; border-radius: 10px;
    color: {_ROJO_ERROR};
    font-family: 'Segoe UI'; font-weight: bold; font-size: 13px;
    padding: 0 28px;
}}
QPushButton:hover {{ background: {_ROJO_ERROR}; color: #0E1117; border-color: {_ROJO_ERROR}; }}
"""

# Turquesa estándar de la app (mismo patrón que `_neon_ui._btn()` / `canal_web_config._btn()` con
# color_fg=color_border=hover_bg=_CIAN): fondo oscuro + contorno turquesa, hover = relleno turquesa.
_QSS_TURQUESA = f"""
QPushButton {{
    background: {_BG2}; color: {_CIAN}; border: 2px solid {_CIAN}; border-radius: 10px;
    font-family: 'Segoe UI'; font-weight: 900; font-size: 13px; padding: 0 12px; outline: 0;
}}
QPushButton:hover {{ background: {_CIAN}; color: #0D1117; }}
QPushButton:focus {{ outline: 0; }}
"""

_QSS = f"""
QColorDialog {{ background: {_BG}; border: 2px solid {_CIAN}; border-radius: 12px; }}
QColorDialog QWidget {{ background: {_BG}; color: {_TEXT}; font-family: 'Segoe UI'; }}
QColorDialog QLabel {{ color: {_TEXT}; background: transparent; }}
QColorDialog QLineEdit, QColorDialog QSpinBox {{
    background: {_BG2}; color: {_TEXT}; border: 1px solid {_BORDE};
    border-radius: 6px; padding: 2px 6px;
}}
QColorDialog QPushButton {{
    background: {_BG2}; color: {_TEXT}; border: 2px solid {_BORDE};
    border-radius: 8px; padding: 6px 18px; font-family: 'Segoe UI';
    font-weight: 700; min-height: 22px; min-width: 96px;
}}
QColorDialog QPushButton:hover {{ border-color: {_CIAN}; color: {_CIAN}; }}
"""


def seleccionar_color(parent, inicial="#00FFC6", titulo="Selector de color"):
    """Abre el selector de color (frameless, legible). Devuelve el HEX (#RRGGBB) o None si se cancela.

    Usa el `QColorDialog` de Qt en modo NO nativo (`DontUseNativeDialog`) — así Qt dibuja su propio
    widget multiplataforma (en vez del picker nativo de Windows), que SÍ puede estilizarse por QSS y
    cuyos botones internos son localizables vía `findChildren(QPushButton)`. Se re-estiliza cada botón
    según su rol: Aceptar = diseño "GUARDAR HORARIOS" en verde, Cancelar = el mismo diseño en rojo
    (`COLOR_ROJO_ERROR` estándar de la app), "Pick Screen Color"/"Add to Custom Colors" = turquesa
    estándar de la app + traducidos al castellano (la UI de la app está en español).
    """
    dlg = QColorDialog(QColor(inicial), parent)
    dlg.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
    dlg.setWindowTitle(titulo)
    # Sin la barra de título negra de Windows: marco propio con borde neón.
    dlg.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
    dlg.setStyleSheet(_QSS)

    roles = {}
    for bb in dlg.findChildren(QDialogButtonBox):
        for b in bb.buttons():
            roles[b] = bb.buttonRole(b)

    for b in dlg.findChildren(QPushButton):
        rol = roles.get(b)
        texto = b.text().replace("&", "").strip()
        if rol == QDialogButtonBox.ButtonRole.AcceptRole:
            b.setStyleSheet(_QSS_ACEPTAR)
        elif rol == QDialogButtonBox.ButtonRole.RejectRole:
            b.setStyleSheet(_QSS_CANCELAR)
        elif texto == "Pick Screen Color":
            b.setText(tr("cfg.color_pick_screen", default="Seleccionar color de pantalla"))
            b.setStyleSheet(_QSS_TURQUESA)
        elif texto == "Add to Custom Colors":
            b.setText(tr("cfg.color_add_custom", default="Añadir a colores personalizados"))
            b.setStyleSheet(_QSS_TURQUESA)

    if dlg.exec() and dlg.currentColor().isValid():
        return dlg.currentColor().name()
    return None
