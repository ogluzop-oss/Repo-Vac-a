"""
Configuración de la PASARELA DE PAGO (proveedor + credenciales + modo) — extraída de `gui/tpv.py`
(Fase 3 e-commerce, Catálogo Web) a un módulo NEUTRAL, autónomo, sin depender de `tpv.py` ni de
`canal_web_config.py`.

Por qué: la configuración de pagos (`db.pagos`, una fila por EMPRESA, no por canal) ya la
comparten TPV y Canal Web — `services.comercio_digital.pagos` ya llama a
`services.tpv.pagos.pasarela_para(config)` — pero el DIÁLOGO que la edita vivía solo dentro de
`gui/tpv.py`. Canal Web tiene su propio test de arquitectura (`test_web07_extraccion_canal_web.py
::test_canal_web_config_no_importa_tpv`) que prohíbe CUALQUIER import de `gui.tpv` para mantener
el desacoplamiento TPV↔Canal Web ya establecido (Fase WEB-07) — importar `_PasarelaConfigDialog`
desde `tpv.py` lo habría violado. La solución correcta no es un atajo: es sacar este diálogo
(genuinamente compartido por diseño) a un sitio neutral que ambos puedan importar sin acoplarse
entre sí. `tpv.py` mantiene `_PasarelaConfigDialog` como alias de compatibilidad (Strangler:
mismo nombre, mismo comportamiento, cero cambios para quien ya lo usaba)."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QComboBox, QDialog, QFrame, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QVBoxLayout)

from src.utils.i18n import tr

# ── Paleta / tipografía (copiadas — mismo criterio de autonomía que canal_web_config.py) ──
_BG = "#0E1117"
_BG2 = "#161B22"
_CIAN = "#00FFC6"
_VERDE = "#3FB950"
_BORDE = "#30363D"
_TEXT = "#E6EDF3"
_TEXT2 = "#8B949E"
_FONT = "Segoe UI"


def _lbl(text: str, bold: bool = False, size: int = 12, color: str = _TEXT) -> QLabel:
    lb = QLabel(text)
    lb.setStyleSheet(
        f"color:{color};font-family:'{_FONT}';font-size:{size}px;"
        f"font-weight:{'900' if bold else '500'};background:transparent;border:none;"
    )
    return lb


def _btn(text: str, color_bg: str = _BG2, color_fg: str = _TEXT, color_border: str = _BORDE,
        hover_bg: str = _CIAN, hover_fg: str = "#0D1117", h: int = 38, radius: int = 10) -> QPushButton:
    b = QPushButton(text)
    b.setFixedHeight(h)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setStyleSheet(
        f"QPushButton{{background:{color_bg};color:{color_fg};"
        f"border:2px solid {color_border};border-radius:{radius}px;"
        f"font-family:'{_FONT}';font-weight:900;font-size:13px;padding:0 12px;outline:0;}}"
        f"QPushButton:hover{{background:{hover_bg};color:{hover_fg};}}"
        f"QPushButton:focus{{outline:0;}}")
    return b


class PasarelaConfigDialog(QDialog):
    """Configuración de la pasarela de pago (proveedor + credenciales + modo)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(480)
        from src.db import pagos as _pg
        self._cfg = _pg.obtener_config()
        self._build()

    def _inp(self, val=""):
        e = QLineEdit(val or "")
        e.setFixedHeight(36)
        e.setStyleSheet(
            f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:0 10px;font-size:12px;font-family:'{_FONT}';}}"
            f"QLineEdit:focus{{border-color:{_CIAN};}}")
        return e

    def _combo(self, opciones, actual):
        cb = QComboBox()
        cb.setFixedHeight(36)
        cb.setStyleSheet(
            f"QComboBox{{combobox-popup:0;background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:0 10px;font-size:12px;font-family:'{_FONT}';}}"
            f"QComboBox:hover,QComboBox:on{{border-color:{_CIAN};}}"
            f"QComboBox::drop-down{{border:none;width:22px;}}"
            f"QComboBox QAbstractItemView{{background:#0D1117;color:{_TEXT};border:2px solid {_CIAN};"
            f"border-radius:8px;selection-background-color:{_CIAN};selection-color:#0D1117;}}")
        for etq, val in opciones:
            cb.addItem(etq, val)
        i = cb.findData(actual)
        if i >= 0:
            cb.setCurrentIndex(i)
        cb.view().setMinimumWidth(260)   # el desplegable no corta los textos largos (p. ej. "(recomendado)")
        return cb

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        cuerpo = QFrame()
        cuerpo.setObjectName("pasto")
        cuerpo.setStyleSheet(f"QFrame#pasto{{background:{_BG};border:2px solid {_CIAN};border-radius:18px;}}")
        outer.addWidget(cuerpo)
        v = QVBoxLayout(cuerpo)
        v.setContentsMargins(24, 22, 24, 22)
        v.setSpacing(10)
        v.addWidget(_lbl("💳  " + tr("online.pas_title", default="PASARELA DE PAGO"),
                         bold=True, size=16, color=_CIAN))
        v.addWidget(_lbl(tr("online.pas_prov", default="Proveedor"), bold=True, size=12, color=_TEXT2))
        # El combo se construye desde el registro de pasarelas (extensible): añadir una pasarela
        # nueva la hace aparecer aquí sin tocar este diálogo.
        from src.services.tpv.pagos.registry import pasarelas_registradas, proveedor_por_defecto
        _rec = tr("online.pas_recomendado", default="recomendado")
        opciones = [(meta["etiqueta"] + (f"  ({_rec})" if meta["recomendada"] else ""), nombre)
                   for nombre, meta in pasarelas_registradas().items()]
        self.cmb = self._combo(opciones, self._cfg.get("proveedor") or proveedor_por_defecto())
        v.addWidget(self.cmb)
        v.addWidget(_lbl(tr("online.pas_key", default="API key / Client ID / Nº terminal"),
                         bold=True, size=12, color=_TEXT2))
        self.inp_key = self._inp(self._cfg.get("api_key"))
        v.addWidget(self.inp_key)
        v.addWidget(_lbl(tr("online.pas_secret", default="API secret / Client secret / Clave Redsys"),
                         bold=True, size=12, color=_TEXT2))
        self.inp_secret = self._inp(self._cfg.get("api_secret"))
        v.addWidget(self.inp_secret)
        v.addWidget(_lbl(tr("online.pas_com", default="Comercio / FUC (Redsys)"),
                         bold=True, size=12, color=_TEXT2))
        self.inp_com = self._inp(self._cfg.get("comercio"))
        v.addWidget(self.inp_com)
        v.addWidget(_lbl(tr("online.pas_whsecret", default="Webhook secret (confirmación automática del pago)"),
                         bold=True, size=12, color=_TEXT2))
        self.inp_whsecret = self._inp(self._cfg.get("webhook_secret"))
        v.addWidget(self.inp_whsecret)
        fila_m = QHBoxLayout()
        fila_m.setSpacing(10)
        colm = QVBoxLayout()
        colm.addWidget(_lbl(tr("online.pas_modo", default="Modo"), bold=True, size=12, color=_TEXT2))
        self.cmb_modo = self._combo([("Test", "test"), ("Live", "live")], self._cfg.get("modo", "test"))
        colm.addWidget(self.cmb_modo)
        fila_m.addLayout(colm)
        colc = QVBoxLayout()
        colc.addWidget(_lbl(tr("online.pas_moneda", default="Moneda"), bold=True, size=12, color=_TEXT2))
        self.inp_moneda = self._inp(self._cfg.get("moneda") or "EUR")
        colc.addWidget(self.inp_moneda)
        fila_m.addLayout(colc)
        v.addLayout(fila_m)
        v.addSpacing(4)
        fila = QHBoxLayout()
        fila.setSpacing(10)
        b_cancel = _btn(tr("online.cfg_cancel", default="CANCELAR"), h=44)
        b_cancel.clicked.connect(self.reject)
        b_ok = _btn(tr("online.cfg_save", default="Guardar"), color_bg=_BG2, color_fg=_VERDE,
                   color_border=_VERDE, hover_bg=_VERDE, hover_fg="#0D1117", h=44)
        b_ok.clicked.connect(self._guardar)
        fila.addWidget(b_cancel)
        fila.addWidget(b_ok)
        v.addLayout(fila)

    def _guardar(self):
        from src.db import pagos as _pg
        from src.gui.mfa_gui import step_up_sesion
        if not step_up_sesion("pagos.pasarela.configurar", self):
            return
        _pg.guardar_config(
            proveedor=self.cmb.currentData(), api_key=self.inp_key.text().strip(),
            api_secret=self.inp_secret.text().strip(), comercio=self.inp_com.text().strip(),
            modo=self.cmb_modo.currentData(), moneda=(self.inp_moneda.text().strip() or "EUR").upper(),
            webhook_secret=self.inp_whsecret.text().strip())
        self.accept()


# Alias de compatibilidad Strangler: `tpv.py` definía esta clase como `_PasarelaConfigDialog`
# (privada); se conserva el nombre para quien ya la importe así.
_PasarelaConfigDialog = PasarelaConfigDialog
