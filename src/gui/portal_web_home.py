"""
Portal Web para Empleados · Núcleo (PortalWebHome) — Fase WEB-08.

Este componente se **extrajo verbatim** de `gui/tpv.py` (antes `_GestionPedidosOnlineDialog`, ~842 líneas):
el "Centro de gestión del Canal Web / pedidos online" YA NO pertenece al TPV. Es ahora la pantalla núcleo
del Portal Web para empleados (Back Office). MISMA lógica, MISMOS servicios, MISMAS validaciones — solo
cambió de hogar (patrón Strangler; sin desarrollar funcionalidades nuevas).

Autonomía: reutiliza las primitivas de estilo desde `gui/_neon_ui` (no importa `gui.tpv` a nivel de
módulo). Los diálogos de POS que reutiliza (`_CobroDialog`/`_EnvioDialog`/`_VentaOnlineDialog`) SIGUEN en
el TPV y se importan de forma PEREZOSA en el punto de uso (reutilización, no duplicación — Objetivo 5).

Alias de compatibilidad: `_GestionPedidosOnlineDialog = PortalWebHome`.
"""

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox,
                             QComboBox, QDialog, QFileDialog, QFrame,
                             QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QPushButton, QScrollArea, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from src.gui._neon_ui import (_BG, _BG2, _BORDE, _CIAN, _FONT, _ROJO, _TEXT,
                              _TEXT2, _VERDE, _RoundTableCorners, _btn, _card,
                              _lbl, _sep, _ss_tabla_neon)
from src.utils import divisas
from src.utils.i18n import tr


