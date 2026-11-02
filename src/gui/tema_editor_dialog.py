"""
Editor visual WYSIWYG del storefront (Fase 4 e-commerce, Catálogo Web / Canal Web).

Secciones/bloques reordenables (hero, texto, banner, grids de producto) con vista previa en vivo
(`QWebEngineView`, datos reales del catálogo) y edición in-situ (clic en una sección → formulario
de sus campos ahí mismo, sin modal aparte). El motor de render es `backend/storefront_bloques.py`
(reutilizado tal cual — el mismo HTML que verá el visitante real de la tienda, nunca una maqueta
aparte) y el texto se guarda en `web_config.tema_json` vía el ÚNICO editor ya existente
(`comercio_digital.canal_web.guardar_presencia` → `db.web_tienda.guardar_config`).

Módulo AUTÓNOMO (mismo criterio que `pasarela_config_dialog.py`/`canal_web_config.py`: copia sus
propias primitivas de estilo, no importa nada de `gui.tpv`).

`PyQt6-WebEngine` es una dependencia OPCIONAL (igual criterio que Prophet/onvif-zeep/ffmpeg en el
resto de la app): si no está instalada, el editor se abre igual (secciones/formularios/IA/guardado
funcionan) pero la vista previa en vivo se sustituye por un aviso honesto — nunca bloquea la
función completa por una dependencia de visualización ausente.
"""

from __future__ import annotations

import json

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QDialog,
                             QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                             QListWidgetItem, QPlainTextEdit, QPushButton, QScrollArea,
                             QVBoxLayout, QWidget)

from assets.estilo_global import _blindar_tamano_fijo, instalar_corner_cover
from src.utils.i18n import tr

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
except Exception:
    QWebEngineView = None

_BG = "#0E1117"
_BG2 = "#161B22"
_CIAN = "#00FFC6"
_ROJO = "#FF4C4C"
_VERDE = "#3FB950"
_BORDE = "#30363D"
_TEXT = "#E6EDF3"
_TEXT2 = "#8B949E"
_FONT = "Segoe UI"

# Diseño de arranque (si la tienda todavía no tiene ningún tema guardado): equivalente en
# contenido/orden al layout fijo de siempre (`storefront.pagina_home`) — el usuario parte de algo
# reconocible, no de un lienzo en blanco, y puede reordenar/editar/añadir desde ahí.
_SECCIONES_INICIALES = ("grid_destacados", "grid_recomendados", "grid_catalogo")

_ICONO_TIPO = {"hero": "🖼", "texto": "📝", "banner": "🏳", "grid_destacados": "⭐",
              "grid_recomendados": "👍", "grid_catalogo": "🛍", "separador": "➖"}


def _lbl(text, bold=False, size=12, color=_TEXT, wrap=True):
    lb = QLabel(text)
    lb.setStyleSheet(f"color:{color};font-family:'{_FONT}';font-size:{size}px;"
                     f"font-weight:{'900' if bold else '500'};background:transparent;border:none;")
    lb.setWordWrap(wrap)
    return lb


def _btn_x(slot=None):
    """Botón rojo ✕ (cerrar) circular, mismo diseño EXACTO que el resto de la app (p. ej.
    `canal_web_config.py`/`canal_web_gui.py`) — a diferencia de `_btn()`, que dibuja un rectángulo
    redondeado CON borde, este es un círculo transparente sin borde, relleno sólido al hover."""
    b = QPushButton("✕")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFixedSize(38, 38)
    b.setStyleSheet(
        f"QPushButton{{background:transparent;color:{_ROJO};border:none;border-radius:19px;"
        f"padding:0;font-weight:900;font-size:18px;}}"
        f"QPushButton:hover{{background:{_ROJO};color:#0D1117;}}")
    b.setProperty("sin_glow", True)
    _blindar_tamano_fijo(b, 38, 38)
    if slot:
        b.clicked.connect(slot)
    return b


def _btn(text, color_fg=_TEXT, color_border=_BORDE, hover_bg=_CIAN, h=34):
    b = QPushButton(text)
    b.setFixedHeight(h)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setStyleSheet(
        f"QPushButton{{background:{_BG2};color:{color_fg};border:2px solid {color_border};"
        f"border-radius:8px;font-family:'{_FONT}';font-weight:900;font-size:12px;padding:0 12px;}}"
        f"QPushButton:hover{{background:{hover_bg};color:#0D1117;}}")
    return b


