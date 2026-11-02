"""
Sección de administración del CORREO CORPORATIVO (multi-tenant / licenciable).

Lista los buzones de la empresa activa con su proveedor, estado, tienda, licencia
y última sincronización; permite dar de alta buzones (con su licencia), conectar
OAuth 2.0 (Google), enviar un correo de prueba y eliminar (revoca tokens).

Identidad: empresa → tienda → correo. Solo ADMINISTRADOR.
"""
from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QGuiApplication, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.db import correo as correo_db
from src.db.usuario import sesion_global
from assets.estilo_global import _blindar_tamano_fijo, aplicar_estilo_widget
from src.gui._neon_ui import _RoundTableCorners, _ss_tabla_neon
from src.gui.components.enterprise import EnterpriseInlineBanner
from src.gui.gestion_usuarios import _NeonComboBox
from src.services import correo as correo_svc
from src.utils.i18n import tr

try:
    from assets.estilo_global import mostrar_confirmacion, mostrar_mensaje
except Exception:  # pragma: no cover
    mostrar_mensaje = mostrar_confirmacion = None

logger = logging.getLogger("gui.correo")

_BG = "#0E1117"
_BG2 = "#161B22"
_CIAN = "#00FFC6"
_BORDE = "#30363D"
_TEXT = "#E6EDF3"
_DIM = "#8B949E"
_ROJO = "#F85149"

# QSS inline estable para combos: el borde neón se conserva tras abrir/cerrar el
# popup (el filtro global guarda/restaura el QSS inline; sin él, lo perdían).
_COMBO_NEON = (
    f"QComboBox{{border:2px solid {_CIAN};border-radius:10px;}}"
    "QComboBox:on{border:2px solid transparent;}"
    f"QComboBox:disabled{{border:2px solid {_BORDE};}}"
)


def _listar_tiendas() -> list[dict]:
    # Cliente fino: reutiliza la capa de datos (db.tiendas.listar_tiendas) en vez de SQL directo.
    from src.db.tiendas import listar_tiendas
    return listar_tiendas()


