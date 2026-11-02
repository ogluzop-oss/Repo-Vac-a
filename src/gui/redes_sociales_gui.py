"""
Gestión de Redes Sociales Corporativas — petición explícita, módulo de nivel superior NUEVO,
EXCLUSIVO de SUPERADMIN (tanto la tarjeta del menú principal como la ruta están vedadas a
cualquier otro perfil — ver el doble gate en `gui/menu_principal.py`). Orquesta ÚNICAMENTE
`services.redes_sociales.*` (toda la lógica vive ahí): cuentas conectadas (OAuth), bandeja de
entrada omnicanal (Social CRM), calendario de contenidos, analítica cruzada con el ERP y
monitorización de reputación con escalado automático a Incidencias.

Mismo patrón sidebar+stack ya usado por los módulos de nivel superior comparables
(`rrhh_gestion.py`/`contabilidad_gestion.py`/`gmao_dashboard.py`/`sat_dashboard.py`): helpers
compartidos de `catalogo_gestion.py`, sin introducir una librería visual nueva.
"""

import logging

from PyQt6.QtCore import QDateTime, Qt, QTimer
from PyQt6.QtWidgets import (QComboBox, QDateTimeEdit, QDialog, QFormLayout, QFrame, QHBoxLayout,
                             QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
                             QStackedWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget)

from src.gui.catalogo_gestion import (_BG, _BORDE, _CIAN, _DIM, _SIDEBAR, _btn, _btn_salir_sidebar,
                                      _dialogo_frameless, _inp, _tabla)

logger = logging.getLogger("gui.redes_sociales")

_PLATAFORMAS_LBL = {"instagram": "Instagram", "facebook": "Facebook", "tiktok": "TikTok",
                   "youtube": "YouTube", "x": "X (Twitter)"}
_ESTADOS_CONV_LBL = {"pendiente_respuesta": "Pendiente respuesta", "respondida": "Respondida",
                    "resuelta": "Resuelta", "archivada": "Archivada"}


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


def _mensaje(parent, titulo, texto, nivel="info"):
    try:
        from assets.estilo_global import mostrar_mensaje
        mostrar_mensaje(parent, titulo, texto, nivel)
    except Exception:
        logger.info("%s: %s", titulo, texto)


def _usar_chevron_combo(filtro_fecha) -> None:
    """Sustituye el icono de `_FechaFilter` (triángulo relleno) por el chevron "v" sin rellenar
    que usa el resto de desplegables de la app — se parchea solo la INSTANCIA de su QLineEdit
    interno (`._le`), sin tocar `tpv.py` ni ninguna otra pantalla que ya use `_FechaFilter`."""
    import types

    from PyQt6.QtCore import QPoint
    from PyQt6.QtGui import QColor, QPainter, QPen
    from PyQt6.QtWidgets import QLineEdit

    def _paint(self, event):
        QLineEdit.paintEvent(self, event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() - 15, self.height() // 2
        pen = QPen(QColor(_CIAN)); pen.setWidthF(1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap); pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawPolyline(QPoint(cx - 5, cy - 2), QPoint(cx, cy + 3), QPoint(cx + 5, cy - 2))
        p.end()

    try:
        filtro_fecha._le.paintEvent = types.MethodType(_paint, filtro_fecha._le)
        filtro_fecha._le.update()
    except Exception:
        logger.debug("_usar_chevron_combo: no se pudo repintar el icono")


class _ConectarCuentaDialog(QDialog):
    """Alta de cuenta en MODO MANUAL (el admin pega el access_token obtenido del panel de
    desarrolladores de la plataforma — Meta/TikTok/Google/X). Vía AVANZADA/alternativa: el flujo
    principal es "🔗 Conectar" (`_conectar_oauth`, login real en el navegador, sin tokens a
    mano) — este diálogo sigue disponible para cuando aún no hay una app OAuth aprobada por la
    plataforma, o para credenciales de servicio que no pasan por un login de usuario."""

    def __init__(self, parent=None):
        super().__init__(parent)
        ly = _dialogo_frameless(self, "Conectar cuenta (manual)", ancho=380)
        aviso = QLabel("Modo manual: pega el access_token obtenido del panel de "
                       "desarrolladores de la plataforma.")
        aviso.setWordWrap(True)
        aviso.setStyleSheet(f"color:{_DIM};font-size:12px;")
        ly.addWidget(aviso)
        form = QFormLayout()
        self.cb_plataforma = QComboBox()
        for k, et in _PLATAFORMAS_LBL.items():
            self.cb_plataforma.addItem(et, k)
        self.in_id_externo = _inp("ID de página/cuenta/canal en la plataforma")
        self.in_nombre = _inp("Nombre visible (opcional)")
        self.in_token = QLineEdit(); self.in_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.in_token.setPlaceholderText("Access token")
        form.addRow("Plataforma:", self.cb_plataforma)
        form.addRow("ID externo:", self.in_id_externo)
        form.addRow("Nombre:", self.in_nombre)
        form.addRow("Access token:", self.in_token)
        ly.addLayout(form)
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn("Conectar", self.accept, primary=True))
        ly.addLayout(fila)

    def datos(self):
        return {"plataforma": self.cb_plataforma.currentData(),
               "id_externo": self.in_id_externo.text().strip(),
               "nombre_cuenta": self.in_nombre.text().strip() or None,
               "access_token": self.in_token.text().strip()}


