"""
Fichajes — módulo standalone (extraído de la pestaña "FICHAJES" de `ConfiguracionWindow` en
`gestion_usuarios.py`, restructuración 2026-09). Control de asistencia por PIN de 4 dígitos:
iniciar/finalizar jornada, histórico propio (todo empleado ve el suyo) y, SOLO SUPERADMIN,
revisión de fichajes de otros empleados de la tienda conectada.

Disponible para los 3 roles (OPERARIO/ADMINISTRADOR/SUPERADMIN) directamente desde el Menú
Principal — antes vivía dentro de Configuración, reservada de facto a quien tuviera acceso a
ese módulo (ADMINISTRADOR/SUPERADMIN); ahora cualquier empleado puede fichar su propia jornada
sin pasar por Configuración. Pura relocación de UI: la lógica de negocio (registro de
entrada/salida, validación de PIN, histórico) es exactamente la misma que ya vivía en
`src/db/usuario.py` — sin cambios.
"""

from datetime import datetime

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from assets.estilo_global import _blindar_tamano_fijo, mostrar_mensaje
from src.db.usuario import (
    listar_fichajes_empleado,
    meses_con_fichajes_empleado,
    obtener_fichaje_abierto,
    registrar_entrada,
    registrar_salida,
    sesion_global,
    validar_pin_fichaje,
)
from src.utils.i18n import tr

_CIAN = "#00FFC6"
_FONDO = "#0E1117"
_PANEL_BG = "#161B22"
_BORDE = "#30363D"


