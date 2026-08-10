"""
Marketplace · Integraciones Comerciales — Centro operativo (Fase WEB-12).

GUI del submódulo `services/marketplace/integraciones_comerciales` (NO es el Marketplace de Plugins). Muestra
las plataformas compatibles con su estado / última sincronización / versión y permite Configurar · Validar ·
Sincronizar · Eliminar · Añadir integración mediante un asistente.

IMPORTANTE (arquitectura preparada, sin conexiones reales):
  · La VALIDACIÓN y la SINCRONIZACIÓN son **SIMULADAS** (transiciones de estado del servicio existente); no hay
    llamadas HTTP/OAuth/API/webhooks. La lógica vive en el servicio (`servicio.validar`/`sincronizar`), no aquí.
  · Los SECRETOS nunca se almacenan: solo se guarda una REFERENCIA (nombre del secreto en Secret Manager).
  · Estados existentes (WEB-03): NO_CONFIGURADA/CONFIGURADA/VALIDADA/SINCRONIZANDO/SINCRONIZADA/ERROR/DESHABILITADA.

Multiempresa: `id_empresa` del contexto/sesión. Reutiliza el catálogo de plataformas y el servicio (N7).
"""

import logging
import time

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QScrollArea, QStackedWidget,
                             QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget)

from src.gui.catalogo_gestion import _btn_x, _tabla

logger = logging.getLogger("gui.integraciones_comerciales")

_CIAN = "#00FFC6"
_BG = "#0E1117"
_BG2 = "#161B22"
_BORDE = "#30363D"
_TEXT = "#E6EDF3"
_TEXT2 = "#8B949E"
_VERDE = "#3FB950"
_ROJO = "#FF4C4C"
_AMBAR = "#F1C40F"

_COLOR_ESTADO = {
    "NO_CONFIGURADA": _TEXT2, "CONFIGURADA": _CIAN, "VALIDADA": _VERDE,
    "SINCRONIZANDO": _AMBAR, "SINCRONIZADA": _VERDE, "ERROR": _ROJO, "DESHABILITADA": _TEXT2,
}


def _btn(texto, primario=False):
    b = QPushButton(texto)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setMinimumHeight(36)
    if primario:
        b.setStyleSheet(f"QPushButton{{background:{_CIAN};color:{_BG};border:none;border-radius:8px;"
                        f"font-weight:900;padding:6px 14px;}}QPushButton:hover{{background:#00d9a8;}}")
    else:
        b.setStyleSheet(f"QPushButton{{background:{_BG2};color:{_CIAN};border:1px solid {_BORDE};"
                        f"border-radius:8px;font-weight:700;padding:6px 12px;}}"
                        f"QPushButton:hover{{border-color:{_CIAN};}}")
    return b


def _inp(ph=""):
    e = QLineEdit()
    e.setPlaceholderText(ph)
    e.setMinimumHeight(34)
    e.setStyleSheet(f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};border-radius:8px;"
                    f"padding:0 10px;}}QLineEdit:focus{{border-color:{_CIAN};}}")
    return e


def _emp(id_empresa=None):
    if id_empresa is not None:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