def _inp(val=""):
    e = QLineEdit(val or "")
    e.setFixedHeight(32)
    e.setStyleSheet(f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
                    f"border-radius:7px;padding:0 8px;font-size:12px;font-family:'{_FONT}';}}"
                    f"QLineEdit:focus{{border-color:{_CIAN};}}")
    return e


def _textarea(val=""):
    t = QPlainTextEdit(val or "")
    t.setFixedHeight(90)
    t.setStyleSheet(f"QPlainTextEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
                    f"border-radius:7px;padding:6px;font-size:12px;font-family:'{_FONT}';}}"
                    f"QPlainTextEdit:focus{{border-color:{_CIAN};}}")
    return t


class _ListaSecciones(QListWidget):
    """Reordenable por arrastre — a diferencia del Kanban (`gui/components/kanban.py`, que IGNORA
    el reordenado interno porque el orden ahí no tiene significado de negocio), aquí el orden de
    la lista ES el orden real de la página, así que se deja el `InternalMove` nativo de Qt (los
    ítems son texto plano, sin `setItemWidget`, por eso no aplica el workaround del Kanban)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setStyleSheet(
            f"QListWidget{{background:{_BG2};color:{_TEXT};border:2px solid {_CIAN};"
            f"border-radius:12px;font-family:'{_FONT}';font-size:12px;outline:0;}}"
            f"QListWidget::item{{padding:8px;border-bottom:1px solid {_BORDE};}}"
            # Las secciones DEBEN mantener esquinas rectas siempre (encargo explícito) — el único
            # redondeo real es el de las 2 esquinas superiores del propio CONTENEDOR, cuando la
            # primera fila queda seleccionada/con el ratón encima (resuelto aparte, vía
            # `instalar_corner_cover(..., esquinas="superior")` tras crear la lista, NO con
            # border-radius por ítem — eso redondearía CUALQUIER fila que se seleccione, no solo
            # la primera).
            f"QListWidget::item:hover{{background:rgba(0,255,198,0.10);}}"
            f"QListWidget::item:selected{{background:{_CIAN};color:#0D1117;}}")


class TemaEditorDialog(QDialog):
    """Editor visual WYSIWYG de la home del storefront."""

    def __init__(self, parent=None, usuario=None):
        super().__init__(parent)
        self._usuario_actual = usuario
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Sin el contorno neón cian global (`QDialog{border:2px solid CIAN}`, estilo_global.py):
        # esta ventana es a PANTALLA COMPLETA.
        self.setObjectName("dlg_tema_editor")
        self.setStyleSheet("#dlg_tema_editor { border: none; }")
        try:
            self.setGeometry(QApplication.primaryScreen().availableGeometry())
        except Exception:
            self.setMinimumSize(1100, 720)

        from src.db.empresa import empresa_actual_id
        from src.db import web_tienda
        self._eid = empresa_actual_id()
        self._cfg = web_tienda.obtener_config(self._eid)
        self._secciones = self._cargar_secciones()
        self._idx_sel = None
        self._dispositivo = "escritorio"

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(150)
        self._debounce.timeout.connect(self._actualizar_preview)

        self._build()
        self._poblar_lista()
        self._actualizar_preview()

    def showEvent(self, e):
        super().showEvent(e)
        try:
            self.setGeometry(QApplication.primaryScreen().availableGeometry())
        except Exception:
            pass

    def moveEvent(self, e):
        """Ventana FIJA: a pantalla completa no tiene sentido que el usuario pueda arrastrarla (ni
        falta ni sitio donde soltarla) — si algo la mueve de su posición (Windows permite mover una
        ventana sin barra de título por varias vías: Alt+arrastrar, snap de bordes…), se reafirma
        aquí mismo. El objetivo se recalcula EN VIVO contra la pantalla actual (misma fuente que
        `showEvent`/`abrir_dialogo_deslizante`) en vez de guardar una posición fija de una vez: así
        la propia reafirmación de geometría de `abrir_dialogo_deslizante` tras el asentamiento de
        Windows (ver su docstring) no entra en conflicto con este guard — ambas convergen al MISMO
        punto. `_restaurando` evita el bucle (mover dispara este mismo evento)."""
        super().moveEvent(e)
        if getattr(self, "_restaurando", False):
            return
        try:
            scr = self.screen() or QApplication.primaryScreen()
            objetivo = scr.availableGeometry().topLeft() if scr is not None else None
        except Exception:
            objetivo = None
        if objetivo is not None and self.pos() != objetivo:
            self._restaurando = True
            try:
                self.move(objetivo)
            finally:
                self._restaurando = False

    # ── Carga / guardado ──────────────────────────────────────────────────────
    def _cargar_secciones(self):
        from src.backend.storefront_bloques import bloque_por_defecto
        crudo = self._cfg.get("tema_json")
        if crudo:
            try:
                tema = json.loads(crudo)
                secciones = tema.get("secciones")
                if secciones:
                    return secciones
            except Exception:
                pass
        return [bloque_por_defecto(t) for t in _SECCIONES_INICIALES]

    def _guardar(self):
        try:
            from src.services.comercio_digital import canal_web as _cw
            r = _cw.guardar_presencia(usuario=self._usuario_actual,
                                      tema_json=json.dumps({"secciones": self._secciones}))
        except Exception as e:
            r = {"ok": False, "error": str(e)}
        if r.get("ok"):
            self.lbl_msg.setText(tr("tema.ok", default="Diseño guardado. Ya se ve así en la tienda."))
            self.lbl_msg.setStyleSheet(f"color:{_VERDE};font-size:11px;font-family:'{_FONT}';")
        else:
            self.lbl_msg.setText(tr("tema.err", default="No se pudo guardar el diseño: {e}",
                                    e=r.get("error") or r.get("permiso") or "error"))
            self.lbl_msg.setStyleSheet(f"color:{_ROJO};font-size:11px;font-family:'{_FONT}';")

    # ── Construcción ──────────────────────────────────────────────────────────
    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        # Pantalla completa, SIN contorno neón (mismo criterio que el resto de ventanas "a pantalla
        # completa" de la app, p. ej. `CanalWebConfigDialog`/`CanalWebWindow`).
        cuerpo = QFrame()
        cuerpo.setObjectName("tema")
        cuerpo.setStyleSheet(f"QFrame#tema{{background:{_BG};border:none;}}")
        outer.addWidget(cuerpo)
        cv = QVBoxLayout(cuerpo)
        cv.setContentsMargins(14, 10, 14, 14)
        cv.setSpacing(10)

        hd = QHBoxLayout()
        titulo = _lbl("🎨  " + tr("tema.titulo", default="Editor visual de la tienda online"),
                      bold=True, size=16, color=_CIAN, wrap=False)
        hd.addWidget(titulo)
        hd.addStretch()
        for etq, disp in (("🖥 " + tr("tema.escritorio", default="Escritorio"), "escritorio"),
                          ("📱 " + tr("tema.movil", default="Móvil"), "movil")):
            b = _btn(etq, h=32)
            b.clicked.connect(lambda _c=False, d=disp: self._cambiar_dispositivo(d))
            hd.addWidget(b)
        b_guardar = _btn(tr("tema.guardar", default="Guardar diseño"), color_fg=_VERDE,
                        color_border=_VERDE, hover_bg=_VERDE, h=36)
        b_guardar.clicked.connect(self._guardar)
        hd.addWidget(b_guardar)
        hd.addWidget(_btn_x(self.reject))
        cv.addLayout(hd)
        self.lbl_msg = _lbl("", size=11, color=_TEXT2)
        cv.addWidget(self.lbl_msg)

        cuerpo_h = QHBoxLayout()
        cuerpo_h.setSpacing(10)
        cuerpo_h.addWidget(self._panel_izquierdo(), 0)
        cuerpo_h.addWidget(self._panel_preview(), 1)
        cv.addLayout(cuerpo_h, 1)

    def _panel_izquierdo(self):
        w = QFrame(); w.setFixedWidth(320)
        ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(8)

        ly.addWidget(_lbl(tr("tema.secciones", default="Secciones de la página"), bold=True, size=12))
        self.lst_secciones = _ListaSecciones()
        self.lst_secciones.setFixedHeight(220)
        self.lst_secciones.currentRowChanged.connect(self._seleccionar_seccion)
        self.lst_secciones.model().rowsMoved.connect(self._reordenar_tras_arrastre)
        ly.addWidget(self.lst_secciones)
        # `bg` = fondo REAL que rodea la lista (`cuerpo`/`_BG`, #0E1117), NO el fondo propio de la
        # lista (`_BG2`, #161B22, más claro) — con `_BG2` el parche de esquina se ve más claro que
        # lo que lo rodea, exactamente el "gris sutil que sobresale" de este mismo tipo de fallo.
        # `esquinas="superior"`: la caja tiene mucho alto de sobra bajo las 3 secciones reales, así
        # que solo la PRIMERA llega a tocar el borde redondeado de arriba — la de abajo no toca
        # ningún borde real, y el resto de secciones debe quedar con esquinas rectas (a propósito).
        instalar_corner_cover(self.lst_secciones, radius=12, bg=_BG, border=_CIAN, esquinas="superior")

        fila_add = QHBoxLayout()
        from src.backend.storefront_bloques import BLOQUES_DISPONIBLES
        self.cmb_tipo_nuevo = QComboBox()
        self.cmb_tipo_nuevo.setFixedHeight(32)
        self.cmb_tipo_nuevo.setStyleSheet(
            f"QComboBox{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
            f"border-radius:7px;padding:0 8px;font-size:12px;font-family:'{_FONT}';}}")
        for tipo, meta in BLOQUES_DISPONIBLES.items():
            self.cmb_tipo_nuevo.addItem(_ICONO_TIPO.get(tipo, "▫") + " " + meta["etiqueta"], tipo)
        self.cmb_tipo_nuevo.view().setMinimumWidth(260)   # el desplegable no corta los textos largos
        fila_add.addWidget(self.cmb_tipo_nuevo, 1)
        b_add = _btn("➕ " + tr("tema.anadir", default="Añadir"), h=32)
        b_add.clicked.connect(self._anadir_seccion)
        fila_add.addWidget(b_add)
        ly.addLayout(fila_add)

        b_del = _btn("🗑 " + tr("tema.eliminar", default="Eliminar sección"), color_fg=_ROJO,
                     color_border=_ROJO, hover_bg=_ROJO, h=32)
        b_del.clicked.connect(self._eliminar_seccion)
        ly.addWidget(b_del)

        ly.addWidget(_lbl(tr("tema.editar", default="Editar sección seleccionada"), bold=True, size=12))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("background:transparent;border:none;")
        self._form_host = QWidget()
        self._form_host.setStyleSheet("background:transparent;")
        self._form_lay = QVBoxLayout(self._form_host)
        self._form_lay.setContentsMargins(0, 0, 0, 0)
        self._form_lay.setSpacing(8)
        self._form_lay.addStretch()
        scroll.setWidget(self._form_host)
        ly.addWidget(scroll, 1)
        return w

    def _panel_preview(self):
        w = QFrame()
        w.setStyleSheet(f"QFrame{{background:{_BG2};border:1px solid {_BORDE};border-radius:10px;}}")
        self._preview_contenedor_lay = QHBoxLayout(w)
        self._preview_contenedor_lay.setContentsMargins(0, 0, 0, 0)
        if QWebEngineView is not None:
            self.preview = QWebEngineView()
            # "Marco de teléfono" (Generador de Apps Móviles PWA, Fase 1 — simulador interactivo):
            # un bisel redondeado + muesca superior alrededor de la vista previa, visible SOLO en
            # modo Móvil, para que se vea/sienta como el simulador de una App, no como una página
            # web estrecha. En Escritorio el marco queda transparente/sin biselar.
            self._marco_telefono = QFrame()
            self._marco_telefono.setObjectName("marcoTelefono")
            self._marco_telefono.setStyleSheet("QFrame#marcoTelefono{background:transparent;border:none;}")
            marco_ly = QVBoxLayout(self._marco_telefono)
            marco_ly.setContentsMargins(10, 28, 10, 10)
            marco_ly.setSpacing(0)
            self._muesca_telefono = QFrame(self._marco_telefono)
            self._muesca_telefono.setFixedSize(120, 16)
            self._muesca_telefono.setStyleSheet("background:#000;border-radius:8px;")
            self._muesca_telefono.setVisible(False)
            self._muesca_telefono.move(0, 6)  # recolocada en _cambiar_dispositivo (centrada)
            marco_ly.addWidget(self.preview)
            self._preview_contenedor_lay.addStretch()
            self._preview_contenedor_lay.addWidget(self._marco_telefono, 0)
            self._preview_contenedor_lay.addStretch()
        else:
            self.preview = None
            self._marco_telefono = None
            aviso = _lbl(tr("tema.sin_webengine",
                            default="Vista previa en vivo no disponible: instala la dependencia "
                                    "'PyQt6-WebEngine' para verla. El resto del editor (secciones, "
                                    "textos, IA, guardado) funciona igual."),
                        size=12, color=_TEXT2)
            aviso.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._preview_contenedor_lay.addWidget(aviso)
        return w

    # ── Lista de secciones ────────────────────────────────────────────────────
    def _poblar_lista(self):
        self.lst_secciones.blockSignals(True)
        self.lst_secciones.clear()
        from src.backend.storefront_bloques import BLOQUES_DISPONIBLES
        for b in self._secciones:
            meta = BLOQUES_DISPONIBLES.get(b["tipo"], {"etiqueta": b["tipo"]})
            item = QListWidgetItem(_ICONO_TIPO.get(b["tipo"], "▫") + "  " + meta["etiqueta"])
            self.lst_secciones.addItem(item)
        self.lst_secciones.blockSignals(False)
        if self._secciones:
            self.lst_secciones.setCurrentRow(min(self._idx_sel or 0, len(self._secciones) - 1))

    def _reordenar_tras_arrastre(self, *_a):
        # Tras el drop, reconstruir `self._secciones` leyendo el orden FINAL de la lista (cada
        # ítem conserva su posición original vía el texto — se resuelve por índice de fila porque
        # los ítems son texto plano, no llevan datos adjuntos que puedan desincronizarse).
        orden_textos = [self.lst_secciones.item(r).text() for r in range(self.lst_secciones.count())]
        from src.backend.storefront_bloques import BLOQUES_DISPONIBLES
        restantes = list(self._secciones)
        nuevas = []
        for texto in orden_textos:
            for i, b in enumerate(restantes):
                meta = BLOQUES_DISPONIBLES.get(b["tipo"], {"etiqueta": b["tipo"]})
                etiqueta = _ICONO_TIPO.get(b["tipo"], "▫") + "  " + meta["etiqueta"]
                if etiqueta == texto:
                    nuevas.append(restantes.pop(i))
                    break
        if len(nuevas) == len(self._secciones):
            self._secciones = nuevas
        self._actualizar_preview()

    def _seleccionar_seccion(self, row):
        self._idx_sel = row if row is not None and row >= 0 else None
        self._reconstruir_formulario()

    def _anadir_seccion(self):
        from src.backend.storefront_bloques import bloque_por_defecto
        tipo = self.cmb_tipo_nuevo.currentData()
        self._secciones.append(bloque_por_defecto(tipo))
        self._idx_sel = len(self._secciones) - 1
        self._poblar_lista()
        self._reconstruir_formulario()
        self._actualizar_preview()

    def _eliminar_seccion(self):
        if self._idx_sel is None or not (0 <= self._idx_sel < len(self._secciones)):
            return
        del self._secciones[self._idx_sel]
        self._idx_sel = None
        self._poblar_lista()
        self._reconstruir_formulario()
        self._actualizar_preview()

    # ── Formulario in-situ de la sección seleccionada ────────────────────────
    def _reconstruir_formulario(self):
        while self._form_lay.count():
            item = self._form_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if self._idx_sel is None or not (0 <= self._idx_sel < len(self._secciones)):
            self._form_lay.addWidget(_lbl(tr("tema.sin_seleccion",
                                             default="Selecciona una sección para editarla."),
                                          size=11, color=_TEXT2))
            self._form_lay.addStretch()
            return
        bloque = self._secciones[self._idx_sel]
        from src.backend.storefront_bloques import BLOQUES_DISPONIBLES
        from src.services.catalogo.ia_contenido import CAMPOS_BLOQUE_VALIDOS
        meta = BLOQUES_DISPONIBLES.get(bloque["tipo"], {"campos": []})
        if not meta["campos"]:
            self._form_lay.addWidget(_lbl(tr("tema.sin_campos",
                                             default="Esta sección no tiene campos editables: "
                                                     "muestra siempre los datos reales del catálogo."),
                                          size=11, color=_TEXT2))
        for campo, etiqueta, _requerido in meta["campos"]:
            fila_etq = QHBoxLayout()
            fila_etq.addWidget(_lbl(etiqueta, size=11, color=_TEXT2), 1)
            if (bloque["tipo"], campo) in CAMPOS_BLOQUE_VALIDOS:
                b_ia = _btn("✨", h=24)
                b_ia.setFixedWidth(30)
                b_ia.setToolTip(tr("tema.ia_tooltip", default="Generar con IA"))
                b_ia.clicked.connect(lambda _c=False, c=campo: self._generar_ia(c))
                fila_etq.addWidget(b_ia)
            self._form_lay.addLayout(fila_etq)
            multilinea = campo in ("texto", "subtitulo")
            inp = _textarea(bloque["config"].get(campo, "")) if multilinea else _inp(bloque["config"].get(campo, ""))
            inp.textChanged.connect(lambda _v=None, c=campo, w=inp, ml=multilinea:
                                    self._campo_cambiado(c, w.toPlainText() if ml else w.text()))
            self._form_lay.addWidget(inp)
        self._form_lay.addStretch()

    def _campo_cambiado(self, campo, valor):
        if self._idx_sel is None:
            return
        self._secciones[self._idx_sel]["config"][campo] = valor
        self._debounce.start()

    def _generar_ia(self, campo):
        if self._idx_sel is None:
            return
        bloque = self._secciones[self._idx_sel]
        from src.services.catalogo.ia_contenido import generar_texto_bloque
        r = generar_texto_bloque(bloque["tipo"], campo, self._cfg.get("nombre") or "",
                                 usuario=self._usuario_actual, id_empresa=self._eid)
        if r.get("ok"):
            bloque["config"][campo] = r["texto"]
            self.lbl_msg.setText(tr("tema.ia_ok", default="Texto generado — revísalo antes de guardar."))
            self.lbl_msg.setStyleSheet(f"color:{_VERDE};font-size:11px;font-family:'{_FONT}';")
            self._reconstruir_formulario()
            self._actualizar_preview()
        else:
            motivos = {
                "sin_api_key": tr("tema.ia_sin_key", default="El asistente IA no está configurado en este equipo."),
                "sin_contexto": tr("tema.ia_sin_ctx", default="Ponle primero un nombre a la tienda."),
                "limite_ia": tr("tema.ia_limite", default="Se alcanzó el límite de uso de IA de la empresa."),
            }
            self.lbl_msg.setText(motivos.get(r.get("motivo"),
                                 tr("tema.ia_error", default="No se pudo generar el texto ahora mismo.")))
            self.lbl_msg.setStyleSheet(f"color:{_ROJO};font-size:11px;font-family:'{_FONT}';")

    # ── Vista previa en vivo ──────────────────────────────────────────────────
    def _cambiar_dispositivo(self, disp):
        self._dispositivo = disp
        if self.preview is None:
            return
        if disp == "movil":
            self.preview.setFixedWidth(390)
            self.preview.setMinimumHeight(720)
            if self._marco_telefono is not None:
                self._marco_telefono.setStyleSheet(
                    "QFrame#marcoTelefono{background:#0D0F12;border:10px solid #0D0F12;"
                    "border-radius:36px;}")
                self._muesca_telefono.setVisible(True)
                self._muesca_telefono.move((410 - 120) // 2, 6)
        else:
            self.preview.setMinimumWidth(0)
            self.preview.setMaximumWidth(16777215)
            self.preview.setMinimumHeight(560)
            if self._marco_telefono is not None:
                self._marco_telefono.setStyleSheet(
                    "QFrame#marcoTelefono{background:transparent;border:none;}")
                self._muesca_telefono.setVisible(False)

    def _actualizar_preview(self):
        if self.preview is None:
            return
        try:
            from src.backend.storefront_bloques import renderizar_home_con_tema
            html = renderizar_home_con_tema(self._eid, self._cfg, {"secciones": self._secciones})
        except Exception as e:
            html = f"<body style='background:#0E1117;color:#F85149;font-family:sans-serif;padding:20px'>Error generando la vista previa: {e}</body>"
        self.preview.setHtml(html)
        if self._dispositivo == "movil":
            self.preview.setFixedWidth(390)
        self.preview.setMinimumHeight(560)