class FichajesWindow(QWidget):
    """Control de asistencia (fichaje por PIN). Ventana de nivel superior, disponible para los
    3 roles. Ver docstring del módulo."""

    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self.callback_vuelta = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background-color: {_FONDO};")
        self.setWindowTitle("FICHAJES")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Cabecera con título + botón de regreso (mismo patrón que otras ventanas de nivel
        # superior extraídas de Configuración, p. ej. `GestionCajaWindow` en gestion_usuarios.py).
        header = QFrame()
        header.setFixedHeight(64)
        header.setStyleSheet(f"background-color:{_FONDO};")
        h_ly = QHBoxLayout(header)
        h_ly.setContentsMargins(28, 0, 28, 0)
        titulo = QLabel("FICHAJES")
        titulo.setStyleSheet(f"color:{_CIAN};font-weight:900;font-size:16px;letter-spacing:1px;")
        h_ly.addWidget(titulo)
        h_ly.addStretch()
        btn_volver = QPushButton("✕")
        btn_volver.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_volver.setFixedSize(50, 50)
        btn_volver.setStyleSheet(
            "QPushButton{background:transparent;color:#F85149;border:none;"
            "border-radius:25px;padding:0;font-family:'Segoe UI';font-weight:900;font-size:18px;}"
            "QPushButton:hover{background:#F85149;color:#0E1117;}"
        )
        btn_volver.setProperty("sin_glow", True)
        _blindar_tamano_fijo(btn_volver, 50, 50)
        btn_volver.clicked.connect(self.ejecutar_regreso)
        h_ly.addWidget(btn_volver)
        root.addWidget(header)

        root.addWidget(self._crear_contenido(), 1)

    def ejecutar_regreso(self):
        if self.callback_vuelta:
            self.callback_vuelta()
        self.close()

    # --- CONTENIDO: CONTROL DE ASISTENCIA ---
    # (extraído verbatim de `ConfiguracionWindow._crear_page_fichajes` en gestion_usuarios.py,
    # salvo el gate de "REVISAR FICHAJES EMPLEADOS": antes ADMINISTRADOR+SUPERADMIN, ahora SOLO
    # SUPERADMIN — instrucción explícita del usuario.)
    def _crear_contenido(self):
        page = QWidget()
        ly = QVBoxLayout(page)
        ly.setContentsMargins(50, 50, 50, 50)
        ly.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl_clock = QLabel("⏳")
        lbl_clock.setStyleSheet(
            "font-size: 180px; background: transparent; border: none; margin-bottom: 30px;"
        )
        lbl_clock.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ly.addWidget(lbl_clock, alignment=Qt.AlignmentFlag.AlignCenter)
        ly.addSpacing(20)

        ly.addWidget(
            QLabel(tr("cfg.attendance", default="CONTROL DE ASISTENCIA"),
                   styleSheet="color: white; font-weight: 900; font-size: 16px;"),
            alignment=Qt.AlignmentFlag.AlignCenter,
        )
        ly.addSpacing(20)

        self.input_pin = QLineEdit()
        self.input_pin.setPlaceholderText(tr("cfg.pin_ph", default="CÓDIGO DE 4 DÍGITOS"))
        self.input_pin.setMaxLength(4)
        self.input_pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_pin.setFixedWidth(300)
        self.input_pin.setFixedHeight(60)
        self.input_pin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.input_pin.setStyleSheet(
            f"border: 2px solid {_CIAN}; border-radius: 15px; "
            "font-size: 24px; color: white; background: #161B22;"
        )
        ly.addWidget(self.input_pin, alignment=Qt.AlignmentFlag.AlignCenter)
        ly.addSpacing(15)

        self._f_btn = QPushButton(tr("cfg.start_shift", default="INICIAR JORNADA"))
        self._f_btn.setFixedSize(300, 60)
        self._f_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._f_btn.setStyleSheet(self._f_style_iniciar())
        self._f_btn.clicked.connect(self._f_on_btn_click)
        ly.addWidget(self._f_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        ly.addSpacing(16)

        self._f_lbl_counter = QLabel("00:00:00")
        self._f_lbl_counter.setStyleSheet(
            f"color: {_CIAN}; font-family: 'Courier New'; font-size: 42px; "
            "font-weight: 900; background: transparent; letter-spacing: 4px;"
        )
        self._f_lbl_counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._f_lbl_counter.hide()
        ly.addWidget(self._f_lbl_counter, alignment=Qt.AlignmentFlag.AlignCenter)

        ly.addStretch()

        # State
        self._f_fichaje_id: int | None = None
        self._f_usuario_id: int | None = None
        self._f_seconds: int = 0
        self._f_jornada_activa: bool = False
        self._f_timer = QTimer(self)
        self._f_timer.setInterval(1000)
        self._f_timer.timeout.connect(self._f_tick_contador)

        btn_hist = QPushButton(tr("cfg.hist_btn", default="HISTÓRICO DE FICHAJES"))
        btn_hist.setFixedHeight(38)
        btn_hist.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_hist.setStyleSheet(f"""
            QPushButton {{
                background: #11181D;
                border: 2px solid {_CIAN};
                border-radius: 10px;
                color: {_CIAN};
                font-family: 'Segoe UI';
                font-weight: bold;
                font-size: 13px;
                padding: 0 20px;
            }}
            QPushButton:hover {{
                background: {_CIAN};
                color: #0E1117;
            }}
        """)
        btn_hist.clicked.connect(lambda: self._f_historico_fichajes())   # sin pasar el 'checked' como uid
        h_bot = QHBoxLayout()
        h_bot.addWidget(btn_hist)
        # REVISAR FICHAJES EMPLEADOS: SOLO SUPERADMIN (instrucción explícita — antes también
        # ADMINISTRADOR, ahora restringido; revisan cualquier empleado de la tienda a la que se
        # han conectado remotamente = empresa/tienda del contexto activo).
        try:
            _perfil = str((sesion_global.usuario_actual or {}).get("perfil", "")).upper()
        except Exception:
            _perfil = ""
        if _perfil == "SUPERADMIN":
            btn_rev = QPushButton(tr("cfg.review_att_btn", default="REVISAR FICHAJES EMPLEADOS"))
            btn_rev.setFixedHeight(38)
            btn_rev.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_rev.setStyleSheet(btn_hist.styleSheet())   # mismo estilo neón que el histórico
            btn_rev.clicked.connect(self._f_revisar_fichajes_empleados)
            h_bot.addSpacing(12)
            h_bot.addWidget(btn_rev)
        h_bot.addStretch()
        ly.addLayout(h_bot)
        return page

    def _f_style_iniciar(self) -> str:
        return f"""
            QPushButton {{
                background: #0E1117;
                color: {_CIAN};
                border: 2px solid {_CIAN};
                border-radius: 15px;
                font-family: 'Segoe UI';
                font-weight: 900;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background: {_CIAN};
                color: #0E1117;
            }}
        """

    def _f_style_finalizar(self) -> str:
        return """
            QPushButton {
                background: #0E1117;
                color: #EF4444;
                border: 2px solid #EF4444;
                border-radius: 15px;
                font-family: 'Segoe UI';
                font-weight: 900;
                font-size: 14px;
            }
            QPushButton:hover {
                background: #EF4444;
                color: #0E1117;
            }
        """

    def _f_on_btn_click(self):
        if self._f_jornada_activa:
            self._f_finalizar_jornada()
        else:
            self._f_iniciar_jornada()

    def _f_iniciar_jornada(self):
        pin = self.input_pin.text().strip()
        if len(pin) != 4 or not pin.isdigit():
            mostrar_mensaje(self, tr("cfg.pin_invalid_title", default="PIN inválido"), tr("cfg.pin_invalid_msg", default="Introduce un código de 4 dígitos numéricos."), "warning")
            return
        usuario = validar_pin_fichaje(pin)
        if not usuario:
            mostrar_mensaje(self, tr("cfg.pin_wrong_title", default="PIN incorrecto"), tr("cfg.pin_wrong_msg", default="No se encontró ningún empleado con ese PIN."), "error")
            return
        # Resume if there's an open fichaje
        fichaje_abierto = obtener_fichaje_abierto(usuario["id"])
        if fichaje_abierto:
            self._f_fichaje_id = fichaje_abierto["id"]
            entrada_dt = fichaje_abierto["entrada"]
            if isinstance(entrada_dt, str):
                entrada_dt = datetime.fromisoformat(entrada_dt)
            self._f_seconds = max(0, int((datetime.now() - entrada_dt).total_seconds()))
        else:
            fichaje_id = registrar_entrada(usuario["id"], usuario["nombre"])
            if fichaje_id is None:
                mostrar_mensaje(self, tr("cfg.error_title", default="Error"), tr("cfg.entry_err", default="No se pudo registrar la entrada en la base de datos."), "error")
                return
            self._f_fichaje_id = fichaje_id
            self._f_seconds = 0
        self._f_usuario_id = usuario["id"]
        self._f_jornada_activa = True
        self._f_btn.setText(tr("cfg.end_shift", default="FINALIZAR JORNADA"))
        self._f_btn.setStyleSheet(self._f_style_finalizar())
        self.input_pin.clear()
        self.input_pin.setPlaceholderText(tr("cfg.pin_to_end_ph", default="PIN PARA FINALIZAR"))
        self._f_update_counter_label()
        self._f_lbl_counter.show()
        self._f_timer.start()

    def _f_finalizar_jornada(self):
        pin = self.input_pin.text().strip()
        if len(pin) != 4 or not pin.isdigit():
            mostrar_mensaje(self, tr("cfg.pin_required_title", default="PIN requerido"),
                            tr("cfg.pin_required_msg", default="Introduce tu PIN de 4 dígitos para finalizar la jornada."), "warning")
            return
        usuario = validar_pin_fichaje(pin)
        if not usuario or usuario["id"] != self._f_usuario_id:
            mostrar_mensaje(self, tr("cfg.pin_wrong_title", default="PIN incorrecto"),
                            tr("cfg.pin_mismatch_msg", default="El PIN introducido no coincide con el empleado que inició la jornada."), "error")
            self.input_pin.clear()
            return
        self._f_timer.stop()
        segundos = registrar_salida(self._f_fichaje_id) if self._f_fichaje_id else None
        self._f_jornada_activa = False
        self._f_fichaje_id = None
        self._f_usuario_id = None
        self._f_btn.setText(tr("cfg.start_shift", default="INICIAR JORNADA"))
        self._f_btn.setStyleSheet(self._f_style_iniciar())
        self._f_lbl_counter.hide()
        self._f_lbl_counter.setText("00:00:00")
        self._f_seconds = 0
        self.input_pin.clear()
        self.input_pin.setPlaceholderText(tr("cfg.pin_ph", default="CÓDIGO DE 4 DÍGITOS"))
        if segundos is not None:
            h = segundos // 3600
            m = (segundos % 3600) // 60
            s = segundos % 60
            mostrar_mensaje(self, tr("cfg.shift_done_title", default="Jornada finalizada"),
                            tr("cfg.worked_time", default="Has trabajado {h}h {m}m {s}s.", h=f"{h:02d}", m=f"{m:02d}", s=f"{s:02d}"), "info")
        else:
            mostrar_mensaje(self, tr("cfg.shift_done_title", default="Jornada finalizada"), tr("cfg.shift_registered", default="Jornada registrada correctamente."), "info")

    def _f_tick_contador(self):
        self._f_seconds += 1
        self._f_update_counter_label()

    def _f_update_counter_label(self):
        h = self._f_seconds // 3600
        m = (self._f_seconds % 3600) // 60
        s = self._f_seconds % 60
        self._f_lbl_counter.setText(f"{h:02d}:{m:02d}:{s:02d}")

    def _f_historico_fichajes(self, uid=None, nombre=None):
        """Histórico de fichajes. SIN argumentos: el empleado EN SESIÓN (cada uno ve los suyos). Con `uid`
        (revisión por SUPERADMIN de otro empleado): el empleado indicado, con su nombre en el título.
        Muestra el mes EN CURSO y permite navegar a meses anteriores con las flechas. Columnas: FECHA ·
        ENTRADA · SALIDA · HORAS DEL DÍA · HORAS DEL MES. Ventana completa; cerrar con la ✕ roja."""
        import datetime
        if uid is not None:
            self._hf_uid = uid
            self._hf_nombre = nombre or ""
        else:
            try:
                self._hf_uid = (sesion_global.usuario_actual or {}).get("id")
            except Exception:
                self._hf_uid = None
            self._hf_nombre = ""
        hoy = datetime.date.today()
        meses = meses_con_fichajes_empleado(self._hf_uid) if self._hf_uid is not None else []
        actual = (hoy.year, hoy.month)
        # Páginas: el mes en curso (siempre) + los meses con fichajes, deduplicado, más reciente primero.
        self._hf_paginas = [actual] + [m for m in meses if m != actual]
        self._hf_idx = 0

        dlg = QDialog(self)
        dlg.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        dlg.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Sin el contorno neón cian global (`QDialog{border:2px solid CIAN}`, estilo_global.py):
        # esta ventana es a PANTALLA COMPLETA (el contorno de "card", más abajo, es intencional).
        dlg.setObjectName("dlg_historico_fichajes")
        dlg.setStyleSheet("#dlg_historico_fichajes { border: none; }")
        try:
            dlg.setGeometry(QApplication.primaryScreen().availableGeometry())  # ventana completa
        except Exception:
            dlg.setMinimumSize(900, 600)

        card = QFrame(dlg)
        card.setObjectName("hfcard")
        card.setStyleSheet(f"QFrame#hfcard{{background:#0D1117;border:2px solid {_CIAN};border-radius:14px;}}")
        root_lay = QVBoxLayout(dlg)
        root_lay.setContentsMargins(10, 10, 10, 10)
        root_lay.addWidget(card)
        ly = QVBoxLayout(card)
        ly.setContentsMargins(26, 20, 26, 18)
        ly.setSpacing(12)

        # Cabecera: título del mes + ✕ roja arriba a la derecha.
        hdr = QHBoxLayout()
        self._hf_titulo = QLabel("")
        self._hf_titulo.setStyleSheet("color: %s; font-family: 'Segoe UI'; font-weight: 900; font-size: 18px;" % _CIAN)
        hdr.addWidget(self._hf_titulo)
        hdr.addStretch()
        bx = QPushButton("✕")
        bx.setFixedSize(40, 40)
        bx.setCursor(Qt.CursorShape.PointingHandCursor)
        bx.setStyleSheet("QPushButton{background:transparent;color:#F85149;border:none;"
                         "border-radius:20px;padding:0;font-weight:900;font-size:18px;}"
                         "QPushButton:hover{background:#F85149;color:#0D1117;}")
        bx.setProperty("sin_glow", True)
        _blindar_tamano_fijo(bx, 40, 40)
        bx.clicked.connect(dlg.accept)
        hdr.addWidget(bx)
        ly.addLayout(hdr)

        headers = [
            tr("cfg.col_date", default="FECHA"),
            tr("cfg.col_entry", default="ENTRADA"),
            tr("cfg.col_exit", default="SALIDA"),
            tr("cfg.col_hours_day", default="HORAS DEL DÍA"),
            tr("cfg.col_hours_month", default="HORAS DEL MES"),
        ]
        self._hf_tbl = QTableWidget(0, len(headers))
        self._hf_tbl.setHorizontalHeaderLabels(headers)
        self._hf_tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._hf_tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._hf_tbl.verticalHeader().setVisible(False)
        for i in range(len(headers)):
            self._hf_tbl.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        # Tabla SIN borde propio: el contorno neón + esquinas redondeadas los aporta un QFrame contenedor,
        # así las cabeceras no cortan el contorno.
        self._hf_tbl.setFrameShape(QFrame.Shape.NoFrame)
        self._hf_tbl.setStyleSheet(f"""
            QTableWidget {{ background: #161B22; color: white; border: none;
                font-size: 13px; gridline-color: #21262D; font-family: 'Segoe UI'; }}
            QHeaderView::section {{ background: #21262D; color: {_CIAN}; font-weight: bold;
                border: none; border-bottom: 2px solid {_CIAN}; padding: 8px 10px;
                font-family: 'Segoe UI'; font-size: 13px; }}
            QHeaderView::section:first {{ border-top-left-radius: 10px; }}
            QHeaderView::section:last {{ border-top-right-radius: 10px; }}
            QHeaderView::section:hover {{ background: {_CIAN}; color: #0D1117; }}
            QTableWidget::item {{ padding: 5px 10px; }}
            QTableWidget::item:selected {{ background: #2D333B; }}
        """)
        _hf_wrap = QFrame()
        _hf_wrap.setObjectName("hfwrap")
        _hf_wrap.setStyleSheet(f"QFrame#hfwrap{{background:#0D1117;border:2px solid {_CIAN};border-radius:12px;}}")
        _hf_wl = QVBoxLayout(_hf_wrap)
        _hf_wl.setContentsMargins(6, 6, 6, 6)
        _hf_wl.addWidget(self._hf_tbl)
        ly.addWidget(_hf_wrap, 1)

        # Pie: flechas de navegación (◀ mes anterior a la izquierda, ▶ mes siguiente a la derecha) + total.
        def _flecha(txt):
            b = QPushButton(txt)
            b.setFixedSize(52, 44)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"QPushButton{{background:#11181D;color:{_CIAN};border:2px solid {_CIAN};"
                            f"border-radius:10px;font-weight:900;font-size:18px;}}"
                            f"QPushButton:hover{{background:{_CIAN};color:#0E1117;}}"
                            f"QPushButton:disabled{{color:#30363D;border-color:#21262D;}}")
            return b
        pie = QHBoxLayout()
        self._hf_prev = _flecha("◀")   # mes anterior (más antiguo)
        self._hf_next = _flecha("▶")   # mes siguiente (más reciente)
        self._hf_prev.clicked.connect(lambda: self._hf_navegar(+1))
        self._hf_next.clicked.connect(lambda: self._hf_navegar(-1))
        self._hf_total = QLabel("")
        self._hf_total.setStyleSheet("color: #8B949E; font-family: 'Segoe UI'; font-size: 12px;")
        pie.addWidget(self._hf_prev)
        pie.addStretch()
        pie.addWidget(self._hf_total)
        pie.addStretch()
        pie.addWidget(self._hf_next)
        ly.addLayout(pie)

        self._hf_pintar()
        # Reaplica la geometría a pantalla completa TRAS mostrarse (setGeometry antes del show no siempre
        # se respeta en frameless/Tool → la ventana salía más pequeña dejando ver la de detrás).
        def _full():
            try:
                dlg.setGeometry(QApplication.primaryScreen().availableGeometry())
            except Exception:
                pass
        QTimer.singleShot(0, _full)
        QTimer.singleShot(60, _full)
        from src.gui.transiciones import abrir_dialogo_deslizante
        abrir_dialogo_deslizante(dlg, self)

    def _f_revisar_fichajes_empleados(self):
        """SOLO SUPERADMIN: elige un empleado de la tienda a la que se está conectado remotamente
        (empresa/tienda del contexto activo, con AISLAMIENTO ESTRICTO por empresa) y abre su histórico de
        fichajes reutilizando el visor `_f_historico_fichajes` con el uid del empleado seleccionado."""
        from src.db.usuario import listar_usuarios_empresa
        try:
            perfil = str((sesion_global.usuario_actual or {}).get("perfil", "")).upper()
        except Exception:
            perfil = ""
        if perfil != "SUPERADMIN":
            mostrar_mensaje(self, tr("cfg.review_att_title", default="Revisar fichajes"),
                            tr("cfg.review_att_denied",
                               default="Solo un superadministrador puede revisar los fichajes de otros empleados."),
                            "warning")
            return
        empleados = listar_usuarios_empresa()   # empleados de la tienda/empresa conectada
        if not empleados:
            mostrar_mensaje(self, tr("cfg.review_att_title", default="Revisar fichajes"),
                            tr("cfg.review_att_empty", default="No hay empleados en la tienda conectada."), "info")
            return
        try:
            from src.db.tiendas import etiqueta_tienda_actual
            _tienda = etiqueta_tienda_actual() or ""
        except Exception:
            _tienda = ""

        dlg = QDialog(self)
        dlg.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        dlg.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        dlg.setMinimumWidth(520)
        card = QFrame(dlg); card.setObjectName("rvcard")
        card.setStyleSheet(f"QFrame#rvcard{{background:#0D1117;border:2px solid {_CIAN};border-radius:14px;}}")
        root = QVBoxLayout(dlg); root.setContentsMargins(12, 12, 12, 12); root.addWidget(card)
        ly = QVBoxLayout(card); ly.setContentsMargins(26, 22, 26, 20); ly.setSpacing(14)

        hdr = QHBoxLayout()
        t = QLabel(tr("cfg.review_att_title2", default="REVISAR FICHAJES DE EMPLEADOS"))
        t.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:17px;background:transparent;")
        hdr.addWidget(t); hdr.addStretch()
        bx = QPushButton("✕"); bx.setFixedSize(38, 38); bx.setCursor(Qt.CursorShape.PointingHandCursor)
        bx.setStyleSheet("QPushButton{background:transparent;color:#F85149;border:none;"
                         "border-radius:19px;padding:0;font-weight:900;font-size:16px;}"
                         "QPushButton:hover{background:#F85149;color:#0D1117;}")
        bx.setProperty("sin_glow", True)
        _blindar_tamano_fijo(bx, 38, 38)
        bx.clicked.connect(dlg.reject); hdr.addWidget(bx)
        ly.addLayout(hdr)

        if _tienda:
            sub = QLabel("🏪  " + _tienda)
            sub.setStyleSheet("color:#8B949E;font-family:'Segoe UI';font-size:12px;font-weight:700;background:transparent;")
            ly.addWidget(sub)

        lbl = QLabel(tr("cfg.review_att_pick", default="Empleado a revisar:"))
        lbl.setStyleSheet("color:white;font-family:'Segoe UI';font-weight:700;font-size:13px;background:transparent;")
        ly.addWidget(lbl)
        combo = QComboBox(); combo.setFixedHeight(44)
        combo.setCursor(Qt.CursorShape.PointingHandCursor)
        combo.setStyleSheet(f"QComboBox{{background:#161B22;color:white;border:2px solid {_CIAN};border-radius:10px;"
                            "padding:4px 14px;font-family:'Segoe UI';font-weight:700;font-size:13px;}"
                            "QComboBox::drop-down{border:none;width:24px;}")
        for e in empleados:
            etiqueta = e.get("nombre") or "?"
            if e.get("perfil"):
                etiqueta += f"   ·   {e['perfil']}"
            combo.addItem(etiqueta, e.get("id"))
        ly.addWidget(combo)
        ly.addSpacing(6)

        fila = QHBoxLayout(); fila.addStretch()
        ver = QPushButton(tr("cfg.review_att_view", default="VER HISTÓRICO"))
        ver.setFixedHeight(42); ver.setCursor(Qt.CursorShape.PointingHandCursor)
        ver.setStyleSheet(f"QPushButton{{background:#0E1117;color:{_CIAN};border:2px solid {_CIAN};border-radius:10px;"
                          "font-family:'Segoe UI';font-weight:900;font-size:13px;padding:0 22px;}"
                          f"QPushButton:hover{{background:{_CIAN};color:#0E1117;}}")

        def _ver():
            idx = combo.currentIndex()
            uid = combo.currentData()
            nombre = empleados[idx].get("nombre") if 0 <= idx < len(empleados) else ""
            dlg.accept()
            if uid is not None:
                self._f_historico_fichajes(uid=uid, nombre=nombre)
        ver.clicked.connect(_ver)
        fila.addWidget(ver)
        ly.addLayout(fila)
        dlg.exec()

    def _hf_navegar(self, delta):
        nuevo = self._hf_idx + delta
        if 0 <= nuevo < len(self._hf_paginas):
            self._hf_idx = nuevo
            self._hf_pintar()

    def _hf_pintar(self):
        import datetime
        meses_nom = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                     "septiembre", "octubre", "noviembre", "diciembre"]
        y, m = self._hf_paginas[self._hf_idx]
        _tit = tr("cfg.hist_title_mes", default="HISTÓRICO DE FICHAJES · {mes} {anio}",
                  mes=meses_nom[m].upper(), anio=y)
        if getattr(self, "_hf_nombre", ""):   # revisión de un empleado concreto (SUPERADMIN): su nombre delante
            _tit = f"{self._hf_nombre.upper()} · {_tit}"
        self._hf_titulo.setText("📅  " + _tit)
        fichajes = listar_fichajes_empleado(self._hf_uid, y, m) if self._hf_uid is not None else []
        total_seg = sum(int(f["segundos"] or 0) for f in fichajes)
        th, tm = total_seg // 3600, (total_seg % 3600) // 60
        mes_str = f"{th}h  {tm:02d}m"
        self._hf_tbl.setRowCount(len(fichajes))
        for row, f in enumerate(fichajes):
            ent = f["entrada"]
            self._hf_tbl.setItem(row, 0, QTableWidgetItem(ent.strftime("%d/%m/%Y") if ent else "-"))
            self._hf_tbl.setItem(row, 1, QTableWidgetItem(ent.strftime("%H:%M:%S") if ent else "-"))
            sal = f["salida"]
            it_sal = QTableWidgetItem(sal.strftime("%H:%M:%S") if sal else tr("cfg.in_progress", default="EN CURSO"))
            if not sal:
                it_sal.setForeground(QColor(_CIAN))
            self._hf_tbl.setItem(row, 2, it_sal)
            seg = int(f["segundos"] or 0)
            h, mm, ss = seg // 3600, (seg % 3600) // 60, seg % 60
            it_dia = QTableWidgetItem(f"{h:02d}h  {mm:02d}m  {ss:02d}s")
            it_dia.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._hf_tbl.setItem(row, 3, it_dia)
            it_mes = QTableWidgetItem(mes_str)
            it_mes.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_mes.setForeground(QColor(_CIAN))
            self._hf_tbl.setItem(row, 4, it_mes)
        self._hf_total.setText(tr("cfg.hist_total_mes", default="Total del mes: {h}h {m:02d}m  ·  {n} fichajes",
                                  h=th, m=tm, n=len(fichajes)))
        # Flechas: activas solo si hay más de una página (mes en curso + meses anteriores con fichajes).
        hay_varias = len(self._hf_paginas) > 1
        self._hf_prev.setEnabled(hay_varias and self._hf_idx < len(self._hf_paginas) - 1)
        self._hf_next.setEnabled(hay_varias and self._hf_idx > 0)
