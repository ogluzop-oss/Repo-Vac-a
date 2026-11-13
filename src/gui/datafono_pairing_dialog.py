"""
Asistente de EMPAREJAMIENTO del datáfono físico (cobro real con tarjeta en TPV/autocobro) —
petición explícita: que cada tienda pueda emparejar su terminal "en pocos minutos, sin
conocimientos informáticos". Mismo criterio neutral/autónomo que `pasarela_config_dialog.py` (no
depende de `gui.tpv` ni de `gui.autocobro`, para que ambos puedan abrirlo sin acoplarse entre sí).

Flujo (todos los pasos dentro de un único diálogo):
  1. Elegir proveedor (registro extensible, `services.tpv.datafono.registry`) + introducir las
     credenciales de SU cuenta de comercio (API key/secret, obtenidas del panel de ese proveedor —
     paso inevitablemente manual: hay que tener la cuenta dada de alta con ellos). Si el banco no
     es ninguno de los ya integrados, "Otro banco (adaptador personalizado)" permite pegar la
     FORMA de su API en un JSON (ver `services.tpv.datafono.generico`) — sin tocar código.
  2. «Probar conexión» (opcional pero recomendado): verifica credenciales/alcance SIN depender de
     que haya terminales — muestra el motivo REAL de un fallo (código HTTP + respuesta del banco),
     para no descubrirlo luego cobrando en caja.
  3. «Buscar terminales»: la app llama a la API del proveedor y lista los terminales YA
     emparejados a esa cuenta (el terminal físico se empareja a la cuenta desde SU PROPIA
     pantalla/app, como cualquier datáfono moderno — eso no lo hace este asistente) — la tienda
     ELIGE el suyo de la lista, o lo escribe a mano si el banco no publica un listado.
  4. «Guardar»: persiste la config (credenciales cifradas) para la tienda ACTIVA de la sesión.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QApplication, QComboBox, QDialog, QFrame, QHBoxLayout, QLabel,
                             QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout)

from src.utils.i18n import tr

_BG = "#0E1117"
_BG2 = "#161B22"
_CIAN = "#00FFC6"
_VERDE = "#3FB950"
_ROJO = "#F85149"
_BORDE = "#30363D"
_TEXT = "#E6EDF3"
_TEXT2 = "#8B949E"
_FONT = "Segoe UI"


def _lbl(text: str, bold: bool = False, size: int = 12, color: str = _TEXT) -> QLabel:
    lb = QLabel(text)
    lb.setStyleSheet(
        f"color:{color};font-family:'{_FONT}';font-size:{size}px;"
        f"font-weight:{'900' if bold else '500'};background:transparent;border:none;")
    lb.setWordWrap(True)
    return lb


def _btn(text: str, color_bg: str = _BG2, color_fg: str = _TEXT, color_border: str = _BORDE,
        hover_bg: str = _CIAN, hover_fg: str = "#0D1117", h: int = 40) -> QPushButton:
    b = QPushButton(text)
    b.setFixedHeight(h)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setStyleSheet(
        f"QPushButton{{background:{color_bg};color:{color_fg};border:2px solid {color_border};"
        f"border-radius:10px;font-family:'{_FONT}';font-weight:900;font-size:13px;padding:0 14px;}}"
        f"QPushButton:hover:enabled{{background:{hover_bg};color:{hover_fg};}}"
        f"QPushButton:disabled{{color:{_TEXT2};border-color:{_BORDE};}}")
    return b


def _inp(val: str = "") -> QLineEdit:
    e = QLineEdit(val or "")
    e.setFixedHeight(36)
    e.setStyleSheet(
        f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};border-radius:8px;"
        f"padding:0 10px;font-size:12px;font-family:'{_FONT}';}}"
        f"QLineEdit:focus{{border-color:{_CIAN};}}")
    return e


def _combo(opciones, actual=None) -> QComboBox:
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
    if actual is not None:
        i = cb.findData(actual)
        if i >= 0:
            cb.setCurrentIndex(i)
    cb.view().setMinimumWidth(260)
    return cb


class DatafonoPairingDialog(QDialog):
    """Asistente de emparejamiento del datáfono de la tienda ACTIVA de la sesión."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(520)
        from src.db import datafono as _datafono_db
        self._cfg = _datafono_db.obtener_config()
        self._terminales = []   # [{"id","nombre"}, ...] de la última búsqueda
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        cuerpo = QFrame()
        cuerpo.setObjectName("datafonowiz")
        cuerpo.setStyleSheet(f"QFrame#datafonowiz{{background:{_BG};border:2px solid {_CIAN};"
                             f"border-radius:18px;}}")
        outer.addWidget(cuerpo)
        v = QVBoxLayout(cuerpo)
        v.setContentsMargins(24, 22, 24, 22)
        v.setSpacing(10)

        from src.gui.tpv import _BotonCerrarX
        cab = QHBoxLayout()
        cab.addWidget(_lbl("💳  " + tr("datafono.titulo", default="DATÁFONO DE ESTA TIENDA"),
                           bold=True, size=16, color=_CIAN), 1)
        bx = _BotonCerrarX(30)
        bx.clicked.connect(self.reject)
        cab.addWidget(bx)
        v.addLayout(cab)
        v.addWidget(_lbl(
            tr("datafono.intro",
               default="Conecta el cobro con tarjeta a un datáfono real. 1) elige tu proveedor e "
                       "introduce las credenciales de tu cuenta de comercio con ellos; 2) busca "
                       "tu terminal (ya debe estar emparejado a esa cuenta desde su propia "
                       "pantalla); 3) guarda."),
            size=11, color=_TEXT2))

        from src.services.tpv.datafono.registry import proveedores_registrados
        v.addWidget(_lbl(tr("datafono.proveedor", default="Proveedor"), bold=True, size=12, color=_TEXT2))
        _rec = tr("datafono.recomendado", default="recomendado")
        opciones = [(meta["etiqueta"] + (f"  ({_rec})" if meta["recomendada"] else ""), nombre)
                   for nombre, meta in proveedores_registrados().items() if nombre != "simulado"]
        self.cmb_proveedor = _combo(opciones, self._cfg.get("proveedor"))
        self.cmb_proveedor.currentIndexChanged.connect(self._actualizar_visibilidad_generico)
        v.addWidget(self.cmb_proveedor)

        v.addWidget(_lbl(tr("datafono.api_key", default="API key / Client ID"),
                         bold=True, size=12, color=_TEXT2))
        self.inp_key = _inp(self._cfg.get("api_key"))
        v.addWidget(self.inp_key)

        v.addWidget(_lbl(tr("datafono.api_secret", default="API secret / Client secret (si aplica)"),
                         bold=True, size=12, color=_TEXT2))
        self.inp_secret = _inp(self._cfg.get("api_secret"))
        self.inp_secret.setEchoMode(QLineEdit.EchoMode.Password)
        v.addWidget(self.inp_secret)

        v.addWidget(_lbl(tr("datafono.comercio", default="Nº de comercio / Merchant code (si aplica)"),
                         bold=True, size=12, color=_TEXT2))
        self.inp_comercio = _inp(self._cfg.get("comercio"))
        v.addWidget(self.inp_comercio)

        # Adaptador REST personalizado (SOLO proveedor "generico") — reduce a configuración lo que
        # antes exigía escribir/desplegar un fichero Python nuevo por banco (petición explícita).
        self.lbl_adaptador = _lbl(
            tr("datafono.adaptador_titulo", default="Adaptador (forma de la API de tu banco)"),
            bold=True, size=12, color=_TEXT2)
        v.addWidget(self.lbl_adaptador)
        self.txt_adaptador = QPlainTextEdit(self._cfg.get("adaptador_json") or "")
        self.txt_adaptador.setFixedHeight(130)
        self.txt_adaptador.setStyleSheet(
            f"QPlainTextEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:8px;font-size:11px;font-family:Consolas,'{_FONT}';}}"
            f"QPlainTextEdit:focus{{border-color:{_CIAN};}}")
        v.addWidget(self.txt_adaptador)
        fila_plantilla = QHBoxLayout()
        self.btn_plantilla = _btn(tr("datafono.cargar_plantilla", default="📋  Cargar plantilla de ejemplo"))
        self.btn_plantilla.clicked.connect(self._cargar_plantilla)
        fila_plantilla.addWidget(self.btn_plantilla)
        v.addLayout(fila_plantilla)
        self._actualizar_visibilidad_generico()

        fila_m = QHBoxLayout()
        fila_m.setSpacing(10)
        colm = QVBoxLayout()
        colm.addWidget(_lbl(tr("datafono.modo", default="Modo"), bold=True, size=12, color=_TEXT2))
        self.cmb_modo = _combo([("Test", "test"), ("Live (cobros reales)", "live")],
                               self._cfg.get("modo", "test"))
        colm.addWidget(self.cmb_modo)
        fila_m.addLayout(colm)
        colc = QVBoxLayout()
        colc.addWidget(_lbl(tr("datafono.moneda", default="Moneda"), bold=True, size=12, color=_TEXT2))
        # Desplegable (petición explícita) con las MISMAS divisas que "Gestión de Caja"/Configuración
        # (`utils.divisas.monedas_soportadas`) — una sola lista de divisas para toda la app, nunca
        # texto libre que pueda desincronizarse de esa lista.
        from src.utils import divisas as _divisas
        opciones_moneda = [(f"{code} · {_divisas.info(code)['nombre']} ({_divisas.info(code)['simbolo']})", code)
                           for code in _divisas.monedas_soportadas()]
        self.cmb_moneda = _combo(opciones_moneda, self._cfg.get("moneda") or "EUR")
        colc.addWidget(self.cmb_moneda)
        fila_m.addLayout(colc)
        v.addLayout(fila_m)

        v.addSpacing(6)
        fila_buscar = QHBoxLayout()
        fila_buscar.setSpacing(8)
        self.btn_probar = _btn(tr("datafono.probar", default="🔌  Probar conexión"))
        self.btn_probar.clicked.connect(self._probar_conexion)
        fila_buscar.addWidget(self.btn_probar)
        self.btn_buscar = _btn(tr("datafono.buscar", default="🔍  Buscar terminales"))
        self.btn_buscar.clicked.connect(self._buscar_terminales)
        fila_buscar.addWidget(self.btn_buscar)
        v.addLayout(fila_buscar)

        self.lbl_estado_busqueda = _lbl("", size=11, color=_TEXT2)
        v.addWidget(self.lbl_estado_busqueda)

        v.addWidget(_lbl(
            tr("datafono.terminal", default="Terminal de esta tienda (elige de la lista o escribe su id)"),
            bold=True, size=12, color=_TEXT2))
        actual_terminal = (self._cfg.get("terminal_id"), self._cfg.get("terminal_nombre"))
        inicial = [(actual_terminal[1] or actual_terminal[0], actual_terminal[0])] if actual_terminal[0] else []
        self.cmb_terminal = _combo(inicial)
        # Editable (petición explícita): si el proveedor no publica listado (o el banco del
        # adaptador personalizado no lo define), la tienda puede escribir el id del terminal a
        # mano en vez de quedar bloqueada esperando una lista que nunca llega.
        self.cmb_terminal.setEditable(True)
        self.cmb_terminal.editTextChanged.connect(
            lambda txt: self.b_ok.setEnabled(bool(txt.strip())))
        v.addWidget(self.cmb_terminal)

        v.addSpacing(4)
        # Sin botón "Cancelar" (petición explícita): cerrar es la X de la cabecera, igual que el
        # resto de diálogos de la app — "Guardar" es la única acción de esta fila.
        self.b_ok = _btn(tr("datafono.guardar", default="Guardar"), color_bg=_BG2, color_fg=_VERDE,
                         color_border=_VERDE, hover_bg=_VERDE, hover_fg="#0D1117", h=44)
        self.b_ok.setEnabled(bool(inicial))
        self.b_ok.clicked.connect(self._guardar)
        v.addWidget(self.b_ok)

    def _es_generico(self) -> bool:
        return self.cmb_proveedor.currentData() == "generico"

    def _actualizar_visibilidad_generico(self):
        generico = self._es_generico()
        self.lbl_adaptador.setVisible(generico)
        self.txt_adaptador.setVisible(generico)
        self.btn_plantilla.setVisible(generico)

    def _cargar_plantilla(self):
        import json
        from src.services.tpv.datafono.generico import PLANTILLA_EJEMPLO
        self.txt_adaptador.setPlainText(json.dumps(PLANTILLA_EJEMPLO, ensure_ascii=False, indent=2))

    def _credenciales_actuales(self) -> dict:
        return {"api_key": self.inp_key.text().strip(),
                "api_secret": self.inp_secret.text().strip(),
                "comercio": self.inp_comercio.text().strip(),
                "modo": self.cmb_modo.currentData(),
                "adaptador_json": self.txt_adaptador.toPlainText().strip()}

    def _probar_conexion(self):
        """Diagnóstico de conectividad/autenticación, SIN depender de que haya terminales dados
        de alta (petición explícita) — muestra el motivo REAL del banco (código HTTP + mensaje),
        no uno genérico, para no descubrir un fallo de config recién al cobrar en caja."""
        from src.services.tpv.datafono.registry import clase_de
        clase = clase_de(self.cmb_proveedor.currentData())
        if clase is None:
            self.lbl_estado_busqueda.setText(tr("datafono.proveedor_desconocido",
                                                default="Proveedor no reconocido."))
            return
        self.btn_probar.setText(tr("datafono.probando", default="⏳ Probando…"))
        self.btn_probar.setEnabled(False)
        QApplication.processEvents()
        try:
            resultado = clase.probar_conexion(self._credenciales_actuales())
        finally:
            self.btn_probar.setText(tr("datafono.probar", default="🔌  Probar conexión"))
            self.btn_probar.setEnabled(True)
        icono = "✅" if resultado.get("ok") else "❌"
        color = _VERDE if resultado.get("ok") else _ROJO
        self.lbl_estado_busqueda.setText(f"{icono} {resultado.get('mensaje', '')}")
        self.lbl_estado_busqueda.setStyleSheet(
            f"color:{color};font-family:'{_FONT}';font-size:11px;background:transparent;border:none;")

    def _buscar_terminales(self):
        from src.services.tpv.datafono.registry import clase_de
        clase = clase_de(self.cmb_proveedor.currentData())
        if clase is None:
            self.lbl_estado_busqueda.setText(tr("datafono.proveedor_desconocido",
                                                default="Proveedor no reconocido."))
            return
        credenciales = self._credenciales_actuales()
        self.btn_buscar.setText(tr("datafono.buscando", default="⏳ Buscando…"))
        self.btn_buscar.setEnabled(False)
        QApplication.processEvents()
        try:
            terminales = clase.listar_terminales(credenciales)
        except Exception as e:
            terminales = None
            error = str(e)
        finally:
            self.btn_buscar.setText(tr("datafono.buscar", default="🔍  Buscar terminales"))
            self.btn_buscar.setEnabled(True)
        if terminales is None:
            self.lbl_estado_busqueda.setText(f"❌ {error}")
            self.lbl_estado_busqueda.setStyleSheet(
                f"color:{_ROJO};font-family:'{_FONT}';font-size:11px;background:transparent;border:none;")
            return
        self._terminales = terminales
        texto_actual = self.cmb_terminal.currentText()
        self.cmb_terminal.clear()
        if not terminales:
            self.lbl_estado_busqueda.setText(
                tr("datafono.sin_terminales",
                   default="No se encontró ningún terminal emparejado a esa cuenta todavía (o "
                           "este proveedor no publica un listado) — escribe el id del terminal a "
                           "mano, lo encontrarás en la pantalla del propio datáfono."))
            self.lbl_estado_busqueda.setStyleSheet(
                f"color:{_TEXT2};font-family:'{_FONT}';font-size:11px;background:transparent;border:none;")
            # Editable siempre (petición explícita): sin lista, la tienda escribe el id a mano,
            # nunca se bloquea el guardado solo porque el proveedor no publique un listado.
            self.cmb_terminal.setEditText(texto_actual)
            return
        self.lbl_estado_busqueda.setText(
            tr("datafono.encontrados", default="✅ {n} terminal(es) encontrados.", n=len(terminales)))
        self.lbl_estado_busqueda.setStyleSheet(
            f"color:{_VERDE};font-family:'{_FONT}';font-size:11px;background:transparent;border:none;")
        for t in terminales:
            self.cmb_terminal.addItem(t["nombre"], t["id"])
        self.b_ok.setEnabled(bool(self.cmb_terminal.currentText().strip()))

    def _guardar(self):
        from src.gui.mfa_gui import step_up_sesion
        # Mismo gate que la pasarela ONLINE (`pagos.pasarela.configurar`, ver `CLAUDE.md`):
        # configurar hacia dónde van los cobros con tarjeta es una acción crítica — no se crea un
        # permiso/motor de step-up nuevo para esto, se reutiliza el ya cableado.
        if not step_up_sesion("pagos.pasarela.configurar", self):
            return
        if self._es_generico() and not self.txt_adaptador.toPlainText().strip():
            self.lbl_estado_busqueda.setText(
                tr("datafono.falta_adaptador",
                   default="Pega (o carga la plantilla y ajusta) el adaptador antes de guardar."))
            self.lbl_estado_busqueda.setStyleSheet(
                f"color:{_ROJO};font-family:'{_FONT}';font-size:11px;background:transparent;border:none;")
            return
        # `currentData()` solo existe para un terminal elegido de la LISTA; un id escrito a mano
        # (o sin búsqueda previa) no tiene dato asociado — se usa el texto tal cual.
        terminal_id = self.cmb_terminal.currentData() or self.cmb_terminal.currentText().strip()
        terminal_nombre = self.cmb_terminal.currentText().strip()
        from src.db import datafono as _datafono_db
        _datafono_db.guardar_config(
            proveedor=self.cmb_proveedor.currentData(), api_key=self.inp_key.text().strip(),
            api_secret=self.inp_secret.text().strip(), comercio=self.inp_comercio.text().strip(),
            terminal_id=terminal_id, terminal_nombre=terminal_nombre,
            modo=self.cmb_modo.currentData(), moneda=self.cmb_moneda.currentData() or "EUR",
            adaptador_json=(self.txt_adaptador.toPlainText().strip() if self._es_generico() else ""))
        self.accept()