class PortalWebHome(QDialog):
    """Centro de gestión del CANAL WEB: página web (Fable 5), pedidos (domicilio + Click & Collect),
    catálogo publicado, sincronización y configuración del canal. Reutiliza los componentes existentes."""

    def __init__(self, empleado="—", id_caja="—", parent=None):
        super().__init__(parent)
        self._empleado = empleado
        self._id_caja = id_caja
        self._pedidos = []
        self.setWindowTitle(tr("online.canal_title", default="CANAL WEB"))
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setObjectName("dlg_ges_online")
        self.setStyleSheet(f"#dlg_ges_online {{ background: {_BG}; }}")
        try:
            self.setGeometry(QApplication.primaryScreen().availableGeometry())
        except Exception:
            self.setMinimumSize(1100, 700)
        self._render()

    def showEvent(self, e):
        super().showEvent(e)
        try:
            self.setGeometry(QApplication.primaryScreen().availableGeometry())
        except Exception:
            pass

    def _canal_existe(self) -> bool:
        try:
            from src.services.comercio_digital import canal_web
            return canal_web.existe()
        except Exception:
            return True   # degradable: si falla la comprobación, se muestra el panel operativo

    def _render(self):
        """State-gate: si el Canal Web NO existe → ASISTENTE de creación; si existe → PANEL operativo."""
        if getattr(self, "_root", None) is None:
            self._root = QVBoxLayout(self)
            self._root.setContentsMargins(12, 12, 12, 12)
        vieja = getattr(self, "_card", None)
        if vieja is not None:
            vieja.setParent(None)
            vieja.deleteLater()
        self._card = QFrame(self)
        self._card.setObjectName("go")
        # Sin contorno propio (el contorno neón exterior lo aporta el shell del Portal): se evita el doble
        # contorno. Se mantiene border-radius para que el fondo case con el borde exterior.
        self._card.setStyleSheet(f"QFrame#go{{background:{_BG};border:none;border-radius:16px;}}")
        self._root.addWidget(self._card)
        ly = QVBoxLayout(self._card)
        ly.setContentsMargins(28, 22, 28, 22)
        ly.setSpacing(14)
        if self._canal_existe():
            self._build_operativo(ly)
            self._refrescar()
        else:
            self._build_asistente(ly)

    def _build_operativo(self, ly):
        # Portal de EMPLEADOS: SOLO pedidos online. Sin ✕ interna (la cierra la ✕ del shell del portal), sin
        # botones de la web-cliente (Ir a la web / Ajustes / Sincronizar catálogo / Cobrar / Importar de la
        # web) ni referencias a la infraestructura de la web (dominio/DNS/HTTPS/Fable 5), que pertenecen al
        # Canal Web / TPV, no al portal del empleado.
        hdr = QHBoxLayout()
        hdr.addWidget(_lbl(tr("online.pedidos_title", default="Pedidos online"),
                           bold=True, size=18, color=_CIAN))
        hdr.addStretch()
        ly.addLayout(hdr)
        ly.addWidget(_lbl(tr("online.pedidos_sub",
                             default="Pedidos a domicilio y recogidas Click & Collect."),
                          size=11, color=_TEXT2))
        b_nuevo = _btn("＋  " + tr("online.ges_nuevo", default="Nuevo pedido"),
                       color_fg=_CIAN, color_border=_CIAN, hover_bg=_CIAN, h=38)
        b_nuevo.clicked.connect(self._nuevo)
        acciones = QHBoxLayout(); acciones.setSpacing(8)
        acciones.addWidget(b_nuevo)
        acciones.addStretch()
        ly.addLayout(acciones)
        ly.addWidget(_sep())

        cols = [
            tr("online.gc_tipo", default="Tipo"),
            tr("online.gc_pedido", default="Pedido"),
            tr("online.gc_fecha", default="Fecha"),
            tr("online.gc_cliente", default="Cliente"),
            tr("online.gc_tel", default="Teléfono"),
            tr("online.gc_total", default="Total"),
            tr("online.gc_estado", default="Estado"),
            tr("online.gc_plat", default="Plataforma"),
            tr("online.gc_ref", default="Ref. web"),
            tr("online.gc_envio", default="Envío"),
        ]
        self.tabla = QTableWidget(0, len(cols))
        self.tabla.setHorizontalHeaderLabels(cols)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(44)
        self.tabla.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tabla.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        hh = self.tabla.horizontalHeader()
        for ci in range(len(cols)):  # anchura equitativa (no se corta a la derecha)
            hh.setSectionResizeMode(ci, QHeaderView.ResizeMode.Stretch)
        self.tabla.setStyleSheet(_ss_tabla_neon())
        _RoundTableCorners(self.tabla)
        ly.addWidget(self.tabla, 1)

        self.lbl_estado = _lbl("", size=11, color=_TEXT2)
        ly.addWidget(self.lbl_estado)

    # ── ASISTENTE DE CREACIÓN (solo la primera vez: el canal aún no existe) ──────
    def _wi(self, ph="", val=""):
        e = QLineEdit(val)
        if ph:
            e.setPlaceholderText(ph)
        e.setFixedHeight(36)
        e.setStyleSheet(f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
                        f"border-radius:8px;padding:0 10px;font-size:12px;font-family:'{_FONT}';}}"
                        f"QLineEdit:focus{{border-color:{_CIAN};}}")
        return e

    def _wchk(self, texto, checked=True):
        from PyQt6.QtWidgets import QCheckBox
        cb = QCheckBox(texto)
        cb.setChecked(checked)
        cb.setCursor(Qt.CursorShape.PointingHandCursor)
        cb.setStyleSheet(f"QCheckBox{{color:{_TEXT};font-size:12px;font-family:'{_FONT}';spacing:8px;}}"
                         f"QCheckBox::indicator{{width:18px;height:18px;border:2px solid {_BORDE};"
                         f"border-radius:5px;background:{_BG2};}}"
                         f"QCheckBox::indicator:checked{{background:{_CIAN};border-color:{_CIAN};}}")
        return cb

    def _wcombo(self, pares):
        cb = QComboBox()
        cb.setFixedHeight(36)
        cb.setStyleSheet(f"QComboBox{{combobox-popup:0;background:{_BG2};color:{_TEXT};"
                         f"border:2px solid {_BORDE};border-radius:8px;padding:0 10px;font-size:12px;"
                         f"font-family:'{_FONT}';}}QComboBox:hover,QComboBox:on{{border-color:{_CIAN};}}"
                         f"QComboBox::drop-down{{border:none;width:22px;}}"
                         f"QComboBox QAbstractItemView{{background:#0D1117;color:{_TEXT};"
                         f"border:2px solid {_CIAN};border-radius:8px;selection-background-color:{_CIAN};"
                         f"selection-color:#0D1117;}}")
        for et, d in pares:
            cb.addItem(et, d)
        return cb

    def _idiomas_disponibles(self):
        """Los 21 idiomas soportados por la app (nombre nativo + código), en el orden del catálogo i18n."""
        try:
            from src.utils.i18n import LANGUAGES
            pares = [(m.get("native", code), code) for code, m in LANGUAGES.items()]
            if pares:
                return pares
        except Exception:
            pass
        return [("Español", "es"), ("English", "en")]

    def _combo_idiomas(self):
        """Combo de idioma con BANDERAS (PNG en assets/flags), igual que el selector del login."""
        import os as _os
        cb = self._wcombo(self._idiomas_disponibles())
        cb.setIconSize(QSize(24, 16))
        try:
            from src.utils import recursos
            _ruta = lambda c: recursos.ruta_recurso("assets", "flags", f"{c}.png")  # noqa: E731
        except Exception:
            _base = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
            _ruta = lambda c: _os.path.join(_base, "assets", "flags", f"{c}.png")  # noqa: E731
        from PyQt6.QtGui import QIcon
        for i in range(cb.count()):
            code = cb.itemData(i)
            ruta = _ruta(code)
            if _os.path.exists(ruta):
                cb.setItemIcon(i, QIcon(ruta))
        return cb

    def _selector_logo_wiz(self):
        """Selector de logo: botón para elegir una imagen del ordenador (como en Logo corporativo)."""
        cont = QWidget(); cont.setStyleSheet("background:transparent;")
        h = QHBoxLayout(cont); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(8)
        btn = _btn("📁 " + tr("canal.f_logo_btn", default="Seleccionar logo"), color_fg=_CIAN,
                   color_border=_BORDE, hover_bg=_CIAN, h=36)
        btn.setProperty("sin_glow", True)  # botón secundario: plano, sin resplandor neón
        self._logo_nombre = _lbl(tr("canal.f_logo_none", default="Ningún archivo seleccionado"),
                                 size=11, color=_TEXT2)

        def _elegir():
            from PyQt6.QtWidgets import QFileDialog
            import os as _os
            path, _ = QFileDialog.getOpenFileName(
                self, tr("canal.f_logo_dialog", default="Seleccionar logo de la empresa"), "",
                "Imágenes (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
            if path:
                self._logo_path = path
                self._logo_nombre.setText(_os.path.basename(path))
                self._logo_nombre.setStyleSheet(f"color:{_CIAN};font-family:'{_FONT}';font-size:11px;")
        btn.clicked.connect(_elegir)
        h.addWidget(btn); h.addWidget(self._logo_nombre, 1)
        return cont

    def _selector_color_wiz(self):
        """Selector de color corporativo: muestra (solo informativa) + botón 'Elegir color' → selector."""
        cont = QWidget(); cont.setStyleSheet("background:transparent;")
        h = QHBoxLayout(cont); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(8)
        # La muestra es un simple recuadro informativo (QLabel): no es clicable ni tiene resplandor.
        muestra = QLabel(); muestra.setFixedSize(64, 36)
        self._color_hex_lbl = _lbl(self._color_sel.upper(), bold=True, size=12, color=_TEXT)

        def _pinta(hexval):
            self._color_sel = hexval.upper()
            muestra.setStyleSheet(f"background:{hexval};border:2px solid {_BORDE};border-radius:8px;")
            self._color_hex_lbl.setText(hexval.upper())
        _pinta(self._color_sel)

        def _elegir():
            from src.gui.color_picker import seleccionar_color
            hexval = seleccionar_color(self, self._color_sel,
                                       tr("canal.f_color_dialog", default="Color corporativo"))
            if hexval:
                _pinta(hexval)
        btn = _btn("🎨 " + tr("canal.f_color_btn", default="Elegir color"), color_fg=_CIAN,
                   color_border=_BORDE, hover_bg=_CIAN, h=36)
        btn.setProperty("sin_glow", True)  # botón secundario: plano, sin resplandor neón
        btn.clicked.connect(_elegir)
        h.addWidget(muestra); h.addWidget(self._color_hex_lbl); h.addWidget(btn); h.addStretch()
        return cont

    def _build_asistente(self, ly):
        # Cabecera del asistente.
        hdr = QHBoxLayout()
        hdr.addWidget(_lbl("🌐  " + tr("canal.wiz_title", default="CREAR CANAL WEB"), bold=True,
                           size=18, color=_CIAN))
        hdr.addStretch()
        bx = QPushButton("✕"); bx.setFixedSize(38, 38); bx.setCursor(Qt.CursorShape.PointingHandCursor)
        bx.setStyleSheet(f"QPushButton{{background:{_BG2};color:{_TEXT2};border:1px solid {_BORDE};"
                         f"border-radius:8px;font-weight:900;}}QPushButton:hover{{border-color:{_ROJO};"
                         f"color:{_ROJO};}}")
        bx.clicked.connect(self.reject)
        hdr.addWidget(bx)
        ly.addLayout(hdr)
        ly.addWidget(_lbl(tr("canal.wiz_sub",
                             default="Aún no tienes tienda online. Configura tu negocio y Smart Manager "
                                     "generará el canal (dominio, credenciales y publicación) por ti."),
                          size=12, color=_TEXT2))
        ly.addWidget(_sep())

        cols = QHBoxLayout(); cols.setSpacing(24)
        # Columna 1 — Publicación + Información general.
        c1 = QVBoxLayout(); c1.setSpacing(8)
        # ── PUBLICACIÓN DEL SITIO WEB: dominio propio / subdominio gratuito / comprar dominio ──
        c1.addWidget(_lbl(tr("canal.wiz_pub", default="PUBLICACIÓN DEL SITIO WEB"), bold=True, size=13,
                          color=_CIAN))
        self.cmb_publicacion = self._wcombo([
            ("🌐 " + tr("canal.pub_propio", default="Usar mi dominio"), "propio"),
            ("🆓 " + tr("canal.pub_sub", default="Crear subdominio gratuito"), "subdominio"),
            ("🛒 " + tr("canal.pub_comprar", default="Comprar un dominio nuevo"), "comprado")])
        self.cmb_publicacion.currentIndexChanged.connect(self._cambio_publicacion)
        c1.addWidget(self.cmb_publicacion)
        # Fila de búsqueda de dominios (solo modalidad "comprar").
        self._pub_buscar_row = QWidget(); self._pub_buscar_row.setStyleSheet("background:transparent;")
        pbr = QHBoxLayout(self._pub_buscar_row); pbr.setContentsMargins(0, 0, 0, 0); pbr.setSpacing(8)
        b_buscar = _btn("🔎 " + tr("canal.pub_buscar", default="Buscar dominios"), color_fg=_CIAN,
                        color_border=_CIAN, hover_bg=_CIAN, h=36)
        b_buscar.clicked.connect(self._buscar_dominios_wiz)
        self.cmb_dominios_disp = self._wcombo([("—", "")])
        self.cmb_dominios_disp.currentIndexChanged.connect(
            lambda _i: self.w_dominio.setText(self.cmb_dominios_disp.currentData() or ""))
        pbr.addWidget(b_buscar); pbr.addWidget(self.cmb_dominios_disp, 1)
        self._pub_buscar_row.setVisible(False)
        c1.addWidget(self._pub_buscar_row)
        c1.addSpacing(6)
        c1.addWidget(_lbl(tr("canal.wiz_general", default="INFORMACIÓN GENERAL"), bold=True, size=13,
                          color=_CIAN))
        self.w_nombre = self._wi(tr("canal.f_nombre", default="Nombre de la tienda"))
        self.w_dominio = self._wi(tr("canal.f_dominio", default="Dominio (p. ej. mitienda.com)"))
        # Logo: se ELIGE un archivo del ordenador (igual que en Configuración → Logo corporativo).
        self._logo_path = ""
        self.w_logo = self._selector_logo_wiz()
        # Color corporativo: se ELIGE con el selector de color (no hay que saber el código HEX).
        self._color_sel = "#00FFC6"
        self.w_color = self._selector_color_wiz()
        # Idioma: los 21 idiomas soportados por la app (nombre nativo + bandera PNG, como el login).
        self.w_idioma = self._combo_idiomas()
        self.w_pais = self._wi(tr("canal.f_pais", default="País"), "ES")
        self.w_moneda = self._wi(tr("canal.f_moneda", default="Moneda"), "EUR")
        for et, wdg in ((tr("canal.f_nombre", default="Nombre de la tienda"), self.w_nombre),
                        (tr("canal.f_dominio", default="Dominio"), self.w_dominio),
                        (tr("canal.f_logo", default="Logo"), self.w_logo),
                        (tr("canal.f_color", default="Color corporativo"), self.w_color),
                        (tr("canal.f_idioma", default="Idioma"), self.w_idioma),
                        (tr("canal.f_pais", default="País"), self.w_pais),
                        (tr("canal.f_moneda", default="Moneda"), self.w_moneda)):
            c1.addWidget(_lbl(et, size=11, color=_TEXT2)); c1.addWidget(wdg)
        c1.addStretch()
        # Columna 2 — Configuración comercial + recogida.
        c2 = QVBoxLayout(); c2.setSpacing(8)
        c2.addWidget(_lbl(tr("canal.wiz_comercial", default="CONFIGURACIÓN COMERCIAL"), bold=True,
                          size=13, color=_CIAN))
        self.chk_stock = self._wchk(tr("canal.c_stock", default="Mostrar stock"))
        self.chk_compra = self._wchk(tr("canal.c_compra", default="Permitir compra online"))
        self.chk_cc = self._wchk(tr("canal.c_cc", default="Permitir Click & Collect (recogida)"))
        self.chk_disp = self._wchk(tr("canal.c_disp", default="Mostrar disponibilidad"))
        self.chk_promo = self._wchk(tr("canal.c_promo", default="Mostrar promociones"))
        for cb in (self.chk_stock, self.chk_compra, self.chk_cc, self.chk_disp, self.chk_promo):
            c2.addWidget(cb)
        c2.addSpacing(10)
        c2.addWidget(_lbl(tr("canal.wiz_recogida", default="CONFIGURACIÓN DE RECOGIDA"), bold=True,
                          size=13, color=_CIAN))
        self.chk_recogida = self._wchk(tr("canal.r_permitir", default="Permitir recogida en tienda"))
        c2.addWidget(self.chk_recogida)
        self.w_tiempo = self._wi(tr("canal.r_tiempo", default="Tiempo máximo (horas)"), "24")
        self.w_mensaje = self._wi(tr("canal.r_msg", default="Mensaje para el cliente"))
        self.w_horario = self._wi(tr("canal.r_horario", default="Horario de recogida (informativo)"))
        for et, wdg in ((tr("canal.r_tiempo", default="Tiempo máximo (horas)"), self.w_tiempo),
                        (tr("canal.r_msg", default="Mensaje para el cliente"), self.w_mensaje),
                        (tr("canal.r_horario", default="Horario de recogida"), self.w_horario)):
            c2.addWidget(_lbl(et, size=11, color=_TEXT2)); c2.addWidget(wdg)
        c2.addStretch()
        cols.addLayout(c1, 1); cols.addLayout(c2, 1)
        # El FORMULARIO va dentro de un scroll (acota el tamaño mínimo: la ventana NO crece por encima de
        # availableGeometry → la barra de tareas queda visible y el borde inferior no se corta). Mismo
        # scrollbar que el resto de la app. El botón GENERAR queda FIJO abajo (siempre visible).
        from PyQt6.QtWidgets import QScrollArea as _QScrollArea
        try:
            from src.gui.foundation import tokens as _T
            _sb = _T.qss_scrollbar()
        except Exception:
            _sb = ""
        form_inner = QWidget()
        form_inner.setStyleSheet("background:transparent;")
        form_inner.setLayout(cols)
        scroll = _QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(_QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}" + _sb)
        scroll.setWidget(form_inner)
        ly.addWidget(scroll, 1)

        # Mensaje de advertencia (validación): Segoe UI Bold, +3 pt (12→15) y amarillo chillón.
        self.lbl_asist = _lbl("", bold=True, size=15, color="#FFEA00")
        ly.addWidget(self.lbl_asist)
        fila = QHBoxLayout(); fila.addStretch()
        b_gen = _btn("✨  " + tr("canal.wiz_generar", default="GENERAR CANAL WEB"), color_bg=_VERDE,
                     color_fg="#0D1117", color_border=_VERDE, hover_bg="#FFF", hover_fg="#0D1117", h=50)
        b_gen.clicked.connect(self._generar_canal)
        fila.addWidget(b_gen)
        ly.addLayout(fila)
        self._cambio_publicacion()  # estado inicial de la modalidad de publicación

    def _cambio_publicacion(self):
        tipo = self.cmb_publicacion.currentData()
        self._pub_buscar_row.setVisible(tipo == "comprado")
        es_sub = tipo == "subdominio"
        self.w_dominio.setEnabled(not es_sub)
        self.w_dominio.setPlaceholderText(
            tr("canal.pub_sub_ph", default="(se genera solo: nombre.smartmanager.ai)") if es_sub
            else tr("canal.f_dominio", default="Dominio (p. ej. mitienda.com)"))

    def _buscar_dominios_wiz(self):
        texto = (self.w_nombre.text().strip() or self.w_dominio.text().strip()).split(".")[0]
        if not texto:
            self.lbl_asist.setText(tr("canal.pub_sin_texto",
                                      default="Indica un nombre para buscar dominios."))
            return
        from src.services.comercio_digital import canal_web
        try:
            from src.db.usuario import sesion_global
            u = sesion_global.usuario_actual or None
        except Exception:
            u = None
        r = canal_web.buscar_dominios(texto, usuario=u)
        self.cmb_dominios_disp.clear()
        if not r.get("ok") or not r.get("resultados"):
            self.cmb_dominios_disp.addItem("—", "")
            self.lbl_asist.setText(tr("canal.pub_sin_res", default="Sin resultados."))
            return
        for p in r["resultados"]:
            marca = "✅" if p.get("disponible") else "❌"
            self.cmb_dominios_disp.addItem(f"{marca} {p['dominio']} · {p.get('precio')}€",
                                           p["dominio"] if p.get("disponible") else "")
        for i in range(self.cmb_dominios_disp.count()):
            if self.cmb_dominios_disp.itemData(i):
                self.cmb_dominios_disp.setCurrentIndex(i)
                break

    def _generar_canal(self):
        nombre = self.w_nombre.text().strip()
        if not nombre:
            self.lbl_asist.setText(tr("canal.wiz_sin_nombre", default="Indica el nombre de la tienda."))
            return
        # Modalidad de publicación (dominio propio / subdominio gratuito / comprar dominio).
        tipo_pub = self.cmb_publicacion.currentData() if hasattr(self, "cmb_publicacion") else "subdominio"
        dom = self.w_dominio.text().strip()
        if tipo_pub in ("propio", "comprado") and not dom:
            self.lbl_asist.setText(tr("canal.pub_sin_dom", default="Indica el dominio."))
            return
        publicacion = ({"tipo": "subdominio", "nombre": nombre} if tipo_pub == "subdominio"
                       else {"tipo": tipo_pub, "dominio": dom})
        try:
            t = int(self.w_tiempo.text().strip())
        except Exception:
            t = 24
        cfg = {
            "nombre": nombre, "dominio": self.w_dominio.text().strip(),
            "logo": getattr(self, "_logo_path", ""), "color": getattr(self, "_color_sel", ""),
            "idioma": self.w_idioma.currentData(), "pais": self.w_pais.text().strip(),
            "moneda": (self.w_moneda.text().strip() or "EUR").upper(),
            "comercial": {"mostrar_stock": self.chk_stock.isChecked(),
                          "permitir_compra": self.chk_compra.isChecked(),
                          "click_collect": self.chk_cc.isChecked(),
                          "mostrar_disponibilidad": self.chk_disp.isChecked(),
                          "mostrar_promociones": self.chk_promo.isChecked()},
            # Preparado para el futuro: se ALMACENA, sin lógica operativa todavía.
            "recogida": {"permitir": self.chk_recogida.isChecked(), "tiempo_max_h": t,
                         "mensaje": self.w_mensaje.text().strip(),
                         "horario": self.w_horario.text().strip()},
        }
        from src.services.comercio_digital import canal_web
        try:
            from src.db.usuario import sesion_global
            u = sesion_global.usuario_actual or None
        except Exception:
            u = None
        self.lbl_asist.setText(tr("canal.wiz_generando", default="Generando canal web…"))
        r = canal_web.crear(cfg, publicacion=publicacion, usuario=u, actor=self._empleado)
        if not r.get("ok"):
            self.lbl_asist.setText(tr("canal.wiz_error", default="No se pudo crear el canal: {m}",
                                      m=str(r.get("error") or r.get("motivo") or "")))
            return
        # Canal creado y publicado → recargar la ventana como PANEL OPERATIVO.
        self._render()

    def _refrescar(self):
        from src.services.tpv import online_orders_service as OS

        # Fuente 1: pedidos online (entrega a domicilio) — servicio legacy, sin modificar consultas.
        self._pedidos = OS.listar_pedidos_online()
        # Fuente 2: reservas Click & Collect (transacciones con cumplimiento PICKUP_STORE) — SOLO lectura
        # vía el servicio existente `comercio_digital.transacciones` (no se modifica el backend).
        pickup = self._pedidos_pickup()
        self._pickup = pickup
        self.tabla.setRowCount(0)
        for p in self._pedidos:
            self._fila_pedido(p, "DELIVERY")
        for p in pickup:
            self._fila_pedido(p, "PICKUP")
        self.lbl_estado.setText(
            tr("online.canal_n", default="{n} pedido(s) · {r} recogida(s) en tienda",
               n=len(self._pedidos) + len(pickup), r=len(pickup))
        )

    def _pedidos_pickup(self):
        """Reservas Click & Collect (transacciones PICKUP_STORE). SOLO lectura; reutiliza el servicio
        existente. Aislamiento por empresa/tienda lo aplica el propio servicio (contexto)."""
        try:
            import json as _json

            from src.services.comercio_digital import transacciones
        except Exception:
            return []
        out = []
        try:
            for tx in transacciones.listar(limite=1000):
                meta = tx.get("metadata")
                if isinstance(meta, str):
                    try:
                        meta = _json.loads(meta)
                    except Exception:
                        meta = {}
                if (meta or {}).get("cumplimiento") != "PICKUP_STORE":
                    continue
                out.append({
                    "id_pedido": tx.get("id_tx"),
                    "fecha": tx.get("actualizada") or tx.get("creada"),
                    "cliente_nombre": tx.get("cliente_nombre"),
                    "cliente_telefono": tx.get("cliente_telefono"),
                    "total": (meta or {}).get("total_cotizado") or 0,
                    "estado": tx.get("estado"),
                    "plataforma": tr("online.canal_web", default="Web"),
                    "referencia_externa": tx.get("id_tienda"),
                })
        except Exception:
            return []
        return out

    def _fila_pedido(self, p, tipo):
        """Pinta una fila reutilizando el estilo de la tabla. `tipo` = DELIVERY (combo editable, legacy)
        o PICKUP (estado de solo lectura, gobernado por el servicio de recogida)."""
        r = self.tabla.rowCount()
        self.tabla.insertRow(r)
        es_pickup = tipo == "PICKUP"
        fecha = str(p.get("fecha") or "")[:16]
        if es_pickup:
            envio = "🏪 " + tr("online.recogida_tienda", default="Recogida en tienda")
            tipo_txt = "🏪 " + tr("online.tipo_pickup", default="Recogida")
        else:
            envio = " · ".join(x for x in (p.get("transportista"), p.get("seguimiento")) if x) or "—"
            tipo_txt = "🚚 " + tr("online.tipo_delivery", default="Domicilio")
        vals = [
            tipo_txt,
            str(p.get("id_pedido") or "")[:8],
            fecha,
            p.get("cliente_nombre") or "—",
            p.get("cliente_telefono") or "—",
            divisas.formatear(float(p.get("total") or 0)),
            None,   # estado (índice 6)
            p.get("plataforma") or "—",
            str(p.get("referencia_externa") or "—"),
            envio,
        ]
        for c, val in enumerate(vals):
            if c == 6:
                if es_pickup:
                    it = QTableWidgetItem(str(p.get("estado") or "—"))
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.tabla.setItem(r, 6, it)
                else:
                    self.tabla.setCellWidget(r, 6, self._combo_estado(p))
                continue
            it = QTableWidgetItem(str(val))
            if c in (0, 2, 4, 5, 7, 8, 9):
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabla.setItem(r, c, it)

    def _combo_estado(self, p):
        from src.services.tpv.online_orders_service import ESTADOS

        cb = QComboBox()
        cb.setFixedHeight(30)
        cb.setStyleSheet(
            f"QComboBox{{combobox-popup:0;background:{_BG};color:{_CIAN};border:1px solid {_BORDE};"
            f"border-radius:7px;padding:0 8px;font-size:11px;font-family:'{_FONT}';font-weight:900;}}"
            f"QComboBox:hover,QComboBox:on{{border-color:{_CIAN};}}"
            f"QComboBox::drop-down{{border:none;width:18px;}}"
            f"QComboBox QAbstractItemView{{background:#0D1117;color:{_TEXT};border:2px solid {_CIAN};"
            f"border-radius:8px;selection-background-color:{_CIAN};selection-color:#0D1117;}}"
        )
        for e in ESTADOS:
            cb.addItem(e, e)
        i = cb.findData(p.get("estado"))
        if i >= 0:
            cb.setCurrentIndex(i)
        cb.currentIndexChanged.connect(
            lambda _i, pid=p.get("id_pedido"), c=cb: self._cambiar_estado(
                pid, c.currentData()
            )
        )
        return cb

    def _cambiar_estado(self, pid, estado):
        from src.services.tpv import online_orders_service as OS

        if estado == "ENVIADO":
            from src.gui.tpv import _EnvioDialog  # POS reutilizado (sigue en TPV) — import perezoso
            dlg = _EnvioDialog(parent=self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                self._refrescar()  # revierte el combo al estado anterior
                return
            OS.cambiar_estado(pid, estado)
            OS.registrar_envio(pid, dlg.transportista(), dlg.seguimiento())
            self._refrescar()
            return
        OS.cambiar_estado(pid, estado)
        self._refrescar()

    def _nuevo(self):
        from src.gui.tpv import _VentaOnlineDialog  # POS reutilizado (sigue en TPV) — import perezoso
        _VentaOnlineDialog(
            empleado=self._empleado, id_caja=self._id_caja, parent=self
        ).exec()
        self._refrescar()


# Alias de compatibilidad (Strangler).
_GestionPedidosOnlineDialog = PortalWebHome
