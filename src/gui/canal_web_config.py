"""
Canal Web · Configuración de la presencia digital (Fase WEB-07).

Este diálogo se **extrajo físicamente** de `gui/tpv.py` (`_CanalWebConfigDialog`, 3657-4166) al módulo
Canal Web para eliminar el acoplamiento privado TPV↔Canal Web (Strangler, WEB-07). Es AUTÓNOMO: copia las
primitivas de estilo que antes tomaba de `tpv.py` (`_lbl`/`_btn`/`_ss_tabla_neon`/`_RoundTableCorners`), de
modo que NO importa nada de `tpv.py`.

Responsabilidad (CONGELADA · CLAUDE.md): Canal Web es el ÚNICO editor de la marca de la web (reutiliza
`services/comercio_digital/canal_web` → `web_config` vía `db/web_tienda`) y la administración de la presencia
digital (estado/dominios/publicación/sincronización/conexiones). SOLO consume servicios existentes (N7); no
crea backend/tablas/motores nuevos. Feedback INLINE (no modales: SOMA activo en el proceso principal).

Se alcanza desde el módulo Canal Web (asistente `canal_web_gui.CanalWebWindow`) y desde la redirección "Web"
del Catálogo (`catalogo_gestion._abrir_canal_web`). El TPV ya NO lo abre (solo navega a Portal Web).
"""

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtGui import QBitmap, QPainter, QRegion
from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox,
                             QComboBox, QDialog, QFrame, QHBoxLayout,
                             QHeaderView, QLabel, QLineEdit, QPushButton,
                             QTableWidget, QTableWidgetItem, QVBoxLayout,
                             QWidget)

from src.utils.i18n import tr

# ── Paleta / tipografía (copiadas de tpv.py para autonomía; presentación, no lógica) ──
_BG = "#0E1117"
_BG2 = "#161B22"
_CIAN = "#00FFC6"
_ROJO = "#FF4C4C"
_VERDE = "#3FB950"
_BORDE = "#30363D"
_TEXT = "#E6EDF3"
_TEXT2 = "#8B949E"
_FONT = "Segoe UI"


# ── Primitivas de estilo (copiadas de tpv.py: _lbl / _btn / _RoundTableCorners / _ss_tabla_neon) ──
def _lbl(text: str, bold: bool = False, size: int = 12, color: str = _TEXT) -> QLabel:
    lb = QLabel(text)
    lb.setStyleSheet(
        f"color:{color};font-family:'{_FONT}';font-size:{size}px;"
        f"font-weight:{'900' if bold else '500'};background:transparent;border:none;"
    )
    return lb


def _btn(
    text: str,
    color_bg: str = _BG2,
    color_fg: str = _TEXT,
    color_border: str = _BORDE,
    hover_bg: str = _CIAN,
    hover_fg: str = "#0D1117",
    h: int = 38,
    radius: int = 10,
) -> QPushButton:
    b = QPushButton(text)
    b.setFixedHeight(h)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setStyleSheet(
        f"QPushButton{{background:{color_bg};color:{color_fg};"
        f"border:2px solid {color_border};border-radius:{radius}px;"
        f"font-family:'{_FONT}';font-weight:900;font-size:13px;padding:0 12px;outline:0;}}"
        f"QPushButton:hover{{background:{hover_bg};color:{hover_fg};}}"
        f"QPushButton:focus{{outline:0;}}"
    )
    return b


class _RoundTableCorners(QObject):
    """Redondea las esquinas exteriores de un QTableWidget con una máscara: las 4
    del widget y, además, las superiores de la cabecera (para que el contorno
    neón no se corte arriba)."""

    def __init__(self, table, radius=10):
        super().__init__(table)
        self._r = radius
        self._table = table
        table.installEventFilter(self)
        table.horizontalHeader().installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Show) and obj.width() > 0:
            from PyQt6.QtCore import QRect

            if obj is self._table:
                rect = QRect(0, 0, obj.width(), obj.height())  # 4 esquinas
            else:  # cabecera: redondear solo arriba (extiende el rect por abajo)
                rect = QRect(0, 0, obj.width(), obj.height() + self._r)
            bmp = QBitmap(obj.size())
            bmp.fill(Qt.GlobalColor.color0)
            p = QPainter(bmp)
            p.setBrush(Qt.GlobalColor.color1)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(rect, self._r, self._r)
            p.end()
            obj.setMask(QRegion(bmp))
        return False


