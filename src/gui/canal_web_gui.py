"""
Canal Web · Entrada del ecosistema web (Fases WEB-02/WEB-12+). El Canal Web es el ORQUESTADOR: al entrar
muestra ÚNICAMENTE una pregunta — ¿la empresa ya tiene página web?

  • SÍ → ventana de 3 columnas (E-commerce / Marketplace / Web tradicional) → Integraciones Comerciales.
  • NO → creación con **Hostinger** por DELEGACIÓN TOTAL: un único botón abre el creador web con IA de
    Hostinger en el navegador (enlace de afiliado + código promo). Smart Manager NO genera webs; solo
    conecta la web resultante después (desde «Sí, ya tengo web» → Web tradicional).

Smart Manager AI **NO** genera páginas web (ni CMS, ni editor, ni plantillas, ni dominios/hosting): eso es de
Hostinger. Reutiliza el orquestador de `services/comercio_digital/canal_web`. Autónoma respecto al TPV.
"""

import logging
import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                             QStackedWidget, QVBoxLayout, QWidget)

logger = logging.getLogger("gui.canal_web")

_CIAN = "#00FFC6"
_BG = "#0E1117"
_BG2 = "#161B22"
_TEXT2 = "#8B949E"

# Enlace de AFILIADO al creador web/tienda online de Shopify + código promo (configurables por entorno).
# Rellena con tu enlace/código reales de afiliado de Shopify para obtener beneficios por cada cliente referido.
SHOPIFY_URL = os.getenv("SHOPIFY_REFERRAL_URL", "https://www.shopify.com/es")
SHOPIFY_PROMO = os.getenv("SHOPIFY_PROMO_CODE", "SMARTMANAGER")


