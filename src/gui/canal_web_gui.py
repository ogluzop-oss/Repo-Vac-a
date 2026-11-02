"""
Canal Web · Entrada del ecosistema web (Fases WEB-02/WEB-12+). El Canal Web es el ORQUESTADOR: al entrar
muestra ÚNICAMENTE una pregunta — ¿la empresa ya tiene página web?

  • SÍ → ventana de 3 columnas (E-commerce / Marketplace / Web tradicional) → Integraciones Comerciales.
  • NO → creación con el EDITOR VISUAL propio de Smart Manager (Fase 4 e-commerce,
    `gui/tema_editor_dialog.TemaEditorDialog`): ya no se delega en un proveedor externo — Smart Manager
    genera la tienda online íntegramente (secciones/bloques, vista previa en vivo, IA de contenido).
    (Los métodos conservan el nombre histórico `_pagina_creador_web`, heredado de los proveedores
    externos que ocupaban antes este ramal — Hostinger primero, Shopify después —, sin relación con el
    adaptador Hostinger de Integraciones Comerciales, ver `gui/integraciones_comerciales_gui.py`.)

Reutiliza el orquestador de `services/comercio_digital/canal_web`. Autónoma respecto al TPV.
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                             QStackedWidget, QVBoxLayout, QWidget)

from assets.estilo_global import _blindar_tamano_fijo

logger = logging.getLogger("gui.canal_web")

_CIAN = "#00FFC6"
_BG = "#0E1117"
_BG2 = "#161B22"
_TEXT2 = "#8B949E"


def _btn_x(slot=None):
    """Botón rojo ✕ (cerrar) para la esquina superior derecha, estilo unificado de la app."""
    b = QPushButton("✕")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFixedSize(50, 50)
    b.setStyleSheet("QPushButton{background:transparent;color:#FF4C4C;border:none;"
                    "border-radius:25px;padding:0;font-weight:900;font-size:18px;}"
                    "QPushButton:hover{background:#FF4C4C;color:#0D1117;}")
    b.setProperty("sin_glow", True)
    _blindar_tamano_fijo(b, 50, 50)
    if slot:
        b.clicked.connect(slot)
    return b


def _abrir_ventana_completa(ventana, origen=None):
    """Abre una ventana HIJA a pantalla completa, SIN la barra de título nativa de Windows, con la
    MISMA animación de deslizamiento de entrada que usa `menu_principal.manejar_apertura`. Canal Web
    abre sus ventanas (CanalWebWindow, IntegracionesComercialesWindow) directamente, fuera de
    `manejar_apertura`, así que replica aquí ese mismo tratamiento (si no, se ven con la barra de
    título nativa de Windows, inconsistente con el resto de módulos, todos frameless)."""
    try:
        ventana.setWindowFlags(ventana.windowFlags() | Qt.WindowType.FramelessWindowHint)
    except Exception:
        pass
    snap = None
    try:
        if origen is not None:
            from src.gui.transiciones import capturar_pantalla
            snap = capturar_pantalla(origen)
    except Exception:
        pass
    try:
        from PyQt6.QtWidgets import QApplication
        ventana.setWindowOpacity(0.0)
        scr = ventana.screen() or QApplication.primaryScreen()
        if scr is not None:
            ventana.setGeometry(scr.availableGeometry())
    except Exception:
        pass
    ventana.showMaximized()
    try:
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
    except Exception:
        pass
    try:
        from src.gui.transiciones import deslizar_entrada_modulo
        deslizar_entrada_modulo(snap, ventana, revelar=ventana)
    except Exception:
        try:
            ventana.setWindowOpacity(1.0)
        except Exception:
            pass


def _boton(texto, primario=True):
    """Botón con el diseño estándar de la app: contorno turquesa, fondo azul oscuro, texto turquesa y hover
    swap (tanto para primario como secundario; `primario` solo cambia el grosor tipográfico)."""
    b = QPushButton(texto)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setMinimumHeight(46)
    peso = "900" if primario else "800"
    b.setStyleSheet(f"QPushButton{{background:{_BG2};color:{_CIAN};border:2px solid {_CIAN};"
                    f"border-radius:10px;font-weight:{peso};padding:8px 18px;}}"
                    f"QPushButton:hover{{background:{_CIAN};color:{_BG};}}")
    return b


class CanalWebWindow(QWidget):
    """Ventana de entrada del Canal Web. `on_ir_marketplace` = callback opcional para abrir Marketplace ›
    Integraciones Comerciales (lo cablea el menú); si no se aporta, abre la ventana directamente."""

    def __init__(self, id_empresa=None, usuario=None, on_ir_marketplace=None, parent=None):
        super().__init__(parent)
        self._id_empresa = id_empresa
        self._usuario = usuario
        self._on_ir_marketplace = on_ir_marketplace
        self.setStyleSheet(f"background:{_BG};color:#E6E6E6;")
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 24, 30, 24)
        root.setSpacing(16)

        cab = QHBoxLayout()
        titulo = QLabel("🌐 CANAL WEB")
        titulo.setStyleSheet(f"color:{_CIAN};font-size:24px;font-weight:900;")
        cab.addWidget(titulo)
        cab.addStretch()
        cab.addWidget(_btn_x(self._cerrar_o_volver))   # ✕ roja (esquina superior derecha)
        root.addLayout(cab)

        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)
        self._stack.addWidget(self._pagina_pregunta())    # 0
        self._stack.addWidget(self._pagina_creador_web())   # 1 (ramal "No": crear con el Editor Visual)
        self._stack.addWidget(self._pagina_tipo_web())    # 2 (ramal "Sí": ¿qué tipo de web?)
        self._stack.setCurrentIndex(0)
        # Deslizamiento (mismo lenguaje visual que el resto de la app) en CADA cambio de pantalla
        # dentro de Canal Web (pregunta → creador/tipo y vuelta) — entrada Y salida, es el mismo
        # efecto en ambos sentidos.
        try:
            from src.gui.transiciones import instalar_transicion_stack
            instalar_transicion_stack(self._stack)
        except Exception as e:
            logger.debug("instalar_transicion_stack canal web: %s", e)

    # ── Página 0: SOLO la pregunta inicial ──
    def _pagina_pregunta(self) -> QWidget:
        w = QWidget()
        ly = QVBoxLayout(w)
        ly.setSpacing(16)
        ly.addStretch(1)
        preg = QLabel("¿Tu empresa ya dispone de una página web?")
        preg.setStyleSheet("font-size:22px;font-weight:800;")
        preg.setWordWrap(True)
        preg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ly.addWidget(preg)
        fila = QHBoxLayout()
        fila.setSpacing(16)
        fila.addStretch()
        b_si = _boton("Sí", primario=True)
        b_si.setMinimumWidth(180)
        b_si.clicked.connect(lambda: self._elegir(tiene_web=True))
        b_no = _boton("No", primario=False)
        b_no.setMinimumWidth(180)
        b_no.clicked.connect(lambda: self._elegir(tiene_web=False))
        fila.addWidget(b_si)
        fila.addWidget(b_no)
        fila.addStretch()
        ly.addLayout(fila)
        ly.addStretch(2)
        return w

    # ── Página 1: creación con el EDITOR VISUAL propio de Smart Manager ──
    def _pagina_creador_web(self) -> QWidget:
        w = QWidget()
        ly = QVBoxLayout(w)
        ly.setSpacing(14)
        ly.addStretch(1)
        t = QLabel("Crea tu página web con Smart Manager")
        t.setStyleSheet(f"color:{_CIAN};font-size:22px;font-weight:900;")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ly.addWidget(t)
        prov = QLabel("Motor de creación propio:  EDITOR VISUAL (IA)")
        prov.setStyleSheet(f"color:{_CIAN};font-size:14px;font-weight:800;")
        prov.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ly.addWidget(prov)
        exp = QLabel("Smart Manager genera tu tienda online íntegramente: secciones y bloques "
                     "reordenables, vista previa en vivo con tu catálogo real y asistente de IA para los "
                     "textos — sin depender de ningún proveedor externo.")
        exp.setWordWrap(True)
        exp.setAlignment(Qt.AlignmentFlag.AlignCenter)
        exp.setStyleSheet(f"color:{_TEXT2};font-size:13px;")
        ly.addWidget(exp)
        fila = QHBoxLayout()
        fila.addStretch()
        b = _boton("🎨  Crear mi web con el Editor Visual", primario=True)
        b.setMinimumWidth(340)
        b.clicked.connect(self._abrir_editor_creacion)
        fila.addWidget(b)
        fila.addStretch()
        ly.addLayout(fila)
        ly.addStretch(2)
        return w

    def _abrir_editor_creacion(self):
        """Abre el editor visual WYSIWYG propio (Fase 4 e-commerce, `TemaEditorDialog`) para crear la
        tienda desde cero — con la MISMA animación de deslizamiento de entrada/salida que el resto de
        ventanas a pantalla completa de la app."""
        try:
            from src.gui.tema_editor_dialog import TemaEditorDialog
            from src.gui.transiciones import abrir_dialogo_deslizante
            abrir_dialogo_deslizante(TemaEditorDialog(self, usuario=self._usuario), self)
        except Exception as e:
            logger.debug("abrir editor creacion: %s", e)

    def _cerrar_ventana(self):
        """Cierra ESTA ventana (Canal Web) con la MISMA animación de deslizamiento de salida que el
        resto de ventanas a pantalla completa de la app (`CanalWebWindow` es un `QWidget` plano, no un
        `QDialog` — el helper correspondiente es `deslizar_salida_y_cerrar`, no
        `instalar_cierre_deslizante`, que es solo para diálogos)."""
        try:
            from src.gui.transiciones import deslizar_salida_y_cerrar
            deslizar_salida_y_cerrar(self, self.close)
        except Exception:
            self.close()

    def _cerrar_o_volver(self):
        """✕: navega hacia atrás. Desde el editor de creación (ramal "No") o desde la selección de tipo
        (ramal "Sí", 3 columnas) → a la pregunta inicial (AMBOS ramales cuelgan directamente de la
        pregunta, no son pasos secuenciales entre sí). En la pregunta inicial → cierra la ventana."""
        idx = self._stack.currentIndex()
        if idx in (1, 2):
            self._stack.setCurrentIndex(0)
        else:
            self._cerrar_ventana()

    # ── Página 2: ramal "Sí" → ¿qué tipo de plataforma es tu web? (3 columnas) ──
    def _pagina_tipo_web(self) -> QWidget:
        w = QWidget()
        ly = QVBoxLayout(w)
        ly.setSpacing(12)
        t = QLabel("¿Qué tipo de plataforma es tu web?")
        t.setStyleSheet("font-size:20px;font-weight:800;")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ly.addWidget(t)
        sub = QLabel("Elige el tipo de tu web actual para conectarla con Smart Manager.")
        sub.setStyleSheet(f"color:{_TEXT2};font-size:12px;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ly.addWidget(sub)
        cols = QHBoxLayout(); cols.setSpacing(16)
        cols.addStretch()
        cols.addWidget(self._columna_tipo(
            "🛒  E-COMMERCE", "Tu propia tienda online",
            ["WooCommerce", "Shopify", "PrestaShop", "Magento", "OpenCart"], "ecommerce"))
        cols.addWidget(self._columna_tipo(
            "📦  MARKETPLACE", "Vendes en un tercero",
            ["Amazon", "eBay", "Miravia", "AliExpress", "TikTok Shop"], "marketplace"))
        cols.addWidget(self._columna_tipo(
            "🌐  WEB TRADICIONAL", "Tu web con otro proveedor",
            ["Wix", "WordPress", "Squarespace", "Web a medida", "(catálogo por feed o API REST)"],
            "web_tradicional"))
        cols.addStretch()
        ly.addLayout(cols)
        ly.addStretch(1)
        return w

    def _columna_tipo(self, titulo, subtitulo, ejemplos, tipo) -> QWidget:
        card = QFrame()
        card.setFixedWidth(310)
        card.setStyleSheet(f"QFrame{{background:{_BG2};border:2px solid {_CIAN};border-radius:14px;}}")
        cl = QVBoxLayout(card); cl.setContentsMargins(18, 18, 18, 18); cl.setSpacing(9)
        t = QLabel(titulo)
        t.setStyleSheet(f"color:{_CIAN};font-size:16px;font-weight:900;background:transparent;border:none;")
        cl.addWidget(t)
        s = QLabel(subtitulo)
        s.setStyleSheet(f"color:{_TEXT2};font-size:12px;background:transparent;border:none;")
        cl.addWidget(s)
        for ej in ejemplos:
            e = QLabel("•  " + ej)
            e.setStyleSheet("color:#E6E6E6;font-size:13px;background:transparent;border:none;")
            cl.addWidget(e)
        cl.addStretch(1)
        b = _boton("Conectar", primario=True)
        b.clicked.connect(lambda: self._elegir_tipo(tipo))
        cl.addWidget(b)
        return card

    def _elegir_tipo(self, tipo):
        """Abre Marketplace › Integraciones Comerciales prefiltrado por el tipo elegido (ecommerce/
        marketplace/web_tradicional). `_abrir_integraciones` decide si Canal Web se cierra del todo
        (entrada por menú, `_on_ir_marketplace`) o se oculta para reaparecer en esta misma pantalla
        al cerrar Integraciones (entrada normal, bug real corregido: antes SIEMPRE se cerraba, así
        que al cerrar Integraciones el usuario "caía" sobre lo que hubiera detrás — p. ej. la pestaña
        "Web propia" del Catálogo — en vez de volver aquí)."""
        self._abrir_integraciones(tipo=tipo)

    # ── Lógica de decisión (reutiliza el orquestador) ──
    def _elegir(self, *, tiene_web: bool):
        try:
            from src.services.comercio_digital.canal_web import orquestador
            orquestador.elegir(self._id_empresa, tiene_web_ya=tiene_web)   # registra/decide (reutilizado)
        except Exception as e:
            logger.debug("elegir: %s", e)
        # SÍ → ¿qué tipo de web? (3 columnas). NO → creación con el Editor Visual propio.
        self._stack.setCurrentIndex(2 if tiene_web else 1)

    def _abrir_integraciones(self, tipo=None):
        """Redirección AUTOMÁTICA a Marketplace › Integraciones Comerciales, prefiltrada por `tipo`
        (ecommerce/marketplace/web_tradicional). El usuario no navega a mano.

        Entrada por MENÚ (`_on_ir_marketplace` ya aportado por quien abrió Canal Web): delega la
        ventana entera en ese callback y cierra Canal Web, igual que siempre.

        Entrada NORMAL (rama "Sí" → tipo de plataforma, sin callback externo): Canal Web se OCULTA
        (nunca se cierra) mientras Integraciones está abierta, y reaparece —en esta misma pantalla,
        con su propia animación de entrada/salida— en cuanto el usuario cierra Integraciones
        (`_volver_desde_integraciones`, pasado como `al_cerrar`)."""
        if callable(self._on_ir_marketplace):
            self._on_ir_marketplace()
            self._cerrar_ventana()
            return
        try:
            from src.gui.integraciones_comerciales_gui import \
                IntegracionesComercialesWindow
            self._ic_win = IntegracionesComercialesWindow(
                id_empresa=self._id_empresa, usuario=self._usuario, tipo_inicial=tipo,
                al_cerrar=self._volver_desde_integraciones)
            self._ic_win.setWindowFlag(Qt.WindowType.Window)
            _abrir_ventana_completa(self._ic_win, origen=self)
            self.hide()
        except Exception as e:
            logger.debug("abrir integraciones: %s", e)

    def _volver_desde_integraciones(self):
        try:
            self.show()
            self.raise_()
            self.activateWindow()
        except Exception as e:
            logger.debug("volver desde integraciones: %s", e)

def abrir_canal_web(parent=None, id_empresa=None, usuario=None, on_ir_marketplace=None):
    """Punto ÚNICO de entrada a Canal Web (WEB-12).

    Flujo directo (automatización UX): si el canal YA está configurado (`canal_web.existe`,
    cualquier estado salvo `no_configurado`), la pregunta "¿tu empresa ya dispone de web?" no
    tiene sentido — ya se respondió una vez — así que se salta directa y automáticamente a la
    gestión del canal (`CanalWebConfigDialog`, con acceso directo al Editor Visual). Solo un canal
    SIN configurar todavía muestra la pregunta inicial. Devuelve la ventana/diálogo abierto (el
    llamante DEBE conservar la referencia para que no la recoja el GC)."""
    if id_empresa is None:
        try:
            from src.db.empresa import empresa_actual_id
            id_empresa = empresa_actual_id()
        except Exception:
            id_empresa = None
    try:
        from src.services.comercio_digital import canal_web
        if canal_web.existe(id_empresa):
            from src.gui.canal_web_config import CanalWebConfigDialog
            from src.gui.transiciones import abrir_dialogo_deslizante
            dlg = CanalWebConfigDialog(parent=parent)
            abrir_dialogo_deslizante(dlg, parent)
            return dlg
    except Exception as e:
        logger.debug("abrir_canal_web (flujo directo): %s", e)
    w = CanalWebWindow(id_empresa=id_empresa, usuario=usuario, on_ir_marketplace=on_ir_marketplace)
    w.setWindowFlag(Qt.WindowType.Window)
    w.setWindowModality(Qt.WindowModality.ApplicationModal)
    _abrir_ventana_completa(w, origen=parent)
    return w
