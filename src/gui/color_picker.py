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

_CIAN = "#00FFC6"
_VERDE = "#3FB950"
_BG = "#0E1117"
_BG2 = "#161B22"
_TEXT = "#E6EDF3"
_BORDE = "#30363D"

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
QColorDialog QPushButton:default {{
    background: {_VERDE}; color: {_BG}; border: 2px solid {_VERDE};
}}
QColorDialog QPushButton:default:hover {{ background: #FFFFFF; color: {_BG}; border-color: #FFFFFF; }}
"""


def seleccionar_color(parent, inicial="#00FFC6", titulo="Selector de color"):
    """Abre el selector de color (frameless, legible). Devuelve el HEX (#RRGGBB) o None si se cancela."""
    dlg = QColorDialog(QColor(inicial), parent)
    dlg.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
    dlg.setWindowTitle(titulo)
    # Sin la barra de título negra de Windows: marco propio con borde neón.
    dlg.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
    dlg.setStyleSheet(_QSS)

    # Refuerzo directo sobre los botones Aceptar/Cancelar por si el estilo global los tapa: el botón por
    # defecto (Aceptar) verde con texto oscuro; el resto oscuro con texto claro. Garantiza texto visible.
    for bb in dlg.findChildren(QDialogButtonBox):
        for b in bb.buttons():
            if bb.buttonRole(b) in (QDialogButtonBox.ButtonRole.AcceptRole,):
                b.setStyleSheet(f"QPushButton{{background:{_VERDE};color:{_BG};border:2px solid {_VERDE};"
                                f"border-radius:8px;padding:6px 18px;font-family:'Segoe UI';"
                                f"font-weight:900;min-height:22px;min-width:96px;}}"
                                f"QPushButton:hover{{background:#FFFFFF;color:{_BG};border-color:#FFFFFF;}}")
            else:
                b.setStyleSheet(f"QPushButton{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
                                f"border-radius:8px;padding:6px 18px;font-family:'Segoe UI';"
                                f"font-weight:700;min-height:22px;min-width:96px;}}"
                                f"QPushButton:hover{{border-color:{_CIAN};color:{_CIAN};}}")

    if dlg.exec() and dlg.currentColor().isValid():
        return dlg.currentColor().name()
    return None
