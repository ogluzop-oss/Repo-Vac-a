"""
Videovigilancia — GUI (CamarasWindow). SOLO consume `src.services.camaras` (sin lógica de negocio).

Sidebar (departamento + cámaras con nombre editable + añadir/eliminar) · rejilla 3×3 con directo ·
reproductor a pantalla completa con línea de tiempo (hora al pasar el cursor), pausa/±10 s, descarga de
clip y filtro por fecha. Estilo global (COLOR_CIAN, botones redondeados, hover swap).
"""

import datetime as _dt
import logging
import os

from PyQt6.QtCore import Qt, QTimer, QTime
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView, QComboBox, QDateEdit, QDialog, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QSlider, QStackedWidget,
    QVBoxLayout, QWidget,
)

from src.services import camaras as _cam

try:
    from assets.estilo_global import mostrar_mensaje
except Exception:  # pragma: no cover
    mostrar_mensaje = None

logger = logging.getLogger("gui.camaras")

_BG = "#0E1117"; _BG2 = "#161B22"; _CIAN = "#00FFC6"; _BORDE = "#30363D"; _TEXT = "#E6EDF3"
_DIM = "#8B949E"; _ROJO = "#F85149"


def _btn(txt, cb, *, primary=False, rojo=False):
    b = QPushButton(txt); b.setCursor(Qt.CursorShape.PointingHandCursor); b.setFixedHeight(38)
    col = _ROJO if rojo else _CIAN
    if primary:
        b.setStyleSheet(f"QPushButton{{background:{col};color:{_BG};border:none;border-radius:10px;"
                        "font-weight:900;padding:6px 16px;}"
                        f"QPushButton:hover{{background:{_BG};color:{col};border:2px solid {col};}}")
    else:
        b.setStyleSheet(f"QPushButton{{background:transparent;color:{col};border:2px solid {col};"
                        "border-radius:10px;font-weight:900;padding:6px 16px;}"
                        f"QPushButton:hover{{background:{col};color:{_BG};}}")
    b.clicked.connect(cb); return b


class _PedirTextoDialog(QDialog):
    """Diálogo de entrada de texto propio (sustituye a QInputDialog): SIN barra negra de Windows, esquinas
    redondeadas con contorno neón y botones con texto visible + hover swap."""

    def __init__(self, titulo, prompt, texto="", parent=None):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setMinimumWidth(440)
        self.setStyleSheet(f"QDialog{{background:{_BG};border:2px solid {_CIAN};border-radius:14px;}}"
                           f"QLabel{{color:{_TEXT};background:transparent;border:none;}}")
        self._drag = None
        ly = QVBoxLayout(self); ly.setContentsMargins(20, 18, 20, 18); ly.setSpacing(12)
        t = QLabel(titulo)
        t.setStyleSheet(f"color:{_CIAN};font-weight:900;font-size:16px;background:transparent;border:none;")
        ly.addWidget(t)
        lp = QLabel(prompt); lp.setStyleSheet(f"color:{_TEXT};font-weight:700;background:transparent;border:none;")
        ly.addWidget(lp)
        self.inp = QLineEdit(texto); self.inp.setFixedHeight(38)
        self.inp.setStyleSheet(f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_CIAN};"
                               "border-radius:10px;padding:6px 12px;font-size:13px;}")
        self.inp.returnPressed.connect(self.accept)
        ly.addWidget(self.inp)
        fila = QHBoxLayout(); fila.setSpacing(10)
        fila.addWidget(_btn("Aceptar", self.accept, primary=True))
        fila.addWidget(_btn("Cancelar", self.reject))
        ly.addLayout(fila)
        self.inp.setFocus()

    # Arrastre (ventana sin marco, sin barra de título de Windows).
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft(); e.accept()

    def mouseMoveEvent(self, e):
        if self._drag is not None and (e.buttons() & Qt.MouseButton.LeftButton):
            self.move(e.globalPosition().toPoint() - self._drag); e.accept()

    def mouseReleaseEvent(self, e):
        self._drag = None; super().mouseReleaseEvent(e)

    def valor(self):
        return self.inp.text()