class IntegracionesComercialesWindow(QWidget):
    """Centro operativo de Integraciones Comerciales. `plataforma_inicial` abre el asistente de alta
    directamente (lo usa el Canal Web cuando el usuario responde «Sí, ya tengo web»)."""

    def __init__(self, id_empresa=None, usuario=None, plataforma_inicial=None, tipo_inicial=None,
                 parent=None):
        super().__init__(parent)
        self._id_empresa = _emp(id_empresa)
        self._usuario = usuario
        self._tipo_inicial = tipo_inicial
        self.setStyleSheet(f"background:{_BG};color:{_TEXT};")
        # Toda la ventana es desplazable: el contenido nunca queda cortado por la parte inferior.
        _outer = QVBoxLayout(self); _outer.setContentsMargins(0, 0, 0, 0)
        _scroll = QScrollArea(); _scroll.setWidgetResizable(True)
        _scroll.setFrameShape(QFrame.Shape.NoFrame)
        _scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        _outer.addWidget(_scroll)
        _content = QWidget(); _content.setStyleSheet(f"background:{_BG};")
        _scroll.setWidget(_content)
        root = QVBoxLayout(_content)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(12)

        cab = QHBoxLayout()
        t = QLabel("🛒 MARKETPLACE · INTEGRACIONES COMERCIALES")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:900;")
        cab.addWidget(t)
        cab.addStretch()
        cab.addWidget(_btn_x(self.close))   # cerrar la ventana (✕ roja, esquina superior derecha)
        root.addLayout(cab)
        sub = QLabel("Todas las plataformas soportadas en un único panel. Conectores reales degradables "
                     "(operativos solo con credenciales en Secret Manager). Escalable: cualquier conector "
                     "nuevo registrado en el motor aparece automáticamente.")
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color:{_TEXT2};font-size:12px;")
        root.addWidget(sub)

        # Cola de trabajos (reutiliza la cola local del motor).
        self._cola_lbl = QLabel("")
        self._cola_lbl.setStyleSheet(f"color:{_TEXT};background:{_BG2};border:1px solid {_BORDE};"
                                     f"border-radius:8px;padding:6px 10px;font-size:12px;")
        root.addWidget(self._cola_lbl)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        for etiqueta, fn, prim in (("＋ Añadir integración", lambda: self._add(tipo=self._tipo_inicial), True),
                                   ("⚙ Configurar", self._configurar, False),
                                   ("✔ Validar", self._validar, False),
                                   ("🔄 Sincronizar", self._sincronizar, False),
                                   ("🔁 Reintentar", self._reintentar, False),
                                   ("🗑 Eliminar", self._eliminar, False),
                                   ("🔃 Actualizar", self._refrescar, False)):
            b = _btn(etiqueta, prim)
            b.clicked.connect(fn)
            bar.addWidget(b)
        bar.addStretch()
        root.addLayout(bar)

        # Tabla con el diseño estándar de la app (contorno neón turquesa, cabeceras redondeadas + hover swap).
        self.tabla = _tabla(["Plataforma", "Proveedor", "Estado", "Salud",
                             "Versión", "Última sync", "Habilitada"])
        # Sin barra de desplazamiento interna: la tabla se ajusta a su contenido (en _refrescar) para que
        # las esquinas redondeadas y el contorno neón se vean completos (no los tapa el scrollbar). El
        # desbordamiento lo gestiona el scroll de la ventana.
        self.tabla.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tabla.itemSelectionChanged.connect(self._detalle)
        root.addWidget(self.tabla)

        # Estado vacío (cuando se entra por tipo y aún no hay integraciones de ese tipo): mensaje profesional
        # en lugar de la tabla.
        self._vacio_lbl = QLabel("")
        self._vacio_lbl.setWordWrap(True)
        self._vacio_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._vacio_lbl.setStyleSheet(f"color:{_TEXT2};font-size:13px;padding:48px 24px;")
        self._vacio_lbl.setVisible(False)
        root.addWidget(self._vacio_lbl)

        # Detalle: estadísticas + historial de la plataforma seleccionada (reutiliza datos existentes). Fondo
        # TRANSPARENTE y OCULTO mientras no haya selección: así no aparece el rectángulo gris que separaba la
        # tabla del asistente ocupando espacio en balde.
        self._detalle_txt = QTextEdit()
        self._detalle_txt.setReadOnly(True)
        self._detalle_txt.setMaximumHeight(170)
        self._detalle_txt.setStyleSheet(f"QTextEdit{{background:transparent;color:{_TEXT};border:none;"
                                        f"font-size:12px;}}")
        self._detalle_txt.setVisible(False)
        root.addWidget(self._detalle_txt)

        self._asistente = _AsistenteIntegracion(self)
        self._asistente.finalizado.connect(self._refrescar)
        root.addWidget(self._asistente)

        self._msg = QLabel("")
        self._msg.setStyleSheet(f"color:{_TEXT2};font-size:11px;")
        root.addWidget(self._msg)

        self._refrescar()
        if plataforma_inicial:
            self._add(plataforma_inicial)
        elif tipo_inicial:
            # Ramal "Sí, ya tengo web" → abre el asistente prefiltrado por tipo (ecommerce/marketplace/
            # web_tradicional) elegido en la ventana de 3 columnas.
            self._add(tipo=tipo_inicial)

    # ── Datos ──
    def _servicio(self):
        from src.services.marketplace import integraciones_comerciales as ic
        return ic

    def _refrescar(self):
        """Reconstruye el panel desde la UNIÓN catálogo + adaptadores del motor (escalable). Reutiliza la
        capa de agregación `centro`; no recalcula datos."""
        from src.services.marketplace.integraciones_comerciales import centro
        prev = self._plataforma_sel()          # preserva la selección tras reconstruir
        self.tabla.setRowCount(0)
        try:
            plats = centro.plataformas_soportadas()
        except Exception as e:
            plats = []
            self._msg.setText(str(e))
        # Filtro por tipo (entrada desde las 3 columnas): la tabla muestra SOLO las integraciones YA
        # CONFIGURADAS de ese tipo (las tiendas/webs propias conectadas), no el catálogo. Si no hay ninguna →
        # tabla vacía + mensaje profesional.
        vacio = False
        if self._tipo_inicial:
            try:
                configuradas = {i.get("plataforma")
                                for i in (self._servicio().listar(self._id_empresa) or [])}
            except Exception:
                configuradas = set()
            plats = [p for p in plats if p.get("tipo") == self._tipo_inicial and p["clave"] in configuradas]
            vacio = not plats
        for p in plats:
            clave = p["clave"]
            try:
                r = centro.resumen(self._id_empresa, clave)
            except Exception:
                r = {"estado": "NO_CONFIGURADA", "salud_emoji": "⚪", "version": None,
                     "ultima_sync": None, "habilitada": True}
            us = r.get("ultima_sync")
            us_txt = time.strftime("%Y-%m-%d %H:%M", time.localtime(us)) if us else "—"
            row = self.tabla.rowCount()
            self.tabla.insertRow(row)
            vals = [f"{p['icono']}  {p['nombre']}", p["tipo"], r["estado"], r["salud_emoji"],
                    r.get("version") or "—", us_txt, "Sí" if r.get("habilitada") else "No"]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                it.setData(Qt.ItemDataRole.UserRole, clave)
                if c == 2:
                    it.setForeground(QColor(_COLOR_ESTADO.get(r["estado"], _TEXT)))
                self.tabla.setItem(row, c, it)
            if prev is not None and clave == prev:
                self.tabla.setCurrentCell(row, 0)
        # Estado vacío (tipo filtrado sin integraciones): mensaje profesional en lugar de la tabla.
        self.tabla.setVisible(not vacio)
        self._vacio_lbl.setVisible(vacio)
        if vacio:
            self._vacio_lbl.setText(self._texto_vacio(self._tipo_inicial))
            self._detalle_txt.setVisible(False)
        else:
            # Altura exacta al contenido (sin barra interna) → esquinas redondeadas + contorno neón completos.
            head = max(self.tabla.horizontalHeader().sizeHint().height(), 34)
            self.tabla.setFixedHeight(head + self.tabla.rowCount() * 40 + 6)
        self._cola_refresh()

    def _texto_vacio(self, tipo) -> str:
        if tipo == "web_tradicional":
            return ("Todavía no tienes páginas web propias integradas.\n\n"
                    "Cuando conectes una web propia — por catálogo (feed) o por API (REST) — aparecerá aquí "
                    "con su estado y su última sincronización.\n\n"
                    "Pulsa «＋ Añadir integración» para conectar tu primera web.")
        etiqueta = {"ecommerce": "tiendas e-commerce", "marketplace": "marketplaces"}.get(
            tipo, "integraciones")
        return (f"Todavía no tienes {etiqueta} integradas.\n\n"
                f"Las que conectes aparecerán aquí con su estado y su última sincronización.\n\n"
                "Pulsa «＋ Añadir integración» para conectar la primera.")

    def _cola_refresh(self):
        from src.services.marketplace.integraciones_comerciales import cola_jobs
        s = cola_jobs.resumen()
        self._cola_lbl.setText(
            f"Cola de trabajos (local):   ⏳ Pendientes {s['pendientes']}    🔄 Sincronizando "
            f"{s['sincronizando']}    ✅ Completados {s['completados']}    ❌ Fallidos {s['fallidos']}")

    def _plataforma_sel(self):
        r = self.tabla.currentRow()
        if r < 0:
            return None
        it = self.tabla.item(r, 0)
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _detalle(self):
        clave = self._plataforma_sel()
        if not clave:
            self._detalle_txt.setVisible(False)
            return
        self._detalle_txt.setVisible(True)
        from src.services.marketplace.integraciones_comerciales import centro
        try:
            e = centro.estadisticas(self._id_empresa, clave)
            h = centro.historial(clave, 20)
        except Exception as ex:
            self._detalle_txt.setText(str(ex))
            return
        lineas = [
            f"📊 {clave} · estadísticas (reutiliza datos existentes):",
            f"   Productos {e['productos']} · Clientes {e['clientes']} · Pedidos {e['pedidos']} · "
            f"Reservas {e['reservas']} · Stock {e['stock']}",
            f"   Sincronizaciones {e['sincronizaciones']} · Errores {e['errores']} · Versión API "
            f"{e['version_api']} · Última ejecución {e['ultima_ejecucion'] or '—'}",
            "",
            "🕘 Historial (auditoría):",
        ]
        for f in h[:20]:
            lineas.append(f"   {f.get('fecha')} · {f.get('accion')} · {(f.get('detalles') or '')[:80]}")
        if not h:
            lineas.append("   (sin registros)")
        self._detalle_txt.setText("\n".join(str(x) for x in lineas))

    # ── Acciones (reutilizan el servicio) ──
    def _add(self, plataforma_inicial=None, tipo=None):
        self._asistente.iniciar(self._id_empresa, self._usuario,
                                plataforma_inicial if isinstance(plataforma_inicial, str) else None,
                                tipo=tipo)

    def _accion_servicio(self, fn_nombre, ok_msg):
        clave = self._plataforma_sel()
        if not clave:
            self._msg.setText("Selecciona una plataforma.")
            return
        try:
            fn = getattr(self._servicio(), fn_nombre)
            r = fn(self._id_empresa, clave, usuario=self._usuario)
            if isinstance(r, dict) and not r.get("ok", True) and "estado" not in r:
                self._msg.setText(r.get("error") or "No se pudo completar.")
            else:
                self._msg.setText(ok_msg + (f" (estado: {r.get('estado')})" if isinstance(r, dict) else ""))
        except Exception as e:
            self._msg.setText(str(e))
        self._refrescar()

    def _configurar(self):
        clave = self._plataforma_sel()
        if not clave:
            self._msg.setText("Selecciona una plataforma.")
            return
        self._asistente.iniciar(self._id_empresa, self._usuario, clave)

    def _via_adaptador(self, clave, accion):
        """Enruta a un conector REAL si su adaptador está operativo (dirigido por adaptador, no por
        `if plataforma==`). Devuelve el resultado o None para caer al servicio (estado simulado)."""
        try:
            from src.services.marketplace.integraciones_comerciales import motor
            adap = motor.adaptador(clave)
            try:
                operativo = adap.disponible(self._id_empresa)
            except TypeError:
                operativo = adap.disponible()
            if not operativo:
                return None
            if accion == "validar" and hasattr(adap, "validar"):
                return adap.validar(id_empresa=self._id_empresa, usuario=self._usuario)
            if accion == "sincronizar" and hasattr(adap, "sincronizacion_inicial"):
                return adap.sincronizacion_inicial(id_empresa=self._id_empresa, usuario=self._usuario)
        except Exception as e:
            self._msg.setText(str(e))
        return None

    def _validar(self):
        clave = self._plataforma_sel()
        if not clave:
            self._msg.setText("Selecciona una plataforma.")
            return
        r = self._via_adaptador(clave, "validar")
        if r is None:
            return self._accion_servicio("validar", "Validación (simulada) realizada.")
        self._msg.setText("Validación real: " + ("OK" if r.get("ok") else str(r.get("error") or r.get("codigo")))
                          + (f" · {r.get('estado')}" if r.get("estado") else ""))
        self._refrescar()

    def _sincronizar(self):
        clave = self._plataforma_sel()
        if not clave:
            self._msg.setText("Selecciona una plataforma.")
            return
        self._encolar_y_ejecutar(clave, "sincronizar")

    def _reintentar(self):
        """Reintenta la última sincronización con un único botón (sin reconfigurar la integración)."""
        clave = self._plataforma_sel()
        if not clave:
            self._msg.setText("Selecciona una plataforma.")
            return
        self._encolar_y_ejecutar(clave, "reintentar")

    def _encolar_y_ejecutar(self, clave, tipo):
        """Encola el trabajo en la COLA LOCAL del motor y lo ejecuta (pendiente→sincronizando→completado/
        fallido). El runner enruta al adaptador operativo (real) o cae al estado del servicio (degradable)."""
        from src.services.marketplace.integraciones_comerciales import cola_jobs
        cola_jobs.encolar(self._id_empresa, clave, tipo)
        self._cola_refresh()

        def runner(job):
            r = self._via_adaptador(job["plataforma"], "sincronizar")
            if r is None:
                r = self._servicio().sincronizar(self._id_empresa, job["plataforma"], usuario=self._usuario)
            ok = bool(isinstance(r, dict) and r.get("ok", True) and r.get("codigo") is None)
            return ok, r

        hechos = cola_jobs.ejecutar_pendientes(runner)
        ult = hechos[-1] if hechos else None
        self._msg.setText(f"{tipo.capitalize()}: {ult['estado']}" if ult else "Sin trabajos en cola.")
        self._cola_refresh()
        self._refrescar()

    def _eliminar(self):
        clave = self._plataforma_sel()
        if not clave:
            self._msg.setText("Selecciona una plataforma.")
            return
        try:
            self._servicio().eliminar_integracion(self._id_empresa, clave, usuario=self._usuario)
            self._msg.setText("Integración eliminada.")
        except Exception as e:
            self._msg.setText(str(e))
        self._refrescar()