class _ElegirPlataformaOAuthDialog(QDialog):
    """Paso 1 del alta fluida: elegir la plataforma antes de abrir el navegador. Mismo diseño
    frameless/esquinas redondeadas/✕ roja que el resto de ventanas emergentes de la app
    (`_dialogo_frameless`), en vez del marco nativo de Windows con botón Cancelar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        ly = _dialogo_frameless(self, "Conectar cuenta", ancho=380)
        aviso = QLabel("Se abrirá el navegador para iniciar sesión directamente en la "
                       "plataforma. Al aceptar, la cuenta queda vinculada automáticamente.")
        aviso.setWordWrap(True)
        aviso.setStyleSheet(f"color:{_DIM};font-size:12px;")
        ly.addWidget(aviso)
        form = QFormLayout()
        self.cb_plataforma = QComboBox()
        for k, et in _PLATAFORMAS_LBL.items():
            self.cb_plataforma.addItem(et, k)
        form.addRow("Plataforma:", self.cb_plataforma)
        ly.addLayout(form)
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn("Continuar en el navegador", self.accept, primary=True))
        ly.addLayout(fila)

    def plataforma(self):
        return self.cb_plataforma.currentData()


class _EsperandoConexionDialog(QDialog):
    """Modal ligero mientras el usuario inicia sesión en su navegador (petición explícita: alta
    fluida, sin tener que volver manualmente a refrescar). Sondea `cuentas.listar()` cada 2 s
    buscando una fila NUEVA conectada de la plataforma elegida; se cierra sola al detectarla."""

    def __init__(self, plataforma, ids_previos, parent=None):
        super().__init__(parent)
        self._plataforma = plataforma
        self._ids_previos = set(ids_previos)
        self.resultado = None
        self.setWindowTitle("Esperando conexión…")
        self.setStyleSheet(f"background:{_BG};color:#FFFFFF;")
        ly = QVBoxLayout(self)
        ly.addWidget(QLabel(f"Inicia sesión en {_PLATAFORMAS_LBL.get(plataforma, plataforma)} en "
                            "la pestaña del navegador que se acaba de abrir…",
                            styleSheet=f"color:{_DIM};"))
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn("Cancelar", self.reject))
        ly.addLayout(fila)
        self._timer = QTimer(self); self._timer.timeout.connect(self._comprobar)
        self._timer.start(2000)
        self._segundos = 0

    def _comprobar(self):
        self._segundos += 2
        if self._segundos > 180:
            self._timer.stop()
            self.reject()
            return
        from src.services.redes_sociales import cuentas as _C
        for c in _C.listar(plataforma=self._plataforma):
            if c["id"] not in self._ids_previos and c.get("estado") == "conectada":
                self._timer.stop()
                self.resultado = c
                self.accept()
                return


class _NuevaPublicacionDialog(QDialog):
    def __init__(self, cuentas, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nueva publicación")
        self.setStyleSheet(f"background:{_BG};color:#FFFFFF;")
        self._cuentas = cuentas
        ly = QVBoxLayout(self)
        form = QFormLayout()
        self.cb_cuenta = QComboBox()
        for c in cuentas:
            self.cb_cuenta.addItem(f"{_PLATAFORMAS_LBL.get(c['plataforma'], c['plataforma'])} — "
                                   f"{c.get('nombre_cuenta') or c['id_externo']}", c["id"])
        self.in_titulo = _inp("Título (opcional, uso interno)")
        self.in_contenido = QTextEdit(); self.in_contenido.setFixedHeight(100)
        self.in_adjunto = _inp("URL pública del adjunto (imagen/vídeo, si aplica)")
        self.in_fecha = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        self.in_fecha.setCalendarPopup(True)
        self.ck_programar = QPushButton("Programar para más tarde"); self.ck_programar.setCheckable(True)
        form.addRow("Cuenta:", self.cb_cuenta)
        form.addRow("Título:", self.in_titulo)
        form.addRow("Contenido:", self.in_contenido)
        form.addRow("Adjunto (URL):", self.in_adjunto)
        form.addRow("", self.ck_programar)
        form.addRow("Fecha programada:", self.in_fecha)
        ly.addLayout(form)
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn("Cancelar", self.reject))
        fila.addWidget(_btn("Guardar", self.accept, primary=True))
        ly.addLayout(fila)

    def datos(self):
        cuenta = next(c for c in self._cuentas if c["id"] == self.cb_cuenta.currentData())
        fecha = (self.in_fecha.dateTime().toString("yyyy-MM-dd HH:mm:ss")
                if self.ck_programar.isChecked() else None)
        return {"id_cuenta": cuenta["id"], "plataforma": cuenta["plataforma"],
               "titulo": self.in_titulo.text().strip() or None,
               "contenido": self.in_contenido.toPlainText().strip() or None,
               "ruta_adjunto": self.in_adjunto.text().strip() or None, "fecha_programada": fecha}


class _NuevaReglaDialog(QDialog):
    """Alta Y edición de reglas de reputación (petición explícita: toda regla, incluida la
    predeterminada, es editable/borrable) — se reutiliza el mismo diálogo precargando `inicial`."""

    def __init__(self, parent=None, inicial=None):
        super().__init__(parent)
        inicial = inicial or {}
        self.setWindowTitle("Editar regla de reputación" if inicial else "Nueva regla de reputación")
        self.setStyleSheet(f"background:{_BG};color:#FFFFFF;")
        ly = QVBoxLayout(self)
        form = QFormLayout()
        self.in_nombre = _inp("Nombre de la regla")
        self.in_nombre.setText(inicial.get("nombre") or "")
        self.in_palabras = _inp("Palabras clave separadas por coma (estafa, demanda, denuncia...)")
        self.in_palabras.setText(inicial.get("palabras_clave") or "")
        self.cb_prioridad = QComboBox(); self.cb_prioridad.addItems(["alta", "media", "baja"])
        if inicial.get("prioridad_ticket") in ("alta", "media", "baja"):
            self.cb_prioridad.setCurrentText(inicial["prioridad_ticket"])
        form.addRow("Nombre:", self.in_nombre)
        form.addRow("Palabras clave:", self.in_palabras)
        form.addRow("Prioridad del ticket:", self.cb_prioridad)
        ly.addLayout(form)
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn("Cancelar", self.reject))
        fila.addWidget(_btn("Guardar" if inicial else "Crear", self.accept, primary=True))
        ly.addLayout(fila)

    def datos(self):
        return {"nombre": self.in_nombre.text().strip(),
               "palabras_clave": self.in_palabras.text().strip(),
               "prioridad_ticket": self.cb_prioridad.currentText()}


class RedesSocialesWindow(QWidget):
    SECCIONES = [("📥", "Bandeja de entrada"), ("🗓️", "Calendario de contenidos"),
                ("📊", "Analítica"), ("🚨", "Reputación y Alertas"), ("🔗", "Cuentas conectadas")]

    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.main = main

        root = QHBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        root.addWidget(self._build_sidebar())

        right = QWidget(); right.setStyleSheet(f"background:{_BG};")
        rcol = QVBoxLayout(right); rcol.setContentsMargins(24, 18, 24, 18); rcol.setSpacing(14)
        self._lbl_tit = QLabel("RRSS · Bandeja de entrada")
        self._lbl_tit.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        rcol.addWidget(self._lbl_tit)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._page_bandeja())
        self.stack.addWidget(self._page_calendario())
        self.stack.addWidget(self._page_analitica())
        self.stack.addWidget(self._page_reputacion())
        self.stack.addWidget(self._page_cuentas())
        rcol.addWidget(self.stack, 1)
        root.addWidget(right, 1)

        self._ir(0)

        # Disparo periódico de publicaciones programadas — sin infraestructura de cron en el
        # servidor (auditoría), mismo patrón QTimer que `menu_principal._timer_badges`.
        self._timer_calendario = QTimer(self)
        self._timer_calendario.timeout.connect(self._tick_calendario)
        self._timer_calendario.start(300_000)  # 5 min

        # Flecha de colapso de la sidebar (esquina superior derecha) — mismo helper que el resto
        # de módulos de la app (RRHH/Contabilidad/Catálogo/...).
        try:
            from src.gui.sidebar_colapsable import instalar_sidebar_colapsable
            instalar_sidebar_colapsable(self, self.sidebar, usuario=self.usuario,
                                        clave="redes_sociales")
        except Exception:
            pass

    # ── Sidebar ──────────────────────────────────────────────────────────────
    def _build_sidebar(self):
        wrap = QFrame(); wrap.setObjectName("sw"); wrap.setFixedWidth(260); self.sidebar = wrap
        wrap.setStyleSheet(f"#sw{{background:{_SIDEBAR};}}")
        lay = QVBoxLayout(wrap); lay.setContentsMargins(0, 22, 0, 16); lay.setSpacing(2)
        cab = QLabel("SMART RRSS")
        cab.setStyleSheet("color:#FFFFFF;padding:0 0 24px 28px;font-size:15px;font-weight:900;"
                          "letter-spacing:2px;background:transparent;")
        lay.addWidget(cab)
        self._sb_btns = []
        for i, (_ic, lab) in enumerate(self.SECCIONES):
            b = QPushButton(f"  {lab.upper()}")   # sin icono — sidebar: mayúsculas, tamaño base
            b.setObjectName("btn_sidebar")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setCheckable(True); b.setFixedHeight(50)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(lambda _=False, idx=i: self._ir(idx))
            self._sb_btns.append(b); lay.addWidget(b)
        lay.addStretch(1)
        if self._volver:
            lay.addWidget(_btn_salir_sidebar(self._volver))
        return wrap

    def _ir(self, idx):
        for i, b in enumerate(self._sb_btns):
            b.setChecked(i == idx)
        self.stack.setCurrentIndex(idx)
        self._lbl_tit.setText(f"RRSS · {self.SECCIONES[idx][1]}")
        if idx == 0:
            self._refrescar_bandeja()
        elif idx == 1:
            self._refrescar_calendario()
        elif idx == 3:
            self._refrescar_reputacion()
        elif idx == 4:
            self._refrescar_cuentas()

    def _cuentas_cache(self):
        from src.services.redes_sociales import cuentas as _C
        return _C.listar()

    # ══════════════════════════════════════════════════════════════════
    # 1) Bandeja de entrada
    # ══════════════════════════════════════════════════════════════════
    def _page_bandeja(self):
        w = QWidget(); ly = QHBoxLayout(w)

        izq = QWidget(); izq_ly = QVBoxLayout(izq)
        barra = QHBoxLayout()
        barra.addWidget(_btn("🔃 Sincronizar", self._abrir_sincronizar, primary=True))
        barra.addWidget(_btn("🔄 Actualizar", self._refrescar_bandeja, primary=True))
        barra.addStretch()
        izq_ly.addLayout(barra)
        self.tbl_conversaciones = _tabla(["Plataforma", "Remitente", "Tipo", "Estado", "Prioridad",
                                          "Último mensaje"])
        self.tbl_conversaciones.cellClicked.connect(self._seleccionar_conversacion)
        izq_ly.addWidget(self.tbl_conversaciones)
        ly.addWidget(izq, 3)

        # Panel derecho: SIN tarjeta de fondo propia (un QWidget plano sin stylesheet evita el
        # bug ya corregido una vez — un QWidget normal necesita WA_StyledBackground para pintar
        # su propio fondo/borde por QSS, y sin él el hijo más próximo puede heredar un relleno
        # residual inconsistente). En su lugar, cada zona de texto real (hilo de mensajes / caja
        # de respuesta) es su propio QFrame con contorno turquesa — QFrame SÍ pinta su QSS de
        # forma fiable sin necesitar ese atributo — y las etiquetas sueltas (cabecera/cliente 360)
        # quedan explícitamente transparentes y sin borde, para que no quede ningún rectángulo
        # residual entre ellas.
        der = QWidget()
        der_ly = QVBoxLayout(der)
        self.lbl_hilo_cab = QLabel("Selecciona una conversación.")
        self.lbl_hilo_cab.setStyleSheet(f"color:{_DIM};background:transparent;border:none;")
        der_ly.addWidget(self.lbl_hilo_cab)

        hilo_box = QFrame(); hilo_box.setObjectName("hilo_box")
        hilo_box.setStyleSheet(f"QFrame#hilo_box{{background:{_BG};border:2px solid {_CIAN};"
                               f"border-radius:10px;}}")
        hilo_box_ly = QVBoxLayout(hilo_box)
        self.lbl_hilo = QLabel(""); self.lbl_hilo.setWordWrap(True)
        self.lbl_hilo.setStyleSheet("color:#FFFFFF;background:transparent;border:none;")
        hilo_box_ly.addWidget(self.lbl_hilo)
        hilo_box_ly.addStretch()
        der_ly.addWidget(hilo_box, 1)

        self.lbl_cliente360 = QLabel(""); self.lbl_cliente360.setWordWrap(True)
        self.lbl_cliente360.setStyleSheet(f"color:{_DIM};background:transparent;border:none;")
        der_ly.addWidget(self.lbl_cliente360)
        self.in_respuesta = QTextEdit(); self.in_respuesta.setPlaceholderText("Escribe una respuesta…")
        self.in_respuesta.setFixedHeight(80)
        self.in_respuesta.setStyleSheet(
            f"QTextEdit{{background:{_BG};color:#FFFFFF;border:2px solid {_CIAN};"
            f"border-radius:10px;padding:6px;}}")
        der_ly.addWidget(self.in_respuesta)
        acc = QHBoxLayout()
        acc.addWidget(_btn("✨ Sugerir con IA", self._sugerir_ia, primary=True))
        acc.addWidget(_btn("Vincular cliente ERP", self._vincular_cliente, primary=True))
        acc.addWidget(_btn("Responder", self._responder, primary=True))
        der_ly.addLayout(acc)
        ly.addWidget(der, 2)
        self._conv_sel = None
        return w

    def _refrescar_bandeja(self, *_a):
        from src.services.redes_sociales import inbox as _I
        self._conversaciones = _I.listar_conversaciones()
        self.tbl_conversaciones.setRowCount(len(self._conversaciones))
        for i, c in enumerate(self._conversaciones):
            valores = [_PLATAFORMAS_LBL.get(c.get("plataforma"), c.get("plataforma")),
                      c.get("remitente_nombre") or c.get("remitente_handle") or "—",
                      c.get("tipo"), _ESTADOS_CONV_LBL.get(c.get("estado"), c.get("estado")),
                      c.get("prioridad"), c.get("fecha_ultimo_mensaje")]
            for j, val in enumerate(valores):
                self.tbl_conversaciones.setItem(i, j, _it(val))

    def _seleccionar_conversacion(self, row, _col):
        try:
            self._conv_sel = self._conversaciones[row]
        except (IndexError, AttributeError):
            self._conv_sel = None
            return
        from src.services.redes_sociales import inbox as _I
        c = self._conv_sel
        self.lbl_hilo_cab.setText(
            f"{_PLATAFORMAS_LBL.get(c.get('plataforma'), c.get('plataforma'))} · "
            f"{c.get('remitente_nombre') or '—'}")
        mensajes = _I.listar_mensajes(c["id"])
        lineas = []
        for m in mensajes:
            quien = "Nosotros" if m.get("direccion") == "saliente" else (m.get("autor") or "Cliente")
            ia = " 🤖" if m.get("generado_por_ia") else ""
            lineas.append(f"[{m.get('fecha')}] {quien}{ia}: {m.get('cuerpo')}")
        self.lbl_hilo.setText("\n".join(lineas) or "Sin mensajes todavía.")

        r360 = _I.cliente_360(c["id"])
        if r360.get("vinculado") and r360.get("cliente"):
            cli = r360["cliente"]
            n_fact = len(r360.get("facturas_recientes") or [])
            self.lbl_cliente360.setText(
                f"Cliente ERP: {cli.get('nombre') or cli.get('razon_social') or cli.get('id')} · "
                f"{n_fact} factura(s) reciente(s)")
        else:
            self.lbl_cliente360.setText("Sin vincular a ningún cliente del ERP.")

    def _abrir_sincronizar(self):
        cuentas = self._cuentas_cache()
        if not cuentas:
            _mensaje(self, "RRSS", "No hay cuentas conectadas todavía.", "warning")
            return
        dlg = QDialog(self); dlg.setWindowTitle("Sincronizar cuenta")
        dlg.setStyleSheet(f"background:{_BG};color:#FFFFFF;")
        ly = QVBoxLayout(dlg)
        form = QFormLayout()
        cb = QComboBox()
        for c in cuentas:
            cb.addItem(f"{_PLATAFORMAS_LBL.get(c['plataforma'], c['plataforma'])} — "
                      f"{c.get('nombre_cuenta') or c['id_externo']}", c["id"])
        in_extra = _inp("ID de vídeo (YouTube) / ID de usuario propio (X) — si aplica")
        form.addRow("Cuenta:", cb)
        form.addRow("Parámetro adicional:", in_extra)
        ly.addLayout(form)
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn("Cancelar", dlg.reject))
        fila.addWidget(_btn("Sincronizar", dlg.accept, primary=True))
        ly.addLayout(fila)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        from src.services.redes_sociales import inbox as _I
        id_cuenta = cb.currentData()
        plataforma = next(c["plataforma"] for c in cuentas if c["id"] == id_cuenta)
        kwargs = {}
        if plataforma == "youtube":
            kwargs["id_externo_video"] = in_extra.text().strip() or None
        elif plataforma == "x":
            kwargs["id_externo_usuario"] = in_extra.text().strip() or None
        r = _I.sincronizar(id_cuenta, **kwargs)
        if r.get("ok"):
            _mensaje(self, "RRSS",
                    f"Sincronizado: {r.get('nuevas_conversaciones', 0)} conversación(es), "
                    f"{r.get('nuevos_mensajes', 0)} mensaje(s) nuevo(s).", "success")
        else:
            _mensaje(self, "RRSS",
                    f"No se pudo sincronizar ({r.get('estado')}).", "warning")
        self._refrescar_bandeja()

    def _sugerir_ia(self):
        if not self._conv_sel:
            _mensaje(self, "RRSS", "Selecciona primero una conversación.", "warning")
            return
        from src.services.redes_sociales import inbox as _I
        mensajes = _I.listar_mensajes(self._conv_sel["id"])
        entrantes = [m for m in mensajes if m.get("direccion") == "entrante"]
        if not entrantes:
            _mensaje(self, "RRSS", "No hay ningún mensaje entrante que responder.", "warning")
            return
        from src.services.redes_sociales import asistente_ia as _IA
        r = _IA.sugerir_respuesta(entrantes[-1].get("cuerpo"),
                                  cliente_nombre=self._conv_sel.get("remitente_nombre"))
        if r.get("via") == "ia":
            self.in_respuesta.setPlainText(r["texto"])
        else:
            _mensaje(self, "RRSS",
                    f"Sugerencia de IA no disponible ({r.get('motivo')}).", "warning")

    def _vincular_cliente(self):
        if not self._conv_sel:
            _mensaje(self, "RRSS", "Selecciona primero una conversación.", "warning")
            return
        texto, ok = _pedir_texto(self, "Vincular cliente", "Nombre/teléfono/email del cliente:")
        if not ok or not texto.strip():
            return
        try:
            from src.db.clientes import buscar_clientes
            resultados = buscar_clientes(texto.strip(), None, 10) or []
        except Exception as e:
            logger.error("buscar_clientes: %s", e)
            resultados = []
        if not resultados:
            _mensaje(self, "RRSS", "No se encontró ningún cliente con ese criterio.", "warning")
            return
        dlg = QDialog(self); dlg.setWindowTitle("Selecciona el cliente")
        dlg.setStyleSheet(f"background:{_BG};color:#FFFFFF;")
        ly = QVBoxLayout(dlg)
        lw = QListWidget()
        for c in resultados:
            it = QListWidgetItem(f"{c.get('nombre') or c.get('razon_social')} ({c.get('id')})")
            it.setData(Qt.ItemDataRole.UserRole, c.get("id"))
            lw.addItem(it)
        ly.addWidget(lw)
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn("Cancelar", dlg.reject))
        fila.addWidget(_btn("Vincular", dlg.accept, primary=True))
        ly.addLayout(fila)
        if dlg.exec() != QDialog.DialogCode.Accepted or not lw.currentItem():
            return
        id_cliente = lw.currentItem().data(Qt.ItemDataRole.UserRole)
        from src.services.redes_sociales import inbox as _I
        r = _I.vincular_cliente(self._conv_sel["id"], id_cliente)
        if r.get("ok"):
            _mensaje(self, "RRSS", "Cliente vinculado correctamente.", "success")
            self._seleccionar_conversacion(self.tbl_conversaciones.currentRow(), 0)
        else:
            _mensaje(self, "RRSS", "No se pudo vincular el cliente.", "warning")

    def _responder(self):
        if not self._conv_sel:
            _mensaje(self, "RRSS", "Selecciona primero una conversación.", "warning")
            return
        texto = self.in_respuesta.toPlainText().strip()
        if not texto:
            return
        from src.services.redes_sociales import inbox as _I
        generado_ia = bool(getattr(self, "_ultima_sugerencia_ia", False))
        r = _I.responder(self._conv_sel["id"], texto,
                         autor=self.usuario.get("nombre") or self.usuario.get("usuario"),
                         generado_por_ia=generado_ia)
        if r.get("ok"):
            _mensaje(self, "RRSS", "Respuesta enviada.", "success")
            self.in_respuesta.clear()
            self._refrescar_bandeja()
            self._seleccionar_conversacion(self.tbl_conversaciones.currentRow(), 0)
        else:
            _mensaje(self, "RRSS", f"No se pudo enviar ({r.get('estado')}).", "warning")

    # ══════════════════════════════════════════════════════════════════
    # 2) Calendario de contenidos
    # ══════════════════════════════════════════════════════════════════
    def _page_calendario(self):
        w = QWidget(); ly = QVBoxLayout(w)
        barra = QHBoxLayout()
        barra.addWidget(_btn("➕ Nueva publicación", self._nueva_publicacion, primary=True))
        barra.addWidget(_btn("Publicar ahora", self._publicar_ahora, primary=True))
        barra.addWidget(_btn("🔄 Actualizar", self._refrescar_calendario, primary=True))
        barra.addStretch()
        ly.addLayout(barra)
        self.tbl_publicaciones = _tabla(["ID", "Plataforma", "Título", "Estado", "Programada",
                                         "Publicada", "Error"])
        self.tbl_publicaciones.cellClicked.connect(self._seleccionar_publicacion)
        ly.addWidget(self.tbl_publicaciones)
        self._pub_sel = None
        return w

    def _refrescar_calendario(self, *_a):
        from src.services.redes_sociales import calendario as _CAL
        self._publicaciones = _CAL.listar_publicaciones()
        self.tbl_publicaciones.setRowCount(len(self._publicaciones))
        for i, p in enumerate(self._publicaciones):
            valores = [p.get("id"), _PLATAFORMAS_LBL.get(p.get("plataforma"), p.get("plataforma")),
                      p.get("titulo") or "—", p.get("estado"), p.get("fecha_programada"),
                      p.get("fecha_publicada"), p.get("error_publicacion")]
            for j, val in enumerate(valores):
                self.tbl_publicaciones.setItem(i, j, _it(val))

    def _seleccionar_publicacion(self, row, _col):
        try:
            self._pub_sel = self._publicaciones[row]
        except (IndexError, AttributeError):
            self._pub_sel = None

    def _nueva_publicacion(self):
        cuentas = self._cuentas_cache()
        if not cuentas:
            _mensaje(self, "RRSS", "Conecta primero una cuenta.", "warning")
            return
        dlg = _NuevaPublicacionDialog(cuentas, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        datos = dlg.datos()
        from src.services.redes_sociales import calendario as _CAL
        try:
            _CAL.crear_publicacion(datos["id_cuenta"], datos["plataforma"], titulo=datos["titulo"],
                                   contenido=datos["contenido"], ruta_adjunto=datos["ruta_adjunto"],
                                   fecha_programada=datos["fecha_programada"],
                                   creado_por=self.usuario.get("usuario"))
            _mensaje(self, "RRSS", "Publicación guardada.", "success")
        except _CAL.CalendarioError as e:
            _mensaje(self, "RRSS", str(e), "warning")
        self._refrescar_calendario()

    def _publicar_ahora(self):
        if not self._pub_sel:
            _mensaje(self, "RRSS", "Selecciona primero una publicación.", "warning")
            return
        from src.services.redes_sociales import calendario as _CAL
        r = _CAL.publicar_ahora(self._pub_sel["id"])
        if r.get("ok"):
            _mensaje(self, "RRSS", "Publicado correctamente.", "success")
        else:
            _mensaje(self, "RRSS", f"No se pudo publicar ({r.get('estado')}).", "warning")
        self._refrescar_calendario()

    def _tick_calendario(self):
        try:
            from src.services.redes_sociales import calendario as _CAL
            _CAL.procesar_programadas()
            if self.stack.currentIndex() == 1:
                self._refrescar_calendario()
        except Exception as e:
            logger.debug("tick_calendario: %s", e)

    # ══════════════════════════════════════════════════════════════════
    # 3) Analítica
    # ══════════════════════════════════════════════════════════════════
    def _page_analitica(self):
        w = QWidget(); ly = QVBoxLayout(w)
        barra = QHBoxLayout()
        from PyQt6.QtCore import QDate

        from src.gui.tpv import _FechaFilter
        # Mismo filtro de fecha neón que el resto de la app (Documentos/Ventas/TPV) — NO
        # `QDateEdit` nativo, cuyo calendario emergente no sigue el diseño del resto de
        # desplegables (y además es el widget con el bug documentado de MINMAXINFO en diálogos
        # frameless de Windows, ver `_FechaFilter`). El icono de "desplegable" de `_FechaFilter`
        # (`_TriLineEdit`) es un triángulo relleno, distinto del chevron "v" que usa el resto de
        # los desplegables de la app (`_combo`, flecha nativa de `QComboBox`) — se sustituye SOLO
        # aquí (instancia a instancia, sin tocar `tpv.py` ni el resto de pantallas que ya usan
        # `_FechaFilter` tal cual) por un chevron del mismo estilo.
        self.in_desde = _FechaFilter(QDate.currentDate().addDays(-30))
        self.in_hasta = _FechaFilter(QDate.currentDate())
        _usar_chevron_combo(self.in_desde)
        _usar_chevron_combo(self.in_hasta)
        barra.addWidget(QLabel("Desde:", styleSheet=f"color:{_DIM};")); barra.addWidget(self.in_desde)
        barra.addWidget(QLabel("Hasta:", styleSheet=f"color:{_DIM};")); barra.addWidget(self.in_hasta)
        barra.addWidget(_btn("Generar informe", self._generar_informe, primary=True))
        barra.addStretch()
        ly.addLayout(barra)

        self.lbl_aviso_analitica = QLabel(""); self.lbl_aviso_analitica.setWordWrap(True)
        self.lbl_aviso_analitica.setStyleSheet(f"color:{_DIM};font-style:italic;")
        ly.addWidget(self.lbl_aviso_analitica)

        self.lbl_resumen_ventas = QLabel(""); self.lbl_resumen_ventas.setWordWrap(True)
        self.lbl_resumen_ventas.setStyleSheet("color:#FFFFFF;")
        ly.addWidget(self.lbl_resumen_ventas)

        self.tbl_metricas = _tabla(["Plataforma", "Publicaciones", "Impresiones", "Alcance",
                                    "Interacciones", "Likes", "Comentarios", "Compartidos", "Clics"])
        ly.addWidget(self.tbl_metricas)
        return w

    def _generar_informe(self):
        from src.services.redes_sociales import analitica as _AN
        desde = self.in_desde.date().toString("yyyy-MM-dd")
        hasta = self.in_hasta.date().toString("yyyy-MM-dd")
        r = _AN.cruce_con_ventas(desde, hasta)
        self.lbl_aviso_analitica.setText(f"⚠ {r.get('aviso')}")
        ventas = r.get("ventas_erp") or {}
        self.lbl_resumen_ventas.setText(
            f"ERP ({desde} → {hasta}): facturación {ventas.get('facturacion', 0):,.2f} € · "
            f"{ventas.get('tickets', 0)} tickets · {r.get('presupuestos_creados', 0)} presupuesto(s) "
            f"creado(s) en el mismo periodo.")
        filas = r.get("actividad_social") or []
        self.tbl_metricas.setRowCount(len(filas))
        for i, f in enumerate(filas):
            valores = [_PLATAFORMAS_LBL.get(f.get("plataforma"), f.get("plataforma")),
                      f.get("publicaciones"), f.get("impresiones"), f.get("alcance"),
                      f.get("interacciones"), f.get("likes"), f.get("comentarios"),
                      f.get("compartidos"), f.get("clics")]
            for j, val in enumerate(valores):
                self.tbl_metricas.setItem(i, j, _it(val))

    # ══════════════════════════════════════════════════════════════════
    # 4) Reputación y Alertas
    # ══════════════════════════════════════════════════════════════════
    def _page_reputacion(self):
        w = QWidget(); ly = QVBoxLayout(w)
        barra = QHBoxLayout()
        barra.addWidget(_btn("➕ Nueva regla", self._nueva_regla, primary=True))
        barra.addWidget(_btn("✏️ Editar", self._editar_regla, primary=True))
        barra.addWidget(_btn("🚫 Activar/Desactivar", self._alternar_regla, primary=True))
        barra.addWidget(_btn("Reevaluar ahora", self._reevaluar_reputacion, primary=True))
        barra.addWidget(_btn("🔄 Actualizar", self._refrescar_reputacion, primary=True))
        barra.addWidget(_btn("🗑️ Eliminar", self._eliminar_regla, danger=True))
        barra.addStretch()
        ly.addLayout(barra)
        ly.addWidget(QLabel("REGLAS (la empresa puede crear, editar y borrar las que quiera — la "
                           "predeterminada incluida)", styleSheet=f"color:{_CIAN};font-weight:900;"))
        self.tbl_reglas = _tabla(["ID", "Nombre", "Palabras clave", "Prioridad ticket", "Activa"])
        self.tbl_reglas.cellClicked.connect(self._seleccionar_regla)
        ly.addWidget(self.tbl_reglas, 1)
        ly.addWidget(QLabel("ALERTAS ESCALADAS A INCIDENCIAS", styleSheet=f"color:{_CIAN};"
                           f"font-weight:900;margin-top:10px;"))
        self.tbl_alertas = _tabla(["Plataforma", "Texto detectado", "Nº ticket", "Estado", "Fecha"])
        ly.addWidget(self.tbl_alertas, 1)
        self._regla_sel = None
        return w

    def _refrescar_reputacion(self, *_a):
        from src.services.redes_sociales import reputacion as _REP
        self._reglas = _REP.listar_reglas()
        self.tbl_reglas.setRowCount(len(self._reglas))
        for i, r in enumerate(self._reglas):
            valores = [r.get("id"), r.get("nombre"), r.get("palabras_clave"),
                      r.get("prioridad_ticket"), "Sí" if r.get("activa") else "No"]
            for j, val in enumerate(valores):
                self.tbl_reglas.setItem(i, j, _it(val))
        alertas = _REP.listar_alertas()
        self.tbl_alertas.setRowCount(len(alertas))
        for i, a in enumerate(alertas):
            valores = [_PLATAFORMAS_LBL.get(a.get("plataforma"), a.get("plataforma")),
                      (a.get("texto_detectado") or "")[:120], a.get("id_ticket_incidencia"),
                      a.get("estado"), a.get("fecha_creacion")]
            for j, val in enumerate(valores):
                self.tbl_alertas.setItem(i, j, _it(val))

    def _seleccionar_regla(self, row, _col):
        try:
            self._regla_sel = self._reglas[row]
        except (IndexError, AttributeError):
            self._regla_sel = None

    def _nueva_regla(self):
        dlg = _NuevaReglaDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        datos = dlg.datos()
        from src.services.redes_sociales import reputacion as _REP
        try:
            _REP.crear_regla(datos["nombre"], datos["palabras_clave"],
                             prioridad_ticket=datos["prioridad_ticket"])
            _mensaje(self, "RRSS", "Regla creada.", "success")
        except _REP.ReputacionError as e:
            _mensaje(self, "RRSS", str(e), "warning")
        self._refrescar_reputacion()

    def _editar_regla(self):
        if not self._regla_sel:
            _mensaje(self, "RRSS", "Selecciona primero una regla.", "warning")
            return
        dlg = _NuevaReglaDialog(self, inicial=self._regla_sel)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        datos = dlg.datos()
        from src.services.redes_sociales import reputacion as _REP
        try:
            _REP.editar_regla(self._regla_sel["id"], nombre=datos["nombre"],
                              palabras_clave=datos["palabras_clave"],
                              prioridad_ticket=datos["prioridad_ticket"])
            _mensaje(self, "RRSS", "Regla actualizada.", "success")
        except _REP.ReputacionError as e:
            _mensaje(self, "RRSS", str(e), "warning")
        self._refrescar_reputacion()

    def _alternar_regla(self):
        if not self._regla_sel:
            _mensaje(self, "RRSS", "Selecciona primero una regla.", "warning")
            return
        from src.services.redes_sociales import reputacion as _REP
        _REP.activar_regla(self._regla_sel["id"], not self._regla_sel.get("activa"))
        self._refrescar_reputacion()

    def _eliminar_regla(self):
        if not self._regla_sel:
            _mensaje(self, "RRSS", "Selecciona primero una regla.", "warning")
            return
        from src.services.redes_sociales import reputacion as _REP
        _REP.eliminar_regla(self._regla_sel["id"])
        _mensaje(self, "RRSS", "Regla eliminada.", "success")
        self._regla_sel = None
        self._refrescar_reputacion()

    def _reevaluar_reputacion(self):
        from src.services.redes_sociales import reputacion as _REP
        r = _REP.evaluar_mensajes_nuevos()
        _mensaje(self, "RRSS",
                f"{r.get('evaluados', 0)} mensaje(s) evaluado(s), {r.get('escalados', 0)} "
                f"escalado(s) a Incidencias.", "success")
        self._refrescar_reputacion()

    # ══════════════════════════════════════════════════════════════════
    # 5) Cuentas conectadas
    # ══════════════════════════════════════════════════════════════════
    def _page_cuentas(self):
        w = QWidget(); ly = QVBoxLayout(w)
        barra = QHBoxLayout()
        btn_conectar_oauth = _btn("🔗 Conectar", self._conectar_oauth, primary=True)
        btn_conectar_oauth.setMinimumWidth(170)   # evita que Qt elida el texto bajo presión de layout
        barra.addWidget(btn_conectar_oauth)
        barra.addWidget(_btn("Alta manual (avanzado)", self._conectar_cuenta, primary=True))
        barra.addWidget(_btn("Desconectar", self._desconectar_cuenta, primary=True))
        barra.addWidget(_btn("🔄 Actualizar", self._refrescar_cuentas, primary=True))
        barra.addStretch()
        ly.addLayout(barra)
        ly.addWidget(QLabel("Varias cuentas conectadas de la MISMA plataforma (p. ej. dos páginas "
                           "de Facebook) se gestionan todas a la vez desde esta misma tabla — cada "
                           "fila es independiente en el resto del módulo.",
                           styleSheet=f"color:{_DIM};font-size:11px;"))
        self.tbl_cuentas = _tabla(["Plataforma", "Nombre", "ID externo", "Estado",
                                   "Último error", "Conectado por"])
        self.tbl_cuentas.cellClicked.connect(self._seleccionar_cuenta)
        ly.addWidget(self.tbl_cuentas)
        self._cuenta_sel = None
        return w

    def _refrescar_cuentas(self, *_a):
        self._cuentas = self._cuentas_cache()
        self.tbl_cuentas.setRowCount(len(self._cuentas))
        for i, c in enumerate(self._cuentas):
            valores = [_PLATAFORMAS_LBL.get(c.get("plataforma"), c.get("plataforma")),
                      c.get("nombre_cuenta") or "—", c.get("id_externo"), c.get("estado"),
                      c.get("ultimo_error") or "—", c.get("conectado_por") or "—"]
            for j, val in enumerate(valores):
                self.tbl_cuentas.setItem(i, j, _it(val))

    def _seleccionar_cuenta(self, row, _col):
        try:
            self._cuenta_sel = self._cuentas[row]
        except (IndexError, AttributeError):
            self._cuenta_sel = None

    def _conectar_oauth(self):
        dlg = _ElegirPlataformaOAuthDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        plataforma = dlg.plataforma()
        from src.services.redes_sociales import oauth as _OA
        r = _OA.construir_url_autorizacion(
            plataforma, id_empresa=None, usuario=self.usuario.get("usuario"))
        if not r.get("ok"):
            _mensaje(self, "RRSS",
                    f"No se puede iniciar el login en {_PLATAFORMAS_LBL.get(plataforma, plataforma)}: "
                    f"{r.get('detalle') or r.get('estado')}\n\nPuedes usar 'Alta manual (avanzado)' "
                    "mientras tanto.", "warning")
            return
        from src.services.redes_sociales import cuentas as _C
        ids_previos = [c["id"] for c in _C.listar(plataforma=plataforma)]
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl(r["url"]))
        espera = _EsperandoConexionDialog(plataforma, ids_previos, self)
        if espera.exec() == QDialog.DialogCode.Accepted and espera.resultado:
            _mensaje(self, "RRSS",
                    f"¡{espera.resultado.get('nombre_cuenta') or 'Cuenta'} conectada "
                    f"correctamente!", "success")
        self._refrescar_cuentas()

    def _conectar_cuenta(self):
        dlg = _ConectarCuentaDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        datos = dlg.datos()
        if not datos["id_externo"] or not datos["access_token"]:
            _mensaje(self, "RRSS", "ID externo y access token son obligatorios.", "warning")
            return
        from src.services.redes_sociales import cuentas as _C
        try:
            _C.conectar(datos["plataforma"], id_externo=datos["id_externo"],
                       access_token=datos["access_token"], nombre_cuenta=datos["nombre_cuenta"],
                       conectado_por=self.usuario.get("usuario"))
            _mensaje(self, "RRSS", "Cuenta conectada.", "success")
        except _C.CuentaError as e:
            _mensaje(self, "RRSS", str(e), "warning")
        self._refrescar_cuentas()

    def _desconectar_cuenta(self):
        if not self._cuenta_sel:
            _mensaje(self, "RRSS", "Selecciona primero una cuenta.", "warning")
            return
        from src.services.redes_sociales import cuentas as _C
        _C.desconectar(self._cuenta_sel["id"])
        _mensaje(self, "RRSS", "Cuenta desconectada.", "success")
        self._refrescar_cuentas()


def _pedir_texto(parent, titulo, etiqueta):
    from PyQt6.QtWidgets import QInputDialog
    return QInputDialog.getText(parent, titulo, etiqueta)