def _pedir_texto(parent, titulo, prompt, texto=""):
    """Reemplazo de `QInputDialog.getText` con el estilo de la app. Devuelve (texto, ok)."""
    d = _PedirTextoDialog(titulo, prompt, texto, parent)
    ok = d.exec() == QDialog.DialogCode.Accepted
    return d.valor(), ok


def _preview(nombre, w=280, h=200, en_vivo=True):
    """Genera una previsualización (QPainter) con nombre + reloj + punto REC (feed simulado)."""
    pm = QPixmap(w, h); pm.fill(QColor("#12141a"))
    p = QPainter(pm)
    p.setPen(QColor(_DIM)); p.setFont(QFont("Segoe UI", 9))
    p.drawText(10, h - 14, nombre or "Cámara")
    p.setPen(QColor(_CIAN)); p.setFont(QFont("Segoe UI", 8))
    p.drawText(10, 22, _dt.datetime.now().strftime("%d/%m/%Y  %H:%M:%S"))
    if en_vivo:
        p.setBrush(QColor("#F0403A")); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(w - 26, 12, 10, 10)
        p.setPen(QColor("#F0403A")); p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.drawText(w - 60, 22, "REC")
    p.end()
    return pm


class _TimelineSlider(QSlider):
    """Barra de línea de tiempo: al pasar el cursor muestra la hora:minuto correspondiente."""
    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setMouseTracking(True)
        self.setRange(0, 1000)
        self.setStyleSheet(
            f"QSlider::groove:horizontal{{height:8px;background:{_BG2};border-radius:4px;}}"
            f"QSlider::sub-page:horizontal{{background:{_CIAN};border-radius:4px;}}"
            f"QSlider::handle:horizontal{{background:{_CIAN};width:12px;margin:-4px 0;border-radius:6px;}}")

    def mouseMoveEvent(self, ev):
        frac = ev.position().x() / max(1, self.width())
        frac = min(1.0, max(0.0, frac))
        segundos_dia = int(frac * 24 * 3600)
        hh, mm = segundos_dia // 3600, (segundos_dia % 3600) // 60
        self.setToolTip(f"{hh:02d}:{mm:02d}")
        super().mouseMoveEvent(ev)


class CamarasWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.main = main
        self._camaras = []
        self._pagina = 0
        self._cam_sel = None
        self.setStyleSheet(f"background:{_BG};")
        self._player = None
        self._clip_ini = None
        self._build()
        self._cargar_departamentos()

    # ── Contexto ─────────────────────────────────────────────────────────────
    def _id_empresa(self):
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return None

    def _es_super(self):
        return str(self.usuario.get("perfil", "")).upper() == "SUPERADMIN"

    def _dep(self):
        return self.cb_dep.currentData()

    # ── UI ───────────────────────────────────────────────────────────────────
    def _build(self):
        root = QHBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        root.addWidget(self._sidebar())
        self.stack = QStackedWidget()
        self.stack.addWidget(self._pagina_rejilla())     # 0
        self.stack.addWidget(self._pagina_reproductor())  # 1
        cont = QWidget(); cl = QVBoxLayout(cont); cl.setContentsMargins(18, 16, 18, 16)
        cab = QHBoxLayout()
        tit = QLabel("📹  VIDEOVIGILANCIA")
        tit.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:20px;")
        cab.addWidget(tit); cab.addStretch()
        if self._volver:
            cab.addWidget(_btn("✕", self._volver, rojo=True))
        cl.addLayout(cab); cl.addWidget(self.stack, 1)
        root.addWidget(cont, 1)

    def _sidebar(self):
        w = QFrame(); w.setFixedWidth(280); w.setStyleSheet(f"background:{_BG2};")
        ly = QVBoxLayout(w); ly.setContentsMargins(14, 18, 14, 14); ly.setSpacing(10)
        t = QLabel("CÁMARAS"); t.setStyleSheet(f"color:{_TEXT};font-weight:900;letter-spacing:2px;")
        ly.addWidget(t)
        self.cb_dep = QComboBox()
        self.cb_dep.setStyleSheet(f"QComboBox{{background:{_BG};color:{_TEXT};border:1px solid {_BORDE};"
                                  "border-radius:8px;padding:6px 10px;}")
        self.cb_dep.currentIndexChanged.connect(lambda _=0: self._cargar_camaras())
        ly.addWidget(self.cb_dep)
        self.lst = QListWidget()
        self.lst.setStyleSheet(f"QListWidget{{background:{_BG};color:{_TEXT};border:1px solid {_BORDE};"
                               "border-radius:8px;font-size:13px;}"
                               f"QListWidget::item{{padding:8px;}}"
                               f"QListWidget::item:selected{{background:rgba(0,255,198,0.15);color:{_CIAN};}}")
        self.lst.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.lst.itemDoubleClicked.connect(self._renombrar)
        self.lst.itemClicked.connect(lambda it: self._abrir_reproductor(it.data(Qt.ItemDataRole.UserRole)))
        ly.addWidget(self.lst, 1)
        fila = QHBoxLayout()
        fila.addWidget(_btn("＋ Añadir", self._anadir, primary=True))
        fila.addWidget(_btn("🗑 Eliminar", self._eliminar, rojo=True))
        ly.addLayout(fila)
        # Sin botón "Salir al menú" en el sidebar: la X roja de la cabecera ya vuelve al menú.
        return w

    # ── Rejilla 3×3 ──────────────────────────────────────────────────────────
    def _pagina_rejilla(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(8)
        self.grid_host = QWidget(); self.grid = QGridLayout(self.grid_host)
        self.grid.setSpacing(8)
        ly.addWidget(self.grid_host, 1)
        nav = QHBoxLayout(); nav.addStretch()
        self.btn_prev = _btn("◀", lambda: self._cambiar_pagina(-1))
        self.btn_next = _btn("▶", lambda: self._cambiar_pagina(1))
        self.lbl_pag = QLabel(""); self.lbl_pag.setStyleSheet(f"color:{_DIM};")
        nav.addWidget(self.btn_prev); nav.addWidget(self.lbl_pag); nav.addWidget(self.btn_next)
        nav.addStretch(); ly.addLayout(nav)
        self._tiles = []
        self._timer = QTimer(self); self._timer.setInterval(1000)
        self._timer.timeout.connect(self._refrescar_directo); self._timer.start()
        return w

    def _cambiar_pagina(self, d):
        total = max(1, (len(self._camaras) + 8) // 9)
        self._pagina = max(0, min(total - 1, self._pagina + d))
        self._pintar_rejilla()

    def _pintar_rejilla(self):
        while self.grid.count():
            it = self.grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self._tiles = []
        pag = self._camaras[self._pagina * 9:(self._pagina + 1) * 9]
        for i, cam in enumerate(pag):
            tile = QFrame(); tile.setStyleSheet(f"background:{_BG2};border:1px solid {_BORDE};"
                                                "border-radius:10px;")
            tl = QVBoxLayout(tile); tl.setContentsMargins(6, 6, 6, 6)
            lbl = QLabel(); lbl.setPixmap(_preview(cam.get("nombre")))
            lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            lbl.mousePressEvent = lambda _e, c=cam: self._abrir_reproductor(c.get("id"))
            tl.addWidget(lbl)
            self._tiles.append((lbl, cam))
            self.grid.addWidget(tile, i // 3, i % 3)
        total = max(1, (len(self._camaras) + 8) // 9)
        self.lbl_pag.setText(f"Página {self._pagina + 1}/{total}")

    def _refrescar_directo(self):
        for lbl, cam in getattr(self, "_tiles", []):
            try:
                lbl.setPixmap(_preview(cam.get("nombre")))
            except Exception:
                pass

    # ── Datos ────────────────────────────────────────────────────────────────
    def _cargar_departamentos(self):
        self.cb_dep.blockSignals(True); self.cb_dep.clear()
        deps = _cam.departamentos(self._id_empresa()) or []
        if not deps:
            deps = [{"id_centro": "1", "nombre": "Central", "tipo_centro": "centro"}]
        for d in deps:
            self.cb_dep.addItem(f"{d['nombre']} ({d['tipo_centro']})", d)
        self.cb_dep.blockSignals(False)
        self._cargar_camaras()

    def _cargar_camaras(self):
        dep = self._dep()
        if not dep:
            self._camaras = []
        else:
            self._camaras = _cam.listar_camaras(self._id_empresa(), dep["id_centro"])
        self.lst.clear()
        for c in self._camaras:
            it = QListWidgetItem("🎥  " + (c.get("nombre") or "Cámara"))
            it.setData(Qt.ItemDataRole.UserRole, c.get("id"))
            self.lst.addItem(it)
        self._pagina = 0
        self._pintar_rejilla()

    def _anadir(self):
        dep = self._dep()
        if not dep:
            return
        nombre, ok = _pedir_texto(self, "Añadir cámara", "Nombre de la cámara:")
        if not ok or not nombre.strip():
            return
        fuente, ok2 = _pedir_texto(self, "Fuente", "URL RTSP/ONVIF (vacío = simulado):")
        _cam.crear_camara(nombre.strip(), id_empresa=self._id_empresa(), id_centro=dep["id_centro"],
                          tipo_centro=dep["tipo_centro"], fuente=(fuente.strip() or "simulado"))
        self._cargar_camaras()

    def _eliminar(self):
        it = self.lst.currentItem()
        if not it:
            return
        _cam.eliminar_camara(it.data(Qt.ItemDataRole.UserRole), id_empresa=self._id_empresa())
        self._cargar_camaras()

    def _renombrar(self, it):
        cid = it.data(Qt.ItemDataRole.UserRole)
        nombre, ok = _pedir_texto(self, "Renombrar cámara", "Nuevo nombre:",
                                  texto=it.text().replace("🎥  ", ""))
        if ok and nombre.strip():
            _cam.renombrar_camara(cid, nombre.strip(), id_empresa=self._id_empresa())
            self._cargar_camaras()

    # ── Reproductor ──────────────────────────────────────────────────────────
    def _pagina_reproductor(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(8)
        top = QHBoxLayout()
        top.addWidget(_btn("◀ Volver", lambda: self.stack.setCurrentIndex(0)))
        self.lbl_cam = QLabel(""); self.lbl_cam.setStyleSheet(f"color:{_CIAN};font-weight:900;")
        top.addWidget(self.lbl_cam); top.addStretch()
        top.addWidget(QLabel("Fecha:"))
        self.fecha = QDateEdit(); self.fecha.setCalendarPopup(True)
        self.fecha.setDate(_dt.date.today())
        self.fecha.setStyleSheet(f"QDateEdit{{background:{_BG2};color:{_TEXT};border:1px solid {_BORDE};"
                                 "border-radius:8px;padding:4px 8px;}")
        self.fecha.dateChanged.connect(lambda _=0: self._cargar_video())
        top.addWidget(self.fecha)
        ly.addLayout(top)
        # Zona central: vídeo + panel de EVENTOS DE MOVIMIENTO (detección real, aislada por depto).
        mid = QHBoxLayout(); mid.setSpacing(10)
        self.video_host = QWidget(); self.video_host.setStyleSheet(f"background:#000;border-radius:10px;")
        vh = QVBoxLayout(self.video_host); vh.setContentsMargins(0, 0, 0, 0)
        self._video_ph = QLabel("Selecciona una cámara"); self._video_ph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._video_ph.setStyleSheet(f"color:{_DIM};")
        vh.addWidget(self._video_ph)
        mid.addWidget(self.video_host, 1)
        mid.addWidget(self._panel_eventos())
        ly.addLayout(mid, 1)
        self.tl = _TimelineSlider(); self.tl.sliderReleased.connect(self._seek_slider)
        ly.addWidget(self.tl)
        ly.addLayout(self._panel_ptz())
        ctr = QHBoxLayout()
        ctr.addWidget(_btn("⏪ -10s", lambda: self._saltar(-10000)))
        self.btn_play = _btn("⏸ Pausa", self._toggle_play, primary=True)
        ctr.addWidget(self.btn_play)
        ctr.addWidget(_btn("+10s ⏩", lambda: self._saltar(10000)))
        ctr.addStretch()
        ctr.addWidget(_btn("⧉ Marcar inicio clip", self._marcar_clip))
        ctr.addWidget(_btn("⬇ Descargar clip", self._descargar_clip, primary=True))
        ly.addLayout(ctr)
        return w

    # ── Panel de eventos de movimiento (detección real) ──────────────────────
    def _panel_eventos(self):
        w = QFrame(); w.setFixedWidth(220)
        w.setStyleSheet(f"background:{_BG2};border:1px solid {_BORDE};border-radius:10px;")
        ly = QVBoxLayout(w); ly.setContentsMargins(10, 10, 10, 10); ly.setSpacing(8)
        t = QLabel("⚡ MOVIMIENTO"); t.setStyleSheet(f"color:{_CIAN};font-weight:900;letter-spacing:1px;")
        ly.addWidget(t)
        self.lst_ev = QListWidget()
        self.lst_ev.setStyleSheet(f"QListWidget{{background:{_BG};color:{_TEXT};border:1px solid {_BORDE};"
                                  "border-radius:8px;font-size:12px;}"
                                  f"QListWidget::item{{padding:6px;}}"
                                  f"QListWidget::item:selected{{background:rgba(0,255,198,0.15);color:{_CIAN};}}")
        self.lst_ev.itemClicked.connect(self._ir_a_evento)
        ly.addWidget(self.lst_ev, 1)
        self.lbl_ev = QLabel("—"); self.lbl_ev.setStyleSheet(f"color:{_DIM};font-size:11px;")
        ly.addWidget(self.lbl_ev)
        return w

    def _cargar_eventos(self):
        self.lst_ev.clear()
        if not self._cam_sel:
            self.lbl_ev.setText("—"); return
        fecha = self.fecha.date().toString("yyyy-MM-dd")
        try:
            evs = _cam.listar_eventos(self._id_empresa(), self._cam_sel.get("id_centro"),
                                      id_camara=self._cam_sel.get("id"),
                                      desde=f"{fecha} 00:00:00", hasta=f"{fecha} 23:59:59")
        except Exception as e:
            logger.debug("cargar eventos: %s", e); evs = []
        for ev in evs:
            hora = str(ev.get("instante"))[11:19] or "--:--:--"
            pct = int(round(float(ev.get("score") or 0) * 100))
            it = QListWidgetItem(f"🔴  {hora}   ·   {pct}%")
            it.setData(Qt.ItemDataRole.UserRole, str(ev.get("instante")))
            self.lst_ev.addItem(it)
        self.lbl_ev.setText(f"{len(evs)} evento(s)" if evs else "Sin movimiento")

    def _ir_a_evento(self, it):
        """Salta el reproductor al instante del evento (mismo criterio de 24 h que la línea de tiempo)."""
        inst = it.data(Qt.ItemDataRole.UserRole) or ""
        try:
            hh, mm, ss = (int(x) for x in inst[11:19].split(":"))
        except Exception:
            return
        seg_dia = hh * 3600 + mm * 60 + ss
        if self._player and getattr(self, "_dur", 0):
            self._player.setPosition(int(min(1.0, seg_dia / 86400.0) * self._dur))

    # ── Panel PTZ (control ONVIF, degradable) ─────────────────────────────────
    def _panel_ptz(self):
        fila = QHBoxLayout(); fila.setSpacing(6)
        self._ptz_btns = []
        for txt, direccion in (("⟲", "izquierda"), ("▲", "arriba"), ("▼", "abajo"), ("⟳", "derecha"),
                               ("＋", "zoom_in"), ("－", "zoom_out")):
            b = _btn(txt, lambda _c=False, d=direccion: self._ptz(d)); b.setFixedWidth(48)
            self._ptz_btns.append(b); fila.addWidget(b)
        self.lbl_ptz = QLabel("PTZ"); self.lbl_ptz.setStyleSheet(f"color:{_DIM};font-size:12px;")
        fila.addWidget(self.lbl_ptz); fila.addStretch()
        return fila

    def _cargar_ptz(self):
        try:
            hay = bool(_cam.ptz_disponible())
        except Exception:
            hay = False
        for b in getattr(self, "_ptz_btns", []):
            b.setEnabled(hay)
        if hay:
            self.lbl_ptz.setText("PTZ ONVIF activo")
            self.lbl_ptz.setStyleSheet(f"color:{_CIAN};font-size:12px;font-weight:700;")
        else:
            self.lbl_ptz.setText("PTZ/ONVIF no disponible (requiere cámara ONVIF + onvif-zeep)")
            self.lbl_ptz.setStyleSheet(f"color:{_DIM};font-size:12px;")

    def _ptz(self, direccion):
        if not self._cam_sel:
            return
        try:
            r = _cam.ptz_mover(self._cam_sel, direccion) or {}
        except Exception as e:
            r = {"ok": False, "motivo": str(e)}
        if not r.get("ok") and mostrar_mensaje:
            mostrar_mensaje(self, "PTZ", r.get("motivo") or "Movimiento no disponible", "warning")

    def _abrir_reproductor(self, id_camara):
        if not id_camara:
            return
        self._cam_sel = _cam.obtener_camara(id_camara, id_empresa=self._id_empresa(),
                                            permitir_super=self._es_super())
        if not self._cam_sel:
            return
        self.lbl_cam.setText("🎥  " + (self._cam_sel.get("nombre") or "Cámara"))
        self.fecha.setDate(_dt.date.today())
        self.stack.setCurrentIndex(1)
        self._cargar_ptz()
        self._cargar_video()

    def _cargar_video(self):
        if not self._cam_sel:
            return
        self._cargar_eventos()
        fecha = self.fecha.date().toString("yyyy-MM-dd")
        grab = _cam.grabacion_de(self._cam_sel["id"], fecha, id_empresa=self._id_empresa(),
                                 permitir_super=self._es_super())
        ruta = grab.get("ruta") if grab else None
        if not ruta or not os.path.exists(ruta):
            self._video_ph.setText(f"Sin grabación para {fecha}")
            return
        try:
            from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
            from PyQt6.QtMultimediaWidgets import QVideoWidget
            from PyQt6.QtCore import QUrl
            if self._player is None:
                self._vw = QVideoWidget()
                self.video_host.layout().addWidget(self._vw)
                self._video_ph.hide()
                self._player = QMediaPlayer(); self._audio = QAudioOutput()
                self._player.setAudioOutput(self._audio)
                self._player.setVideoOutput(self._vw)
                self._player.positionChanged.connect(self._on_pos)
                self._player.durationChanged.connect(self._on_dur)
            self._player.setSource(QUrl.fromLocalFile(os.path.abspath(ruta)))
            self._player.play()
            self.btn_play.setText("⏸ Pausa")
        except Exception as e:
            logger.debug("reproductor: %s", e)
            self._video_ph.setText("Reproductor no disponible en este entorno")

    def _on_dur(self, dur):
        self._dur = max(1, dur)

    def _on_pos(self, pos):
        if getattr(self, "_dur", 0):
            self.tl.blockSignals(True)
            self.tl.setValue(int(1000 * pos / self._dur)); self.tl.blockSignals(False)

    def _seek_slider(self):
        if self._player and getattr(self, "_dur", 0):
            self._player.setPosition(int(self.tl.value() / 1000 * self._dur))

    def _saltar(self, ms):
        if self._player:
            self._player.setPosition(max(0, self._player.position() + ms))

    def _toggle_play(self):
        if not self._player:
            return
        from PyQt6.QtMultimedia import QMediaPlayer
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause(); self.btn_play.setText("▶ Reanudar")
        else:
            self._player.play(); self.btn_play.setText("⏸ Pausa")

    def _marcar_clip(self):
        if self._player and getattr(self, "_dur", 0):
            self._clip_ini = self._player.position() / 1000.0
            if mostrar_mensaje:
                mostrar_mensaje(self, "Clip", f"Inicio marcado en {int(self._clip_ini)} s. Ahora "
                                "avanza y pulsa 'Descargar clip'.", "info")

    def _descargar_clip(self):
        if not self._cam_sel or self._clip_ini is None or not self._player:
            if mostrar_mensaje:
                mostrar_mensaje(self, "Clip", "Marca primero el inicio del clip.", "warning")
            return
        fin = self._player.position() / 1000.0
        fecha = self.fecha.date().toString("yyyy-MM-dd")
        ruta = _cam.extraer_clip(self._cam_sel["id"], fecha, inicio_seg=min(self._clip_ini, fin),
                                 fin_seg=max(self._clip_ini, fin), id_empresa=self._id_empresa(),
                                 permitir_super=self._es_super())
        if mostrar_mensaje:
            mostrar_mensaje(self, "Clip", f"Clip guardado en Documentos: {os.path.basename(ruta)}"
                            if ruta else "No se pudo generar el clip.", "info" if ruta else "error")
        self._clip_ini = None