class _StackAuto(QStackedWidget):
    """QStackedWidget que se dimensiona al paso ACTUAL (no al más alto). Evita el enorme hueco vacío que
    dejaba el paso 0 (solo un combo) al reservar la altura del paso de credenciales."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.currentChanged.connect(lambda *_: self.updateGeometry())

    def sizeHint(self):
        w = self.currentWidget()
        return w.sizeHint() if w is not None else super().sizeHint()

    def minimumSizeHint(self):
        w = self.currentWidget()
        return w.minimumSizeHint() if w is not None else super().minimumSizeHint()


class _AsistenteIntegracion(QFrame):
    """Asistente de alta de integración (inline). Flujo: Seleccionar plataforma → URL → credenciales
    (referencia) → Guardar → Validar → Sincronizar → Finalizado. Validación/sincronización SIMULADAS."""

    finalizado = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # Sin marco ni fondo: se elimina el rectángulo turquesa que rodeaba el texto de pasos y el cuadro
        # oscuro intermedio. Solo queda el texto de pasos + el contenido del paso actual.
        self.setStyleSheet("QFrame{background:transparent;border:none;}")
        self.setVisible(False)
        ly = QVBoxLayout(self)
        ly.setContentsMargins(0, 6, 0, 0)
        ly.setSpacing(10)
        self._pasos_lbl = QLabel("")
        self._pasos_lbl.setStyleSheet(f"color:{_CIAN};font-weight:800;font-size:13px;background:transparent;")
        ly.addWidget(self._pasos_lbl)
        self._stack = _StackAuto()
        self._stack.setStyleSheet("background:transparent;")
        ly.addWidget(self._stack)
        ly.addStretch(1)   # empuja el contenido hacia arriba (sin huecos gigantes intermedios)
        # Paso 0: plataforma
        p0 = QWidget(); l0 = QVBoxLayout(p0); l0.setContentsMargins(0, 0, 0, 0); l0.setSpacing(8)
        l0.addWidget(QLabel("Selecciona la plataforma:"))
        self._cmb = QComboBox()
        self._cmb.setMinimumHeight(34)
        self._cmb.setStyleSheet(f"QComboBox{{background:{_BG};color:{_TEXT};border:2px solid {_BORDE};"
                                f"border-radius:8px;padding:0 10px;}}")
        l0.addWidget(self._cmb)
        # Paso 1: url + credenciales
        p1 = QWidget(); l1 = QVBoxLayout(p1)
        l1.addWidget(QLabel("URL de la tienda:"))
        self._url = _inp("https://mitienda.com")
        l1.addWidget(self._url)
        l1.addWidget(QLabel("Referencia de credenciales (nombre del secreto en Secret Manager):"))
        self._cred = _inp("p. ej. woo_mitienda_apikey")
        l1.addWidget(self._cred)
        # WooCommerce (y futuros conectores con clave/secreto): Consumer Key/Secret. Se CIFRAN y se
        # guardan por referencia (SecretManager); nunca en claro.
        l1.addWidget(QLabel("Consumer Key (opcional · WooCommerce):"))
        self._ck = _inp("ck_xxx")
        l1.addWidget(self._ck)
        l1.addWidget(QLabel("Consumer Secret (opcional · WooCommerce):"))
        self._cs = _inp("cs_xxx")
        self._cs.setEchoMode(self._cs.EchoMode.Password)
        l1.addWidget(self._cs)
        # Access Token (Bearer) — Shopify o Web tradicional con API REST. Se CIFRA vía SecretManager.
        l1.addWidget(QLabel("Access Token (opcional · Shopify / Web REST):"))
        self._token = _inp("token de acceso")
        self._token.setEchoMode(self._token.EchoMode.Password)
        l1.addWidget(self._token)
        nota = QLabel("Nunca se guarda el valor del secreto: solo su referencia.")
        nota.setStyleSheet(f"color:{_TEXT2};font-size:11px;")
        l1.addWidget(nota)
        # Paso 2: resultado / finalizado
        p2 = QWidget(); l2 = QVBoxLayout(p2)
        self._res = QLabel("")
        self._res.setWordWrap(True)
        self._res.setStyleSheet(f"color:{_TEXT};font-size:12px;")
        l2.addWidget(self._res)
        for p in (p0, p1, p2):
            self._stack.addWidget(p)
        # Botones
        botones = QHBoxLayout()
        botones.addStretch()
        self._b_cancel = _btn("Cancelar")
        self._b_cancel.clicked.connect(lambda: self.setVisible(False))
        self._b_prim = _btn("Siguiente", True)
        self._b_prim.clicked.connect(self._avanzar)
        botones.addWidget(self._b_cancel)
        botones.addWidget(self._b_prim)
        ly.addLayout(botones)
        self._paso = 0
        self._emp = None
        self._usuario = None

    def iniciar(self, id_empresa, usuario, plataforma=None, tipo=None):
        self._emp = id_empresa
        self._usuario = usuario
        self._cmb.clear()
        try:
            from src.services.marketplace import integraciones_comerciales as ic
            # Prefiltrado por tipo (ecommerce/marketplace/web_tradicional) cuando se entra desde la ventana
            # de 3 columnas; sin tipo, muestra todas las plataformas.
            for p in ic.listar_plataformas(tipo):
                self._cmb.addItem(f"{p['nombre']} ({p['tipo']})", p["clave"])
        except Exception:
            for c in ("woocommerce", "shopify", "prestashop"):
                self._cmb.addItem(c, c)
        if plataforma:
            i = self._cmb.findData(plataforma)
            if i >= 0:
                self._cmb.setCurrentIndex(i)
        self._paso = 0
        self._stack.setCurrentIndex(0)
        self._b_prim.setText("Siguiente")
        self.setVisible(True)
        self._pintar_pasos()

    def _pintar_pasos(self, extra=""):
        flujo = ["Plataforma", "Credenciales", "Guardar", "Validar", "Sincronizar", "Finalizado"]
        idx = {0: 0, 1: 1, 2: 5}[self._paso]
        marca = "  →  ".join((f"[{s}]" if i == idx else s) for i, s in enumerate(flujo))
        self._pasos_lbl.setText("Asistente de integración:  " + marca + ("   " + extra if extra else ""))

    def _avanzar(self):
        ic = None
        try:
            from src.services.marketplace import integraciones_comerciales as ic  # noqa: F811
        except Exception:
            pass
        if self._paso == 0:
            self._paso = 1
            self._stack.setCurrentIndex(1)
            self._b_prim.setText("Guardar y conectar")
            self._pintar_pasos()
            return
        if self._paso == 1:
            plataforma = self._cmb.currentData()
            cred_ref = self._cred.text().strip() or None
            ck, cs = self._ck.text().strip(), self._cs.text().strip()
            token = self._token.text().strip()
            # Credenciales por plataforma → SecretManager (cifradas por referencia, nunca en claro).
            if plataforma == "woocommerce" and ck and cs:
                cred_ref = cred_ref or f"WOO_{self._emp}"
                try:
                    from src.services.marketplace.integraciones_comerciales.woocommerce import \
                        secretos as _wsec
                    _wsec.guardar_runtime(cred_ref, ck, cs)
                except Exception:
                    pass
            elif plataforma == "shopify" and token:
                cred_ref = cred_ref or f"SHOPIFY_{self._emp}"
                try:
                    from src.services.marketplace.integraciones_comerciales.shopify import \
                        secretos as _ssec
                    _ssec.guardar_runtime(cred_ref, token)
                except Exception:
                    pass
            elif plataforma == "web_rest" and token:
                # Web tradicional (Modo B): token de la API REST de la propia web.
                cred_ref = cred_ref or f"WEBREST_{self._emp}"
                try:
                    from src.services.marketplace.integraciones_comerciales.web_generica import \
                        secretos as _wrsec
                    _wrsec.guardar_runtime(cred_ref, token)
                except Exception:
                    pass
            elif plataforma == "web_feed" and not cred_ref:
                # Web tradicional (Modo A): feed LOCAL, sin credenciales externas.
                cred_ref = "LOCAL_FEED"
            try:
                ic.crear_integracion(self._emp, plataforma, url=self._url.text().strip() or None,
                                     credenciales_ref=cred_ref, usuario=self._usuario)
                v = ic.validar(self._emp, plataforma, usuario=self._usuario)
                s = ic.sincronizar(self._emp, plataforma, usuario=self._usuario) if v.get("ok") else {}
                self._res.setText(
                    f"✔ Integración con {plataforma} preparada.\n"
                    f"• Guardar: OK (estado CONFIGURADA)\n"
                    f"• Validar (simulada): {'OK · VALIDADA' if v.get('ok') else v.get('error')}\n"
                    f"• Sincronizar (simulada): {'OK · SINCRONIZADA' if s.get('ok') else '—'}\n"
                    f"Ámbitos preparados: {', '.join(s.get('ambitos', [])) or '—'}\n"
                    "Sin conexiones reales (arquitectura preparada).")
            except Exception as e:
                self._res.setText(f"No se pudo completar: {e}")
            self._paso = 2
            self._stack.setCurrentIndex(2)
            self._b_prim.setText("Finalizar")
            self._pintar_pasos()
            return
        # paso 2 → finalizar
        self.setVisible(False)
        self.finalizado.emit()