class _NuevoCorreoDialog(QDialog):
    """Alta de un buzón corporativo + su licencia."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resultado = None
        self._build()

    def _build(self):
        card = QFrame(self)
        card.setStyleSheet(f"QFrame{{background:{_BG};border:2px solid {_CIAN};border-radius:18px;}}")
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.addWidget(card)
        ly = QVBoxLayout(card); ly.setContentsMargins(26, 22, 26, 22); ly.setSpacing(12)

        t = QLabel("✉️  " + tr("correo.nuevo_titulo", default="NUEVO CORREO CORPORATIVO"))
        t.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:15px;background:transparent;border:none;")
        ly.addWidget(t)

        def _lbl(txt):
            x = QLabel(txt); x.setStyleSheet(f"color:{_DIM};font-family:'Segoe UI';font-weight:900;font-size:11px;background:transparent;border:none;")
            return x

        self.inp_dir = QLineEdit(); self.inp_dir.setPlaceholderText("tienda001@empresa.com")
        self.inp_dir.setFixedHeight(38)
        ly.addWidget(_lbl(tr("correo.col_direccion", default="DIRECCIÓN DE CORREO")))
        ly.addWidget(self.inp_dir)

        fila = QHBoxLayout(); fila.setSpacing(12)
        col1 = QVBoxLayout(); col1.addWidget(_lbl(tr("correo.col_proveedor", default="PROVEEDOR")))
        self.cb_prov = _NeonComboBox(); self.cb_prov.setFixedHeight(38)
        self.cb_prov.setStyleSheet(_COMBO_NEON)
        self.cb_prov.setCursor(Qt.CursorShape.PointingHandCursor)
        for p in correo_db.PROVEEDORES:
            self.cb_prov.addItem(p.capitalize(), p)
        col1.addWidget(self.cb_prov); fila.addLayout(col1)

        col2 = QVBoxLayout(); col2.addWidget(_lbl(tr("correo.col_tipo", default="TIPO")))
        self.cb_tipo = _NeonComboBox(); self.cb_tipo.setFixedHeight(38)
        self.cb_tipo.setStyleSheet(_COMBO_NEON)
        self.cb_tipo.setCursor(Qt.CursorShape.PointingHandCursor)
        for t_ in correo_db.TIPOS_CORREO:
            self.cb_tipo.addItem(t_.capitalize(), t_)
        col2.addWidget(self.cb_tipo); fila.addLayout(col2)
        ly.addLayout(fila)

        fila2 = QHBoxLayout(); fila2.setSpacing(12)
        col3 = QVBoxLayout(); col3.addWidget(_lbl(tr("correo.col_tienda", default="TIENDA")))
        self.cb_tienda = _NeonComboBox(); self.cb_tienda.setFixedHeight(38)
        self.cb_tienda.setStyleSheet(_COMBO_NEON)
        self.cb_tienda.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cb_tienda.addItem(tr("correo.sin_tienda", default="— Empresa (sin tienda) —"), None)
        for t_ in _listar_tiendas():
            self.cb_tienda.addItem(f"{t_.get('codigo_tienda') or ''}  {t_['nombre']}", t_["id"])
        col3.addWidget(self.cb_tienda); fila2.addLayout(col3)

        col4 = QVBoxLayout(); col4.addWidget(_lbl(tr("correo.col_licencia", default="LICENCIA")))
        self.cb_lic = _NeonComboBox(); self.cb_lic.setFixedHeight(38)
        self.cb_lic.setStyleSheet(_COMBO_NEON)
        self.cb_lic.setCursor(Qt.CursorShape.PointingHandCursor)
        for lt in correo_db.TIPOS_LICENCIA:
            self.cb_lic.addItem(lt.replace("correo_", "").capitalize(), lt)
        col4.addWidget(self.cb_lic); fila2.addLayout(col4)
        ly.addLayout(fila2)

        # SMTP (host/puerto/usuario/contraseña de aplicación) — SOLO cuando proveedor="smtp": ya
        # existía el envío real por smtplib (`src.services.correo.servicio._enviar_smtp`) y el
        # guardado cifrado (`correo_db.guardar_smtp`), pero sin ningún campo en la GUI para
        # rellenarlos. Alternativa sin OAuth (sin Google Cloud Console): p. ej. Gmail con una
        # "contraseña de aplicación" de 16 caracteres, host smtp.gmail.com, puerto 587.
        self.wrap_smtp = QWidget()
        ly_smtp = QVBoxLayout(self.wrap_smtp); ly_smtp.setContentsMargins(0, 0, 0, 0); ly_smtp.setSpacing(8)
        fila3 = QHBoxLayout(); fila3.setSpacing(12)
        col5 = QVBoxLayout(); col5.addWidget(_lbl(tr("correo.smtp_host", default="SERVIDOR SMTP")))
        self.inp_smtp_host = QLineEdit(); self.inp_smtp_host.setFixedHeight(38)
        self.inp_smtp_host.setPlaceholderText("smtp.gmail.com")
        col5.addWidget(self.inp_smtp_host); fila3.addLayout(col5, 2)
        col6 = QVBoxLayout(); col6.addWidget(_lbl(tr("correo.smtp_port", default="PUERTO")))
        self.inp_smtp_port = QLineEdit("587"); self.inp_smtp_port.setFixedHeight(38)
        col6.addWidget(self.inp_smtp_port); fila3.addLayout(col6, 1)
        ly_smtp.addLayout(fila3)
        ly_smtp.addWidget(_lbl(tr("correo.smtp_usuario", default="USUARIO SMTP (normalmente la misma dirección)")))
        self.inp_smtp_usuario = QLineEdit(); self.inp_smtp_usuario.setFixedHeight(38)
        ly_smtp.addWidget(self.inp_smtp_usuario)
        ly_smtp.addWidget(_lbl(tr("correo.smtp_password",
                                  default="CONTRASEÑA DE APLICACIÓN (no la contraseña normal)")))
        self.inp_smtp_password = QLineEdit(); self.inp_smtp_password.setFixedHeight(38)
        self.inp_smtp_password.setEchoMode(QLineEdit.EchoMode.Password)
        ly_smtp.addWidget(self.inp_smtp_password)
        ly.addWidget(self.wrap_smtp)
        self.wrap_smtp.setVisible(self.cb_prov.currentData() == "smtp")
        self.cb_prov.currentIndexChanged.connect(
            lambda: self.wrap_smtp.setVisible(self.cb_prov.currentData() == "smtp"))

        botones = QHBoxLayout(); botones.addStretch()
        bc = QPushButton(tr("correo.cancelar", default="CANCELAR")); bc.setFixedSize(130, 40)
        bc.setCursor(Qt.CursorShape.PointingHandCursor)
        bc.setStyleSheet(f"QPushButton{{background:{_BG};color:#F85149;border:2px solid #F85149;border-radius:10px;font-weight:900;}}QPushButton:hover{{background:#F85149;color:{_BG};}}")
        bc.clicked.connect(self.reject)
        bk = QPushButton("✔  " + tr("correo.crear", default="CREAR")); bk.setFixedSize(180, 40)
        bk.setCursor(Qt.CursorShape.PointingHandCursor)
        bk.setStyleSheet(f"QPushButton{{background:{_BG};color:{_CIAN};border:2px solid {_CIAN};border-radius:10px;font-weight:900;}}QPushButton:hover{{background:{_CIAN};color:{_BG};}}")
        bk.clicked.connect(self._aceptar)
        botones.addWidget(bc); botones.addWidget(bk)
        ly.addLayout(botones)
        self.setMinimumWidth(360); self.setMaximumWidth(560)  # responsive (P2): antes fijo 560

    def _aceptar(self):
        direccion = self.inp_dir.text().strip()
        if "@" not in direccion or "." not in direccion:
            if mostrar_mensaje:
                mostrar_mensaje(self, tr("correo.error_titulo", default="Datos incompletos"),
                                tr("correo.error_direccion", default="Introduce una dirección de correo válida."), "warning")
            return
        proveedor = self.cb_prov.currentData()
        smtp = None
        if proveedor == "smtp":
            host = self.inp_smtp_host.text().strip()
            if not host:
                if mostrar_mensaje:
                    mostrar_mensaje(self, tr("correo.error_titulo", default="Datos incompletos"),
                                    tr("correo.error_smtp_host",
                                       default="Introduce el servidor SMTP (p. ej. smtp.gmail.com)."),
                                    "warning")
                return
            smtp = {
                "host": host,
                "port": self.inp_smtp_port.text().strip() or 587,
                "usuario": self.inp_smtp_usuario.text().strip() or direccion,
                "password": self.inp_smtp_password.text(),
            }
        self.resultado = {
            "direccion": direccion,
            "proveedor": proveedor,
            "tipo": self.cb_tipo.currentData(),
            "id_tienda": self.cb_tienda.currentData(),
            "tipo_licencia": self.cb_lic.currentData(),
            "smtp": smtp,
        }
        self.accept()


class _AdjuntosMultiplesWidget(QWidget):
    """Selector de MÚLTIPLES adjuntos para el compositor de correo: selector de archivos
    (multi-selección vía `QFileDialog`), pegado de imágenes/capturas desde el portapapeles
    (botón + atajo Ctrl+V — `QGuiApplication.clipboard()`), lista con miniatura (imágenes,
    `QPixmap` escalado) o icono genérico (resto de tipos) y botón de quitar por fila.

    Límites (documentados, no configurables desde la GUI): 10 archivos / 25 MB en total por
    envío. Si una adición superaría cualquiera de los dos, se descarta ESA adición (las que sí
    caben se añaden igualmente) y se muestra un aviso inline no-modal (`EnterpriseInlineBanner`)
    con el detalle — nunca se trunca en silencio.

    Autocontenido: no reutiliza `_AdjuntosWidget` de `circulares_gui.py` (dominio distinto,
    sin miniaturas/pegado/límites) para no arriesgar regresiones en circulares."""

    MAX_ARCHIVOS = 10
    MAX_TOTAL_BYTES = 25 * 1024 * 1024  # 25 MB

    _EXT_IMAGEN = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rutas: list[str] = []
        self._tamanos: dict[str, int] = {}
        self._filas: dict[str, QWidget] = {}
        self.setStyleSheet("background:transparent;")

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        fila_botones = QHBoxLayout(); fila_botones.setSpacing(8)
        self.btn_elegir = QPushButton("📎  " + tr("correo.adjuntar", default="Adjuntar archivos"))
        self.btn_elegir.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_elegir.setFixedHeight(34)
        self.btn_elegir.setStyleSheet(
            f"QPushButton{{background:{_BG};color:{_CIAN};border:2px solid {_CIAN};"
            f"border-radius:8px;font-weight:900;font-size:11px;padding:0 12px;}}"
            f"QPushButton:hover{{background:{_CIAN};color:{_BG};}}")
        self.btn_elegir.clicked.connect(self._elegir_archivos)
        fila_botones.addWidget(self.btn_elegir)

        self.btn_pegar = QPushButton("🖼  " + tr("correo.pegar_captura", default="Pegar captura (Ctrl+V)"))
        self.btn_pegar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pegar.setFixedHeight(34)
        self.btn_pegar.setStyleSheet(
            f"QPushButton{{background:{_BG};color:{_DIM};border:2px solid {_BORDE};"
            f"border-radius:8px;font-weight:900;font-size:11px;padding:0 12px;}}"
            f"QPushButton:hover{{background:{_DIM};color:{_BG};border-color:{_DIM};}}")
        self.btn_pegar.clicked.connect(self._pegar_portapapeles)
        fila_botones.addWidget(self.btn_pegar)
        fila_botones.addStretch()
        v.addLayout(fila_botones)

        # Ctrl+V con foco en este widget (no roba el atajo global del diálogo contenedor).
        atajo = QShortcut(QKeySequence.StandardKey.Paste, self)
        atajo.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        atajo.activated.connect(self._pegar_portapapeles)

        self._banner = EnterpriseInlineBanner("", rol="advertencia")
        self._banner.hide()
        v.addWidget(self._banner)

        self._lista = QVBoxLayout(); self._lista.setSpacing(4)
        v.addLayout(self._lista)

        self.lbl_resumen = QLabel(self._texto_resumen())
        self.lbl_resumen.setStyleSheet(f"color:{_DIM};font-size:10px;background:transparent;border:none;")
        v.addWidget(self.lbl_resumen)

    # ── Selección ────────────────────────────────────────────────────────────
    def _elegir_archivos(self):
        rutas, _f = QFileDialog.getOpenFileNames(
            self, tr("correo.adjuntar_titulo", default="Adjuntar archivos"), "",
            "Todos los archivos (*.*)")
        if rutas:
            self._agregar_rutas(rutas)

    def _pegar_portapapeles(self):
        cb = QGuiApplication.clipboard()
        md = cb.mimeData() if cb else None
        if md is None or not md.hasImage():
            self._mostrar_aviso(tr("correo.sin_imagen_portapapeles",
                                   default="No hay ninguna imagen en el portapapeles."))
            return
        imagen = cb.image()
        if imagen.isNull():
            self._mostrar_aviso(tr("correo.sin_imagen_portapapeles",
                                   default="No hay ninguna imagen en el portapapeles."))
            return
        try:
            carpeta = os.path.join(tempfile.gettempdir(), "smartmanager_correo_pegado")
            os.makedirs(carpeta, exist_ok=True)
            nombre = "captura_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".png"
            ruta = os.path.join(carpeta, nombre)
            pix = QPixmap.fromImage(imagen)
            if pix.isNull() or not pix.save(ruta, "PNG"):
                raise RuntimeError("no se pudo guardar el PNG del portapapeles")
        except Exception as e:
            logger.error("pegar captura de portapapeles: %s", e)
            self._mostrar_aviso(tr("correo.error_pegar", default="No se pudo guardar la captura pegada."))
            return
        self._agregar_rutas([ruta])

    def _agregar_rutas(self, rutas: list[str]):
        rechazadas = []
        for ruta in rutas:
            if not ruta or ruta in self._rutas:
                continue
            if not os.path.isfile(ruta):
                rechazadas.append((os.path.basename(ruta),
                                   tr("correo.archivo_no_encontrado", default="no encontrado")))
                continue
            if len(self._rutas) >= self.MAX_ARCHIVOS:
                rechazadas.append((os.path.basename(ruta),
                                   tr("correo.limite_archivos", default="máximo {n} archivos",
                                      n=self.MAX_ARCHIVOS)))
                continue
            try:
                tam = os.path.getsize(ruta)
            except OSError:
                rechazadas.append((os.path.basename(ruta),
                                   tr("correo.archivo_no_encontrado", default="no encontrado")))
                continue
            if self._tamano_total() + tam > self.MAX_TOTAL_BYTES:
                rechazadas.append((os.path.basename(ruta),
                                   tr("correo.limite_tamano", default="supera los {mb} MB en total",
                                      mb=self.MAX_TOTAL_BYTES // (1024 * 1024))))
                continue
            self._rutas.append(ruta)
            self._tamanos[ruta] = tam
            self._añadir_fila(ruta)
        self.lbl_resumen.setText(self._texto_resumen())
        if rechazadas:
            detalle = "; ".join(f"{n} ({m})" for n, m in rechazadas)
            self._mostrar_aviso(tr("correo.adjuntos_rechazados",
                                   default="No se adjuntaron: {detalle}", detalle=detalle))
        else:
            self._banner.hide()

    def _mostrar_aviso(self, texto):
        self._banner.set_mensaje(texto)
        self._banner.show()

    def _tamano_total(self) -> int:
        return sum(self._tamanos.get(r, 0) for r in self._rutas)

    def _texto_resumen(self) -> str:
        mb = self._tamano_total() / (1024 * 1024)
        return tr("correo.resumen_adjuntos", default="{n}/{max_n} archivos · {mb:.1f}/{maxmb} MB",
                  n=len(self._rutas), max_n=self.MAX_ARCHIVOS, mb=mb,
                  maxmb=self.MAX_TOTAL_BYTES // (1024 * 1024))

    # ── Fila visual (miniatura + nombre + quitar) ───────────────────────────
    def _añadir_fila(self, ruta):
        cont = QWidget(); cont.setStyleSheet(f"background:{_BG2};border:1px solid {_BORDE};border-radius:8px;")
        fila = QHBoxLayout(cont); fila.setContentsMargins(6, 4, 6, 4); fila.setSpacing(8)

        miniatura = QLabel()
        miniatura.setFixedSize(32, 32)
        miniatura.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ext = os.path.splitext(ruta)[1].lower()
        if ext in self._EXT_IMAGEN:
            pix = QPixmap(ruta)
            if not pix.isNull():
                miniatura.setPixmap(pix.scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation))
            else:
                miniatura.setText("🖼"); miniatura.setStyleSheet("font-size:18px;")
        else:
            miniatura.setText("📄")
            miniatura.setStyleSheet("font-size:18px;")
        fila.addWidget(miniatura)

        tam_kb = self._tamanos.get(ruta, 0) / 1024
        info = QLabel(f"{os.path.basename(ruta)}\n{tam_kb:.0f} KB")
        info.setStyleSheet(f"color:{_TEXT};font-size:11px;background:transparent;border:none;")
        fila.addWidget(info, 1)

        btn_quitar = QPushButton("✕")
        btn_quitar.setFixedSize(22, 22)
        btn_quitar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_quitar.setStyleSheet(f"QPushButton{{background:transparent;color:{_ROJO};border:none;"
                                 f"font-weight:900;}}QPushButton:hover{{color:#FF7B72;}}")
        btn_quitar.clicked.connect(lambda: self._quitar(ruta))
        fila.addWidget(btn_quitar)

        self._lista.addWidget(cont)
        self._filas[ruta] = cont

    def _quitar(self, ruta):
        if ruta in self._rutas:
            self._rutas.remove(ruta)
        self._tamanos.pop(ruta, None)
        w = self._filas.pop(ruta, None)
        if w is not None:
            w.setParent(None); w.deleteLater()
        self.lbl_resumen.setText(self._texto_resumen())
        if len(self._rutas) < self.MAX_ARCHIVOS and self._tamano_total() < self.MAX_TOTAL_BYTES:
            self._banner.hide()

    # ── API pública ───────────────────────────────────────────────────────────
    def rutas(self) -> list[str]:
        """Rutas de archivo de los adjuntos actualmente en la lista, en orden de adición."""
        return list(self._rutas)


class EnviarDocumentoDialog(QDialog):
    """Diálogo reutilizable: enviar un documento generado (PDF, etc.) desde un
    buzón corporativo de la empresa. Lo usan los módulos que generan documentos
    (albaranes, facturas, nóminas, informes...) para 'enviar desde el correo de
    la tienda'."""

    def __init__(self, ruta_documento: str, asunto: str = "", destinatario: str = "", parent=None,
                 contexto: str = None, pistas: dict = None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._ruta = ruta_documento
        self._contexto = contexto   # módulo desde el que se redacta (prioriza fuentes afines)
        self._autocomplete = None
        # Resolución documental (Parte N): si no hay destinatario pero sí pistas del documento
        # (nombre/nif/correo del cliente/proveedor/empleado…), se resuelve vía el Servicio único.
        if not destinatario and pistas:
            try:
                from src.services import destinatarios as _dest
                d = _dest.resolver_para_documento(contexto=contexto, **pistas)
                if d:
                    destinatario = d.correo
            except Exception as e:
                logger.debug("resolver_para_documento: %s", e)
        self._buzones = [c for c in correo_db.listar_correos() if c.get("estado") == "activo"]
        self._build(asunto, destinatario)

    def _build(self, asunto, destinatario):
        import os
        card = QFrame(self)
        card.setStyleSheet(f"QFrame{{background:{_BG};border:2px solid {_CIAN};border-radius:18px;}}")
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.addWidget(card)
        ly = QVBoxLayout(card); ly.setContentsMargins(26, 22, 26, 22); ly.setSpacing(10)

        t = QLabel("📤  " + tr("correo.env_titulo", default="ENVIAR DOCUMENTO POR CORREO"))
        t.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:15px;background:transparent;border:none;")
        ly.addWidget(t)

        def _lbl(x):
            q = QLabel(x); q.setStyleSheet(f"color:{_DIM};font-family:'Segoe UI';font-weight:900;font-size:11px;background:transparent;border:none;")
            return q

        adj = QLabel("📎  " + os.path.basename(self._ruta or ""))
        adj.setStyleSheet(f"color:{_TEXT};font-family:'Segoe UI';font-size:12px;background:{_BG2};border:1px solid {_BORDE};border-radius:8px;padding:8px 10px;")
        ly.addWidget(_lbl(tr("correo.env_adjunto", default="DOCUMENTO ADJUNTO")))
        ly.addWidget(adj)

        ly.addWidget(_lbl(tr("correo.env_buzon", default="ENVIAR DESDE (BUZÓN)")))
        self.cb_buzon = _NeonComboBox(); self.cb_buzon.setFixedHeight(38)
        self.cb_buzon.setStyleSheet(_COMBO_NEON)
        self.cb_buzon.setCursor(Qt.CursorShape.PointingHandCursor)
        for b in self._buzones:
            etq = b["direccion"] + (f"  ·  {b.get('tienda_nombre')}" if b.get("tienda_nombre") else "")
            self.cb_buzon.addItem(etq, b["id_correo"])
        ly.addWidget(self.cb_buzon)

        ly.addWidget(_lbl(tr("correo.env_destinatario", default="DESTINATARIO")))
        self.inp_dest = QLineEdit(destinatario); self.inp_dest.setFixedHeight(38)
        self.inp_dest.setPlaceholderText("destinatario@ejemplo.com")
        ly.addWidget(self.inp_dest)
        # Autocompletado corporativo de destinatarios (Servicio único; multiempresa + contexto).
        try:
            from src.gui.destinatarios_autocomplete import instalar_autocompletado
            self._autocomplete = instalar_autocompletado(self.inp_dest, contexto=self._contexto)
        except Exception as e:
            logger.debug("autocompletado destinatarios no disponible: %s", e)

        ly.addWidget(_lbl(tr("correo.env_asunto", default="ASUNTO")))
        self.inp_asunto = QLineEdit(asunto); self.inp_asunto.setFixedHeight(38)
        ly.addWidget(self.inp_asunto)

        ly.addWidget(_lbl(tr("correo.env_adjuntos_extra", default="ADJUNTOS ADICIONALES (ARCHIVOS/FOTOS/CAPTURAS)")))
        self._adjuntos_widget = _AdjuntosMultiplesWidget()
        ly.addWidget(self._adjuntos_widget)

        botones = QHBoxLayout(); botones.addStretch()
        bc = QPushButton(tr("correo.cancelar", default="CANCELAR")); bc.setFixedSize(130, 40)
        bc.setCursor(Qt.CursorShape.PointingHandCursor)
        bc.setStyleSheet(f"QPushButton{{background:{_BG};color:#F85149;border:2px solid #F85149;border-radius:10px;font-weight:900;}}QPushButton:hover{{background:#F85149;color:{_BG};}}")
        bc.clicked.connect(self.reject)
        bk = QPushButton("📤  " + tr("correo.env_enviar", default="ENVIAR")); bk.setFixedSize(180, 40)
        bk.setCursor(Qt.CursorShape.PointingHandCursor)
        bk.setStyleSheet(f"QPushButton{{background:{_BG};color:{_CIAN};border:2px solid {_CIAN};border-radius:10px;font-weight:900;}}QPushButton:hover{{background:{_CIAN};color:{_BG};}}")
        bk.clicked.connect(self._enviar)
        botones.addWidget(bc); botones.addWidget(bk)
        ly.addLayout(botones)
        self.setMinimumWidth(360); self.setMaximumWidth(560)  # responsive (P2): antes fijo 560

    def _enviar(self):
        if not self._buzones:
            if mostrar_mensaje:
                mostrar_mensaje(self, tr("correo.aviso", default="Aviso"),
                                tr("correo.env_sin_buzones", default="No hay buzones corporativos activos. Crea uno en la sección Correo."), "warning")
            return
        dest = self.inp_dest.text().strip()
        if "@" not in dest:
            if mostrar_mensaje:
                mostrar_mensaje(self, tr("correo.error_titulo", default="Datos incompletos"),
                                tr("correo.env_falta_dest", default="Introduce un destinatario válido."), "warning")
            return
        cuerpo = tr("correo.env_cuerpo", default="Documento adjunto generado por Smart Manager.")
        adj = ([self._ruta] if self._ruta else []) + self._adjuntos_widget.rutas()
        adj = adj or None
        asunto = self.inp_asunto.text().strip()
        # Correo = primer consumidor de la CCP: el envío pasa por la plataforma corporativa, que
        # internamente usa el MISMO motor de envío y el buzón elegido. Registra Communication ID,
        # historial y telemetría. Respaldo directo si la CCP no estuviera disponible (retrocompat).
        try:
            from src.services import ccp as _ccp
            res = _ccp.enviar_comunicacion(
                destinatario=dest, asunto=asunto, cuerpo=cuerpo, adjuntos=adj, canal="email",
                contexto=self._contexto, id_correo=self.cb_buzon.currentData())
            ok, msg = res.ok, res.mensaje
        except Exception as e:
            logger.debug("CCP no disponible; envío directo: %s", e)
            ok, msg = correo_svc.enviar_documento(self.cb_buzon.currentData(), dest, asunto, cuerpo, adj)
        if mostrar_mensaje:
            mostrar_mensaje(self, tr("correo.envio_titulo", default="Envío"), msg, "info" if ok else "error")
        if ok:
            self.accept()


def enviar_documento_por_correo(parent, ruta_documento: str, asunto: str = "", destinatario: str = "",
                                contexto: str = None, pistas: dict = None) -> bool:
    """Punto de entrada reutilizable para 'enviar documento desde el correo de la
    tienda'. Lo pueden llamar albaranes, facturas, nóminas, informes, etc. `contexto` (opcional)
    indica el módulo desde el que se redacta para priorizar sugerencias afines; `pistas` (opcional)
    permite la resolución documental automática del destinatario (correo/nombre/nif/tipo del
    cliente/proveedor/empleado). Todo retrocompatible."""
    dlg = EnviarDocumentoDialog(ruta_documento, asunto, destinatario, parent, contexto=contexto,
                                pistas=pistas)
    return dlg.exec() == QDialog.DialogCode.Accepted


def _btn_accion(txt, slot, *, primary=False, danger=False, h=40):
    """Botón de la barra de acciones (con hover swap)."""
    b = QPushButton(txt); b.setFixedHeight(h); b.setCursor(Qt.CursorShape.PointingHandCursor)
    if danger:
        c, bg, borde = _ROJO, _BG, _ROJO
    elif primary:
        c, bg, borde = _CIAN, _BG2, _CIAN
    else:
        c, bg, borde = _DIM, _BG2, _BORDE
    b.setStyleSheet(f"QPushButton{{background:{bg};color:{c};border:2px solid {borde};border-radius:10px;"
                    f"font-weight:900;font-size:12px;padding:0 16px;}}"
                    f"QPushButton:hover{{background:{c};color:{_BG};border-color:{c};}}")
    b.clicked.connect(slot)
    return b


class _BuzonesDialog(QDialog):
    """Gestión de BUZONES de la empresa (alta, OAuth, prueba, baja). La lista de buzones ya NO se muestra en la
    ventana principal: se abre bajo demanda desde el botón «Buzones» (los buzones se sugieren al redactar o en la
    Agenda). Frameless con contorno neón propio."""

    _PESO_COL0 = 1.45

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Buzones de correo")
        self.setMinimumSize(1040, 560)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setStyleSheet(f"QDialog{{background:{_BG};border:2px solid {_CIAN};border-radius:14px;}}"
                           f"QLabel{{background:transparent;border:none;}}")
        self._drag = None
        self._filas = []
        self._build()
        self.refrescar()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft(); e.accept()

    def mouseMoveEvent(self, e):
        if self._drag is not None and (e.buttons() & Qt.MouseButton.LeftButton):
            self.move(e.globalPosition().toPoint() - self._drag); e.accept()

    def mouseReleaseEvent(self, e):
        self._drag = None; super().mouseReleaseEvent(e)

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(22, 18, 22, 18); root.setSpacing(12)
        cab = QHBoxLayout(); cab.setSpacing(10)
        t = QLabel(tr("correo.buzones_titulo", default="CORREOS CONFIGURADOS"))
        t.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:18px;")
        cab.addWidget(t); cab.addStretch()
        bx_cerrar = QPushButton("✕")
        bx_cerrar.setFixedSize(38, 38)
        bx_cerrar.setCursor(Qt.CursorShape.PointingHandCursor)
        bx_cerrar.setStyleSheet(
            f"QPushButton{{background:transparent;color:{_ROJO};border:none;border-radius:19px;padding:0;"
            f"font-weight:900;font-size:18px;}}"
            f"QPushButton:hover{{background:{_ROJO};color:#0D1117;}}")
        bx_cerrar.setProperty("sin_glow", True)
        _blindar_tamano_fijo(bx_cerrar, 38, 38)
        bx_cerrar.clicked.connect(self.accept)
        cab.addWidget(bx_cerrar)
        root.addLayout(cab)
        acc = QHBoxLayout(); acc.setSpacing(10)
        acc.addWidget(_btn_accion("✉️  " + tr("correo.nuevo", default="NUEVO CORREO"), self._nuevo, primary=True))
        acc.addWidget(_btn_accion("🔗  " + tr("correo.conectar", default="CONECTAR (OAuth)"), self._conectar,
                                  primary=True))
        acc.addWidget(_btn_accion("📤  " + tr("correo.enviar_prueba", default="ENVIAR PRUEBA"),
                                  self._enviar_prueba, primary=True))
        acc.addStretch()
        root.addLayout(acc)
        cols = [
            tr("correo.col_direccion", default="CORREO"), tr("correo.col_proveedor", default="PROVEEDOR"),
            tr("correo.col_tipo", default="TIPO"), tr("correo.col_estado", default="ESTADO"),
            tr("correo.col_tienda", default="TIENDA"), tr("correo.col_licencia", default="LICENCIA"),
            tr("correo.col_lic_estado", default="EST. LIC."), tr("correo.col_oauth", default="OAUTH"),
            tr("correo.col_sync", default="ÚLT. SINC."), tr("correo.col_alta", default="ALTA"),
        ]
        self.tabla = QTableWidget(0, len(cols)); self.tabla.setHorizontalHeaderLabels(cols)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.verticalHeader().setVisible(False)
        hdr = self.tabla.horizontalHeader(); hdr.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        hdr.setHighlightSections(False)
        self.tabla.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tabla.setFrameShape(QTableWidget.Shape.NoFrame)
        self.tabla.setStyleSheet(_ss_tabla_neon())          # contorno neón + cabeceras redondeadas + hover swap
        self._mask = _RoundTableCorners(self.tabla, radius=10)
        root.addWidget(self.tabla, 1)
        fila_elim = QHBoxLayout(); fila_elim.addStretch()
        fila_elim.addWidget(_btn_accion("🗑  " + tr("correo.eliminar", default="ELIMINAR"), self._eliminar,
                                        danger=True))
        root.addLayout(fila_elim)
        self.lbl_estado = QLabel(""); self.lbl_estado.setStyleSheet(f"color:{_DIM};font-size:11px;")
        root.addWidget(self.lbl_estado)
        QTimer.singleShot(0, self._ajustar_columnas)

    def _ajustar_columnas(self):
        try:
            n = self.tabla.columnCount(); w = self.tabla.viewport().width()
            if n <= 1 or w <= 0:
                return
            unidad = w / (self._PESO_COL0 + (n - 1))
            ancho0 = int(unidad * self._PESO_COL0); resto = int(unidad)
            self.tabla.setColumnWidth(0, ancho0)
            for c in range(1, n - 1):
                self.tabla.setColumnWidth(c, resto)
            self.tabla.setColumnWidth(n - 1, max(resto, w - ancho0 - resto * (n - 2)))
        except Exception:
            pass

    def resizeEvent(self, e):
        super().resizeEvent(e); self._ajustar_columnas()

    def refrescar(self):
        self._filas = correo_db.listar_correos()
        self.tabla.setRowCount(len(self._filas))
        for r, c in enumerate(self._filas):
            est_oauth = correo_svc.estado_oauth(c["id_correo"])
            oauth_txt = "✔" if est_oauth["conectado"] else "—"
            valores = [
                c.get("direccion", ""), str(c.get("proveedor", "")).capitalize(),
                str(c.get("tipo", "")).capitalize(), str(c.get("estado", "")).capitalize(),
                c.get("tienda_nombre") or tr("correo.sin_tienda_corta", default="(empresa)"),
                str(c.get("tipo_licencia") or "—").replace("correo_", "").capitalize(),
                str(c.get("licencia_estado") or "—").capitalize(), oauth_txt,
                str(c.get("ultima_sincronizacion") or "—"), str(c.get("fecha_alta") or "—"),
            ]
            for col, v in enumerate(valores):
                it = QTableWidgetItem("  " + str(v))
                if col == 0:
                    it.setForeground(Qt.GlobalColor.white)
                self.tabla.setItem(r, col, it)
        self.lbl_estado.setText(tr("correo.resumen", default="{n} correo(s) configurado(s).", n=len(self._filas)))

    def _correo_seleccionado(self) -> dict | None:
        r = self.tabla.currentRow()
        if r < 0 or r >= len(self._filas):
            if mostrar_mensaje:
                mostrar_mensaje(self, tr("correo.aviso", default="Aviso"),
                                tr("correo.selecciona", default="Selecciona un correo de la lista."), "info")
            return None
        return self._filas[r]

    def _nuevo(self):
        dlg = _NuevoCorreoDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.resultado:
            return
        d = dlg.resultado
        lic = correo_db.crear_licencia(tipo_licencia=d["tipo_licencia"], id_tienda=d["id_tienda"])
        cid = correo_db.crear_correo(d["direccion"], proveedor=d["proveedor"], tipo=d["tipo"],
                                     id_tienda=d["id_tienda"], id_licencia=lic)
        if cid and d.get("smtp"):
            correo_db.guardar_smtp(cid, host=d["smtp"]["host"], port=d["smtp"]["port"],
                                   usuario=d["smtp"]["usuario"], password=d["smtp"]["password"])
        if cid and mostrar_mensaje:
            mostrar_mensaje(self, tr("correo.creado_titulo", default="Correo creado"),
                            tr("correo.creado_msg", default="Buzón {dir} dado de alta.", dir=d["direccion"]), "info")
        elif not cid and mostrar_mensaje:
            mostrar_mensaje(self, tr("correo.error_titulo", default="Error"),
                            tr("correo.error_crear", default="No se pudo crear el correo (¿duplicado?)."), "error")
        self.refrescar()

    def _conectar(self):
        c = self._correo_seleccionado()
        if not c:
            return
        if c.get("proveedor") != "google":
            if mostrar_mensaje:
                mostrar_mensaje(self, tr("correo.aviso", default="Aviso"),
                                tr("correo.solo_google", default="La conexión OAuth está disponible para proveedor Google."), "info")
            return
        if not correo_svc.oauth_google_configurado():
            if mostrar_mensaje:
                mostrar_mensaje(self, tr("correo.oauth_no_conf_titulo", default="OAuth no configurado"),
                                tr("correo.oauth_no_conf_msg",
                                   default="No se pudo iniciar la conexión con Google: la aplicación no "
                                           "tiene configurado su cliente OAuth. Contacta con el soporte "
                                           "de Smart Manager."), "warning")
            return
        ok, msg = correo_svc.iniciar_oauth_google(c["id_correo"])
        if ok:
            # Sincroniza una vez automáticamente: listo para empezar a trabajar sin pasos
            # adicionales (best-effort — un fallo de sincronización nunca rompe el mensaje de
            # "conectado correctamente", que ya es cierto en ese momento).
            try:
                correo_svc.sincronizar_gmail_api(c["id_correo"])
            except Exception as e:
                logger.debug("sincronización automática tras conectar OAuth: %s", e)
        if mostrar_mensaje:
            mostrar_mensaje(self, tr("correo.oauth_titulo", default="Conexión OAuth"), msg, "info" if ok else "error")
        self.refrescar()

    def _enviar_prueba(self):
        c = self._correo_seleccionado()
        if not c:
            return
        ok, msg = correo_svc.enviar_documento(
            c["id_correo"], c["direccion"],
            tr("correo.prueba_asunto", default="Correo de prueba — Smart Manager"),
            tr("correo.prueba_cuerpo", default="Este es un envío de prueba desde Smart Manager."))
        if mostrar_mensaje:
            mostrar_mensaje(self, tr("correo.envio_titulo", default="Envío"), msg, "info" if ok else "error")
        self.refrescar()

    def _eliminar(self):
        c = self._correo_seleccionado()
        if not c:
            return
        if mostrar_confirmacion and not mostrar_confirmacion(
            self, tr("correo.eliminar_titulo", default="Eliminar correo"),
            tr("correo.eliminar_msg", default="¿Eliminar {dir}? Se revocarán sus tokens.", dir=c["direccion"])):
            return
        correo_db.eliminar_correo(c["id_correo"])
        self.refrescar()


def _vaciar_layout(layout):
    """Quita y destruye (recursivamente) todos los widgets/sub-layouts de `layout`, dejándolo
    vacío sin destruir el layout contenedor en sí. Usado para reconstruir el área variable de la
    bandeja de Gmail (vacía/vincular vs. inbox real) en cada `refrescar()`."""
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.setParent(None)
            w.deleteLater()
            continue
        sub = item.layout()
        if sub is not None:
            _vaciar_layout(sub)


class _FilaRemitenteCelda(QWidget):
    """Casilla de selección múltiple + texto del REMITENTE compartiendo la MISMA celda (columna 0
    de la tabla, sin columna aparte — petición explícita del usuario), para poder aplicar una misma
    acción de carpeta (IMPORTANTE/POSPONER/PAPELERA/RESTAURAR/CANCELAR PROGRAMACIÓN) a varios
    mensajes a la vez. Clicar la casilla SOLO marca/desmarca (no abre el mensaje, ver
    `on_check`); clicar el resto de la celda (el texto) selecciona la fila Y abre el mensaje —
    mismo comportamiento que tenía la celda antes de añadir la casilla (`on_abrir`)."""

    def __init__(self, texto, negrita, on_check, on_abrir, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        self._on_abrir = on_abrir
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 0, 2, 0)
        lay.setSpacing(6)
        self.checkbox = QCheckBox()
        self.checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        # Estilo inline explícito (mismo criterio que el botón SALIR del sidebar, ver
        # `_build_sidebar`): esta ventana ya tiene su propio `setStyleSheet()` en la raíz, lo que
        # rompe la cascada del QSS global hacia descendientes — no depender de ella aquí tampoco.
        self.checkbox.setStyleSheet(
            f"QCheckBox::indicator{{width:16px;height:16px;}}"
            f"QCheckBox::indicator:unchecked{{border:1px solid {_BORDE};background:{_BG2};"
            f"border-radius:3px;}}"
            f"QCheckBox::indicator:checked{{border:1px solid {_CIAN};background:{_CIAN};"
            f"border-radius:3px;}}")
        self.checkbox.toggled.connect(lambda checked: on_check(checked))
        lay.addWidget(self.checkbox, 0, Qt.AlignmentFlag.AlignVCenter)
        lbl = QLabel("  " + str(texto))
        f = lbl.font(); f.setBold(negrita); f.setPixelSize(13); lbl.setFont(f)
        lbl.setStyleSheet("color:white;background:transparent;")
        lay.addWidget(lbl, 1, Qt.AlignmentFlag.AlignVCenter)

    def mousePressEvent(self, event):
        # Clic en cualquier punto de la celda QUE NO SEA la propia casilla (esta ya consume el
        # evento ella misma, nunca llega aquí): mismo comportamiento que antes de la casilla.
        if self._on_abrir:
            self._on_abrir()
        super().mousePressEvent(event)


def _usuario_actual_cc() -> dict:
    try:
        return sesion_global.usuario_actual or {}
    except Exception:
        return {}


def _leido_ids(tipo_entidad: str, ids: list, usuario_id) -> set:
    """IDs de `ids` que `usuario_id` ya marcó leídos (`com_destinatarios.leido=1`). Lectura directa
    de solo consulta — la escritura vive en la capa de servicio
    (`circulares.marcar_leido_circular`/`encuestas.marcar_leido_encuesta`)."""
    ids = [i for i in (ids or []) if i is not None]
    if not ids or usuario_id is None:
        return set()
    try:
        from src.db.conexion import obtener_conexion
        marcadores = ",".join(["%s"] * len(ids))
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT id_entidad FROM com_destinatarios WHERE tipo_entidad=%s AND usuario_id=%s "
                f"AND id_entidad IN ({marcadores}) AND leido=1",
                (tipo_entidad, usuario_id, *ids))
            return {r[0] for r in cur.fetchall()}
    except Exception as e:
        logger.debug("_leido_ids(%s): %s", tipo_entidad, e)
        return set()


