"""
Selector de centro ("Cambiar de Centro" — antes "Selector de tienda", F1).

Diálogo para cambiar de centro operativo (tienda) sin cerrar sesión, o simplemente ELEGIR un centro
(modo="elegir", p. ej. para vincular un empleado — ver `gestion_usuarios.py::_de_vincular_centro`).
Lista `centros_trabajo` ("Centros de empresa" unificados, migración 0257 — identidad de cada centro
físico: tienda/almacén/fábrica/oficina/otro, ver `db/centros.py`; antes listaba `centros_perfil`,
tabla retirada), aislados por `creado_por_id` = superadmin actual (aislamiento entre superadmins),
con un desbloqueo puntual por PIN para ver también los centros de OTRO superadmin.

Seleccionar un centro tipo 'tienda' con `id_tienda` vinculado SIGUE cambiando el TenantContext real
(`tiendas_db.cambiar_contexto_tienda`), exactamente como antes (F1). Seleccionar cualquier otro tipo
NO toca ese contexto operativo — solo marca el "centro en foco" (`sesion_global.set_centro_en_foco`,
puramente informativo) para pantallas de administración/identidad. La empresa es implícita (la app
es mono-empresa hoy, confirmado por auditoría) — no hay selector de empresa.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from assets.estilo_global import _blindar_tamano_fijo
from src.db import centros as centros_db
from src.db import empresa as emp_db
from src.db import tiendas as tiendas_db
from src.db.usuario import listar_usuarios, sesion_global, validar_pin_de_usuario
from src.utils.i18n import tr

_BG = "#0E1117"
_BG2 = "#161B22"
_CIAN = "#00FFC6"
_BORDE = "#30363D"
_TEXT = "#E6EDF3"
_DIM = "#8B949E"
_ROJO = "#F85149"

_ICONOS_TIPO = {"tienda": "🏬", "almacen": "📦", "fabrica": "🏭", "oficina": "🏢", "otro": "📍"}


def _btn_x(slot=None) -> QPushButton:
    """Botón rojo ✕ (cerrar), esquina superior derecha — mismo patrón unificado que el resto de
    diálogos de la app (ver `gui/canal_web_gui.py::_btn_x`)."""
    b = QPushButton("✕")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFixedSize(36, 36)
    b.setStyleSheet(
        "QPushButton{background:transparent;color:#FF4C4C;border:none;border-radius:18px;"
        "padding:0;font-weight:900;font-size:16px;}"
        "QPushButton:hover{background:#FF4C4C;color:#0D1117;}")
    b.setProperty("sin_glow", True)
    # Blindaje de tamaño fijo (ver `assets/estilo_global.py::_blindar_tamano_fijo`): sin esto, el
    # filtro global de estilos reinicia la política de tamaño a Minimum en cada Show/Polish de este
    # diálogo frameless+translúcido, e infla el ancho del botón (redondo en reposo, "píldora" ancha
    # al hacer hover) — mismo patrón que `gui/canal_web_gui.py::_btn_x`.
    _blindar_tamano_fijo(b, 36, 36)
    if slot:
        b.clicked.connect(slot)
    return b


class SelectorCentroDialog(QDialog):
    """Devuelve el centro/tienda elegido (dict) en `get_resultado()`, o None si se cerró sin elegir.

    modo="cambiar" (por defecto, F1): elegir un centro tipo 'tienda' vinculado cambia el contexto
    operativo real (TenantContext); cualquier otro tipo solo marca "centro en foco".
    modo="elegir": ninguna selección toca el TenantContext ni el centro en foco — solo se devuelve
    el centro elegido (usado por «🔗 Vincular a centro» en Configuración)."""

    def __init__(self, parent=None, modo="cambiar"):
        super().__init__(parent)
        self._modo = modo
        self._resultado: dict | None = None
        self._creadores_desbloqueados: set = set()
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(560)
        self._build()
        self._cargar_centros()

    def _build(self):
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        card = QFrame(); card.setObjectName("selCentro")
        card.setStyleSheet(f"QFrame#selCentro{{background:{_BG};border:2px solid {_CIAN};"
                           f"border-radius:20px;}}")
        outer.addWidget(card)
        lay = QVBoxLayout(card); lay.setContentsMargins(24, 18, 24, 22); lay.setSpacing(12)

        cab = QHBoxLayout()
        tit = QLabel("🏪  " + tr("centro.titulo", default="CAMBIAR DE CENTRO"))
        tit.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;"
                          f"font-size:17px;background:transparent;")
        cab.addWidget(tit); cab.addStretch()
        cab.addWidget(_btn_x(self.reject))
        lay.addLayout(cab)

        sub = QLabel(tr("centro.sub", default="Selecciona el centro que quieres gestionar."))
        sub.setStyleSheet(f"color:{_DIM};font-family:'Segoe UI';font-weight:700;"
                          f"font-size:15px;background:transparent;")
        lay.addWidget(sub)

        # Lista de centros (scroll). Fondo = _BG (el MISMO que la card del diálogo, no _BG2 —
        # antes usaba _BG2/#161B22, un gris más claro que el fondo real del diálogo (#0E1117),
        # lo que dejaba una "caja" gris visible con costura alrededor de la lista, ver Fix 3).
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFixedHeight(300)
        scroll.setStyleSheet(
            f"QScrollArea{{background:{_BG};border:1px solid {_BORDE};border-radius:12px;}}"
            f"QScrollBar:vertical{{background:transparent;width:10px;margin:4px;}}"
            f"QScrollBar::handle:vertical{{background:{_CIAN};border-radius:5px;min-height:28px;}}"
            f"QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0;}}")
        self._cont = QWidget(); self._cont.setStyleSheet("background:transparent;")
        self._cont_lay = QVBoxLayout(self._cont)
        self._cont_lay.setContentsMargins(8, 8, 8, 8); self._cont_lay.setSpacing(6)
        self._cont_lay.addStretch()
        scroll.setWidget(self._cont)
        lay.addWidget(scroll)

        # Aislamiento entre superadmins: desbloqueo puntual (no persistente) por PIN del creador.
        fila = QHBoxLayout()
        b_unlock = QPushButton("🔓  " + tr("centro.otros_superadmin",
                                          default="VER CENTROS DE OTROS SUPERADMINS"))
        b_unlock.setCursor(Qt.CursorShape.PointingHandCursor); b_unlock.setFixedHeight(44)
        # Mismo patrón turquesa que "Cambiar PIN"/"Editar perfil"/"Vincular a centro"/"Resetear MFA"
        # en `gestion_usuarios.py::_crear_page_perfiles` (fuente única del estilo de botón
        # secundario turquesa) — font-size +1pt (14px -> 15px) respecto a la referencia.
        b_unlock.setStyleSheet(
            f"QPushButton{{background:#0D1117;color:{_CIAN};border:2px solid {_CIAN};"
            f"border-radius:12px;font-family:'Segoe UI';font-weight:bold;font-size:15px;"
            f"padding:0 12px;}}"
            f"QPushButton:hover{{background:{_CIAN};color:#0E1117;}}")
        b_unlock.clicked.connect(self._desbloquear_otro_superadmin)
        fila.addWidget(b_unlock); fila.addStretch()
        lay.addLayout(fila)

    def _empresa_actual(self):
        return emp_db.empresa_actual_id()

    def _usuario_actual_id(self):
        try:
            return (sesion_global.usuario_actual or {}).get("id")
        except Exception:
            return None

    def _cargar_centros(self):
        # Limpiar lista (menos el stretch final).
        while self._cont_lay.count() > 1:
            it = self._cont_lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()

        id_empresa = self._empresa_actual()
        uid = self._usuario_actual_id()
        centros = list(centros_db.listar_centros(id_empresa, creado_por_id=uid))
        vistos = {c.get("id_centro") for c in centros}
        for creador in self._creadores_desbloqueados:
            for c in centros_db.listar_centros(id_empresa, creado_por_id=creador):
                if c.get("id_centro") not in vistos:
                    centros.append(c); vistos.add(c.get("id_centro"))

        actual = emp_db.tienda_actual_id()
        if not centros:
            vacio = QLabel(tr("centro.vacio", default="No hay centros dados de alta todavía "
                                                        "(añádelos en Configuración → Datos de empresa)."))
            vacio.setWordWrap(True)
            vacio.setStyleSheet(f"color:{_DIM};font-family:'Segoe UI';font-size:12px;"
                                f"background:transparent;padding:14px;")
            self._cont_lay.insertWidget(0, vacio)
            return
        for i, c in enumerate(centros):
            # Guardia contra falso positivo: si el centro NO está vinculado a una tienda real
            # (`id_tienda is None` — en la práctica ya no debería ocurrir para centros nuevos: F1
            # cierra la brecha con AUTO-PROVISIONING, `gestion_usuarios.py::_de_add_centro` crea la
            # tienda real en la misma operación de alta vía `tiendas_db.crear_tienda`; esta guardia
            # queda como red de seguridad, p. ej. para datos legados ya cubiertos por la migración
            # de backfill) y tampoco hay contexto activo (`actual is None`), `None == None`
            # marcaría "✓ ACTUAL" sobre un centro que en realidad nunca puede activar el
            # TenantContext (root cause del bug F1 original).
            id_t = c.get("id_tienda")
            es_actual = c.get("tipo_centro") == "tienda" and id_t is not None and id_t == actual
            self._cont_lay.insertWidget(i, self._fila_centro(c, es_actual=es_actual))

    def _fila_centro(self, c, es_actual=False) -> QPushButton:
        icono = _ICONOS_TIPO.get(c.get("tipo_centro"), "📍")
        codigo = c.get("codigo_centro") or f"CTR-{c.get('id_centro')}"
        nombre = c.get("nombre_centro") or ""
        suf = ("   ✓ " + tr("centro.actual", default="ACTUAL")) if es_actual else ""
        b = QPushButton(f"  {icono}   {codigo}   ·   {nombre}{suf}")
        b.setCursor(Qt.CursorShape.PointingHandCursor); b.setFixedHeight(48)
        borde = _CIAN if es_actual else _BORDE
        b.setStyleSheet(
            f"QPushButton{{background:{_BG};color:{_TEXT};border:2px solid {borde};"
            f"border-radius:10px;text-align:left;padding:0 14px;font-family:'Segoe UI';"
            f"font-weight:900;font-size:13px;}}"
            f"QPushButton:hover{{border-color:{_CIAN};background:#11312B;}}")
        b.clicked.connect(lambda _c, cd=c: self._elegir(cd))
        return b

    def _elegir(self, c):
        if self._modo == "elegir":
            # Solo devolver el centro elegido: no toca TenantContext ni centro en foco (usado por
            # "Vincular a centro").
            self._resultado = c
            self.accept()
            return
        if c.get("tipo_centro") == "tienda" and c.get("id_tienda"):
            res = tiendas_db.cambiar_contexto_tienda(c.get("id_tienda"))
            if res:
                self._resultado = res
                try:
                    sesion_global.set_centro_en_foco(c)
                except Exception:
                    pass
                self.accept()
            return
        # Centro NO operativo (almacén/fábrica/oficina/otro): no toca el TenantContext real, solo
        # marca el "centro en foco" para pantallas de administración/identidad.
        try:
            sesion_global.set_centro_en_foco(c)
        except Exception:
            pass
        self._resultado = c
        self.accept()

    def _desbloquear_otro_superadmin(self):
        """Aislamiento entre superadmins: por defecto solo se listan los centros creados por el
        superadmin actual (`creado_por_id`). Este desbloqueo, puntual y NO persistente (solo para
        esta instancia del diálogo), exige el PIN del OTRO superadmin creador
        (`db.usuario.validar_pin_de_usuario` — NUNCA el step-up MFA, mecanismo distinto, ver
        CLAUDE.md) antes de incluir sus centros en la lista."""
        uid_actual = self._usuario_actual_id()
        otros = [u for u in (listar_usuarios() or [])
                if str(u.get("perfil", "")).upper() == "SUPERADMIN" and u.get("id") != uid_actual]
        if not otros:
            _MensajeDialog(
                tr("centro.sin_otros_t", default="Sin otros superadmins"),
                tr("centro.sin_otros_msg", default="No hay otro superadmin en el sistema."),
                self).exec()
            return
        dlg = _DesbloqueoSuperadminDialog(otros, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        uid_otro, pin = dlg.valores()
        if not uid_otro or not pin:
            return
        res = validar_pin_de_usuario(uid_otro, pin)
        if not res:
            _MensajeDialog(tr("centro.pin_error_t", default="PIN incorrecto"),
                           tr("centro.pin_error_msg", default="El PIN introducido no es correcto."),
                           self).exec()
            return
        self._creadores_desbloqueados.add(uid_otro)
        self._cargar_centros()

    def get_resultado(self) -> dict | None:
        return self._resultado


class _DesbloqueoSuperadminDialog(QDialog):
    """Sub-diálogo del desbloqueo de aislamiento: elegir el superadmin creador + su PIN de 4
    dígitos (`validar_pin_de_usuario`)."""

    def __init__(self, superadmins, parent=None):
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(360)
        card = QFrame(self); card.setObjectName("desb")
        card.setStyleSheet(f"QFrame#desb{{background:{_BG};border:2px solid {_CIAN};"
                           f"border-radius:18px;}}")
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.addWidget(card)
        ly = QVBoxLayout(card); ly.setContentsMargins(22, 20, 22, 20); ly.setSpacing(10)

        tit = QLabel(tr("centro.desb_titulo", default="DESBLOQUEAR CENTROS DE OTRO SUPERADMIN"))
        tit.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:13px;"
                          f"background:transparent;")
        tit.setWordWrap(True)
        ly.addWidget(tit)

        self.cmb = QComboBox(); self.cmb.setFixedHeight(38)
        self.cmb.setStyleSheet(
            f"QComboBox{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:9px;padding:0 12px;font-size:13px;}}"
            f"QComboBox QAbstractItemView{{background:#0D1117;color:{_TEXT};"
            f"border:2px solid {_CIAN};selection-background-color:{_CIAN};selection-color:#0D1117;}}")
        for u in superadmins:
            self.cmb.addItem(str(u.get("nombre") or f"#{u.get('id')}"), u.get("id"))
        ly.addWidget(self.cmb)

        self.inp_pin = QLineEdit()
        self.inp_pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_pin.setMaxLength(4)
        self.inp_pin.setPlaceholderText(tr("centro.pin_ph", default="PIN (4 dígitos) de ese superadmin"))
        self.inp_pin.setFixedHeight(38)
        self.inp_pin.setStyleSheet(
            f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:9px;padding:0 12px;font-size:14px;}}"
            f"QLineEdit:focus{{border-color:{_CIAN};}}")
        ly.addWidget(self.inp_pin)

        fila = QHBoxLayout(); fila.addStretch()
        bc = QPushButton(tr("cfg.ban_cancelar", default="CANCELAR")); bc.setFixedHeight(36)
        bc.setCursor(Qt.CursorShape.PointingHandCursor)
        bc.setStyleSheet("QPushButton{background:#0E1117;color:#F85149;border:2px solid #F85149;"
                        "border-radius:8px;font-weight:900;font-size:12px;padding:0 16px;}"
                        "QPushButton:hover{background:#F85149;color:#0E1117;}")
        bc.clicked.connect(self.reject)
        bo = QPushButton(tr("centro.desbloquear", default="DESBLOQUEAR")); bo.setFixedHeight(36)
        bo.setCursor(Qt.CursorShape.PointingHandCursor)
        bo.setStyleSheet(f"QPushButton{{background:#0E1117;color:{_CIAN};border:2px solid {_CIAN};"
                         f"border-radius:8px;font-weight:900;font-size:12px;padding:0 16px;}}"
                         f"QPushButton:hover{{background:{_CIAN};color:#0E1117;}}")
        bo.clicked.connect(self.accept)
        fila.addWidget(bc); fila.addWidget(bo)
        ly.addLayout(fila)

    def valores(self):
        return self.cmb.currentData(), self.inp_pin.text().strip()


class _MensajeDialog(QDialog):
    """Aviso simple frameless (p. ej. PIN incorrecto) — mismo patrón visual que el resto de
    diálogos de este selector."""

    def __init__(self, titulo, mensaje, parent=None):
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(340)
        card = QFrame(self)
        card.setStyleSheet(f"background:{_BG};border:2px solid {_ROJO};border-radius:16px;")
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.addWidget(card)
        ly = QVBoxLayout(card); ly.setContentsMargins(20, 18, 20, 18); ly.setSpacing(8)
        t = QLabel(titulo)
        # `border:none` explícito (Fix 2): sin él, QLabel (subclase de QFrame) puede acabar
        # pintando un borde "fantasma" redondeado, en el MISMO color que el texto, propio del
        # motor de estilos de Qt (WA_StyledBackground + hoja de estilos de app + re-polish
        # diferido tras el primer show — confirmado con una prueba headless aislada: el mismo
        # QLabel sin `border:none` pinta el borde, y deja de hacerlo en cuanto se añade). Esto
        # era lo que parecía "una caja roja interior separada" alrededor del título/mensaje.
        t.setStyleSheet(f"color:{_ROJO};font-weight:900;font-size:14px;background:transparent;"
                        f"border:none;")
        ly.addWidget(t)
        m = QLabel(mensaje); m.setWordWrap(True)
        m.setStyleSheet(f"color:{_TEXT};font-size:12px;background:transparent;border:none;")
        ly.addWidget(m)
        fila = QHBoxLayout(); fila.addStretch()
        bo = QPushButton(tr("cfg.aceptar", default="ACEPTAR")); bo.setFixedHeight(34)
        bo.setCursor(Qt.CursorShape.PointingHandCursor)
        bo.setStyleSheet(f"QPushButton{{background:#0E1117;color:{_CIAN};border:2px solid {_CIAN};"
                         f"border-radius:8px;font-weight:900;font-size:12px;padding:0 16px;}}"
                         f"QPushButton:hover{{background:{_CIAN};color:#0E1117;}}")
        bo.clicked.connect(self.accept)
        fila.addWidget(bo)
        ly.addLayout(fila)


# Compatibilidad hacia atrás: el nombre histórico ("SelectorTiendaDialog", F1) seguía en uso en
# varios puntos de llamada (`menu_principal.py`, `paneles/panel_tareas_empleados.py`) — mismo
# objeto, sin necesidad de tocar esos imports.
SelectorTiendaDialog = SelectorCentroDialog
