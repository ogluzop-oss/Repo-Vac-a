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
from PyQt6.QtGui import QBitmap, QPainter, QPixmap, QRegion
from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox,
                             QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout,
                             QHeaderView, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
                             QTableWidget, QTableWidgetItem, QVBoxLayout,
                             QWidget)

from assets.estilo_global import _blindar_tamano_fijo
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

# ── Plantillas predeterminadas de políticas legales (Fase 3 e-commerce) ───────────────────────
# Punto de partida genérico y EDITABLE (encargo: "plantillas predeterminadas completas y
# editables") — no es asesoramiento legal, cada empresa debe adaptarlo a su caso real antes de
# publicar; por eso el botón se llama "Usar plantilla" (rellena, no impone) y el texto queda en un
# campo libre que el usuario siempre puede reescribir entero.
_PLANTILLA_TERMINOS = (
    "TÉRMINOS Y CONDICIONES\n\n"
    "1. Objeto. Las presentes condiciones regulan la compra de productos a través de esta tienda "
    "online, operada por [NOMBRE DE LA EMPRESA], con NIF [NIF] y domicilio en [DIRECCIÓN].\n\n"
    "2. Proceso de compra. Los precios mostrados incluyen impuestos aplicables, salvo que se "
    "indique lo contrario. El pedido se confirma tras el pago y la verificación de stock.\n\n"
    "3. Pago. Se aceptan los métodos de pago indicados en el proceso de compra. El cargo se "
    "realiza en el momento de confirmar el pedido.\n\n"
    "4. Entrega. Los plazos de entrega son orientativos y dependen de la zona de envío "
    "seleccionada (ver Política de Envíos).\n\n"
    "5. Derecho de desistimiento. El cliente dispone de 14 días naturales desde la recepción del "
    "pedido para desistir de la compra (ver Política de Devoluciones).\n\n"
    "6. Legislación aplicable. Estas condiciones se rigen por la legislación española/UE vigente "
    "en materia de comercio electrónico y protección de consumidores."
)
_PLANTILLA_PRIVACIDAD = (
    "POLÍTICA DE PRIVACIDAD\n\n"
    "Responsable del tratamiento: [NOMBRE DE LA EMPRESA], NIF [NIF], [DIRECCIÓN], "
    "[EMAIL DE CONTACTO].\n\n"
    "Finalidad: gestionar pedidos, atención al cliente y, en su caso, el envío de comunicaciones "
    "comerciales si el usuario lo ha consentido expresamente.\n\n"
    "Legitimación: ejecución de la relación contractual (compra) y consentimiento del interesado "
    "para finalidades adicionales.\n\n"
    "Conservación: mientras exista relación contractual y, posteriormente, durante los plazos "
    "legalmente exigibles (fiscal/mercantil).\n\n"
    "Derechos: el usuario puede ejercer sus derechos de acceso, rectificación, supresión, "
    "oposición, limitación y portabilidad escribiendo a [EMAIL DE CONTACTO].\n\n"
    "Destinatarios: no se ceden datos a terceros salvo obligación legal o proveedores necesarios "
    "para la prestación del servicio (pasarela de pago, transporte)."
)
_PLANTILLA_DEVOLUCIONES = (
    "POLÍTICA DE DEVOLUCIONES\n\n"
    "Derecho de desistimiento: dispones de 14 días naturales desde la recepción del pedido para "
    "devolverlo sin necesidad de justificación.\n\n"
    "Cómo devolver: contacta con nosotros en [EMAIL DE CONTACTO] indicando el número de pedido. "
    "Te indicaremos la dirección de devolución y el procedimiento.\n\n"
    "Estado del producto: el producto debe devolverse en su embalaje original, sin usar y con "
    "todas sus etiquetas.\n\n"
    "Reembolso: una vez recibido y verificado el producto devuelto, reembolsaremos el importe "
    "pagado (incluidos los gastos de envío iniciales, si los hubo) en un plazo máximo de 14 días "
    "naturales, usando el mismo medio de pago empleado en la compra.\n\n"
    "Gastos de devolución: salvo error nuestro, los gastos de envío de la devolución corren a "
    "cargo del cliente.\n\n"
    "Productos excluidos: [INDICAR SI APLICA — p. ej. productos personalizados, perecederos, "
    "precintados de higiene abiertos]."
)
_PLANTILLA_POLITICA_ENVIOS = (
    "POLÍTICA DE ENVÍOS\n\n"
    "Zonas de envío y tarifas: el coste de envío se calcula según la zona geográfica de destino y, "
    "en su caso, el peso del pedido — se muestra siempre antes de confirmar la compra. Consulta "
    "las zonas y condiciones configuradas en la pestaña «Envíos».\n\n"
    "Plazos de entrega: [INDICAR PLAZO ORIENTATIVO, p. ej. 24-72h laborables en península].\n\n"
    "Seguimiento: recibirás un número de seguimiento por email en cuanto tu pedido sea enviado.\n\n"
    "Incidencias en el transporte: si tu pedido llega dañado o incompleto, contacta con nosotros "
    "en [EMAIL DE CONTACTO] en las 48h siguientes a la recepción.\n\n"
    "Envío gratuito: [INDICAR SI APLICA, p. ej. a partir de cierto importe de pedido o con "
    "determinados cupones — ver configuración de cada zona de envío]."
)


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
        # desbordamiento del contenido se desplaza con scroll interno. Sin el contorno neón cian
        # global (`QDialog{border:2px solid CIAN}`, estilo_global.py).
        self.setObjectName("dlg_canal_web_config")
        self.setStyleSheet("#dlg_canal_web_config { border: none; }")
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

    def _textarea(self, val=""):
        t = QPlainTextEdit(val or "")
        t.setFixedHeight(110)
        t.setStyleSheet(
            f"QPlainTextEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:8px;font-size:12px;font-family:'{_FONT}';}}"
            f"QPlainTextEdit:focus{{border-color:{_CIAN};}}")
        return t

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

    def _fila_color_marca(self, valor_actual, *, attr="_color_marca", defecto="#00FFC6",
                          titulo=None) -> QWidget:
        """Botón-muestra que abre el selector de color UNIFICADO de la app (`gui/color_picker.py`,
        el mismo que usa Smart Config/Horarios) — nunca se escribe un HEX a mano.

        `attr` parametriza en qué atributo de instancia se guarda el HEX elegido — permite
        reutilizar esta misma fila para el color PRIMARIO (`_color_marca`) y el SECUNDARIO/acentos
        (`_color_secundario_marca`, Generador de Apps Móviles PWA Fase 1) sin duplicar el widget."""
        setattr(self, attr, valor_actual or defecto)
        valor = getattr(self, attr)
        fila = QWidget(); fila.setStyleSheet("background:transparent;")
        ly = QHBoxLayout(fila); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(10)
        muestra = QPushButton()
        muestra.setFixedSize(64, 34)
        muestra.setCursor(Qt.CursorShape.PointingHandCursor)
        hexlbl = _lbl(valor.upper(), size=12, color=_TEXT)

        def _pinta(color_hex):
            muestra.setStyleSheet(
                f"QPushButton{{background:{color_hex};border:2px solid {_BORDE};border-radius:8px;}}"
                f"QPushButton:hover{{border:2px solid {_CIAN};}}")
            hexlbl.setText(color_hex.upper())
            setattr(self, attr, color_hex.upper())

        if attr == "_color_marca":
            self._pintar_color_marca = _pinta   # reusado por el reset tras despublicar
        _pinta(getattr(self, attr))

        def _elegir():
            from src.gui.color_picker import seleccionar_color
            hexval = seleccionar_color(self, getattr(self, attr),
                                       titulo or tr("canalweb.color_pick", default="Color de marca"))
            if hexval:
                _pinta(hexval)

        muestra.clicked.connect(_elegir)
        ly.addWidget(muestra); ly.addWidget(hexlbl); ly.addStretch()
        return fila

    def _combo_monedas(self, actual) -> QComboBox:
        """Desplegable con TODAS las divisas registradas en la app (`utils.divisas`, el mismo
        catálogo que usa el selector de Gestión Caja) — nunca una barra de texto libre."""
        from src.utils import divisas
        cb = QComboBox()
        cb.setFixedHeight(36)
        cb.setStyleSheet(
            f"QComboBox{{combobox-popup:0;background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:8px;padding:0 10px;font-size:12px;font-family:'{_FONT}';}}"
            f"QComboBox:hover,QComboBox:on{{border-color:{_CIAN};}}"
            f"QComboBox::drop-down{{border:none;width:22px;}}"
            f"QComboBox QAbstractItemView{{background:#0D1117;color:{_TEXT};border:2px solid {_CIAN};"
            f"border-radius:8px;selection-background-color:{_CIAN};selection-color:#0D1117;}}")
        try:
            codigos = divisas.monedas_soportadas()
        except Exception:
            codigos = ["EUR"]
        for code in codigos:
            try:
                inf = divisas.info(code)
                etiqueta = f"{code} · {inf['nombre']} ({inf['simbolo']})"
            except Exception:
                etiqueta = code
            cb.addItem(etiqueta, code)
        i = cb.findData((actual or "EUR").upper())
        if i >= 0:
            cb.setCurrentIndex(i)
        cb.view().setMinimumWidth(340)   # "USD · Dólar estadounidense ($)" es la etiqueta más larga
        return cb

    def _fila_logo_marca(self, valor_actual) -> QWidget:
        """Botón de subida (mismo criterio visual que la pestaña "Logo corporativo" de Smart
        Config) en vez de pedir una URL a mano: sube la imagen al backend de almacenamiento YA
        existente (`services.storage`, el mismo que usa la publicación en AWS — Fase 5) y guarda
        la URL resultante. Nota honesta: con el backend LOCAL degradado (sin AWS real) la URL no
        es accesible desde un navegador externo — mismo criterio de degradación transparente que
        `publicar_aws` (nunca se finge que funciona si el backend real no está configurado)."""
        self._logo_url_marca = valor_actual or ""
        cont = QWidget(); cont.setStyleSheet("background:transparent;")
        cly = QVBoxLayout(cont); cly.setContentsMargins(0, 0, 0, 0); cly.setSpacing(8)
        self._logo_preview = QLabel()
        self._logo_preview.setFixedSize(160, 80)
        self._logo_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._logo_preview.setWordWrap(True)
        self._logo_preview.setStyleSheet(
            f"border:1px dashed {_BORDE};border-radius:10px;color:{_TEXT2};"
            f"font-family:'{_FONT}';font-size:10px;background:{_BG2};")
        cly.addWidget(self._logo_preview)
        self._refrescar_logo_preview()
        fb = QHBoxLayout(); fb.setSpacing(8)
        b_subir = _btn(tr("canalweb.logo_subir", default="SUBIR LOGO"), color_fg=_CIAN,
                      color_border=_CIAN, hover_bg=_CIAN, h=34)
        b_subir.clicked.connect(self._subir_logo_marca)
        fb.addWidget(b_subir)
        b_quitar = _btn(tr("canalweb.logo_quitar", default="QUITAR LOGO"), color_fg=_ROJO,
                        color_border=_ROJO, hover_bg=_ROJO, h=34)
        b_quitar.clicked.connect(self._quitar_logo_marca)
        fb.addWidget(b_quitar)
        fb.addStretch()
        cly.addLayout(fb)
        return cont

    def _refrescar_logo_preview(self):
        url = getattr(self, "_logo_url_marca", "") or ""
        if url.startswith(("http://", "https://")):
            try:
                import urllib.request
                with urllib.request.urlopen(url, timeout=4) as r:
                    datos = r.read()
                pix = QPixmap()
                if pix.loadFromData(datos):
                    self._logo_preview.setPixmap(
                        pix.scaled(160, 80, Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation))
                    self._logo_preview.setText("")
                    return
            except Exception:
                pass
        self._logo_preview.setPixmap(QPixmap())
        self._logo_preview.setText(url or tr("canalweb.logo_sin", default="Sin logo"))

    def _subir_logo_marca(self):
        path, _f = QFileDialog.getOpenFileName(
            self, tr("canalweb.logo_dialog", default="Seleccionar logo de la tienda"), "",
            "Imágenes (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        if not path:
            return
        try:
            with open(path, "rb") as f:
                datos = f.read()
            import mimetypes
            import os as _os
            tipo = mimetypes.guess_type(path)[0] or "image/png"
            nombre = "logo" + _os.path.splitext(path)[1]
            from src.db.empresa import empresa_actual_id
            from src.services.storage import obtener_storage
            eid = empresa_actual_id()
            st = obtener_storage()
            clave = st.guardar(eid, "canal_web", nombre, datos, content_type=tipo)
            url = st.url_firmada(eid, clave, segundos=365 * 24 * 3600, usuario=self._usuario(),
                                 autorizado=True)
            self._logo_url_marca = url
            self._refrescar_logo_preview()
            self.lbl_msg.setText(tr("canalweb.logo_subido",
                                    default="Logo subido. Pulsa GUARDAR MARCA para aplicarlo."))
            self.lbl_msg.setStyleSheet(f"color:{_VERDE};font-size:11px;font-family:'{_FONT}';")
        except Exception as e:
            self.lbl_msg.setText(tr("canalweb.logo_err", default="No se pudo subir el logo: {e}", e=e))
            self.lbl_msg.setStyleSheet(f"color:{_ROJO};font-size:11px;font-family:'{_FONT}';")

    def _quitar_logo_marca(self):
        self._logo_url_marca = ""
        self._refrescar_logo_preview()

    def _nombre_empresa_sugerido(self) -> str:
        """Nombre comercial YA conocido por el ERP (`db.empresa`), para sugerir el nombre de la
        tienda sin que el usuario tenga que volver a escribirlo. Degradable: cualquier fallo deja
        el campo vacío (nunca un texto inventado)."""
        try:
            from src.db import empresa as _emp_db
            e = _emp_db.obtener_empresa() or {}
            return (e.get("nombre_comercial") or e.get("nombre_empresa") or "").strip()
        except Exception:
            return ""

    def _info_canal(self) -> dict:
        """Reúne el estado del canal reutilizando SERVICIOS existentes: entidad+métricas del Canal Web
        (`comercio_digital.canal_web`), pasarela (tpv.pagos) y conexión (conexiones). Solo lectura."""
        info = {"dominio": "—", "canal_estado": "—", "pasarela": "—", "conexiones": 0, "auth": "—",
                "publicado_en": "—", "ultima_sync": "—", "productos": 0, "pedidos": 0, "reservas": 0,
                "tipo_dom": "—", "proveedor_dom": "—", "dns": "—", "https": "—", "expira": "—",
                "aws_disponible": "—", "aws_ultima": "—"}
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
            from src.services.comercio_digital import canal_web
            aws = canal_web.estado_publicacion_aws()
            info["aws_disponible"] = (tr("canalweb.aws_si", default="Sí (configurada)") if aws["disponible"]
                                      else tr("canalweb.aws_no", default="No (modo vista previa local)"))
            ultima = aws.get("ultima_publicacion")
            if ultima:
                info["aws_ultima"] = f"{ultima.get('modo', '—')} · {str(ultima.get('publicado_en') or '—')}"
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
        # Pantalla completa, SIN contorno neón (mismo criterio que el resto de ventanas "a pantalla
        # completa" de la app, p. ej. `CanalWebWindow`/`IntegracionesComercialesWindow`): el cuerpo
        # rellena el diálogo entero, sin borde ni esquinas redondeadas.
        cuerpo = QFrame()
        cuerpo.setObjectName("cfgcw")
        cuerpo.setStyleSheet(f"QFrame#cfgcw{{background:{_BG};border:none;}}")
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
            f"QPushButton{{background:transparent;color:{_ROJO};border:none;border-radius:19px;padding:0;font-weight:900;font-size:18px;}}"
            f"QPushButton:hover{{background:{_ROJO};color:#0D1117;}}")
        bx.setProperty("sin_glow", True)
        _blindar_tamano_fijo(bx, 38, 38)
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
            (tr("canalweb.i_aws_disp", default="AWS real configurada"), info["aws_disponible"]),
            (tr("canalweb.i_aws_ult", default="Última publicación AWS"), info["aws_ultima"]),
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
            ("☁ " + tr("canalweb.a_aws", default="Publicar en AWS"), "aws", self._acc_publicar_aws, False),
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
        # Configuración cero-esfuerzo (automatización UX): si la tienda todavía no tiene nombre
        # propio guardado, se sugiere el de la empresa (YA conocido por el ERP) en vez de dejar el
        # campo en blanco — el usuario no tiene que volver a escribir un dato que el sistema ya
        # tiene. Nunca se inventa nada que el ERP no tenga (moneda ya tiene un valor por defecto
        # sensato —EUR— y color/dominio no tienen ninguna fuente real en el ERP, así que se dejan
        # tal cual, sin fabricar un valor).
        self.inp_web_nombre = self._inp(_pre.get("nombre") or self._nombre_empresa_sugerido(),
                                        tr("canalweb.m_nombre", default="Nombre de la tienda"))
        v.addWidget(self.inp_web_nombre)
        v.addWidget(_lbl(tr("canalweb.m_desc_l", default="Descripción / eslogan"), size=11, color=_TEXT2))
        self.inp_web_desc = self._inp(_pre.get("descripcion") or "",
                                      tr("canalweb.m_desc", default="Descripción / eslogan"))
        v.addWidget(self.inp_web_desc)
        fmarca = QHBoxLayout(); fmarca.setSpacing(8)
        colc = QVBoxLayout()
        colc.addWidget(_lbl(tr("canalweb.m_color", default="Color primario"), size=11, color=_TEXT2))
        colc.addWidget(self._fila_color_marca(_pre.get("color") or "#00FFC6"))
        # Color secundario/acentos (Generador de Apps Móviles PWA, Fase 1): mismo picker unificado,
        # mismo `web_config` — inyectado como variable CSS en la tienda Y como `background_color`
        # del manifest.json de la app (ver `backend/storefront.py`/`pwa.py`).
        cols = QVBoxLayout()
        cols.addWidget(_lbl(tr("canalweb.m_color2", default="Color secundario / acentos"),
                           size=11, color=_TEXT2))
        cols.addWidget(self._fila_color_marca(
            _pre.get("color_secundario") or "", attr="_color_secundario_marca", defecto="#161B22",
            titulo=tr("canalweb.color2_pick", default="Color secundario / acentos")))
        colm = QVBoxLayout()
        colm.addWidget(_lbl(tr("canalweb.m_moneda", default="Moneda"), size=11, color=_TEXT2))
        self.cmb_web_moneda = self._combo_monedas(_pre.get("moneda") or "EUR")
        colm.addWidget(self.cmb_web_moneda)
        fmarca.addLayout(colc); fmarca.addLayout(cols); fmarca.addLayout(colm); fmarca.addStretch()
        v.addLayout(fmarca)
        v.addWidget(_lbl(tr("canalweb.m_logo_l", default="Logo de la tienda (opcional)"), size=11, color=_TEXT2))
        v.addWidget(self._fila_logo_marca(_pre.get("logo_url") or ""))
        fbm = QHBoxLayout(); fbm.addStretch()
        # Pasarela de pago (Fase 3 e-commerce): NO se reconstruye aquí — abre el diálogo YA
        # existente y ya funcional (`tpv._PasarelaConfigDialog`: Stripe/PayPal/Redsys, modo
        # test/live, credenciales cifradas, MFA step-up). Canal Web lo reutiliza TAL CUAL
        # (`comercio_digital.pagos` ya llama a `tpv.pagos.pasarela_para`) — un único punto de
        # configuración de pagos para toda la app, aquí solo se da acceso rápido desde Catálogo Web.
        b_pago = _btn("💳  " + tr("canalweb.pago_btn", default="PASARELA DE PAGO"), color_fg=_CIAN,
                      color_border=_CIAN, hover_bg=_CIAN, h=42)
        b_pago.clicked.connect(self._abrir_pasarela_pago)
        fbm.addWidget(b_pago)
        # Editor visual del storefront (Fase 4 e-commerce): WYSIWYG con vista previa en vivo y
        # secciones/bloques reordenables, vive en un módulo PROPIO (`gui/tema_editor_dialog.py`,
        # análogo a `pasarela_config_dialog.py`) — Canal Web solo le da acceso rápido, no lo
        # reimplementa aquí.
        b_tema = _btn("🎨  " + tr("canalweb.tema_btn", default="EDITOR VISUAL"), color_fg=_CIAN,
                      color_border=_CIAN, hover_bg=_CIAN, h=42)
        b_tema.clicked.connect(self._abrir_editor_visual)
        fbm.addWidget(b_tema)
        b_marca = _btn(tr("canalweb.m_guardar", default="Guardar marca"), color_bg=_BG2,
                       color_fg=_VERDE, color_border=_VERDE, hover_bg=_VERDE, hover_fg="#0D1117", h=42)
        b_marca.clicked.connect(self._guardar_marca)
        fbm.addWidget(b_marca)
        v.addLayout(fbm)

        # ── POLÍTICAS LEGALES (Fase 3 e-commerce) — plegada por defecto, mismo patrón que
        # "Configuración avanzada". Texto libre guardado en `web_config` (reutiliza
        # `canal_web.guardar_presencia`, único editor — sin tabla/motor nuevos) y servido por el
        # storefront real.
        self._btn_legal = _btn("📄  " + tr("canalweb.legal_title", default="Políticas legales"),
                               color_fg=_TEXT2, color_border=_BORDE, hover_bg=_CIAN, h=38)
        self._btn_legal.clicked.connect(self._toggle_legal)
        v.addWidget(self._btn_legal)
        self._legal = QWidget(); self._legal.setStyleSheet("background:transparent;")
        self._legal.setVisible(False)
        v.addWidget(self._legal)
        lg = QVBoxLayout(self._legal); lg.setContentsMargins(0, 4, 0, 0); lg.setSpacing(10)
        self._campos_legales = {}
        for clave, etiqueta_key, etiqueta_def, plantilla in (
                ("texto_terminos", "canalweb.legal_terminos", "Términos y condiciones", _PLANTILLA_TERMINOS),
                ("texto_privacidad", "canalweb.legal_privacidad", "Política de privacidad", _PLANTILLA_PRIVACIDAD),
                ("texto_devoluciones", "canalweb.legal_devoluciones", "Política de devoluciones",
                 _PLANTILLA_DEVOLUCIONES),
                ("texto_politica_envios", "canalweb.legal_envios", "Política de envíos",
                 _PLANTILLA_POLITICA_ENVIOS)):
            filah = QHBoxLayout()
            filah.addWidget(_lbl(tr(etiqueta_key, default=etiqueta_def), size=11, color=_TEXT2), 1)
            b_plantilla = _btn(tr("canalweb.legal_usar_plantilla", default="Usar plantilla"),
                               color_fg=_TEXT2, color_border=_BORDE, hover_bg=_CIAN, h=28)
            b_plantilla.clicked.connect(lambda _c=False, c=clave, p=plantilla: self._aplicar_plantilla_legal(c, p))
            filah.addWidget(b_plantilla)
            lg.addLayout(filah)
            txt = self._textarea(_pre.get(clave) or "")
            self._campos_legales[clave] = txt
            lg.addWidget(txt)
        fbl = QHBoxLayout(); fbl.addStretch()
        b_legal_guardar = _btn(tr("canalweb.legal_guardar", default="Guardar políticas"),
                               color_bg=_BG2, color_fg=_VERDE, color_border=_VERDE,
                               hover_bg=_VERDE, hover_fg="#0D1117", h=42)
        b_legal_guardar.clicked.connect(self._guardar_legal)
        fbl.addWidget(b_legal_guardar)
        lg.addLayout(fbl)

        # ── BORRADOR CON CONTRASEÑA (Fase 5 e-commerce) — plegada por defecto, mismo patrón que
        # "Políticas legales". La tienda sigue respondiendo (`activa` no cambia) pero exige una
        # credencial HTTP Basic (`backend/storefront.py`) hasta que se desactive el borrador.
        # Reutiliza `canal_web.configurar_borrador` (hash vía `seguridad.passwords`; nunca se ve ni
        # se guarda la contraseña en claro aquí).
        self._btn_borrador = _btn("🔒  " + tr("canalweb.borrador_title", default="Borrador con contraseña"),
                                  color_fg=_TEXT2, color_border=_BORDE, hover_bg=_CIAN, h=38)
        self._btn_borrador.clicked.connect(self._toggle_borrador)
        v.addWidget(self._btn_borrador)
        self._borrador_w = QWidget(); self._borrador_w.setStyleSheet("background:transparent;")
        self._borrador_w.setVisible(False)
        v.addWidget(self._borrador_w)
        bw = QVBoxLayout(self._borrador_w); bw.setContentsMargins(0, 4, 0, 0); bw.setSpacing(10)
        bw.addWidget(_lbl(tr("canalweb.borrador_info",
                             default="Con el borrador activado, la tienda solo es visible para "
                                     "quien tenga la contraseña (ideal mientras la preparas)."),
                         size=11, color=_TEXT2))
        self.ck_borrador = QCheckBox(tr("canalweb.borrador_activar", default="Activar borrador"))
        self.ck_borrador.setChecked(bool(int(_pre.get("borrador") or 0)))
        self.ck_borrador.setStyleSheet(
            f"QCheckBox{{color:{_TEXT};font-size:12px;font-family:'{_FONT}';spacing:8px;}}")
        bw.addWidget(self.ck_borrador)
        bw.addWidget(_lbl(tr("canalweb.borrador_pass_l", default="Contraseña (déjala en blanco para "
                             "mantener la ya guardada)"), size=11, color=_TEXT2))
        self.inp_borrador_pass = self._inp("", tr("canalweb.borrador_pass_ph", default="Contraseña"))
        self.inp_borrador_pass.setEchoMode(QLineEdit.EchoMode.Password)
        bw.addWidget(self.inp_borrador_pass)
        fbb = QHBoxLayout(); fbb.addStretch()
        b_borrador_guardar = _btn(tr("canalweb.borrador_guardar", default="Guardar borrador"),
                                  color_bg=_BG2, color_fg=_VERDE, color_border=_VERDE,
                                  hover_bg=_VERDE, hover_fg="#0D1117", h=42)
        b_borrador_guardar.clicked.connect(self._guardar_borrador)
        fbb.addWidget(b_borrador_guardar)
        bw.addLayout(fbb)

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
        b_guardar = _btn(tr("canalweb.guardar", default="Guardar"), color_bg=_BG2, color_fg=_VERDE,
                         color_border=_VERDE, hover_bg=_VERDE, hover_fg="#0D1117", h=42)
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
                color=getattr(self, "_color_marca", "") or "#00FFC6",
                color_secundario=getattr(self, "_color_secundario_marca", "") or "",
                moneda=self.cmb_web_moneda.currentData() or "EUR",
                logo_url=getattr(self, "_logo_url_marca", "") or "")
        except Exception as e:
            r = {"ok": False, "error": str(e)}
        if r.get("ok"):
            self.lbl_msg.setText(tr("canalweb.m_ok", default="Marca de la web guardada."))
            self.lbl_msg.setStyleSheet(f"color:{_VERDE};font-size:11px;font-family:'{_FONT}';")
        else:
            self.lbl_msg.setText(tr("canalweb.m_err", default="No se pudo guardar la marca: {e}",
                                    e=r.get("error") or r.get("permiso") or "error"))
            self.lbl_msg.setStyleSheet(f"color:{_ROJO};font-size:11px;font-family:'{_FONT}';")

    def _abrir_pasarela_pago(self):
        """Abre el diálogo de pasarela de pago — vive en `gui/pasarela_config_dialog.py` (módulo
        NEUTRAL, fuera del TPV: este fichero tiene su propio test de arquitectura que prohíbe
        importar nada del módulo TPV, ver `pasarela_config_dialog.py` para el porqué). Reutilización
        directa, cero diálogo duplicado."""
        try:
            from src.gui.pasarela_config_dialog import PasarelaConfigDialog
            PasarelaConfigDialog(self).exec()
        except Exception as e:
            self.lbl_msg.setText(tr("canalweb.pago_err", default="No se pudo abrir la pasarela de pago: {e}", e=e))
            self.lbl_msg.setStyleSheet(f"color:{_ROJO};font-size:11px;font-family:'{_FONT}';")

    def _abrir_editor_visual(self):
        """Abre el editor visual WYSIWYG del storefront — vive en su propio módulo
        (`gui/tema_editor_dialog.py`), igual criterio que la pasarela de pago. A PANTALLA COMPLETA
        vía `abrir_dialogo_deslizante` (NUNCA un `.exec()` directo): es el mismo helper que ya
        reafirma la geometría tras el asentamiento nativo de Windows, el bug real que antes dejaba
        esta ventana (y las del módulo de correo, por el mismo motivo) abriendo más pequeña de lo
        pedido."""
        try:
            from src.gui.tema_editor_dialog import TemaEditorDialog
            from src.gui.transiciones import abrir_dialogo_deslizante
            abrir_dialogo_deslizante(TemaEditorDialog(self, usuario=self._usuario()), self)
        except Exception as e:
            self.lbl_msg.setText(tr("canalweb.tema_err", default="No se pudo abrir el editor visual: {e}", e=e))
            self.lbl_msg.setStyleSheet(f"color:{_ROJO};font-size:11px;font-family:'{_FONT}';")

    def _toggle_legal(self):
        self._legal_abierto = not getattr(self, "_legal_abierto", False)
        self._legal.setVisible(self._legal_abierto)
        self._btn_legal.setText(("📄  " + tr("canalweb.legal_hide", default="Ocultar políticas legales"))
                                if self._legal_abierto else
                                ("📄  " + tr("canalweb.legal_title", default="Políticas legales")))

    def _aplicar_plantilla_legal(self, clave, plantilla):
        self._campos_legales[clave].setPlainText(plantilla)

    def _guardar_legal(self):
        """Guarda las 4 políticas legales reutilizando `canal_web.guardar_presencia` (el MISMO
        único editor de `web_config` que ya usa `_guardar_marca` — nunca un segundo camino de
        escritura a la misma fila)."""
        try:
            from src.services.comercio_digital import canal_web as _cw
            r = _cw.guardar_presencia(
                usuario=self._usuario(),
                texto_terminos=self._campos_legales["texto_terminos"].toPlainText().strip(),
                texto_privacidad=self._campos_legales["texto_privacidad"].toPlainText().strip(),
                texto_devoluciones=self._campos_legales["texto_devoluciones"].toPlainText().strip(),
                texto_politica_envios=self._campos_legales["texto_politica_envios"].toPlainText().strip())
        except Exception as e:
            r = {"ok": False, "error": str(e)}
        if r.get("ok"):
            self.lbl_msg.setText(tr("canalweb.legal_ok", default="Políticas legales guardadas."))
            self.lbl_msg.setStyleSheet(f"color:{_VERDE};font-size:11px;font-family:'{_FONT}';")
        else:
            self.lbl_msg.setText(tr("canalweb.legal_err", default="No se pudieron guardar las políticas: {e}",
                                    e=r.get("error") or r.get("permiso") or "error"))
            self.lbl_msg.setStyleSheet(f"color:{_ROJO};font-size:11px;font-family:'{_FONT}';")

    def _toggle_borrador(self):
        self._borrador_abierto = not getattr(self, "_borrador_abierto", False)
        self._borrador_w.setVisible(self._borrador_abierto)
        self._btn_borrador.setText(
            ("🔒  " + tr("canalweb.borrador_hide", default="Ocultar borrador con contraseña"))
            if self._borrador_abierto else
            ("🔒  " + tr("canalweb.borrador_title", default="Borrador con contraseña")))

    def _guardar_borrador(self):
        """Activar/desactivar el borrador con contraseña — reutiliza
        `canal_web.configurar_borrador` (hash vía `seguridad.passwords`, mismo editor único de
        `web_config`). Dejar la contraseña en blanco mientras el borrador YA estaba activo es un
        no-op honesto (no se rota el hash sin que el usuario escriba una contraseña nueva)."""
        quiere_activar = self.ck_borrador.isChecked()
        password = self.inp_borrador_pass.text().strip()
        try:
            from src.services.comercio_digital import canal_web as _cw
            estaba_activado = bool(int(_cw.config_presencia().get("borrador") or 0))
            if quiere_activar and not password and estaba_activado:
                self.lbl_msg.setText(tr("canalweb.borrador_sin_cambios",
                                        default="El borrador ya estaba activo (sin cambiar la contraseña)."))
                self.lbl_msg.setStyleSheet(f"color:{_TEXT2};font-size:11px;font-family:'{_FONT}';")
                return
            r = _cw.configurar_borrador(activar=quiere_activar, password=password or None,
                                        usuario=self._usuario())
        except Exception as e:
            r = {"ok": False, "error": str(e)}
        if r.get("ok"):
            self.inp_borrador_pass.clear()
            self.lbl_msg.setText(
                tr("canalweb.borrador_ok_on", default="Borrador activado.") if quiere_activar else
                tr("canalweb.borrador_ok_off", default="Borrador desactivado: la tienda vuelve a ser pública."))
            self.lbl_msg.setStyleSheet(f"color:{_VERDE};font-size:11px;font-family:'{_FONT}';")
        else:
            motivo = r.get("error")
            texto = (tr("canalweb.borrador_sin_pass", default="Indica una contraseña para activar el borrador.")
                    if motivo == "password_requerida" else
                    tr("canalweb.borrador_err", default="No se pudo guardar: {e}", e=motivo or "error"))
            self.lbl_msg.setText(texto)
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
        """Despublicar es un reset completo (`canal_web.despublicar`: la marca/legales/borrador
        vuelven a sus valores por defecto en BD, y el canal deja de "existir" para que
        `abrir_canal_web` vuelva a mostrar la pregunta inicial la próxima vez). No basta con
        `_acc()`/`_refrescar()` (solo recargan la tabla de conexiones): aquí además se reflejan los
        valores por defecto en los campos YA abiertos del diálogo, para que no sigan mostrando
        datos antiguos hasta cerrarlo y volver a abrirlo."""
        from src.services.comercio_digital import canal_web
        try:
            r = canal_web.despublicar(usuario=self._usuario())
        except Exception as e:
            r = {"ok": False, "error": str(e)}
        if r.get("ok"):
            self.lbl_msg.setText(tr("canalweb.msg_desp", default="Canal despublicado."))
            self.lbl_msg.setStyleSheet(f"color:{_VERDE};font-size:11px;font-family:'{_FONT}';")
            self._resetear_campos_tras_despublicar()
        else:
            self.lbl_msg.setText(str(r.get("error") or r.get("motivo") or ""))
            self.lbl_msg.setStyleSheet(f"color:{_ROJO};font-size:11px;font-family:'{_FONT}';")
        try:
            self._refrescar()
        except Exception:
            pass

    def _resetear_campos_tras_despublicar(self):
        self.ck_web_activa.setChecked(False)
        self.inp_web_nombre.setText("")
        self.inp_web_desc.setText("")
        if hasattr(self, "_pintar_color_marca"):
            self._pintar_color_marca("#00FFC6")
        i = self.cmb_web_moneda.findData("EUR")
        if i >= 0:
            self.cmb_web_moneda.setCurrentIndex(i)
        self._logo_url_marca = ""
        self._refrescar_logo_preview()
        self.inp_dom_nuevo.setText("")
        for txt in self._campos_legales.values():
            txt.setPlainText("")
        self.ck_borrador.setChecked(False)
        self.inp_borrador_pass.setText("")

    def _acc_publicar_aws(self):
        """Publicación en un clic a AWS (Fase 5 e-commerce) — mensaje HONESTO según el modo real
        devuelto (`aws` vs `simulado`/`no_disponible`): nunca se muestra "publicado en AWS" si en
        realidad se guardó en el backend local degradado."""
        try:
            from src.services.comercio_digital import canal_web
            r = canal_web.publicar_aws(usuario=self._usuario())
        except Exception as e:
            r = {"ok": False, "motivo": str(e)}
        if r.get("ok") and r.get("modo") == "aws":
            self.lbl_msg.setText(tr("canalweb.aws_ok", default="Publicado en AWS: {u}", u=r.get("url") or ""))
            self.lbl_msg.setStyleSheet(f"color:{_VERDE};font-size:11px;font-family:'{_FONT}';")
        elif r.get("ok"):
            self.lbl_msg.setText(tr("canalweb.aws_simulado",
                                    default="No hay AWS real configurada: se guardó una vista previa "
                                            "local ({u}). Configura las credenciales AWS para publicar de verdad.",
                                    u=r.get("url") or r.get("clave") or ""))
            self.lbl_msg.setStyleSheet(f"color:{_TEXT2};font-size:11px;font-family:'{_FONT}';")
        else:
            self.lbl_msg.setText(tr("canalweb.aws_err", default="No se pudo publicar en AWS: {e}",
                                    e=r.get("motivo") or r.get("error") or "error"))
            self.lbl_msg.setStyleSheet(f"color:{_ROJO};font-size:11px;font-family:'{_FONT}';")

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