def _btn_x(slot=None):
    """Botón rojo ✕ (cerrar) para la esquina superior derecha, estilo unificado de la app."""
    b = QPushButton("✕")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFixedSize(50, 44)
    b.setStyleSheet("QPushButton{background:transparent;color:#FF4C4C;border:2px solid #FF4C4C;"
                    "border-radius:9px;font-weight:900;font-size:18px;}"
                    "QPushButton:hover{background:#FF4C4C;color:#0D1117;}")
    if slot:
        b.clicked.connect(slot)
    return b


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
        self._stack.addWidget(self._pagina_hostinger())   # 1 (ramal "No": crear con Hostinger)
        self._stack.addWidget(self._pagina_tipo_web())    # 2 (ramal "Sí": ¿qué tipo de web?)
        self._stack.setCurrentIndex(0)

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

    # ── Página 1: creación con Hostinger — DELEGACIÓN TOTAL (1 paso) ──
    def _pagina_hostinger(self) -> QWidget:
        w = QWidget()
        ly = QVBoxLayout(w)
        ly.setSpacing(14)
        ly.addStretch(1)
        t = QLabel("Crear tu página web con Shopify")
        t.setStyleSheet(f"color:{_CIAN};font-size:22px;font-weight:900;")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ly.addWidget(t)
        prov = QLabel("Proveedor oficial de creación web:  SHOPIFY (IA)")
        prov.setStyleSheet(f"color:{_CIAN};font-size:14px;font-weight:800;")
        prov.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ly.addWidget(prov)
        exp = QLabel("Shopify creará tu página web automáticamente con inteligencia artificial. Smart "
                     "Manager NO genera páginas web: cuando tu web esté lista, la conectas aquí en un paso "
                     "(«Sí, ya tengo web» → Web tradicional).")
        exp.setWordWrap(True)
        exp.setAlignment(Qt.AlignmentFlag.AlignCenter)
        exp.setStyleSheet(f"color:{_TEXT2};font-size:13px;")
        ly.addWidget(exp)
        # Código promocional (descuento para los clientes de Smart Manager que crean su web en Shopify).
        if SHOPIFY_PROMO:
            fila_promo = QHBoxLayout()
            fila_promo.addStretch()
            promo = QLabel(f"🎁  Código de descuento:   {SHOPIFY_PROMO}")
            promo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            promo.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            promo.setStyleSheet(f"color:{_CIAN};background:{_BG2};border:2px dashed {_CIAN};border-radius:10px;"
                                f"padding:12px 18px;font-size:15px;font-weight:900;")
            fila_promo.addWidget(promo)
            fila_promo.addStretch()
            ly.addLayout(fila_promo)
            nota = QLabel("Aplícalo en el pago de Shopify para obtener tu descuento como cliente de Smart "
                          "Manager.")
            nota.setWordWrap(True)
            nota.setAlignment(Qt.AlignmentFlag.AlignCenter)
            nota.setStyleSheet(f"color:{_TEXT2};font-size:11px;")
            ly.addWidget(nota)
        # Un ÚNICO paso: abrir el creador de Shopify (delegación total).
        fila = QHBoxLayout()
        fila.addStretch()
        b = _boton("🌐  Crear mi web con Shopify", primario=True)
        b.setMinimumWidth(320)
        b.clicked.connect(self._abrir_hostinger)
        fila.addWidget(b)
        fila.addStretch()
        ly.addLayout(fila)
        ly.addStretch(2)
        return w

    def _abrir_hostinger(self):
        """Delegación TOTAL: abre el creador web/tienda online de Shopify en el navegador (enlace de
        afiliado + código promo). La creación ocurre ÍNTEGRAMENTE en Shopify; Smart Manager solo conecta
        la web resultante después. Un solo clic (mínimo número de pasos). (Flujo/lógica sin cambios.)"""
        import webbrowser
        try:
            webbrowser.open(SHOPIFY_URL)
        except Exception as e:
            logger.debug("abrir shopify: %s", e)

    def _cerrar_o_volver(self):
        """✕: navega hacia atrás. Desde el asistente Hostinger → a la selección de tipo (3 columnas); desde
        las 3 columnas → a la pregunta inicial; en la pregunta → cierra la ventana."""
        idx = self._stack.currentIndex()
        if idx == 1:
            self._stack.setCurrentIndex(2)
        elif idx == 2:
            self._stack.setCurrentIndex(0)
        else:
            self.close()

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
        marketplace/web_tradicional) y cierra la ventana de Canal Web."""
        self._abrir_integraciones(tipo=tipo)
        self.close()

    # ── Lógica de decisión (reutiliza el orquestador) ──
    def _elegir(self, *, tiene_web: bool):
        try:
            from src.services.comercio_digital.canal_web import orquestador
            orquestador.elegir(self._id_empresa, tiene_web_ya=tiene_web)   # registra/decide (reutilizado)
        except Exception as e:
            logger.debug("elegir: %s", e)
        # SÍ → ¿qué tipo de web? (3 columnas). NO → creación con Hostinger (delegación total).
        self._stack.setCurrentIndex(2 if tiene_web else 1)

    def _abrir_integraciones(self, tipo=None):
        """Redirección AUTOMÁTICA a Marketplace › Integraciones Comerciales, prefiltrada por `tipo`
        (ecommerce/marketplace/web_tradicional). El usuario no navega a mano."""
        if callable(self._on_ir_marketplace):
            self._on_ir_marketplace()
            return
        try:
            from src.gui.integraciones_comerciales_gui import \
                IntegracionesComercialesWindow
            self._ic_win = IntegracionesComercialesWindow(id_empresa=self._id_empresa,
                                                          usuario=self._usuario, tipo_inicial=tipo)
            self._ic_win.setWindowFlag(Qt.WindowType.Window)
            self._ic_win.showMaximized()
        except Exception as e:
            logger.debug("abrir integraciones: %s", e)

    def _abrir_config(self):
        """Configuración de la presencia digital (Canal Web es el único editor de la marca). Accesible desde
        el Portal Web (sección Administración); conservado para compatibilidad (no se muestra en la pregunta
        inicial: la pregunta queda pura, solo Sí/No)."""
        try:
            from src.gui.canal_web_config import CanalWebConfigDialog
            CanalWebConfigDialog(parent=self).exec()
        except Exception as e:
            logger.debug("abrir_config canal web: %s", e)


def abrir_canal_web(parent=None, id_empresa=None, usuario=None, on_ir_marketplace=None):
    """Punto ÚNICO de entrada a Canal Web (WEB-12): abre la ventana que muestra ÚNICAMENTE la pregunta
    inicial (¿tu empresa ya dispone de web? Sí/No). Lo usan los redirects de Catálogo y del Portal Web para
    NO saltarse la pregunta. Devuelve la ventana (el llamante DEBE conservar la referencia para que no la
    recoja el GC)."""
    if id_empresa is None:
        try:
            from src.db.empresa import empresa_actual_id
            id_empresa = empresa_actual_id()
        except Exception:
            id_empresa = None
    w = CanalWebWindow(id_empresa=id_empresa, usuario=usuario, on_ir_marketplace=on_ir_marketplace)
    w.setWindowFlag(Qt.WindowType.Window)
    w.setWindowModality(Qt.WindowModality.ApplicationModal)
    w.showMaximized()
    return w