# Carpetas de la columna lateral estilo Gmail: (id, icono, clave i18n, texto por defecto).
# Solo «recibidos» y «enviados» tienen una fuente de datos real (ver docstring de la clase);
# el resto se muestra para que la UI quede visualmente completa, pero con un aviso honesto de
# "no disponible" (CLAUDE.md: nunca falsear con mocks una capacidad que no existe de verdad).
_CARPETAS = [
    ("recibidos", "📥", "correo.carpeta_recibidos", "Recibidos"),
    ("pospuestos", "⏰", "correo.carpeta_pospuestos", "Pospuestos"),
    ("enviados", "📤", "correo.carpeta_enviados", "Enviados"),
    ("borradores", "📝", "correo.carpeta_borradores", "Borradores"),
    ("papelera", "🗑", "correo.carpeta_papelera", "Papelera"),
    ("programados", "🕒", "correo.carpeta_programados", "Programados"),
    ("importantes", "⭐", "correo.carpeta_importantes", "Importantes"),
]


class CorreoCorporativoWindow(QWidget):
    """Ventana principal del módulo CORREO: bandeja ÚNICA estilo Gmail (columna lateral de
    carpetas + lista de mensajes), fusionando tres fuentes en «Recibidos»: los correos Gmail
    sincronizados (`db.correo.listar_recibidos`, solo lectura) y las circulares/encuestas
    internas dirigidas al usuario actual (`services.comunicacion_interna`). Ya NO existe un popup
    separado para comunicados (`BandejaComunicacionDialog` queda huérfana en `circulares_gui.py`,
    Strangler Pattern — ver CLAUDE.md): todo vive aquí.

    Clic sobre una fila Gmail oculta la lista y muestra el contenido en primer plano (como Gmail),
    con un botón «← Volver a la bandeja»; clic sobre una circular/encuesta abre su visor modal ya
    existente (`_CircularViewerDialog`/`_EncuestaViewerDialog`). Sin columna "LEÍDO": los mensajes
    no leídos se muestran en negrita, igual que Gmail.

    Las 7 carpetas tienen fuente de datos REAL (migración 0288): Recibidos (las tres fuentes,
    excluyendo lo pospuesto/en papelera) y Enviados (circulares/encuestas PUBLICADAS creadas por el
    usuario — Gmail no se sincroniza en modo envío, solo lectura); Borradores/Papelera/Programados/
    Pospuestos/Importantes son reales para circulares/encuestas (`estado`/`pospuesto_hasta`/
    `importante`, ver `services.comunicacion_interna.circulares`/`encuestas`), y Papelera/
    Pospuestos/Importantes TAMBIÉN para el correo Gmail sincronizado (columnas propias en
    `correos_recibidos`, siempre LOCALES — nunca se llama a la API de Gmail para nada destructivo).
    «Importantes» es una estrella MANUAL (Gmail no expone su etiqueta algorítmica IMPORTANT por
    sync de solo lectura) y «Pospuestos»/«Papelera»/«importante» son estados COMPARTIDOS por
    circular/encuesta (no por-destinatario) — ver docstrings de `circulares.py`/`encuestas.py`
    para el porqué de esa simplificación deliberada."""

    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self._main = main
        self._carpeta_actual = "recibidos"
        self._filas = []             # filas normalizadas de la carpeta actualmente pintada
        self._filas_marcadas = set() # (tipo, id) de las filas con la casilla de selección activada
        self._buzones_conectados = []
        self.cb_buzon = None
        self.tabla = None
        self._botones_accion = []    # botones de la barra superior (test de alineación)
        self.setStyleSheet(f"background:{_BG};")
        # Delegación a SOMA (SUPERADMIN): construida ANTES de `_build()` porque tanto el sidebar
        # (botón) como el stack de contenido (página) necesitan saber si existe; se decide una
        # sola vez aquí para que ambos lean el mismo resultado sin reordenar `_build()`.
        self._pagina_delegacion = None
        if str((sesion_global.usuario_actual or {}).get("perfil", "")).strip().upper() == "SUPERADMIN":
            from src.gui.soma_delegacion_gui import DelegacionSomaPanel
            self._pagina_delegacion = DelegacionSomaPanel(
                pantalla="correo", usuario=sesion_global.usuario_actual)
        self._build()
        self.refrescar()

    def _build(self):
        # Root ENTERPRISE: sidebar de carpetas (ancho fijo, TODA la altura de la ventana) | columna
        # de contenido (cabecera + barra de acciones + bandeja) — mismo patrón estructural que
        # `recepcion_pale.py::setup_ui` ("SMART LOGISTICS"): `QHBoxLayout` raíz sin márgenes/espaciado
        # conteniendo directamente el QFrame de sidebar (objectName reconocido por `QSS_SIDEBAR` en
        # `assets/estilo_global.py`). Antes el root era un QVBoxLayout con la cabecera y la barra de
        # acciones ARRIBA de un `body` horizontal más abajo: el sidebar nunca llegaba a ocupar toda
        # la altura y la cabecera/acciones "invadían" visualmente su columna. Ahora el sidebar es
        # hermano directo del contenido, de arriba a abajo.
        root = QHBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        self._sidebar = self._build_sidebar()
        root.addWidget(self._sidebar)

        contenido = QWidget()
        col = QVBoxLayout(contenido); col.setContentsMargins(28, 22, 28, 22); col.setSpacing(16)

        # Cabecera: solo título (sin X de cierre — igual que el resto de módulos enterprise de la
        # app, que salen por el botón "SALIR" al final del sidebar, ver `_build_sidebar()`, no por
        # una X en la esquina).
        cab = QHBoxLayout()
        titulo = QLabel("📧  " + tr("correo.titulo", default="CORREO CORPORATIVO"))
        titulo.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:22px;background:transparent;")
        cab.addWidget(titulo); cab.addStretch()
        col.addLayout(cab)

        # Barra de acciones: TODOS los botones a la MISMA altura (44px) y en la MISMA fila —
        # crear (izquierda) + utilidades/sincronizar (derecha). Antes «SINCRONIZAR» quedaba en una
        # fila propia más abajo, descuadrada del resto; ahora vive aquí siempre (deshabilitado si
        # no hay ninguna cuenta de Gmail conectada con la que sincronizar).
        acc = QHBoxLayout(); acc.setSpacing(10)
        self._botones_accion = []

        def _add(btn):
            btn.setFixedHeight(44)
            self._botones_accion.append(btn)
            return btn

        # Visibilidad por rol (mismo idioma que `gestion_usuarios.py`/`menu_principal.py`:
        # `usuario_actual.get("perfil")` comparado en mayúsculas): OPERARIO no ve ninguno de los dos
        # botones de creación; ADMINISTRADOR ve solo NUEVO MENSAJE; SUPERADMIN ve ambos. (Un agente
        # en paralelo está rediseñando la bandeja de esta misma ventana — este cambio se limita a la
        # visibilidad de estos dos botones, sin tocar el área de bandeja/tabla.)
        _perfil_actual = str((sesion_global.usuario_actual or {}).get("perfil", "")).strip().upper()
        if _perfil_actual != "OPERARIO":
            acc.addWidget(_add(_btn_accion("✉️  " + tr("correo.circulares", default="NUEVO MENSAJE"),
                                           self._nueva_circular, primary=True, h=44)))
        if _perfil_actual == "SUPERADMIN":
            acc.addWidget(_add(_btn_accion("📊  " + tr("correo.encuestas", default="NUEVA ENCUESTA"),
                                           self._nueva_encuesta, primary=True, h=44)))
        acc.addStretch()

        def _btn_outline(txt, slot):
            b = QPushButton(txt)
            b.setCursor(Qt.CursorShape.PointingHandCursor); b.setFixedHeight(44)
            b.setStyleSheet(f"QPushButton{{background:transparent;color:{_CIAN};border:2px solid {_CIAN};"
                           "border-radius:9px;font-weight:900;padding:0 16px;}"
                           f"QPushButton:hover{{background:{_CIAN};color:{_BG};}}")
            b.clicked.connect(slot)
            return b

        acc.addWidget(_add(_btn_outline("📇  " + tr("correo.agenda", default="AGENDA"), self._abrir_agenda)))
        acc.addWidget(_add(_btn_outline("📡  CCP", self._abrir_ccp)))
        acc.addWidget(_add(_btn_outline("✉️  " + tr("correo.buzones", default="CONFIGURAR CORREO"),
                                        self._abrir_buzones)))
        self.btn_sincronizar = _add(_btn_accion("🔄  " + tr("correo.sincronizar", default="SINCRONIZAR"),
                                                self._sincronizar, primary=True, h=44))
        acc.addWidget(self.btn_sincronizar)
        col.addLayout(acc)

        # Cuerpo variable: lista/detalle de la bandeja. El sidebar de carpetas ya NO vive aquí —
        # es hermano directo de esta columna en el `root` horizontal, fuera de sus márgenes, para
        # que ocupe toda la altura de la ventana (ver `root` arriba).
        self._stack = QStackedWidget()
        self._pagina_lista = QWidget()
        self._layout_lista = QVBoxLayout(self._pagina_lista)
        self._layout_lista.setContentsMargins(0, 0, 0, 0); self._layout_lista.setSpacing(10)
        self._pagina_detalle = QWidget()
        self._layout_detalle = QVBoxLayout(self._pagina_detalle)
        self._layout_detalle.setContentsMargins(0, 0, 0, 0); self._layout_detalle.setSpacing(10)
        self._stack.addWidget(self._pagina_lista)
        self._stack.addWidget(self._pagina_detalle)
        # Delegación a SOMA (SUPERADMIN): 3ª página del mismo stack, fuera del grupo de carpetas
        # (no es una carpeta de la bandeja, así que no participa de `_cambiar_carpeta`/su
        # animación de deslizamiento) — construida en `__init__`, ver botón de sidebar dedicado
        # en `_build_sidebar()`.
        if self._pagina_delegacion is not None:
            self._stack.addWidget(self._pagina_delegacion)
        col.addWidget(self._stack, 1)

        self.lbl_estado = QLabel("")
        self.lbl_estado.setStyleSheet(f"color:{_DIM};font-family:'Segoe UI';font-size:11px;background:transparent;")
        col.addWidget(self.lbl_estado)

        root.addWidget(contenido, 1)

    def _build_sidebar(self):
        """Columna lateral de carpetas con el MISMO patrón ESTRUCTURAL que el resto de sidebars
        ENTERPRISE de la app (idéntico a `recepcion_pale.py::setup_ui`, "SMART LOGISTICS"): QFrame
        de ancho fijo 280 con `objectName="sidebar_modulo"` — reconocido globalmente por
        `QSS_SIDEBAR` en `assets/estilo_global.py` (background/borde ya vienen de ahí, nada
        hand-rolled aquí) — con su propio `QVBoxLayout(contentsMargins=(0,40,0,20))`, título "SMART
        MAIL" con `objectName="sidebar_title"` (fuente/color/espaciado también globales, igual
        patrón que "SMART LOGISTICS"/"SMART CONFIG") como primer elemento, y debajo los mismos
        botones `_SidebarBtn` de `gestion_usuarios.py` reutilizados tal cual (checkable+
        autoExclusive, 55px, borde izquierdo cian al marcar, hover blanco/oscuro — llevan su propio
        estilo inline, no dependen del QSS global). Import local (no en cabecera) para no forzar a
        cargar `gestion_usuarios.py` en todo arranque que solo abra Correo."""
        from src.gui.gestion_usuarios import _SidebarBtn
        panel = QFrame()
        panel.setObjectName("sidebar_modulo")
        panel.setFixedWidth(280)
        v = QVBoxLayout(panel); v.setContentsMargins(0, 40, 0, 20); v.setSpacing(0)

        titulo = QLabel(tr("correo.sidebar_titulo", default="SMART MAIL").upper())
        titulo.setObjectName("sidebar_title")
        v.addWidget(titulo)

        self._grupo_carpetas = QButtonGroup(panel)
        self._grupo_carpetas.setExclusive(True)
        self._botones_carpeta = {}
        for cid, _icono, clave, por_defecto in _CARPETAS:
            # Sin emoji — igual que "SMART LOGISTICS"/"SMART CONFIG" (solo texto). `_icono` se
            # conserva en `_CARPETAS` porque otras partes del módulo SÍ lo usan (p. ej. la columna
            # TIPO de la tabla), pero el botón del sidebar ya no lo antepone.
            # Mayúsculas — igual que el resto de pestañas/botones de sidebar de la app (p. ej.
            # "SALIR", "SMART LOGISTICS"), que usan el texto literal en mayúsculas (QSS no soporta
            # text-transform). Antes solo tenían mayúscula inicial (Title Case).
            b = _SidebarBtn(tr(clave, default=por_defecto).upper())
            # Tamaño: tras subirlo dos veces (+1pt, +1pt más → 14px) el usuario pidió bajarlo 2
            # puntos de nuevo — vuelve a coincidir con el tamaño base de `_SidebarBtn` (12px), así
            # que ya no hace falta ningún override local.
            b.clicked.connect(lambda _checked=False, c=cid: self._cambiar_carpeta(c))
            self._grupo_carpetas.addButton(b)
            self._botones_carpeta[cid] = b
            v.addWidget(b)
        # Delegación a SOMA (SUPERADMIN): botón aparte — no es una carpeta de correo, así que su
        # `clicked` no pasa por `_cambiar_carpeta` (muestra directamente la 3ª página del stack
        # construida en `_build()`) — pero SÍ se añade al MISMO `QButtonGroup` exclusivo que los
        # botones de carpeta para que el acento turquesa de "seleccionado" se mueva aquí al
        # pulsarlo (y vuelva a una carpeta cuando se pulse otra), igual que el resto del sidebar.
        # Ausente del todo para otros perfiles (ni siquiera deshabilitado).
        if self._pagina_delegacion is not None:
            btn_delegacion = _SidebarBtn("DELEGACIÓN IA")
            btn_delegacion.setCheckable(True)
            self._grupo_carpetas.addButton(btn_delegacion)
            btn_delegacion.clicked.connect(self._mostrar_delegacion_ia)
            v.addWidget(btn_delegacion)

        v.addStretch()
        self._botones_carpeta["recibidos"].setChecked(True)

        # "SALIR" al final del sidebar en vez de la X roja de la esquina — mismo patrón EXACTO que
        # el resto de módulos enterprise de la app (`recepcion_pale.py`: objectName
        # "btn_sidebar_exit", ya estilizado en rojo globalmente por `QSS_SIDEBAR`, sin hand-rollear
        # nada aquí). La X de la cabecera se retira en `_build()` (ver más abajo). Condicionado a
        # `self._volver` igual que la X que sustituye (ya resuelto en `__init__` antes de `_build()`).
        if self._volver:
            btn_salir = QPushButton(tr("correo.salir", default="SALIR"))
            btn_salir.setObjectName("btn_sidebar_exit")
            btn_salir.setFixedHeight(55)
            btn_salir.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_salir.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            btn_salir.setMouseTracking(True)
            # El `:hover` del QSS global (`QSS_SIDEBAR#btn_sidebar_exit`) no se repintaba de forma
            # fiable aquí (reportado tras el primer intento con solo WA_Hover+aplicar_estilo_widget)
            # — esta ventana YA tiene su propio `setStyleSheet()` a nivel de widget raíz
            # (`self.setStyleSheet(f"background:{_BG};")`, en `__init__`), y una vez CUALQUIER
            # ancestro en la jerarquía tiene su propia hoja de estilos, la cascada de Qt hacia
            # selectores por objectName en descendientes deja de ser fiable para pseudo-estados como
            # `:hover`. Fix definitivo: copiar la regla EXACTA (mismos colores que `COLOR_ROJO_ERROR`/
            # `COLOR_FONDO_APP` en `assets/estilo_global.py`, aquí `_ROJO`/`_BG`) como estilo INLINE
            # de este botón concreto — no depende de ninguna cascada, nunca puede quedar sin aplicar.
            btn_salir.setStyleSheet(
                f"QPushButton{{text-align:left;padding:6px 8px 6px 28px;color:{_ROJO};"
                f"background-color:transparent;border:none;border-radius:0px;"
                f"font-family:'Segoe UI';font-weight:900;letter-spacing:0.5px;}}"
                f"QPushButton:hover{{background-color:{_ROJO};color:{_BG};}}")
            btn_salir.clicked.connect(self._volver_menu)
            v.addWidget(btn_salir)
            try:
                aplicar_estilo_widget(btn_salir)
            except Exception:
                pass
        return panel

    def _volver_menu(self):
        if self._volver:
            self._volver()
        self.close()

    @staticmethod
    def _etq_pagina(self, pagina):
        """Nombre legible de una página del stack, para los logs de diagnóstico — "DELEGACION_IA"/
        "LISTA"/"DETALLE"/"OTRA(repr)" en vez de la dirección de memoria del objeto Qt."""
        if pagina is None:
            return "None"
        if pagina is self._pagina_lista:
            return "LISTA(bandeja)"
        if pagina is self._pagina_detalle:
            return "DETALLE"
        if pagina is getattr(self, "_pagina_delegacion", None):
            return "DELEGACION_IA"
        return f"OTRA({pagina!r})"

    def _mostrar_delegacion_ia(self):
        pagina_antes = self._etq_pagina(self, self._stack.currentWidget())
        logger.info("[CORREO-CARPETA] click sidebar: DELEGACION_IA | pagina_stack_antes=%s "
                   "(carpeta_actual sigue siendo %r, NO se toca — ver _cambiar_carpeta)",
                   pagina_antes, self._carpeta_actual)
        self._stack.setCurrentWidget(self._pagina_delegacion)

    def _cambiar_carpeta(self, carpeta_id):
        pagina_antes = self._etq_pagina(self, self._stack.currentWidget())
        logger.info("[CORREO-CARPETA] click sidebar: carpeta=%r (actual=%r) | pagina_stack_antes=%s",
                   carpeta_id, self._carpeta_actual, pagina_antes)
        # BUG REAL encontrado y corregido aquí: `self._carpeta_actual` SOLO lo actualiza este
        # método — pero el botón "Delegación IA" cambia el stack con su PROPIO manejador
        # (`self._stack.setCurrentWidget(self._pagina_delegacion)`, ver `_build_sidebar()`), sin
        # pasar por aquí. Si el usuario ya estaba en p.ej. "Importantes" antes de entrar a
        # Delegación IA y vuelve a pulsar "Importantes", `carpeta_id == self._carpeta_actual` era
        # cierto DESDE EL PRINCIPIO (nunca se había actualizado) y el método cortaba aquí sin
        # volver a activar `_pagina_lista` — el sidebar marcaba "Importantes" pero la pantalla
        # seguía mostrando Delegación IA. El guard de "no hacer nada" ahora exige ADEMÁS que el
        # stack ya esté mostrando la bandeja, no solo que el id de carpeta coincida.
        ya_mostrando_esta_carpeta = (carpeta_id == self._carpeta_actual
                                     and self._stack.currentWidget() is self._pagina_lista)
        if ya_mostrando_esta_carpeta:
            logger.info("[CORREO-CARPETA] ya se estaba mostrando esta carpeta -> no hace nada")
            return
        self._carpeta_actual = carpeta_id
        self._animar_cambio_carpeta()

    def _animar_cambio_carpeta(self):
        """Cambiar de carpeta repinta el contenido de `_pagina_lista` (normalmente en el sitio,
        sin cambio de página de stack que `transiciones.instalar_transicion_stack` pueda enganchar
        solo vía `currentChanged`). Reutiliza directamente el MISMO motor de deslizamiento que usa
        el resto de la app (`transiciones._deslizar` — recorrido de la anchura COMPLETA del
        contenedor, 240ms, InOutCubic).

        Dos casos:
        - Repintado EN EL SITIO (carpeta -> carpeta, el caso normal): saliente y entrante son el
          MISMO widget, así que se captura su instantánea ANTES de repintar (`_deslizar` solo
          puede capturar en caliente cuando saliente y entrante son widgets DISTINTOS) y se pasa
          como `snapshot_viejo`, para que la carpeta anterior se vea deslizándose hacia fuera.
        - Venir de OTRA página del stack que no es la bandeja (p. ej. "Delegación IA",
          `self._pagina_delegacion`): esa página queda oculta por el `setCurrentWidget` de abajo
          — SIN snapshot (ver más abajo el porqué: mostrarlo deslizándose por encima se veía como
          un parpadeo de la pantalla anterior). Antes de este fix, sin el `setCurrentWidget`
          siquiera, `_pagina_lista` se repintaba pero seguía OCULTA detrás de la página anterior
          — el sidebar marcaba la carpeta nueva pero la pantalla seguía mostrando Delegación IA,
          "colgada"."""
        from src.gui.transiciones import _DUR, _deslizar, capturar_pantalla
        widget = self._pagina_lista
        pagina_saliente = self._stack.currentWidget()
        logger.info("[CORREO-CARPETA] animar: pagina_saliente=%s", self._etq_pagina(self, pagina_saliente))
        # Si la transición anterior seguía en marcha (cambio más rápido que sus 240ms), se detiene
        # antes de arrancar la siguiente — nunca dos animaciones compitiendo por la misma
        # propiedad `pos` del mismo widget (`_deslizar` deja la entrante en `widget._a_in`).
        anterior = getattr(widget, "_a_in", None)
        if anterior is not None:
            logger.info("[CORREO-CARPETA] deteniendo animacion anterior en marcha (estado=%s)",
                       anterior.state())
            try:
                anterior.stop()
            except Exception:
                logger.error("[CORREO-CARPETA] fallo deteniendo la animacion anterior", exc_info=True)
        # El "snapshot_viejo" (instantánea de la pantalla ANTERIOR, que `_deslizar` muestra
        # deslizándose hacia fuera mientras la nueva entra) solo tiene sentido cuando la pantalla
        # saliente es la MISMA bandeja con el contenido de la carpeta anterior (no hay otra forma
        # de animar un repintado en el sitio). Si se viene de OTRA página del stack (p. ej.
        # "Delegación IA"), esa página ya queda oculta por el `setCurrentWidget` de abajo — mostrar
        # ADEMÁS su instantánea deslizándose por encima es lo que el usuario veía como un
        # "parpadeo" de Delegación IA antes de asentarse en la carpeta nueva: no aporta nada (son
        # pantallas de naturaleza distinta, no una continuación de la misma bandeja) y solo añade
        # ruido visual. En ese caso se omite del todo: la carpeta nueva simplemente entra deslizando
        # desde la izquierda, sin ningún rastro de la pantalla anterior.
        es_repintado_en_el_sitio = pagina_saliente is widget
        snapshot_anterior = None
        if es_repintado_en_el_sitio:
            try:
                snapshot_anterior = capturar_pantalla(widget) if widget.isVisible() else None
            except Exception:
                logger.error("[CORREO-CARPETA] fallo capturando la instantanea de la pagina saliente",
                            exc_info=True)
        logger.info("[CORREO-CARPETA] repintado_en_el_sitio=%s snapshot_capturado=%s",
                   es_repintado_en_el_sitio, snapshot_anterior is not None)
        self._pintar_carpeta()
        pagina_tras_pintar = self._etq_pagina(self, self._stack.currentWidget())
        if self._stack.currentWidget() is not widget:
            logger.info("[CORREO-CARPETA] stack seguia en %s tras repintar -> forzando "
                       "setCurrentWidget(LISTA)", pagina_tras_pintar)
            self._stack.setCurrentWidget(widget)
        logger.info("[CORREO-CARPETA] pagina_stack_final=%s (debe ser LISTA(bandeja))",
                   self._etq_pagina(self, self._stack.currentWidget()))
        _deslizar(None, widget, _DUR, snapshot_viejo=snapshot_anterior)

    # ── Bandeja unificada ─────────────────────────────────────────────────────
    def refrescar(self):
        """Refresca la carpeta actualmente abierta (recarga mensajes/circulares/encuestas, el
        estado de conexión de Gmail y el banner/selector correspondientes)."""
        self._pintar_carpeta()

    def _pintar_carpeta(self):
        _vaciar_layout(self._layout_lista)
        self.tabla = None
        self.cb_buzon = None
        buzones_google = [c for c in correo_db.listar_correos() if c.get("proveedor") == "google"]
        self._buzones_conectados = [
            b for b in buzones_google if correo_svc.estado_oauth(b["id_correo"]).get("conectado")
        ]
        self.btn_sincronizar.setEnabled(bool(self._buzones_conectados))
        carpeta = self._carpeta_actual
        if carpeta == "recibidos":
            self._pintar_recibidos(buzones_google)
        elif carpeta == "enviados":
            self._pintar_enviados()
        elif carpeta == "borradores":
            self._pintar_borradores()
        elif carpeta == "papelera":
            self._pintar_papelera()
        elif carpeta == "programados":
            self._pintar_programados()
        elif carpeta == "pospuestos":
            self._pintar_pospuestos()
        elif carpeta == "importantes":
            self._pintar_importantes()
        else:
            self._pintar_no_disponible(tr(
                "correo.no_disp_generica",
                default="Esta función todavía no está disponible en Smart Manager."))
        self._stack.setCurrentWidget(self._pagina_lista)

    # ── Barra de acciones contextual por carpeta (opera sobre la fila seleccionada) ──────────────
    def _fila_acciones_carpeta(self):
        carpeta = self._carpeta_actual
        fila = QHBoxLayout(); fila.setSpacing(8)
        if carpeta == "recibidos":
            # IMPORTANTE/POSPONER: turquesa estándar de la app (mismo `_btn_accion(primary=True)`
            # que el resto de botones cian) — antes gris/dim por omisión de `primary=True`. PAPELERA
            # se queda tal cual (rojo/`danger=True`, acción destructiva intencional).
            fila.addWidget(_btn_accion("⭐  " + tr("correo.marcar_importante", default="IMPORTANTE"),
                                       lambda: self._accion_importante(True), primary=True))
            fila.addWidget(_btn_accion("⏰  " + tr("correo.posponer", default="POSPONER"),
                                       self._accion_posponer, primary=True))
            fila.addWidget(_btn_accion("🗑  " + tr("correo.mover_papelera", default="PAPELERA"),
                                       self._accion_papelera, danger=True))
        elif carpeta == "papelera":
            fila.addWidget(_btn_accion("♻  " + tr("correo.restaurar", default="RESTAURAR"),
                                       self._accion_restaurar, primary=True))
        elif carpeta == "programados":
            fila.addWidget(_btn_accion(
                "✖  " + tr("correo.cancelar_programacion", default="CANCELAR PROGRAMACIÓN"),
                self._accion_cancelar_programacion, danger=True))
        elif carpeta == "importantes":
            fila.addWidget(_btn_accion("⭐  " + tr("correo.quitar_importante", default="QUITAR IMPORTANTE"),
                                       lambda: self._accion_importante(False)))
        elif carpeta == "borradores":
            fila.addWidget(_btn_accion("🗑  " + tr("correo.eliminar_borrador", default="ELIMINAR BORRADOR"),
                                       self._accion_eliminar_borrador, danger=True))
        fila.addStretch()
        return fila

    def _fila_seleccionada(self):
        if self.tabla is None:
            return None
        r = self.tabla.currentRow()
        if not (0 <= r < len(self._filas)):
            if mostrar_mensaje:
                mostrar_mensaje(self, tr("correo.aviso", default="Aviso"),
                                tr("correo.selecciona_fila", default="Selecciona un mensaje de la lista."),
                                "info")
            return None
        return self._filas[r]

    def _filas_seleccionadas_multiples(self):
        """Filas sobre las que debe operar la acción de carpeta actual (IMPORTANTE/POSPONER/
        PAPELERA/RESTAURAR/CANCELAR PROGRAMACIÓN/ELIMINAR BORRADOR): si hay una o más casillas de
        selección marcadas (`_filas_marcadas`, ver `_FilaRemitenteCelda`), esas; si no hay ninguna
        marcada, cae al comportamiento de siempre (la única fila con foco en la tabla, vía
        `_fila_seleccionada` — incluye su aviso si no hay ninguna)."""
        if self._filas_marcadas:
            claves = set(self._filas_marcadas)
            return [it for it in self._filas if (it["tipo"], it["id"]) in claves]
        item = self._fila_seleccionada()
        return [item] if item else []

    def _accion_importante(self, valor: bool):
        items = self._filas_seleccionadas_multiples()
        if not items:
            return
        for item in items:
            try:
                if item["tipo"] == "gmail":
                    correo_db.marcar_recibido_importante(item["id"], valor)
                elif item["tipo"] == "circular":
                    from src.services.comunicacion_interna import circulares
                    circulares.marcar_importante(item["id"], valor)
                else:
                    from src.services.comunicacion_interna import encuestas
                    encuestas.marcar_importante(item["id"], valor)
            except Exception as e:
                logger.error("marcar importante: %s", e)
        self._pintar_carpeta()

    def _accion_posponer(self):
        items = self._filas_seleccionadas_multiples()
        if not items:
            return
        from src.gui.circulares_gui import _FechaHoraDialog
        dlg = _FechaHoraDialog(self, titulo=tr("correo.posponer_t", default="POSPONER HASTA"))
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.resultado:
            return
        for item in items:
            try:
                if item["tipo"] == "gmail":
                    correo_db.posponer_recibido(item["id"], dlg.resultado)
                elif item["tipo"] == "circular":
                    from src.services.comunicacion_interna import circulares
                    circulares.posponer(item["id"], dlg.resultado)
                else:
                    from src.services.comunicacion_interna import encuestas
                    encuestas.posponer(item["id"], dlg.resultado)
            except Exception as e:
                logger.error("posponer: %s", e)
        self._pintar_carpeta()

    def _accion_papelera(self):
        items = self._filas_seleccionadas_multiples()
        if not items:
            return
        u = _usuario_actual_cc()
        for item in items:
            try:
                if item["tipo"] == "gmail":
                    correo_db.mover_recibido_papelera(item["id"])
                elif item["tipo"] == "circular":
                    from src.services.comunicacion_interna import circulares
                    r = circulares.mover_papelera(item["id"], usuario=u)
                    if not r.get("ok") and mostrar_mensaje:
                        mostrar_mensaje(self, tr("correo.error_titulo", default="Error"), r.get("error", ""),
                                        "warning")
                else:
                    from src.services.comunicacion_interna import encuestas
                    r = encuestas.mover_papelera(item["id"], usuario=u)
                    if not r.get("ok") and mostrar_mensaje:
                        mostrar_mensaje(self, tr("correo.error_titulo", default="Error"), r.get("error", ""),
                                        "warning")
            except Exception as e:
                logger.error("mover a papelera: %s", e)
        self._pintar_carpeta()

    def _accion_restaurar(self):
        items = self._filas_seleccionadas_multiples()
        if not items:
            return
        u = _usuario_actual_cc()
        for item in items:
            try:
                if item["tipo"] == "gmail":
                    correo_db.restaurar_recibido(item["id"])
                elif item["tipo"] == "circular":
                    from src.services.comunicacion_interna import circulares
                    circulares.restaurar_de_papelera(item["id"], usuario=u)
                else:
                    from src.services.comunicacion_interna import encuestas
                    encuestas.restaurar_de_papelera(item["id"], usuario=u)
            except Exception as e:
                logger.error("restaurar: %s", e)
        self._pintar_carpeta()

    def _accion_cancelar_programacion(self):
        items = self._filas_seleccionadas_multiples()
        if not items:
            return
        u = _usuario_actual_cc()
        for item in items:
            try:
                if item["tipo"] == "circular":
                    from src.services.comunicacion_interna import circulares
                    circulares.cancelar_programacion(item["id"], usuario=u)
                else:
                    from src.services.comunicacion_interna import encuestas
                    encuestas.cancelar_programacion(item["id"], usuario=u)
            except Exception as e:
                logger.error("cancelar programación: %s", e)
        self._pintar_carpeta()

    def _accion_eliminar_borrador(self):
        items = self._filas_seleccionadas_multiples()
        if not items:
            return
        msg = (tr("correo.eliminar_borrador_msg", default="¿Eliminar este borrador definitivamente?")
               if len(items) == 1 else
               tr("correo.eliminar_borradores_msg_multi",
                  default="¿Eliminar estos {n} borradores definitivamente?", n=len(items)))
        if mostrar_confirmacion and not mostrar_confirmacion(
            self, tr("correo.eliminar_titulo", default="Eliminar"), msg):
            return
        u = _usuario_actual_cc()
        for item in items:
            try:
                if item["tipo"] == "circular":
                    from src.services.comunicacion_interna import circulares
                    circulares.eliminar_borrador(item["id"], usuario=u)
                else:
                    from src.services.comunicacion_interna import encuestas
                    encuestas.eliminar_borrador(item["id"], usuario=u)
            except Exception as e:
                logger.error("eliminar borrador: %s", e)
        self._pintar_carpeta()

    def _pintar_recibidos(self, buzones_google):
        if not self._buzones_conectados:
            self._layout_lista.addWidget(self._banner_vincular(buzones_google))
        elif len(self._buzones_conectados) > 1:
            self._layout_lista.addLayout(self._fila_selector_buzon())
        self._filas = self._cargar_bandeja_unificada()
        if self._filas:
            self._layout_lista.addLayout(self._fila_acciones_carpeta())
        self._renderizar_lista(self._filas)

    def _pintar_borradores(self):
        """BORRADORES — real: circulares/encuestas propias en `estado='BORRADOR'`. Clic en una fila
        reabre el compositor precargado (ver `_abrir_fila_unificada`)."""
        from src.services.comunicacion_interna import circulares, encuestas
        uid = _usuario_actual_cc().get("id")
        filas = []
        for c in circulares.listar_borradores(uid):
            filas.append({
                "tipo": "circular", "id": c["id"], "remitente_o_emisor": c.get("creador_nombre") or "—",
                "asunto_o_titulo": c.get("titulo") or tr("correo.sin_titulo", default="(sin título)"),
                "fecha": c.get("creado"), "leido": True, "raw": c,
            })
        for e in encuestas.listar_borradores(uid):
            filas.append({
                "tipo": "encuesta", "id": e["id"], "remitente_o_emisor": e.get("creador_nombre") or "—",
                "asunto_o_titulo": e.get("titulo") or tr("correo.sin_titulo", default="(sin título)"),
                "fecha": e.get("creado"), "leido": True, "raw": e,
            })
        filas.sort(key=lambda x: str(x["fecha"] or ""), reverse=True)
        self._filas = filas
        if filas:
            self._layout_lista.addLayout(self._fila_acciones_carpeta())
        self._renderizar_lista(filas, nota=tr(
            "correo.nota_borradores",
            default="Borradores guardados — haz clic en uno para seguir editándolo."))

    def _pintar_papelera(self):
        """PAPELERA — real y LOCAL: circulares/encuestas propias en `estado='PAPELERA'` + correo
        Gmail marcado `papelera=1` (soft-delete local, nunca se llama a la API de Gmail)."""
        from src.services.comunicacion_interna import circulares, encuestas
        uid = _usuario_actual_cc().get("id")
        filas = []
        for m in correo_db.listar_recibidos_papelera():
            filas.append({
                "tipo": "gmail", "id": m.get("id"), "remitente_o_emisor": m.get("remitente") or "—",
                "asunto_o_titulo": m.get("asunto") or "—",
                "fecha": m.get("fecha") or m.get("fecha_descarga"), "leido": True, "raw": m,
            })
        for c in circulares.listar_papelera(uid):
            filas.append({
                "tipo": "circular", "id": c["id"], "remitente_o_emisor": c.get("creador_nombre") or "—",
                "asunto_o_titulo": c.get("titulo") or "—", "fecha": c.get("creado"), "leido": True, "raw": c,
            })
        for e in encuestas.listar_papelera(uid):
            filas.append({
                "tipo": "encuesta", "id": e["id"], "remitente_o_emisor": e.get("creador_nombre") or "—",
                "asunto_o_titulo": e.get("titulo") or "—", "fecha": e.get("creado"), "leido": True, "raw": e,
            })
        filas.sort(key=lambda x: str(x["fecha"] or ""), reverse=True)
        self._filas = filas
        if filas:
            self._layout_lista.addLayout(self._fila_acciones_carpeta())
        self._renderizar_lista(filas, nota=tr(
            "correo.nota_papelera",
            default="Papelera LOCAL de Smart Manager — nunca se borra ni se modifica nada en tu "
                    "cuenta real de Gmail."))

    def _pintar_programados(self):
        """PROGRAMADOS — real: circulares/encuestas propias en `estado='PROGRAMADA'`, disparadas
        automáticamente por el job del scheduler `com_programados_envio` al llegar su hora."""
        from src.services.comunicacion_interna import circulares, encuestas
        uid = _usuario_actual_cc().get("id")
        filas = []
        for c in circulares.listar_programadas(uid):
            filas.append({
                "tipo": "circular", "id": c["id"], "remitente_o_emisor": c.get("creador_nombre") or "—",
                "asunto_o_titulo": c.get("titulo") or "—", "fecha": c.get("fecha_programada"),
                "leido": True, "raw": c,
            })
        for e in encuestas.listar_programadas(uid):
            filas.append({
                "tipo": "encuesta", "id": e["id"], "remitente_o_emisor": e.get("creador_nombre") or "—",
                "asunto_o_titulo": e.get("titulo") or "—", "fecha": e.get("fecha_programada"),
                "leido": True, "raw": e,
            })
        filas.sort(key=lambda x: str(x["fecha"] or ""))
        self._filas = filas
        if filas:
            self._layout_lista.addLayout(self._fila_acciones_carpeta())
        self._renderizar_lista(filas, nota=tr(
            "correo.nota_programados",
            default="Envío programado — se publicará automáticamente en la fecha/hora indicada "
                    "(solo destinatarios internos; los contactos externos no se incluyen en el "
                    "envío programado)."))

    def _pintar_pospuestos(self):
        """POSPUESTOS — real: resuelve solo con la consulta (sin job en segundo plano, igual que
        Gmail): mientras `pospuesto_hasta` está en el futuro, el mensaje aparece aquí en vez de en
        Recibidos; en cuanto vence, reaparece en Recibidos en la siguiente lectura."""
        from src.services.comunicacion_interna import circulares, encuestas
        uid = _usuario_actual_cc().get("id")
        filas = []
        for m in correo_db.listar_recibidos_pospuestos():
            filas.append({
                "tipo": "gmail", "id": m.get("id"), "remitente_o_emisor": m.get("remitente") or "—",
                "asunto_o_titulo": m.get("asunto") or "—", "fecha": m.get("pospuesto_hasta"),
                "leido": True, "raw": m,
            })
        for c in circulares.listar_pospuestos(uid):
            filas.append({
                "tipo": "circular", "id": c["id"], "remitente_o_emisor": c.get("creador_nombre") or "—",
                "asunto_o_titulo": c.get("titulo") or "—", "fecha": c.get("pospuesto_hasta"),
                "leido": True, "raw": c,
            })
        for e in encuestas.listar_pospuestos(uid):
            filas.append({
                "tipo": "encuesta", "id": e["id"], "remitente_o_emisor": e.get("creador_nombre") or "—",
                "asunto_o_titulo": e.get("titulo") or "—", "fecha": e.get("pospuesto_hasta"),
                "leido": True, "raw": e,
            })
        filas.sort(key=lambda x: str(x["fecha"] or ""))
        self._filas = filas
        if filas:
            self._layout_lista.addLayout(self._fila_acciones_carpeta())
        self._renderizar_lista(filas, nota=tr(
            "correo.nota_pospuestos",
            default="Pospuesto — reaparecerá en Recibidos automáticamente al llegar la fecha/hora "
                    "indicada."))

    def _pintar_importantes(self):
        """IMPORTANTES — real pero MANUAL: la sync de Gmail es de solo lectura y no guarda la
        etiqueta algorítmica IMPORTANT real de Google — esta es una estrella que el propio usuario
        pone a mano (también en circulares/encuestas), igual que el propio Gmail permite marcar."""
        from src.services.comunicacion_interna import circulares, encuestas
        uid = _usuario_actual_cc().get("id")
        filas = []
        for m in correo_db.listar_recibidos_importantes():
            filas.append({
                "tipo": "gmail", "id": m.get("id"), "remitente_o_emisor": m.get("remitente") or "—",
                "asunto_o_titulo": m.get("asunto") or "—",
                "fecha": m.get("fecha") or m.get("fecha_descarga"), "leido": True, "raw": m,
            })
        for c in circulares.listar_importantes(uid):
            filas.append({
                "tipo": "circular", "id": c["id"], "remitente_o_emisor": c.get("creador_nombre") or "—",
                "asunto_o_titulo": c.get("titulo") or "—", "fecha": c.get("creado"), "leido": True, "raw": c,
            })
        for e in encuestas.listar_importantes(uid):
            filas.append({
                "tipo": "encuesta", "id": e["id"], "remitente_o_emisor": e.get("creador_nombre") or "—",
                "asunto_o_titulo": e.get("titulo") or "—", "fecha": e.get("creado"), "leido": True, "raw": e,
            })
        filas.sort(key=lambda x: str(x["fecha"] or ""), reverse=True)
        self._filas = filas
        if filas:
            self._layout_lista.addLayout(self._fila_acciones_carpeta())
        self._renderizar_lista(filas, nota=tr(
            "correo.nota_importantes",
            default="Estrella MANUAL de Smart Manager — Gmail no expone su etiqueta algorítmica "
                    "IMPORTANT en la sincronización de solo lectura, así que esta marca la pones tú."))

    def _pintar_enviados(self):
        from src.services.comunicacion_interna import circulares, encuestas
        u = _usuario_actual_cc()
        uid, nombre = u.get("id"), u.get("nombre")
        filas = []
        for c in circulares.listar_circulares(usuario_id=uid):
            if c.get("creador_nombre") == nombre:
                filas.append({
                    "tipo": "circular", "id": c["id"], "remitente_o_emisor": c.get("creador_nombre") or "—",
                    "asunto_o_titulo": c.get("titulo") or "—", "fecha": c.get("creado"),
                    "leido": True, "raw": c,
                })
        for e in encuestas.listar_encuestas(usuario_id=uid):
            if e.get("creador_nombre") == nombre:
                filas.append({
                    "tipo": "encuesta", "id": e["id"], "remitente_o_emisor": e.get("creador_nombre") or "—",
                    "asunto_o_titulo": e.get("titulo") or "—", "fecha": e.get("creado"),
                    "leido": True, "raw": e,
                })
        filas.sort(key=lambda x: str(x["fecha"] or ""), reverse=True)
        self._filas = filas
        self._renderizar_lista(filas, nota=tr(
            "correo.nota_enviados",
            default="Nota: la sincronización de Gmail es de solo lectura (no registra lo que envías "
                    "desde tu cuenta de Gmail) — aquí se muestran los mensajes y encuestas internos "
                    "que tú has creado."))

    def _cargar_bandeja_unificada(self) -> list[dict]:
        """Fusiona Gmail + circulares + encuestas dirigidas al usuario actual en una sola lista
        normalizada `{tipo, id, remitente_o_emisor, asunto_o_titulo, fecha, leido, raw}`, ordenada
        de más reciente a más antigua."""
        from src.services.comunicacion_interna import circulares, encuestas
        u = _usuario_actual_cc()
        uid = u.get("id")
        filas = []
        for b in self._buzones_conectados:
            for m in correo_db.listar_recibidos(id_correo=b["id_correo"]):
                filas.append({
                    "tipo": "gmail", "id": m.get("id"),
                    "remitente_o_emisor": m.get("remitente") or "—",
                    "asunto_o_titulo": m.get("asunto") or "—",
                    "fecha": m.get("fecha") or m.get("fecha_descarga"),
                    "leido": bool(m.get("leido")), "raw": m,
                })
        circs = circulares.listar_circulares(usuario_id=uid)
        leidos_c = _leido_ids("CIRCULAR", [c["id"] for c in circs], uid)
        for c in circs:
            filas.append({
                "tipo": "circular", "id": c["id"], "remitente_o_emisor": c.get("creador_nombre") or "—",
                "asunto_o_titulo": c.get("titulo") or "—", "fecha": c.get("creado"),
                "leido": c["id"] in leidos_c, "raw": c,
            })
        encs = encuestas.listar_encuestas(usuario_id=uid)
        leidos_e = _leido_ids("ENCUESTA", [e["id"] for e in encs], uid)
        for e in encs:
            filas.append({
                "tipo": "encuesta", "id": e["id"], "remitente_o_emisor": e.get("creador_nombre") or "—",
                "asunto_o_titulo": e.get("titulo") or "—", "fecha": e.get("creado"),
                "leido": e["id"] in leidos_e, "raw": e,
            })
        filas.sort(key=lambda x: str(x["fecha"] or ""), reverse=True)
        return filas

    # ── Render de contenido (lista / vacío real / no-disponible honesto) ────────
    def _renderizar_lista(self, filas, *, nota=None):
        if nota:
            lbl_nota = QLabel(nota); lbl_nota.setWordWrap(True)
            lbl_nota.setStyleSheet(f"color:{_DIM};font-size:11px;background:transparent;")
            self._layout_lista.addWidget(lbl_nota)
        if not filas:
            self._pintar_vacio_real()
            self.lbl_estado.setText(tr("correo.bandeja_resumen", default="{n} mensaje(s) en la bandeja.", n=0))
            return
        cols = [tr("correo.col_remitente", default="REMITENTE"), tr("correo.col_asunto2", default="ASUNTO"),
               tr("correo.col_fecha2", default="FECHA")]
        tabla = QTableWidget(0, len(cols)); tabla.setHorizontalHeaderLabels(cols)
        tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tabla.verticalHeader().setVisible(False)
        # Altura de fila explícita (antes: la de por defecto de Qt, ~30px) — petición explícita:
        # la casilla de selección de la columna REMITENTE (`_FilaRemitenteCelda`) quedaba cortada
        # por arriba con la altura por defecto (demasiado ajustada para casilla+texto a la vez).
        tabla.verticalHeader().setDefaultSectionSize(40)
        hdr = tabla.horizontalHeader()
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for c in (0, 2):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)
        hdr.resizeSection(0, 220); hdr.resizeSection(2, 150)
        hdr.setHighlightSections(False)
        tabla.setFrameShape(QTableWidget.Shape.NoFrame)
        tabla.setStyleSheet(_ss_tabla_neon())
        self._mask = _RoundTableCorners(tabla, radius=10)
        tabla.setRowCount(len(filas))
        # Reinicio de la selección múltiple: las marcas son por-pintado (la tabla se reconstruye
        # entera en cada `_pintar_carpeta()`/cambio de carpeta, así que no tendría sentido arrastrar
        # marcas de una lista de filas que ya no existe).
        self._filas_marcadas = set()
        for r, item in enumerate(filas):
            asunto = item["asunto_o_titulo"] or "—"
            if item["tipo"] == "circular":
                asunto = "📢 " + asunto
            elif item["tipo"] == "encuesta":
                asunto = "📊 " + asunto
            valores = [item["remitente_o_emisor"] or "—", asunto, str(item["fecha"] or "—")[:16]]
            # Enviados: SIEMPRE en negrita (elección deliberada del usuario — "mis propios envíos
            # destacan siempre", no un error), independientemente de `leido` (que aquí se fija a
            # `True` solo para no afectar a otras lecturas del dato). El resto de carpetas respeta
            # el flag real de lectura.
            negrita = True if self._carpeta_actual == "enviados" else not item.get("leido")
            clave = (item["tipo"], item["id"])
            for col, val in enumerate(valores):
                if col == 0:
                    # Casilla de selección múltiple compartiendo celda con el texto del REMITENTE
                    # (sin columna aparte, petición explícita) — permite aplicar la misma acción de
                    # carpeta a varios mensajes a la vez (ver `_filas_seleccionadas_multiples`).
                    celda = _FilaRemitenteCelda(
                        val, negrita,
                        on_check=lambda marcada, k=clave: (
                            self._filas_marcadas.add(k) if marcada else self._filas_marcadas.discard(k)),
                        on_abrir=lambda rr=r: (self.tabla.selectRow(rr), self._abrir_fila_unificada(rr, 0)))
                    tabla.setCellWidget(r, col, celda)
                    continue
                it = QTableWidgetItem("  " + str(val))
                # +1px sobre el 12px declarado en `_ss_tabla_neon()` (petición explícita: aumentar
                # un punto el texto de las celdas de ESTA tabla — bandeja unificada de Correo —
                # sin tocar el estilo compartido que usan otras tablas de la app).
                f = it.font(); f.setBold(negrita); f.setPixelSize(13); it.setFont(f)
                tabla.setItem(r, col, it)
        tabla.cellClicked.connect(self._abrir_fila_unificada)
        self.tabla = tabla
        self._layout_lista.addWidget(tabla, 1)
        self.lbl_estado.setText(
            tr("correo.bandeja_resumen", default="{n} mensaje(s) en la bandeja.", n=len(filas)))

    def _pintar_vacio_real(self):
        """Carpeta con fuente de datos real pero genuinamente SIN mensajes (distinto del aviso de
        «no disponible» — ver `_pintar_no_disponible`)."""
        cont = QWidget(); cont.setStyleSheet("background:transparent;")
        v = QVBoxLayout(cont); v.setSpacing(10); v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icono = QLabel("📭"); icono.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icono.setStyleSheet("font-size:40px;background:transparent;")
        v.addWidget(icono)
        texto = QLabel(tr("correo.carpeta_vacia", default="No hay mensajes en esta carpeta."))
        texto.setObjectName("lbl_carpeta_vacia")
        texto.setAlignment(Qt.AlignmentFlag.AlignCenter)
        texto.setStyleSheet(f"color:{_DIM};font-size:13px;background:transparent;")
        v.addWidget(texto)
        self._layout_lista.addWidget(cont, 1)

    def _pintar_no_disponible(self, mensaje):
        """Carpeta SIN fuente de datos real todavía (pospuestos/borradores/papelera/programados/
        importantes): aviso honesto, nunca una lista vacía que parezca "sin mensajes" ni datos
        inventados (CLAUDE.md: «NO falsear con mocks»)."""
        cont = QWidget(); cont.setStyleSheet("background:transparent;")
        v = QVBoxLayout(cont); v.setSpacing(12); v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icono = QLabel("🚧"); icono.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icono.setStyleSheet("font-size:40px;background:transparent;")
        v.addWidget(icono)
        texto = QLabel(mensaje); texto.setWordWrap(True)
        texto.setObjectName("lbl_no_disponible")
        texto.setAlignment(Qt.AlignmentFlag.AlignCenter)
        texto.setStyleSheet(f"color:{_DIM};font-size:13px;background:transparent;padding:0 20px;")
        v.addWidget(texto)
        self._layout_lista.addWidget(cont, 1)
        self.lbl_estado.setText("")

    def _banner_vincular(self, buzones_google):
        """Invitación COMPACTA a vincular Gmail (ya no bloquea toda la pantalla: circulares/
        encuestas recibidas se muestran igualmente aunque no haya ninguna cuenta de Google)."""
        cont = QFrame()
        cont.setStyleSheet(f"QFrame{{background:{_BG2};border:1px solid {_CIAN};border-radius:10px;}}")
        h = QHBoxLayout(cont); h.setContentsMargins(14, 10, 14, 10); h.setSpacing(12)
        icono = QLabel("📭"); icono.setStyleSheet("font-size:22px;background:transparent;")
        h.addWidget(icono)
        texto = QLabel(tr("correo.sin_vincular", default="No tienes ninguna cuenta de Gmail vinculada."))
        texto.setStyleSheet(f"color:{_DIM};font-family:'Segoe UI';font-size:12px;background:transparent;")
        h.addWidget(texto, 1)
        b = QPushButton("🔗  " + tr("correo.vincular_google", default="VINCULAR CUENTA DE GOOGLE"))
        b.setCursor(Qt.CursorShape.PointingHandCursor); b.setFixedHeight(36)
        b.setStyleSheet(f"QPushButton{{background:{_BG};color:{_CIAN};border:2px solid {_CIAN};"
                       "border-radius:9px;font-weight:900;padding:0 16px;}"
                       f"QPushButton:hover{{background:{_CIAN};color:{_BG};}}")
        b.clicked.connect(lambda: self._vincular_google(buzones_google))
        h.addWidget(b)
        return cont

    def _vincular_google(self, buzones_google):
        """Botón «Vincular cuenta de Google» del banner. Si ya existe un buzón Google (sin
        conectar), lanza el OAuth directamente; si no existe ninguno, abre «Configurar correo»
        primero (con un aviso explicativo) para que el usuario cree el buzón."""
        if not buzones_google:
            if mostrar_mensaje:
                mostrar_mensaje(self, tr("correo.aviso", default="Aviso"),
                                tr("correo.sin_buzon_google",
                                   default="Todavía no tienes ningún correo de proveedor Google. "
                                           "Créalo primero en «Configurar correo»."), "info")
            _BuzonesDialog(self).exec()
            self.refrescar()
            return
        if not correo_svc.oauth_google_configurado():
            if mostrar_mensaje:
                mostrar_mensaje(self, tr("correo.oauth_no_conf_titulo", default="OAuth no configurado"),
                                tr("correo.oauth_no_conf_msg",
                                   default="No se pudo iniciar la conexión con Google: la aplicación no "
                                           "tiene configurado su cliente OAuth. Contacta con el soporte "
                                           "de Smart Manager."), "warning")
            return
        id_correo = buzones_google[0]["id_correo"]
        ok, msg = correo_svc.iniciar_oauth_google(id_correo)
        if ok:
            # Listo para empezar a sincronizar sin pasos adicionales: una sincronización
            # automática best-effort (nunca rompe el mensaje de "conectado correctamente").
            try:
                correo_svc.sincronizar_gmail_api(id_correo)
            except Exception as e:
                logger.debug("sincronización automática tras vincular Google: %s", e)
        if mostrar_mensaje:
            mostrar_mensaje(self, tr("correo.oauth_titulo", default="Conexión OAuth"), msg, "info" if ok else "error")
        self.refrescar()

    def _fila_selector_buzon(self):
        """Selector de buzón (solo si hay VARIAS cuentas de Google conectadas): determina a cuál
        apunta «SINCRONIZAR» — la lista de Recibidos siempre fusiona TODAS las cuentas conectadas."""
        fila = QHBoxLayout(); fila.setSpacing(10)
        lbl_buzon = QLabel(tr("correo.bandeja_buzon", default="SINCRONIZAR BUZÓN:"))
        lbl_buzon.setStyleSheet(f"color:{_DIM};font-weight:900;font-size:11px;background:transparent;")
        fila.addWidget(lbl_buzon)
        self.cb_buzon = _NeonComboBox(); self.cb_buzon.setFixedHeight(36)
        self.cb_buzon.setStyleSheet(_COMBO_NEON)
        self.cb_buzon.setCursor(Qt.CursorShape.PointingHandCursor)
        for b in self._buzones_conectados:
            etq = b["direccion"] + (f"  ·  {b.get('tienda_nombre')}" if b.get("tienda_nombre") else "")
            self.cb_buzon.addItem(etq, b["id_correo"])
        fila.addWidget(self.cb_buzon, 1)
        fila.addStretch()
        return fila

    def _buzon_actual(self) -> str | None:
        if self.cb_buzon is not None:
            return self.cb_buzon.currentData()
        return self._buzones_conectados[0]["id_correo"] if self._buzones_conectados else None

    # ── Clic en una fila de la lista unificada ───────────────────────────────
    def _abrir_fila_unificada(self, row, _col):
        if not (0 <= row < len(self._filas)):
            return
        item = self._filas[row]
        if item["tipo"] == "gmail":
            self._mostrar_detalle_gmail(row, item)
        elif self._carpeta_actual == "borradores":
            self._reabrir_borrador(item)
        elif item["tipo"] == "circular":
            from src.gui.circulares_gui import _CircularViewerDialog
            dlg = _CircularViewerDialog(item["id"], self)
            dlg.exec()
            self._marcar_leido_tras_visor("circular", item["id"], dlg)
            self._pintar_carpeta()
            self._forzar_leido_en_memoria("circular", item["id"])
        elif item["tipo"] == "encuesta":
            from src.gui.circulares_gui import _EncuestaViewerDialog
            dlg = _EncuestaViewerDialog(item["id"], self)
            dlg.exec()
            self._marcar_leido_tras_visor("encuesta", item["id"], dlg)
            self._pintar_carpeta()
            self._forzar_leido_en_memoria("encuesta", item["id"])

    def _forzar_leido_en_memoria(self, tipo: str, id_entidad):
        """Red de seguridad tras abrir y marcar leído un mensaje de Recibidos (circular/encuesta) y
        repintar la carpeta (`_pintar_carpeta()`, que recarga `self._filas` desde BD vía
        `_cargar_bandeja_unificada()`): si por cualquier motivo esa relectura todavía NO reflejase
        el `leido=1` recién escrito (p.ej. el usuario es el propio creador del mensaje, sin fila de
        destinatario en `com_destinatarios` — ver docstring de `marcar_leido_circular`/
        `marcar_leido_encuesta`, que entonces no actualiza ninguna fila), corrige el dato EN MEMORIA
        (`self._filas`) y la celda ya pintada en la tabla directamente, en vez de depender solo de
        que la recarga de BD lo reflejara — así el negrita desaparece siempre, de inmediato."""
        if self._carpeta_actual != "recibidos" or self.tabla is None:
            return
        for r, fila in enumerate(self._filas):
            if fila["tipo"] == tipo and fila["id"] == id_entidad and not fila.get("leido"):
                fila["leido"] = True
                if 0 <= r < self.tabla.rowCount():
                    # Columna 0 (REMITENTE): widget (casilla + texto), no un `QTableWidgetItem` —
                    # ver la misma corrección en `_mostrar_detalle_gmail`.
                    celda0 = self.tabla.cellWidget(r, 0)
                    lbl0 = celda0.findChild(QLabel) if celda0 is not None else None
                    if lbl0 is not None:
                        f = lbl0.font(); f.setBold(False); lbl0.setFont(f)
                    for col in range(1, self.tabla.columnCount()):
                        it = self.tabla.item(r, col)
                        if it is not None:
                            f = it.font(); f.setBold(False); it.setFont(f)
                break

    def _marcar_leido_tras_visor(self, tipo, id_entidad, dlg):
        """Tras un visor de circular/encuesta que SÍ cargó datos, marca `com_destinatarios.leido=1`
        para el usuario actual (sin esto, la fila seguiría en negrita aunque ya se haya leído)."""
        if not getattr(dlg, "_data", None):
            return
        uid = _usuario_actual_cc().get("id")
        if uid is None:
            return
        try:
            if tipo == "circular":
                from src.services.comunicacion_interna import circulares
                circulares.marcar_leido_circular(id_entidad, uid)
            else:
                from src.services.comunicacion_interna import encuestas
                encuestas.marcar_leido_encuesta(id_entidad, uid)
        except Exception as e:
            logger.debug("marcar leído tras visor (%s): %s", tipo, e)

    def _mostrar_detalle_gmail(self, row, item):
        """Clic-para-expandir estilo Gmail: oculta la lista (vía `QStackedWidget`) y muestra el
        contenido del mensaje a pantalla completa, con botón de vuelta."""
        m = item["raw"]
        if not m.get("leido"):
            correo_db.marcar_recibido_leido(m["id"])
            m["leido"] = True
            item["leido"] = True
            if self.tabla is not None and 0 <= row < self.tabla.rowCount():
                # Columna 0 (REMITENTE) ya no es un `QTableWidgetItem` — es un widget
                # (`_FilaRemitenteCelda`, casilla + texto); su negrita vive en el `QLabel` interno.
                celda0 = self.tabla.cellWidget(row, 0)
                lbl0 = celda0.findChild(QLabel) if celda0 is not None else None
                if lbl0 is not None:
                    f = lbl0.font(); f.setBold(False); lbl0.setFont(f)
                for col in range(1, self.tabla.columnCount()):
                    it = self.tabla.item(row, col)
                    if it is not None:
                        f = it.font(); f.setBold(False); it.setFont(f)
        _vaciar_layout(self._layout_detalle)
        fila_volver = QHBoxLayout()
        btn_volver = QPushButton("←  " + tr("correo.volver_bandeja", default="Volver a la bandeja"))
        btn_volver.setCursor(Qt.CursorShape.PointingHandCursor); btn_volver.setFixedHeight(38)
        btn_volver.setStyleSheet(
            f"QPushButton{{background:{_BG2};color:{_CIAN};border:2px solid {_CIAN};border-radius:9px;"
            f"font-weight:900;padding:0 14px;}}QPushButton:hover{{background:{_CIAN};color:{_BG};}}")
        btn_volver.clicked.connect(self._volver_a_lista)
        fila_volver.addWidget(btn_volver); fila_volver.addStretch()
        self._layout_detalle.addLayout(fila_volver)

        asunto = QLabel(m.get("asunto") or "—"); asunto.setWordWrap(True)
        asunto.setStyleSheet(f"color:{_TEXT};font-family:'Segoe UI';font-weight:900;font-size:18px;"
                             "background:transparent;")
        self._layout_detalle.addWidget(asunto)
        meta = QLabel(f"{m.get('remitente') or '—'}  ·  "
                     f"{str(m.get('fecha') or m.get('fecha_descarga') or '—')[:16]}")
        meta.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-size:12px;background:transparent;")
        self._layout_detalle.addWidget(meta)
        sep = QFrame(); sep.setFixedHeight(1); sep.setStyleSheet(f"background:{_BORDE};border:none;")
        self._layout_detalle.addWidget(sep)
        cuerpo = QTextEdit(); cuerpo.setReadOnly(True)
        cuerpo.setStyleSheet(
            f"QTextEdit{{background:{_BG2};color:{_TEXT};border:1px solid {_BORDE};border-radius:10px;"
            "padding:12px;font-family:'Segoe UI';font-size:13px;}}")
        cuerpo.setPlainText(m.get("cuerpo") or "")
        self._layout_detalle.addWidget(cuerpo, 1)
        self._stack.setCurrentWidget(self._pagina_detalle)

    def _volver_a_lista(self):
        self._stack.setCurrentWidget(self._pagina_lista)

    def _sincronizar(self):
        id_correo = self._buzon_actual()
        if not id_correo:
            if mostrar_mensaje:
                mostrar_mensaje(self, tr("correo.aviso", default="Aviso"),
                                tr("correo.sin_cuenta_conectada",
                                   default="No hay ninguna cuenta de Gmail conectada todavía."), "info")
            return
        n, msg = correo_svc.sincronizar_gmail_api(id_correo)
        if mostrar_mensaje:
            mostrar_mensaje(self, tr("correo.sync_titulo", default="Sincronización Gmail"), msg, "info")
        self._pintar_carpeta()

    # ── Acciones ─────────────────────────────────────────────────────────────
    def _nueva_circular(self):
        try:
            from src.gui.circulares_gui import _CircularComposerDialog
            if _CircularComposerDialog(self).exec() == QDialog.DialogCode.Accepted:
                self.refrescar()
        except Exception as e:
            logger.error("nueva circular: %s", e)

    def _nueva_encuesta(self):
        try:
            from src.gui.circulares_gui import _EncuestaComposerDialog
            if _EncuestaComposerDialog(self).exec() == QDialog.DialogCode.Accepted:
                self.refrescar()
        except Exception as e:
            logger.error("nueva encuesta: %s", e)

    def _reabrir_borrador(self, item):
        """Carpeta Borradores: reabre el compositor precargado con el título/cuerpo/destinatarios
        ya guardados (ver `_CircularComposerDialog`/`_EncuestaComposerDialog` con `id_borrador`)."""
        try:
            if item["tipo"] == "circular":
                from src.gui.circulares_gui import _CircularComposerDialog
                _CircularComposerDialog(self, id_borrador=item["id"]).exec()
            else:
                from src.gui.circulares_gui import _EncuestaComposerDialog
                _EncuestaComposerDialog(self, id_borrador=item["id"]).exec()
        except Exception as e:
            logger.error("reabrir borrador: %s", e)
        self._pintar_carpeta()

    def _abrir_buzones(self):
        """Gestión de BUZONES de correo (popup): alta, OAuth, envío de prueba, baja. Al cerrar,
        refresca la bandeja (puede haberse conectado/creado/eliminado una cuenta de Google)."""
        _BuzonesDialog(self).exec()
        self.refrescar()

    def _abrir_agenda(self):
        """Abre la Agenda Corporativa Virtual (vista consolidada de solo lectura)."""
        try:
            from src.gui.agenda_corporativa import abrir_agenda_corporativa
            abrir_agenda_corporativa(self, contexto="correo")
        except Exception as e:
            logger.error("abrir agenda corporativa: %s", e)

    def _abrir_ccp(self):
        """Abre el panel de la Corporate Communication Platform (analítica/timeline/campañas)."""
        try:
            from src.gui.ccp_panel import abrir_ccp_panel
            abrir_ccp_panel(self)
        except Exception as e:
            logger.error("abrir panel CCP: %s", e)