def _ss_tabla_neon() -> str:
    """Estilo de tabla con contorno neón, cabeceras redondeadas y hover swap."""
    return (
        f"QTableWidget{{background:{_BG};color:{_TEXT};border:2px solid {_CIAN};"
        f"border-radius:10px;gridline-color:{_BORDE};font-family:'{_FONT}';font-size:12px;"
        f"selection-background-color:rgba(0,255,198,0.18);selection-color:{_CIAN};}}"
        f"QTableWidget::item{{padding:6px 10px;}}"
        f"QTableWidget::item:alternate{{background:#0B0F14;}}"
        f"QHeaderView::section{{background:{_BG2};color:{_CIAN};border:none;"
        f"border-bottom:2px solid {_CIAN};padding:9px 8px;font-weight:900;font-family:'{_FONT}';}}"
        f"QHeaderView::section:first{{border-top-left-radius:8px;}}"
        f"QHeaderView::section:last{{border-top-right-radius:8px;}}"
        f"QHeaderView::section:hover{{background:{_CIAN};color:#0D1117;}}"
    )


class CanalWebConfigDialog(QDialog):
    """Configuración del CANAL WEB — refleja el servicio `comercio_digital.conexiones` (conexiones por
    canal con credenciales CIFRADAS vía Secret Manager). Sustituye al antiguo formulario URL/API Key/
    Secret. SOLO consume servicios existentes (no modifica backend)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # VENTANA COMPLETA: ocupa el área de trabajo (sin tapar la barra de tareas de Windows). El
        # desbordamiento del contenido se desplaza con scroll DENTRO del borde neón.
        try:
            self.setGeometry(QApplication.primaryScreen().availableGeometry())
        except Exception:
            self.setMinimumSize(900, 640)
        self._build()
        self._refrescar()

    def showEvent(self, e):
        super().showEvent(e)
        try:
            self.setGeometry(QApplication.primaryScreen().availableGeometry())
        except Exception:
            pass

    def _inp(self, val="", ph=""):
        e = QLineEdit(val or "")
        if ph:
            e.setPlaceholderText(ph)
        e.setFixedHeight(36)
        e.setStyleSheet(
            f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:0 10px;font-size:12px;font-family:'{_FONT}';}}"
            f"QLineEdit:focus{{border-color:{_CIAN};}}"
        )
        return e

    def _combo(self, valores):
        cb = QComboBox()
        cb.setFixedHeight(36)
        cb.setStyleSheet(
            f"QComboBox{{combobox-popup:0;background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:0 10px;font-size:12px;font-family:'{_FONT}';}}"
            f"QComboBox:hover,QComboBox:on{{border-color:{_CIAN};}}"
            f"QComboBox::drop-down{{border:none;width:22px;}}"
            f"QComboBox QAbstractItemView{{background:#0D1117;color:{_TEXT};border:2px solid {_CIAN};"
            f"border-radius:8px;selection-background-color:{_CIAN};selection-color:#0D1117;}}"
        )
        for v in valores:
            cb.addItem(v, v)
        return cb

    def _info_canal(self) -> dict:
        """Reúne el estado del canal reutilizando SERVICIOS existentes: entidad+métricas del Canal Web
        (`comercio_digital.canal_web`), pasarela (tpv.pagos) y conexión (conexiones). Solo lectura."""
        info = {"dominio": "—", "canal_estado": "—", "pasarela": "—", "conexiones": 0, "auth": "—",
                "publicado_en": "—", "ultima_sync": "—", "productos": 0, "pedidos": 0, "reservas": 0,
                "tipo_dom": "—", "proveedor_dom": "—", "dns": "—", "https": "—", "expira": "—"}
        try:
            from src.services.comercio_digital import canal_web
            p = canal_web.panel()
            info["canal_estado"] = p.get("estado") or "—"
            info["dominio"] = p.get("dominio") or "—"
            info["publicado_en"] = str(p.get("publicado_en") or "—")
            info["ultima_sync"] = str(p.get("ultima_sync") or "—")
            m = p.get("metricas", {})
            info["productos"] = m.get("productos_publicados", 0)
            info["pedidos"] = m.get("pedidos_pendientes", 0)
            info["reservas"] = m.get("reservas_activas", 0)
            da = p.get("dominio_activo") or {}
            info["tipo_dom"] = {"propio": "Dominio propio", "subdominio": "Subdominio Smart Manager",
                                "comprado": "Dominio comprado"}.get(da.get("tipo"), "—")
            info["proveedor_dom"] = da.get("proveedor") or "—"
            info["dns"] = da.get("estado_dns") or "—"
            info["https"] = da.get("estado_https") or "—"
            info["expira"] = str(da.get("fecha_expiracion") or "—")
        except Exception:
            pass
        try:
            from src.services.tpv.pagos import pasarela_actual
            info["pasarela"] = getattr(pasarela_actual(), "nombre", "—") or "—"
        except Exception:
            pass
        try:
            from src.services.comercio_digital import conexiones as _cx
            conns = _cx.listar() or []
            info["conexiones"] = len(conns)
            web = _cx.obtener("web") or (conns[0] if conns else None)
            if web:
                if info["dominio"] == "—":
                    info["dominio"] = web.get("endpoint_base") or "—"
                info["auth"] = web.get("tipo_auth") or "—"
        except Exception:
            pass
        return info

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        # El BORDE (cuerpo) va directo en el diálogo → siempre visible, sin cortar. El scroll va DENTRO
        # de cuerpo → el scrollbar queda dentro del borde. Mismo scrollbar que el resto de la app.
        cuerpo = QFrame()
        cuerpo.setObjectName("cfgcw")
        cuerpo.setStyleSheet(f"QFrame#cfgcw{{background:{_BG};border:2px solid {_CIAN};border-radius:18px;}}")
        outer.addWidget(cuerpo)
        cv = QVBoxLayout(cuerpo)
        cv.setContentsMargins(8, 8, 8, 8)
        # CABECERA FIJA (título + botón ✕): fuera del scroll → el ✕ queda SIEMPRE visible en la esquina
        # superior derecha, sin desplazarse ni recortarse aunque el contenido desborde.
        hd = QHBoxLayout()
        hd.setContentsMargins(16, 8, 16, 0)
        hd.addWidget(_lbl("⚙  " + tr("canalweb.cfg_title", default="CONFIGURACIÓN DEL CANAL WEB"),
                          bold=True, size=16, color=_CIAN))
        hd.addStretch()
        bx = QPushButton("✕"); bx.setFixedSize(38, 38); bx.setCursor(Qt.CursorShape.PointingHandCursor)
        bx.setStyleSheet(
            f"QPushButton{{background:{_BG};color:{_ROJO};border:2px solid {_ROJO};border-radius:8px;"
            f"font-weight:900;font-size:16px;}}QPushButton:hover{{background:{_ROJO};color:#FFF;}}")
        bx.clicked.connect(self.reject)
        hd.addWidget(bx)
        cv.addLayout(hd)
        from PyQt6.QtWidgets import QScrollArea as _QScrollArea
        try:
            from src.gui.foundation import tokens as _T
            _sb = _T.qss_scrollbar()
        except Exception:
            _sb = ""
        scroll = _QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(_QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}" + _sb)
        cv.addWidget(scroll)
        inner = QWidget()
        inner.setStyleSheet("background:transparent;")
        scroll.setWidget(inner)
        v = QVBoxLayout(inner)
        v.setContentsMargins(24, 14, 24, 22)
        v.setSpacing(10)
        v.addWidget(_lbl(tr("canalweb.cfg_sub",
                            default="Conexiones del canal con credenciales cifradas (Secret Manager)."),
                         size=11, color=_TEXT2))

        # Panel de ESTADO del canal (solo lectura, reutiliza datos existentes): dominio Fable 5,
        # estado, pasarela, conexiones y autenticación. No crea configuración/tablas/modelos nuevos.
        info = self._info_canal()
        panel = QFrame()
        panel.setStyleSheet(f"QFrame{{background:{_BG2};border:1px solid {_BORDE};border-radius:10px;}}")
        pv = QVBoxLayout(panel)
        pv.setContentsMargins(14, 10, 14, 10)
        pv.setSpacing(4)
        pv.addWidget(_lbl(tr("canalweb.estado_title", default="Estado del canal web"), bold=True,
                          size=12, color=_CIAN))
        for etiqueta, val in (
            (tr("canalweb.i_estado", default="Estado del canal"), info["canal_estado"]),
            (tr("canalweb.i_dominio", default="Dominio actual"), info["dominio"]),
            (tr("canalweb.i_tipodom", default="Tipo de dominio"), info["tipo_dom"]),
            (tr("canalweb.i_provdom", default="Proveedor"), info["proveedor_dom"]),
            (tr("canalweb.i_expira", default="Expiración"), info["expira"]),
            (tr("canalweb.i_dns", default="Estado DNS"), info["dns"]),
            (tr("canalweb.i_https", default="Estado HTTPS"), info["https"]),
            (tr("canalweb.i_publicado", default="Última publicación"), info["publicado_en"]),
            (tr("canalweb.i_sync", default="Última sincronización"), info["ultima_sync"]),
            (tr("canalweb.i_prod", default="Productos publicados"), str(info["productos"])),
            (tr("canalweb.i_ped", default="Pedidos pendientes"), str(info["pedidos"])),
            (tr("canalweb.i_res", default="Reservas Click & Collect activas"), str(info["reservas"])),
            (tr("canalweb.i_pasarela", default="Pasarela de pago"), info["pasarela"]),
        ):
            f = QHBoxLayout()
            f.addWidget(_lbl(etiqueta, size=11, color=_TEXT2))
            f.addStretch()
            f.addWidget(_lbl(str(val), size=11, color=_TEXT))
            pv.addLayout(f)
        v.addWidget(panel)

        # ── Acciones de administración del canal (reutilizan comercio_digital.canal_web) ──
        acc_adm = QHBoxLayout(); acc_adm.setSpacing(8)
        for txt, key, handler, prim in (
            ("🔄 " + tr("canalweb.a_sync", default="Sincronizar"), "s", self._acc_sincronizar, False),
            ("📢 " + tr("canalweb.a_publicar", default="Publicar"), "p", self._acc_publicar, False),
            ("♻ " + tr("canalweb.a_regen", default="Regenerar"), "r", self._acc_regenerar, False),
            ("🌐 " + tr("canalweb.a_abrir", default="Abrir web"), "w", self._acc_abrir, False),
            ("⏸ " + tr("canalweb.a_despub", default="Despublicar"), "d", self._acc_despublicar, True)):
            b = (_btn(txt, color_fg=_TEXT2, color_border=_BORDE, hover_bg=_ROJO, h=42) if prim
                 else _btn(txt, color_fg=_CIAN, color_border=_CIAN, hover_bg=_CIAN, h=42))
            b.clicked.connect(handler)
            acc_adm.addWidget(b)
        acc_adm.addStretch()
        v.addLayout(acc_adm)

        # ── Gestión de DOMINIO (cambiar / comprar / renovar; reutiliza canal_web.dominios) ──
        v.addWidget(_lbl(tr("canalweb.dom_title", default="Dominio del canal"), bold=True, size=12,
                         color=_CIAN))
        fdom = QHBoxLayout(); fdom.setSpacing(8)
        self.inp_dom_nuevo = self._inp("", tr("canalweb.dom_ph", default="dominio (empresa.com)"))
        fdom.addWidget(self.inp_dom_nuevo, 1)
        for txt, handler in (("🌐 " + tr("canalweb.dom_cambiar", default="Cambiar"), self._acc_cambiar_dominio),
                             ("🛒 " + tr("canalweb.dom_comprar", default="Comprar"), self._acc_comprar_dominio),
                             ("♻ " + tr("canalweb.dom_renovar", default="Renovar"), self._acc_renovar_dominio)):
            b = _btn(txt, color_fg=_CIAN, color_border=_CIAN, hover_bg=_CIAN, h=40)
            b.clicked.connect(handler)
            fdom.addWidget(b)
        v.addLayout(fdom)
        self.lbl_msg = _lbl("", size=11, color=_TEXT2)
        v.addWidget(self.lbl_msg)

        # ── MARCA / CONFIGURACIÓN COMERCIAL (presencia digital propia) ────────────────────────────────
        #   Canal Web es el ÚNICO editor de la marca de la web (Rearquitectura CD · Fase 2). Reutiliza la
        #   capa de datos `web_tienda` (fila `web_config` que sirve el storefront) vía el servicio
        #   canal_web.config_presencia / guardar_presencia — sin motor nuevo (N7).
        v.addWidget(_lbl(tr("canalweb.marca_title", default="Marca y configuración comercial"),
                         bold=True, size=12, color=_CIAN))
        try:
            from src.services.comercio_digital import canal_web as _cw
            _pre = _cw.config_presencia() or {}
        except Exception:
            _pre = {}
        self.ck_web_activa = QCheckBox(tr("canalweb.m_activa", default="Tienda online activa"))
        self.ck_web_activa.setChecked(bool(_pre.get("activa")))
        self.ck_web_activa.setStyleSheet(
            f"QCheckBox{{color:{_TEXT};font-size:12px;font-family:'{_FONT}';spacing:8px;}}")
        v.addWidget(self.ck_web_activa)
        v.addWidget(_lbl(tr("canalweb.m_nombre_l", default="Nombre de la tienda"), size=11, color=_TEXT2))
        self.inp_web_nombre = self._inp(_pre.get("nombre") or "",
                                        tr("canalweb.m_nombre", default="Nombre de la tienda"))
        v.addWidget(self.inp_web_nombre)
        v.addWidget(_lbl(tr("canalweb.m_desc_l", default="Descripción / eslogan"), size=11, color=_TEXT2))
        self.inp_web_desc = self._inp(_pre.get("descripcion") or "",
                                      tr("canalweb.m_desc", default="Descripción / eslogan"))
        v.addWidget(self.inp_web_desc)
        fmarca = QHBoxLayout(); fmarca.setSpacing(8)
        colc = QVBoxLayout()
        colc.addWidget(_lbl(tr("canalweb.m_color", default="Color de marca (#hex)"), size=11, color=_TEXT2))
        self.inp_web_color = self._inp(_pre.get("color") or "#00FFC6")
        colc.addWidget(self.inp_web_color)
        colm = QVBoxLayout()
        colm.addWidget(_lbl(tr("canalweb.m_moneda", default="Moneda"), size=11, color=_TEXT2))
        self.inp_web_moneda = self._inp(_pre.get("moneda") or "EUR")
        colm.addWidget(self.inp_web_moneda)
        fmarca.addLayout(colc); fmarca.addLayout(colm); fmarca.addStretch()
        v.addLayout(fmarca)
        v.addWidget(_lbl(tr("canalweb.m_logo_l", default="URL del logo (opcional)"), size=11, color=_TEXT2))
        self.inp_web_logo = self._inp(_pre.get("logo_url") or "",
                                      tr("canalweb.m_logo", default="URL del logo (opcional)"))
        v.addWidget(self.inp_web_logo)
        fbm = QHBoxLayout(); fbm.addStretch()
        b_marca = _btn(tr("canalweb.m_guardar", default="GUARDAR MARCA"), color_bg=_VERDE,
                       color_fg="#0D1117", color_border=_VERDE, hover_bg="#FFF", hover_fg="#0D1117", h=42)
        b_marca.clicked.connect(self._guardar_marca)
        fbm.addWidget(b_marca)
        v.addLayout(fbm)

        # ── Configuración AVANZADA (conexiones técnicas: administración/soporte). Plegada por defecto. ──
        self._btn_avz = _btn("⚙  " + tr("canalweb.avz_title", default="Configuración avanzada (conexiones)"),
                             color_fg=_TEXT2, color_border=_BORDE, hover_bg=_CIAN, h=38)
        self._btn_avz.clicked.connect(self._toggle_avanzado)
        v.addWidget(self._btn_avz)
        self._avz = QWidget(); self._avz.setStyleSheet("background:transparent;")
        self._avz.setVisible(False)
        v.addWidget(self._avz)
        av = QVBoxLayout(self._avz); av.setContentsMargins(0, 4, 0, 0); av.setSpacing(10)

        # Tabla de conexiones existentes (reutiliza el estilo neón).
        self.tabla = QTableWidget(0, 5)
        self.tabla.setHorizontalHeaderLabels([
            tr("canalweb.c_canal", default="Canal"), tr("canalweb.c_nombre", default="Nombre"),
            tr("canalweb.c_endpoint", default="Endpoint"), tr("canalweb.c_auth", default="Auth"),
            tr("canalweb.c_estado", default="Estado")])
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(38)
        for ci in range(5):
            self.tabla.horizontalHeader().setSectionResizeMode(ci, QHeaderView.ResizeMode.Stretch)
        self.tabla.setStyleSheet(_ss_tabla_neon())
        self.tabla.setFixedHeight(180)
        _RoundTableCorners(self.tabla)
        self.tabla.itemSelectionChanged.connect(self._sel)
        av.addWidget(self.tabla)

        # Formulario (canal + nombre + endpoint + auth + credencial).
        fila1 = QHBoxLayout(); fila1.setSpacing(8)
        canales = ["web"]
        try:
            from src.services.integraciones import enterprise as _ent
            canales += sorted(_ent.disponibles().keys())
        except Exception:
            pass
        self.cmb_canal = self._combo(canales)
        self.inp_nombre = self._inp("default", tr("canalweb.ph_nombre", default="nombre (default)"))
        fila1.addWidget(self.cmb_canal, 1); fila1.addWidget(self.inp_nombre, 1)
        av.addWidget(_lbl(tr("canalweb.l_canal", default="Canal / nombre de la conexión"), size=11,
                          color=_TEXT2))
        av.addLayout(fila1)
        self.inp_endpoint = self._inp("", tr("canalweb.ph_endpoint", default="https://… (endpoint base)"))
        av.addWidget(_lbl(tr("canalweb.l_endpoint", default="Endpoint base"), size=11, color=_TEXT2))
        av.addWidget(self.inp_endpoint)
        fila2 = QHBoxLayout(); fila2.setSpacing(8)
        try:
            from src.services.comercio_digital import conexiones as _cx
            tipos = list(_cx.TIPOS_AUTH)
        except Exception:
            tipos = ["apikey", "oauth2", "basic", "hmac", "none"]
        self.cmb_auth = self._combo(tipos)
        self.inp_cred = self._inp("", tr("canalweb.ph_cred", default="api_key / token (se cifra)"))
        self.inp_cred.setEchoMode(QLineEdit.EchoMode.Password)
        fila2.addWidget(self.cmb_auth, 1); fila2.addWidget(self.inp_cred, 2)
        av.addWidget(_lbl(tr("canalweb.l_auth", default="Autenticación y credencial"), size=11,
                          color=_TEXT2))
        av.addLayout(fila2)
        av.addSpacing(4)
        acc = QHBoxLayout(); acc.setSpacing(8)
        b_probar = _btn("🔌  " + tr("canalweb.probar", default="Probar"), color_fg=_CIAN,
                        color_border=_CIAN, hover_bg=_CIAN, h=42)
        b_probar.clicked.connect(self._probar)
        b_elim = _btn("🗑  " + tr("canalweb.eliminar", default="Eliminar"), color_fg=_TEXT2,
                      color_border=_BORDE, hover_bg=_ROJO, h=42)
        b_elim.clicked.connect(self._eliminar)
        acc.addWidget(b_probar); acc.addWidget(b_elim); acc.addStretch()
        b_guardar = _btn(tr("canalweb.guardar", default="GUARDAR"), color_bg=_VERDE, color_fg="#0D1117",
                         color_border=_VERDE, hover_bg="#FFF", hover_fg="#0D1117", h=42)
        b_guardar.clicked.connect(self._guardar)
        acc.addWidget(b_guardar)
        av.addLayout(acc)

    def _toggle_avanzado(self):
        self._avz_abierto = not getattr(self, "_avz_abierto", False)
        self._avz.setVisible(self._avz_abierto)
        self._btn_avz.setText(("⚙  " + tr("canalweb.avz_hide", default="Ocultar configuración avanzada"))
                              if self._avz_abierto else
                              ("⚙  " + tr("canalweb.avz_title", default="Configuración avanzada (conexiones)")))

    def _guardar_marca(self):
        """Guarda la MARCA / PRESENCIA de la web reutilizando el servicio canal_web (único editor).
        Feedback INLINE en `self.lbl_msg` (no modales: SOMA activo en el proceso principal)."""
        try:
            from src.services.comercio_digital import canal_web as _cw
            r = _cw.guardar_presencia(
                usuario=self._usuario(),
                activa=1 if self.ck_web_activa.isChecked() else 0,
                nombre=self.inp_web_nombre.text().strip(),
                descripcion=self.inp_web_desc.text().strip(),
                color=self.inp_web_color.text().strip() or "#00FFC6",
                moneda=(self.inp_web_moneda.text().strip() or "EUR").upper(),
                logo_url=self.inp_web_logo.text().strip())
        except Exception as e:
            r = {"ok": False, "error": str(e)}
        if r.get("ok"):
            self.lbl_msg.setText(tr("canalweb.m_ok", default="Marca de la web guardada."))
            self.lbl_msg.setStyleSheet(f"color:{_VERDE};font-size:11px;font-family:'{_FONT}';")
        else:
            self.lbl_msg.setText(tr("canalweb.m_err", default="No se pudo guardar la marca: {e}",
                                    e=r.get("error") or r.get("permiso") or "error"))
            self.lbl_msg.setStyleSheet(f"color:{_ROJO};font-size:11px;font-family:'{_FONT}';")

    # ── Acciones de administración del canal (reutilizan canal_web) ──────────────
    def _usuario(self):
        try:
            from src.db.usuario import sesion_global
            return sesion_global.usuario_actual or None
        except Exception:
            return None

    def _acc(self, fn, ok_txt):
        try:
            r = fn(usuario=self._usuario())
            self.lbl_msg.setText(ok_txt if r.get("ok") else str(r.get("error") or r.get("motivo") or ""))
        except Exception as e:
            self.lbl_msg.setText(str(e))
        try:
            self._refrescar()
        except Exception:
            pass

    def _acc_sincronizar(self):
        from src.services.comercio_digital import canal_web
        self._acc(canal_web.sincronizar, tr("canalweb.msg_sync", default="Catálogo sincronizado."))

    def _acc_publicar(self):
        from src.services.comercio_digital import canal_web
        self._acc(canal_web.publicar, tr("canalweb.msg_pub", default="Canal publicado."))

    def _acc_regenerar(self):
        from src.services.comercio_digital import canal_web
        self._acc(canal_web.regenerar, tr("canalweb.msg_regen", default="Credenciales regeneradas."))

    def _acc_despublicar(self):
        from src.services.comercio_digital import canal_web
        self._acc(canal_web.despublicar, tr("canalweb.msg_desp", default="Canal despublicado."))

    def _acc_abrir(self):
        try:
            from src.services.comercio_digital import canal_web
            url = (canal_web.estado() or {}).get("endpoint")
            if not url:
                self.lbl_msg.setText(tr("canalweb.sin_url", default="El canal no tiene URL."))
                return
            if not url.lower().startswith(("http://", "https://")):
                url = "https://" + url
            import webbrowser
            webbrowser.open(url)
        except Exception as e:
            self.lbl_msg.setText(str(e))

    # ── Gestión de dominio (reutiliza canal_web.dominios) ──
    def _acc_cambiar_dominio(self):
        from src.gui.mfa_gui import step_up_sesion
        from src.services.comercio_digital import canal_web
        dom = self.inp_dom_nuevo.text().strip()
        if not dom:
            self.lbl_msg.setText(tr("canalweb.dom_sin", default="Indica el dominio."))
            return
        if not step_up_sesion("canal_web.dominios", self):
            return
        r = canal_web.cambiar_dominio(dom, usuario=self._usuario())
        self.lbl_msg.setText(tr("canalweb.dom_ok", default="Dominio actualizado.") if r.get("ok")
                             else str(r.get("error") or r.get("motivo") or ""))

    def _acc_comprar_dominio(self):
        from src.gui.mfa_gui import step_up_sesion
        from src.services.comercio_digital import canal_web
        dom = self.inp_dom_nuevo.text().strip()
        if not dom:
            self.lbl_msg.setText(tr("canalweb.dom_sin", default="Indica el dominio."))
            return
        if not step_up_sesion("canal_web.dominios", self):
            return
        r = canal_web.comprar_dominio(dom, usuario=self._usuario())
        self.lbl_msg.setText(tr("canalweb.dom_comprado", default="Dominio comprado.") if r.get("ok")
                             else str(r.get("motivo") or r.get("error") or ""))

    def _acc_renovar_dominio(self):
        from src.gui.mfa_gui import step_up_sesion
        from src.services.comercio_digital import canal_web
        da = canal_web.dominio_activo()
        if not da:
            self.lbl_msg.setText(tr("canalweb.dom_none", default="No hay dominio activo."))
            return
        if not step_up_sesion("canal_web.dominios", self):
            return
        r = canal_web.renovar_dominio(da["dominio"], usuario=self._usuario())
        self.lbl_msg.setText(tr("canalweb.dom_renov", default="Dominio renovado.") if r.get("ok")
                             else str(r.get("error") or ""))

    def _refrescar(self):
        self.tabla.setRowCount(0)
        try:
            from src.services.comercio_digital import conexiones as _cx
            filas = _cx.listar()
        except Exception:
            filas = []
        for cx in filas:
            r = self.tabla.rowCount(); self.tabla.insertRow(r)
            vals = [cx.get("canal") or "—", cx.get("nombre") or "default",
                    cx.get("endpoint_base") or "—", cx.get("tipo_auth") or "—",
                    cx.get("estado") or "—"]
            for c, val in enumerate(vals):
                it = QTableWidgetItem(str(val))
                if c in (3, 4):
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tabla.setItem(r, c, it)

    def _sel(self):
        r = self.tabla.currentRow()
        if r < 0:
            return
        canal = self.tabla.item(r, 0).text() if self.tabla.item(r, 0) else ""
        nombre = self.tabla.item(r, 1).text() if self.tabla.item(r, 1) else "default"
        i = self.cmb_canal.findData(canal)
        if i >= 0:
            self.cmb_canal.setCurrentIndex(i)
        self.inp_nombre.setText(nombre)
        self.inp_endpoint.setText(self.tabla.item(r, 2).text() if self.tabla.item(r, 2) else "")

    def _guardar(self):
        try:
            from src.services.comercio_digital import conexiones as _cx
            cred = self.inp_cred.text().strip()
            ok = _cx.registrar(
                self.cmb_canal.currentData(), nombre=self.inp_nombre.text().strip() or "default",
                tipo_auth=self.cmb_auth.currentData(), endpoint_base=self.inp_endpoint.text().strip(),
                credenciales=({"api_key": cred} if cred else None), actor="canal_web_config")
            self.lbl_msg.setText(tr("canalweb.msg_ok", default="Conexión guardada.") if ok
                                 else tr("canalweb.msg_err", default="No se pudo guardar."))
            self.inp_cred.clear()
            self._refrescar()
        except Exception as e:
            self.lbl_msg.setText(str(e))

    def _probar(self):
        try:
            from src.services.comercio_digital import conexiones as _cx
            r = _cx.probar(self.cmb_canal.currentData(),
                           nombre=self.inp_nombre.text().strip() or "default")
            self.lbl_msg.setText(("✓ " if r.get("ok") else "✕ ") + str(r.get("motivo", "")))
        except Exception as e:
            self.lbl_msg.setText(str(e))

    def _eliminar(self):
        try:
            from src.services.comercio_digital import conexiones as _cx
            _cx.eliminar(self.cmb_canal.currentData(),
                         nombre=self.inp_nombre.text().strip() or "default")
            self._refrescar()
            self.lbl_msg.setText(tr("canalweb.msg_del", default="Conexión eliminada."))
        except Exception as e:
            self.lbl_msg.setText(str(e))


# Alias de compatibilidad (Strangler): el nombre privado histórico sigue disponible durante la transición.
_CanalWebConfigDialog = CanalWebConfigDialog
