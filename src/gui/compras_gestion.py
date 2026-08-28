"""
Ventana de COMPRAS (Smart Suppliers · Fase E) — dashboard de bienvenida de la Extranet B2B.

Tras la transformación a Extranet Empresa + Portal Proveedor (ver plan "Smart Suppliers"), esta
ventana YA NO contiene el CRUD de proveedores, la bolsa/carrito de pedidos ni el sidebar de 7
secciones (todo eso vivía aquí en E2-GUI y se ha retirado): ahora solo orquesta la entrada a los dos
puntos de acceso del ecosistema B2B, ambos servidos por el backend Flask (`src/backend/
portal_empresa_b2b.py`, patrón `storefront.py`, sin motor paralelo):

  • "Entrar al portal B2B" → abre en el navegador la Extranet Empresa (catálogo por sector, carrito,
    reposición, pedidos con custodia de fondos) para la EMPRESA y la TIENDA con la que el escritorio
    está conectado en ESE MOMENTO (`src.db.empresa.tienda_actual_id_int`) — el token de sesión fija esa
    tienda; no se puede cambiar de tienda desde el portal (matiz de negocio confirmado).
  • "Invitar Proveedor" → sustituye el alta manual de proveedores: envía una invitación por email con
    un token de un solo uso (`src.services.compras.invitaciones.invitar_proveedor`); el proveedor
    completa su propia alta en el Portal Proveedor.

`_DialogoPrecioRef` se conserva en este módulo (lo usa `src/gui/info_articulo.py` para editar el
Precio ref. manual de un artículo) — es lo único que sobrevive del código anterior, sin cambios.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from src.gui.catalogo_gestion import _BG, _CIAN, _DIM, _ROJO, _btn, _dialogo_frameless, _inp
from src.utils.i18n import tr

logger = logging.getLogger("gui.compras")

_TEXT_TIENDA = "#8B949E"

try:
    from assets.estilo_global import mostrar_mensaje
except Exception:  # pragma: no cover
    mostrar_mensaje = None

try:
    from assets.estilo_global import mostrar_confirmacion
except Exception:  # pragma: no cover
    mostrar_confirmacion = None


def _aviso(parent, titulo, msg, nivel="info"):
    if mostrar_mensaje is not None:
        mostrar_mensaje(parent, titulo, msg, nivel=nivel)
    else:  # pragma: no cover
        logger.info("%s: %s", titulo, msg)


def _confirmar(parent, titulo, msg) -> bool:
    """Confirmación modal (unificada). Sin diálogo → asume aceptar (entornos de test)."""
    if mostrar_confirmacion is not None:
        return bool(mostrar_confirmacion(parent, titulo, msg))
    return True


def _btn_x(slot=None):
    """Botón rojo ✕ (cerrar/volver) para la cabecera, mismo estilo unificado que Canal Web
    (`gui/canal_web_gui.py::_btn_x`) — se reutiliza el patrón visual, no se inventa uno nuevo."""
    b = QPushButton("✕")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFixedSize(50, 44)
    b.setStyleSheet(f"QPushButton{{background:transparent;color:{_ROJO};border:2px solid {_ROJO};"
                    f"border-radius:9px;font-weight:900;font-size:18px;}}"
                    f"QPushButton:hover{{background:{_ROJO};color:{_BG};}}")
    if slot:
        b.clicked.connect(slot)
    return b


def _boton_grande(texto, subtitulo, slot=None):
    """Botón grande de acción principal del dashboard (icono+texto arriba, subtítulo descriptivo
    debajo). Usa el objectName "btn_primario" — el mismo estilo global (contorno cyan + hover
    relleno) que el botón "ABRIR ESCÁNER DE ENTRADA" de Recepción (Logística) — sin CSS propio, para
    quedar visualmente idéntico al resto de botones principales de la app."""
    b = QPushButton()
    b.setObjectName("btn_primario")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setMinimumHeight(96)
    lay = QVBoxLayout(b); lay.setSpacing(4)
    lay.setContentsMargins(20, 14, 20, 14)
    t = QLabel(texto); t.setStyleSheet("background:transparent;font-size:17px;font-weight:900;color:inherit;")
    t.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    s = QLabel(subtitulo); s.setStyleSheet("background:transparent;font-size:14px;font-weight:600;"
                                           "color:inherit;")
    s.setWordWrap(True)
    s.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    lay.addWidget(t); lay.addWidget(s)
    if slot:
        b.clicked.connect(slot)
    return b


class ComprasWindow(QWidget):
    """Dashboard de entrada a Smart Suppliers (Extranet B2B). Firma del constructor conservada
    (`callback_vuelta`/`usuario`/`main`/`parent`) por compatibilidad con el enrutado del menú
    principal (`menu_principal.py`, v_id "compras")."""

    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setWindowTitle("Smart Manager — " + tr("compras.titulo", default="COMPRAS"))

        root = QVBoxLayout(self)
        root.setContentsMargins(30, 24, 30, 24)
        root.setSpacing(18)

        cab = QHBoxLayout()
        titulo = QLabel("🏭  " + tr("compras.titulo", default="SMART SUPPLIERS · EXTRANET B2B"))
        titulo.setStyleSheet(f"color:{_CIAN};font-size:22px;font-weight:900;")
        cab.addWidget(titulo); cab.addStretch(1)
        if self._volver:
            cab.addWidget(_btn_x(self._volver_menu))
        root.addLayout(cab)

        intro = QLabel(tr(
            "compras.b2b_intro",
            default="Gestiona proveedores, catálogo y pedidos desde la Extranet B2B: catálogo por "
                    "sector, custodia de fondos y trazabilidad completa. Esta pantalla de escritorio "
                    "es solo el punto de entrada — el resto de la operativa vive en el portal web."))
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color:{_DIM};font-size:13px;")
        root.addWidget(intro)

        self.lbl_tienda = QLabel("")
        self.lbl_tienda.setStyleSheet(f"color:{_TEXT_TIENDA};font-size:14px;font-weight:700;")
        root.addWidget(self.lbl_tienda)
        self._refrescar_estado_tienda()

        root.addStretch(1)
        # Sin QFrame contenedor: cada botón lleva su propio contorno (btn_primario) y no hace falta
        # (ni se quiere) un segundo contorno envolviendo al grupo.
        root.addWidget(_boton_grande(
            "🏢  " + tr("compras.b2b_entrar", default="Entrar al portal B2B"),
            tr("compras.b2b_entrar_sub",
               default="Catálogo por sector, carrito, reposición y pedidos con custodia de fondos."),
            self._entrar_portal_b2b))
        root.addSpacing(14)
        root.addWidget(_boton_grande(
            "✉️  " + tr("compras.b2b_invitar", default="Invitar Proveedor"),
            tr("compras.b2b_invitar_sub",
               default="Envía una invitación por email; el proveedor completa su alta en su propio portal."),
            self._dlg_invitar_proveedor))
        root.addStretch(2)

    def _volver_menu(self):
        if callable(self._volver):
            self._volver()

    # ── Estado de la tienda conectada ───────────────────────────────────────
    def _refrescar_estado_tienda(self):
        from src.db.empresa import tienda_actual_id_int
        id_tienda = tienda_actual_id_int()
        if not id_tienda:
            self.lbl_tienda.setText(
                "⚠️  " + tr("compras.b2b_sin_tienda",
                           default="Sin tienda conectada — conéctate a una tienda en Smart Manager "
                                   "antes de entrar al portal B2B."))
            return
        nombre = None
        try:
            from src.db.tiendas import obtener_tienda
            t = obtener_tienda(id_tienda)
            nombre = t.get("nombre") if t else None
        except Exception as e:
            logger.debug("obtener_tienda(%s): %s", id_tienda, e)
        self.lbl_tienda.setText(
            "🏬  " + tr("compras.b2b_tienda_activa", default="Tienda conectada: {n}",
                       n=(nombre or f"#{id_tienda}")))

    # ── Entrar al portal B2B ─────────────────────────────────────────────────
    def _mensaje_error_sesion(self, error: str) -> str:
        return {
            "empresa_sin_sector_comercial_asignado": tr(
                "compras.b2b_err_sector",
                default="Tu empresa no tiene un Sector Comercial asignado. Configúralo antes de "
                        "entrar al portal B2B (el catálogo se filtra por sector)."),
            "sin_tienda_activa_conectate_a_una_tienda_primero": tr(
                "compras.b2b_err_tienda",
                default="No hay ninguna tienda conectada. Conéctate a una tienda en Smart Manager "
                        "antes de entrar al portal."),
        }.get(error, tr("compras.b2b_err_generico", default="No se pudo abrir el portal B2B."))

    def _entrar_portal_b2b(self):
        from src.db.empresa import empresa_actual_id, tienda_actual_id_int
        id_tienda = tienda_actual_id_int()
        self._refrescar_estado_tienda()
        if not id_tienda:
            _aviso(self, tr("compras.b2b_entrar", default="Entrar al portal B2B"),
                   self._mensaje_error_sesion("sin_tienda_activa_conectate_a_una_tienda_primero"),
                   "warning")
            return
        from src.services.compras import b2b_sesion_empresa as SES
        r = SES.crear_sesion(empresa_actual_id(), self.usuario.get("id"), id_tienda,
                             nombre_usuario=self.usuario.get("nombre"))
        if not r.get("ok"):
            _aviso(self, tr("compras.b2b_entrar", default="Entrar al portal B2B"),
                   self._mensaje_error_sesion(r.get("error")), "error")
            return
        import os
        import webbrowser
        base = os.getenv("PORTAL_EMPRESA_URL", "http://localhost:8090/portal/empresa")
        try:
            webbrowser.open(f"{base}/{r['token']}/dashboard")
        except Exception as e:
            logger.debug("abrir portal empresa: %s", e)

    # ── Invitar Proveedor ────────────────────────────────────────────────────
    def _dlg_invitar_proveedor(self):
        dlg = QDialog(self); dlg.setFixedSize(460, 260)
        v = _dialogo_frameless(dlg, titulo=tr("compras.b2b_invitar", default="Invitar Proveedor"),
                               ancho=460)
        info = QLabel(tr("compras.b2b_invitar_info",
                         default="Se enviará un email con un enlace de alta de un solo uso. El "
                                 "proveedor completa su propio registro (razón social, CIF, sector, "
                                 "datos bancarios) en su portal."))
        info.setWordWrap(True); info.setStyleSheet(f"color:{_DIM};background:transparent;font-size:12px;")
        v.addWidget(info)
        cap = QLabel(tr("compras.b2b_invitar_email", default="Email del proveedor"))
        cap.setStyleSheet(f"color:{_DIM};background:transparent;font-weight:700;font-size:13px;")
        v.addWidget(cap)
        in_email = _inp("proveedor@empresa.com")
        v.addWidget(in_email)
        v.addStretch(1)

        def _enviar():
            email = in_email.text().strip()
            if not email or "@" not in email:
                _aviso(dlg, tr("compras.b2b_invitar", default="Invitar Proveedor"),
                       tr("compras.b2b_email_invalido", default="Introduce un email válido."),
                       "warning")
                return
            from src.db.empresa import empresa_actual_id
            from src.services.compras import invitaciones as INV
            r = INV.invitar_proveedor(empresa_actual_id(), email, usuario=self.usuario.get("nombre"))
            if not r.get("ok"):
                _aviso(dlg, tr("compras.b2b_invitar", default="Invitar Proveedor"),
                       tr("compras.b2b_invitar_err", default="No se pudo enviar la invitación."),
                       "error")
                return
            dlg.accept()
            base = __import__("os").getenv("PORTAL_PROVEEDOR_URL", "http://localhost:8090/portal/proveedor")
            enlace = f"{base}/onboarding/{r['token']}"
            _aviso(self, tr("compras.b2b_invitar", default="Invitar Proveedor"),
                   tr("compras.b2b_invitado_ok",
                      default="Invitación enviada a {e}.\n\nEnlace de alta (válido 14 días, por si el "
                              "email no llega): {enlace}", e=email, enlace=enlace), "success")

        in_email.returnPressed.connect(_enviar)
        in_email.setFocus()
        row = QHBoxLayout(); row.addStretch(1)
        row.addWidget(_btn(tr("compras.cancelar", default="Cancelar"), dlg.reject))
        row.addWidget(_btn(tr("compras.b2b_enviar_invitacion", default="Enviar invitación"), _enviar,
                           primary=True))
        v.addLayout(row)
        dlg.exec()


# ── Diálogos mínimos ─────────────────────────────────────────────────────────
class _DialogoPrecioRef(QDialog):
    """Editor rápido del Precio ref. de un artículo (frameless). Permite fijar un valor MANUAL prioritario
    o restablecerlo a la media histórica. Expone `valor` (float|None) y `restablecer` (bool)."""

    def __init__(self, codigo, actual, es_manual, media, parent=None):
        super().__init__(parent)
        self.valor = None
        self.restablecer = False
        self.setFixedSize(440, 340)
        v = _dialogo_frameless(self, titulo=tr("compras.precio_ref", default="Precio de referencia"),
                               ancho=440)
        cab = QLabel(f"{codigo}")
        cab.setStyleSheet(f"color:{_CIAN};background:transparent;font-size:14px;font-weight:900;")
        v.addWidget(cab)
        origen = (tr("compras.pref_manual", default="valor manual (prioritario)") if es_manual
                  else tr("compras.pref_auto", default="cálculo automático"))
        info = QLabel(tr("compras.pref_info",
                         default="Precio ref. actual: {a} € · origen: {o}.",
                         a=(f"{actual:.2f}" if actual is not None else "—"), o=origen))
        info.setStyleSheet(f"color:{_DIM};background:transparent;font-size:13px;"); info.setWordWrap(True)
        v.addWidget(info)
        med = QLabel(tr("compras.pref_media",
                        default="Media histórica (30 días): {m}.",
                        m=(f"{media:.2f} €" if media is not None else "sin histórico")))
        med.setStyleSheet(f"color:{_DIM};background:transparent;font-size:13px;")
        v.addWidget(med)
        cap = QLabel(tr("compras.pref_nuevo", default="Nuevo Precio ref. manual (€)"))
        cap.setStyleSheet(f"color:{_DIM};background:transparent;font-weight:700;font-size:13px;")
        v.addWidget(cap)
        self.in_val = _inp("0.00")
        if actual is not None:
            self.in_val.setText(f"{float(actual):.2f}")
        self.in_val.returnPressed.connect(self._ok)
        v.addWidget(self.in_val)
        v.addWidget(_btn(tr("compras.pref_restablecer", default="🔄  Restablecer a media histórica"),
                         self._reset, primary=True))
        v.addStretch(1)
        row = QHBoxLayout(); row.addStretch(1)
        row.addWidget(_btn(tr("compras.cancelar", default="Cancelar"), self.reject))
        row.addWidget(_btn(tr("compras.guardar", default="Guardar"), self._ok, primary=True))
        v.addLayout(row)
        self.in_val.setFocus(); self.in_val.selectAll()

    def _reset(self):
        self.restablecer = True
        self.accept()

    def _ok(self):
        try:
            v = float((self.in_val.text() or "0").replace(",", "."))
        except ValueError:
            return
        if v <= 0:
            return
        self.valor = round(v, 2)
        self.accept()
