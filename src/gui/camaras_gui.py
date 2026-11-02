"""
Videovigilancia — GUI (CamarasWindow). SOLO consume `src.services.camaras` (sin lógica de negocio).

Sidebar (departamento + cámaras con nombre editable + añadir/eliminar) · rejilla 3×3 con directo ·
reproductor a pantalla completa con línea de tiempo (hora al pasar el cursor), pausa/±10 s, descarga de
clip y filtro por fecha. Estilo global (COLOR_CIAN, botones redondeados, hover swap).
"""

import datetime as _dt
import logging
import os

from PyQt6.QtCore import QObject, QTimer, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView, QComboBox, QDateEdit, QDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QProgressBar, QPushButton,
    QSlider, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from src.gui.catalogo_gestion import centrar_en_pantalla
from src.gui.transiciones import StackedActual
from src.services import autorizacion
from src.services import camaras as _cam

try:
    from assets.estilo_global import _ARROW_ICON, mostrar_mensaje
except Exception:  # pragma: no cover
    mostrar_mensaje = None
    _ARROW_ICON = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "assets", "combo_arrow.png",
    ).replace("\\", "/")

logger = logging.getLogger("gui.camaras")

_BG = "#0E1117"; _BG2 = "#161B22"; _CIAN = "#00FFC6"; _BORDE = "#30363D"; _TEXT = "#E6EDF3"
_DIM = "#8B949E"; _ROJO = "#F85149"; _AMBAR = "#FFB020"


def _btn(txt, cb, *, primary=False, rojo=False):
    b = QPushButton(txt); b.setCursor(Qt.CursorShape.PointingHandCursor); b.setFixedHeight(38)
    col = _ROJO if rojo else _CIAN
    if primary:
        b.setStyleSheet(f"QPushButton{{background:{_BG};color:{col};border:2px solid {col};border-radius:10px;"
                        "font-weight:900;padding:6px 16px;}"
                        f"QPushButton:hover{{background:{col};color:{_BG};}}")
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
        QTimer.singleShot(0, lambda: centrar_en_pantalla(self))
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


class _HiloTarea(QThread):
    """Ejecuta `fn(*args, **kwargs)` en un hilo secundario y emite el resultado (o la excepción, si
    la hubo) por señal — evita bloquear la UI en descubrimiento/pruebas de conexión ONVIF, que pueden
    tardar varios segundos. Reutilizable para cualquier llamada de red de este módulo."""
    resultado = pyqtSignal(object)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn, self._args, self._kwargs = fn, args, kwargs

    def run(self):
        try:
            r = self._fn(*self._args, **self._kwargs)
        except Exception as e:  # nunca deja el hilo "colgado" sin resultado
            r = e
        self.resultado.emit(r)


class CamaraLiveWorker(QObject):
    """Decodificación en vivo de una fuente (RTSP/ONVIF) en un hilo secundario — mismo patrón que
    `src/utils/rfid_worker.py` (QObject + moveToThread, nunca toca widgets desde aquí, solo emite
    señales). Honesto: si la fuente cae, emite 'sin_senal' con el motivo real en vez de congelar el
    último fotograma o inventar imagen."""
    frame_listo = pyqtSignal(QImage)
    sin_senal = pyqtSignal(str)

    def __init__(self, fuente, *, fps=6, reintento_seg=5):
        super().__init__()
        self._fuente = fuente
        self._periodo = 1.0 / max(1, fps)
        self._reintento_seg = reintento_seg
        self._activo = False

    def detener(self):
        self._activo = False

    def run(self):
        import time
        try:
            import cv2
        except Exception:
            self.sin_senal.emit("OpenCV no disponible")
            return
        self._activo = True
        cap = None
        ultimo_intento = 0.0
        while self._activo:
            if cap is None:
                ahora = time.time()
                if ultimo_intento and (ahora - ultimo_intento) < self._reintento_seg:
                    time.sleep(0.2)
                    continue
                ultimo_intento = ahora
                try:
                    cap = cv2.VideoCapture(self._fuente)
                    try:
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)   # mejor esfuerzo: menor latencia
                    except Exception:
                        pass
                    if not cap.isOpened():
                        cap.release(); cap = None
                except Exception:
                    cap = None
                if cap is None:
                    self.sin_senal.emit("Conectando…")
                    continue
            ok, frame = cap.read()
            if not ok or frame is None:
                self.sin_senal.emit("SIN SEÑAL")
                try:
                    cap.release()
                except Exception:
                    pass
                cap = None
                continue
            try:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                img = QImage(rgb.tobytes(), w, h, ch * w, QImage.Format.Format_RGB888)
                self.frame_listo.emit(img)
            except Exception:
                pass
            time.sleep(self._periodo)
        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass


def _iniciar_worker(fuente, *, fps=6):
    """Crea un CamaraLiveWorker + su QThread, ya arrancado (mismo cableado que RFIDWorker en
    main.py: moveToThread → started.connect(run) → start()). Devuelve (worker, hilo)."""
    worker = CamaraLiveWorker(fuente, fps=fps)
    hilo = QThread()
    worker.moveToThread(hilo)
    hilo.started.connect(worker.run)
    hilo.start()
    return worker, hilo


def _detener_worker(par):
    """Para y libera (worker, hilo) de forma ordenada, tolerante a None."""
    if not par:
        return
    worker, hilo = par
    try:
        worker.detener()
    except Exception:
        pass
    try:
        hilo.quit()
        hilo.wait(1500)
    except Exception:
        pass


class _AltaManualDialog(QDialog):
    """Alta manual (fallback) — formulario claro con campos separados, en vez de diálogos de texto
    encadenados. 'Probar conexión' es opcional: informa si ONVIF funciona (y por tanto habrá
    perfiles main/sub), pero 'Guardar' funciona igual sin haberla pulsado (RTSP crudo, como el alta
    de siempre) — nunca bloquea el fallback total."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Añadir cámara manualmente")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setMinimumWidth(460)
        QTimer.singleShot(0, lambda: centrar_en_pantalla(self))
        self.setStyleSheet(f"QDialog{{background:{_BG};border:2px solid {_CIAN};border-radius:14px;}}"
                           f"QLabel{{color:{_TEXT};background:transparent;border:none;}}")
        self._drag = None
        self._hilo = None
        ly = QVBoxLayout(self); ly.setContentsMargins(20, 18, 20, 18); ly.setSpacing(10)
        cab = QHBoxLayout()
        t = QLabel("Añadir cámara manualmente")
        t.setStyleSheet(f"color:{_CIAN};font-weight:900;font-size:16px;background:transparent;border:none;")
        cab.addWidget(t); cab.addStretch()
        from src.gui.catalogo_gestion import _btn_x
        cab.addWidget(_btn_x(self.reject))
        ly.addLayout(cab)

        def _campo(label, texto=""):
            ly.addWidget(QLabel(label))
            inp = QLineEdit(texto); inp.setFixedHeight(36)
            inp.setStyleSheet(f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
                              "border-radius:8px;padding:4px 10px;font-size:13px;}"
                              f"QLineEdit:focus{{border-color:{_CIAN};}}")
            ly.addWidget(inp)
            return inp

        self.in_nombre = _campo("Nombre")
        self.in_ip = _campo("Dirección IP")
        fila_p = QHBoxLayout()
        col1 = QVBoxLayout(); col1.addWidget(QLabel("Puerto ONVIF"))
        self.in_puerto_onvif = QLineEdit("80"); self.in_puerto_onvif.setFixedHeight(36)
        col1.addWidget(self.in_puerto_onvif)
        col2 = QVBoxLayout(); col2.addWidget(QLabel("Puerto RTSP"))
        self.in_puerto_rtsp = QLineEdit("554"); self.in_puerto_rtsp.setFixedHeight(36)
        col2.addWidget(self.in_puerto_rtsp)
        for w in (self.in_puerto_onvif, self.in_puerto_rtsp):
            w.setStyleSheet(f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
                            "border-radius:8px;padding:4px 10px;font-size:13px;}")
        fila_p.addLayout(col1); fila_p.addLayout(col2)
        ly.addLayout(fila_p)
        self.in_usuario = _campo("Usuario")
        self.in_pass = _campo("Contraseña")
        self.in_pass.setEchoMode(QLineEdit.EchoMode.Password)

        self.lbl_estado = QLabel("—"); self.lbl_estado.setStyleSheet(f"color:{_DIM};font-size:12px;")
        self.lbl_estado.setWordWrap(True)
        ly.addWidget(self.lbl_estado)

        fila = QHBoxLayout(); fila.setSpacing(10)
        self.btn_probar = _btn("🔎 Probar conexión y extraer streams", self._probar)
        fila.addWidget(self.btn_probar)
        ly.addLayout(fila)

        fila2 = QHBoxLayout(); fila2.setSpacing(10)
        fila2.addWidget(_btn("Guardar", self.accept))
        ly.addLayout(fila2)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft(); e.accept()

    def mouseMoveEvent(self, e):
        if self._drag is not None and (e.buttons() & Qt.MouseButton.LeftButton):
            self.move(e.globalPosition().toPoint() - self._drag); e.accept()

    def mouseReleaseEvent(self, e):
        self._drag = None; super().mouseReleaseEvent(e)

    def closeEvent(self, e):
        if self._hilo is not None and self._hilo.isRunning():
            self._hilo.wait(2000)
        super().closeEvent(e)

    def _probar(self):
        ip = self.in_ip.text().strip()
        if not ip:
            self.lbl_estado.setText("Indica la dirección IP antes de probar."); return
        try:
            puerto = int(self.in_puerto_onvif.text().strip() or 80)
        except ValueError:
            puerto = 80
        self.btn_probar.setEnabled(False)
        self.lbl_estado.setStyleSheet(f"color:{_DIM};font-size:12px;")
        self.lbl_estado.setText("Probando conexión…")
        self._hilo = _HiloTarea(_cam.onvif_probar_conexion, ip, self.in_usuario.text(),
                                self.in_pass.text(), puerto_onvif=puerto)
        self._hilo.resultado.connect(self._on_resultado_prueba)
        self._hilo.start()

    def _on_resultado_prueba(self, r):
        self.btn_probar.setEnabled(True)
        if isinstance(r, Exception) or not isinstance(r, dict):
            self.lbl_estado.setStyleSheet(f"color:{_ROJO};font-size:12px;")
            self.lbl_estado.setText(f"Error al probar: {r}")
            return
        if r.get("ok"):
            fab = r.get("fabricante") or "desconocido"
            self.lbl_estado.setStyleSheet(f"color:{_CIAN};font-size:12px;")
            self.lbl_estado.setText(f"✅ Conexión ONVIF correcta ({fab}). Se extraerán los streams "
                                    "main/sub al guardar.")
        else:
            self.lbl_estado.setStyleSheet(f"color:{_AMBAR};font-size:12px;")
            self.lbl_estado.setText(f"⚠ {r.get('motivo') or 'No se pudo conectar por ONVIF'} — puedes "
                                    "guardar igualmente con conexión RTSP directa.")

    def datos(self) -> dict:
        try:
            p_onvif = int(self.in_puerto_onvif.text().strip() or 80)
        except ValueError:
            p_onvif = 80
        try:
            p_rtsp = int(self.in_puerto_rtsp.text().strip() or 554)
        except ValueError:
            p_rtsp = 554
        return {"nombre": self.in_nombre.text().strip(), "host": self.in_ip.text().strip(),
                "usuario": self.in_usuario.text(), "contrasena": self.in_pass.text(),
                "puerto_onvif": p_onvif, "puerto_rtsp": p_rtsp}


class _AltaCamaraWizard(QDialog):
    """Asistente de alta rápida: Buscar (WS-Discovery) → Credenciales maestras → Confirmar. Mismo
    espíritu de navegación que `gui/onboarding_wizard.py`/`gui/calculadora_fiscal_wizard.py`
    (QStackedWidget + barra Atrás/Siguiente), con los widgets propios de este fichero (sin importar
    el Enterprise Shell aquí: este módulo nunca lo usó)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Añadir cámaras")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setMinimumSize(560, 480)
        QTimer.singleShot(0, lambda: centrar_en_pantalla(self))
        self.setStyleSheet(f"QDialog{{background:{_BG};border:2px solid {_CIAN};border-radius:14px;}}"
                           f"QLabel{{color:{_TEXT};background:transparent;border:none;}}")
        self._drag = None
        self._hilo = None
        self._encontradas = []          # [{'ip','xaddr','uuid','fabricante'}, ...]
        self._seleccion = []            # subconjunto marcado en el paso 1
        self._resultado_pruebas = {}    # ip -> {'ok','motivo','fabricante'}
        self.abrir_manual = False       # el llamador comprueba esto tras exec() == Rejected

        root = QVBoxLayout(self); root.setContentsMargins(20, 18, 20, 18); root.setSpacing(12)
        cab = QHBoxLayout()
        t = QLabel("🔍 Añadir cámaras")
        t.setStyleSheet(f"color:{_CIAN};font-weight:900;font-size:16px;")
        cab.addWidget(t); cab.addStretch()
        self.lbl_paso = QLabel("Paso 1/3 — Buscar"); self.lbl_paso.setStyleSheet(f"color:{_DIM};")
        cab.addWidget(self.lbl_paso)
        from src.gui.catalogo_gestion import _btn_x
        cab.addWidget(_btn_x(self.reject))
        root.addLayout(cab)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._paso_buscar())
        self._stack.addWidget(self._paso_credenciales())
        self._stack.addWidget(self._paso_confirmar())
        root.addWidget(self._stack, 1)

        nav = QHBoxLayout()
        self.btn_atras = _btn("← Atrás", self._atras)
        self.btn_manual = _btn("Añadir manualmente", self._ir_manual)
        nav.addWidget(self.btn_atras); nav.addWidget(self.btn_manual); nav.addStretch()
        self.btn_siguiente = _btn("Buscar cámaras →", self._siguiente)
        nav.addWidget(self.btn_siguiente)
        root.addLayout(nav)
        self._actualizar_paso()

    # ── arrastre (ventana sin marco) ──────────────────────────────────────
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft(); e.accept()

    def mouseMoveEvent(self, e):
        if self._drag is not None and (e.buttons() & Qt.MouseButton.LeftButton):
            self.move(e.globalPosition().toPoint() - self._drag); e.accept()

    def mouseReleaseEvent(self, e):
        self._drag = None; super().mouseReleaseEvent(e)

    def closeEvent(self, e):
        if self._hilo is not None and self._hilo.isRunning():
            self._hilo.wait(2000)
        super().closeEvent(e)

    # ── paso 1: buscar ──────────────────────────────────────────────────
    def _paso_buscar(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(10)
        ly.addWidget(QLabel("Busca cámaras ONVIF en tu red local (WS-Discovery, 10-15 s)."))
        self.barra_busqueda = QProgressBar(); self.barra_busqueda.setRange(0, 0)
        self.barra_busqueda.setVisible(False)
        self.barra_busqueda.setStyleSheet(f"QProgressBar{{background:{_BG2};border:1px solid {_BORDE};"
                                          "border-radius:6px;}"
                                          f"QProgressBar::chunk{{background:{_CIAN};border-radius:6px;}}")
        ly.addWidget(self.barra_busqueda)
        self.lst_encontradas = QListWidget()
        self.lst_encontradas.setStyleSheet(
            f"QListWidget{{background:{_BG2};color:{_TEXT};border:1px solid {_BORDE};border-radius:8px;}}"
            f"QListWidget::item{{padding:8px;}}")
        ly.addWidget(self.lst_encontradas, 1)
        self.lbl_buscar_estado = QLabel("")
        self.lbl_buscar_estado.setStyleSheet(f"color:{_DIM};font-size:12px;")
        self.lbl_buscar_estado.setWordWrap(True)
        ly.addWidget(self.lbl_buscar_estado)
        return w

    def _lanzar_busqueda(self):
        self.lst_encontradas.clear()
        self.lbl_buscar_estado.setText("")
        self.barra_busqueda.setVisible(True)
        self.btn_siguiente.setEnabled(False)
        self._hilo = _HiloTarea(_cam.escanear_red, timeout_seg=12)
        self._hilo.resultado.connect(self._on_busqueda_lista)
        self._hilo.start()

    def _on_busqueda_lista(self, r):
        self.barra_busqueda.setVisible(False)
        self.btn_siguiente.setEnabled(True)
        self._encontradas = r if isinstance(r, list) else []
        self.lst_encontradas.clear()
        if not self._encontradas:
            self.lbl_buscar_estado.setText(
                "No se ha encontrado ninguna cámara ONVIF en la red (o el descubrimiento no está "
                "disponible). Puedes reintentar o añadir la cámara manualmente.")
            return
        self.lbl_buscar_estado.setText(f"{len(self._encontradas)} cámara(s) encontrada(s). Marca las "
                                       "que quieras añadir.")
        for c in self._encontradas:
            fab = c.get("fabricante") or "sin identificar"
            it = QListWidgetItem(f"{c['ip']}  ·  {fab}")
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked)
            it.setData(Qt.ItemDataRole.UserRole, c)
            self.lst_encontradas.addItem(it)

    # ── paso 2: credenciales maestras ────────────────────────────────────
    def _paso_credenciales(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(10)
        ly.addWidget(QLabel("Credenciales maestras (se probarán en todas las cámaras marcadas):"))
        ly.addWidget(QLabel("Usuario"))
        self.in_w_usuario = QLineEdit(); self.in_w_usuario.setFixedHeight(36)
        ly.addWidget(self.in_w_usuario)
        ly.addWidget(QLabel("Contraseña"))
        self.in_w_pass = QLineEdit(); self.in_w_pass.setFixedHeight(36)
        self.in_w_pass.setEchoMode(QLineEdit.EchoMode.Password)
        ly.addWidget(self.in_w_pass)
        for inp in (self.in_w_usuario, self.in_w_pass):
            inp.setStyleSheet(f"QLineEdit{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};"
                              "border-radius:8px;padding:4px 10px;font-size:13px;}")
        ly.addWidget(_btn("Probar conexión en todas", self._probar_todas))
        self.tbl_pruebas = QTableWidget(0, 2)
        self.tbl_pruebas.setHorizontalHeaderLabels(["Cámara", "Resultado"])
        self.tbl_pruebas.setStyleSheet(f"QTableWidget{{background:{_BG2};color:{_TEXT};"
                                       f"border:1px solid {_BORDE};border-radius:8px;}}")
        self.tbl_pruebas.horizontalHeader().setStretchLastSection(True)
        self.tbl_pruebas.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        ly.addWidget(self.tbl_pruebas, 1)
        return w

    def _probar_todas(self):
        seleccion = self._marcadas()
        if not seleccion:
            return
        usuario, contrasena = self.in_w_usuario.text(), self.in_w_pass.text()
        self.tbl_pruebas.setRowCount(0)

        def _probar_todas_fn():
            from src.services.camaras.descubrimiento import puerto_de
            out = {}
            for c in seleccion:
                puerto = puerto_de(c.get("xaddr"), 80)
                out[c["ip"]] = _cam.onvif_probar_conexion(c["ip"], usuario, contrasena,
                                                          puerto_onvif=puerto)
            return out

        self._hilo = _HiloTarea(_probar_todas_fn)
        self._hilo.resultado.connect(self._on_pruebas_listas)
        self._hilo.start()

    def _on_pruebas_listas(self, r):
        if isinstance(r, Exception) or not isinstance(r, dict):
            return
        self._resultado_pruebas = r
        self.tbl_pruebas.setRowCount(0)
        for ip, res in r.items():
            row = self.tbl_pruebas.rowCount(); self.tbl_pruebas.insertRow(row)
            self.tbl_pruebas.setItem(row, 0, QTableWidgetItem(ip))
            if res.get("ok"):
                texto, color = f"✅ {res.get('fabricante') or 'ok'}", _CIAN
            else:
                texto, color = f"❌ {res.get('motivo') or 'error'}", _AMBAR
            item = QTableWidgetItem(texto); item.setForeground(QColor(color))
            self.tbl_pruebas.setItem(row, 1, item)

    def _marcadas(self):
        out = []
        for i in range(self.lst_encontradas.count()):
            it = self.lst_encontradas.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                out.append(it.data(Qt.ItemDataRole.UserRole))
        return out

    # ── paso 3: confirmar ────────────────────────────────────────────────
    def _paso_confirmar(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(10)
        ly.addWidget(QLabel("Departamento de destino:"))
        self.cmb_w_dep = QComboBox()
        self.cmb_w_dep.setStyleSheet(f"QComboBox{{background:{_BG2};color:{_TEXT};border:1px solid "
                                     f"{_BORDE};border-radius:8px;padding:6px 10px;}}")
        ly.addWidget(self.cmb_w_dep)
        ly.addWidget(QLabel("Nombre de cada cámara:"))
        self.tbl_confirmar = QTableWidget(0, 2)
        self.tbl_confirmar.setHorizontalHeaderLabels(["IP", "Nombre"])
        self.tbl_confirmar.setStyleSheet(f"QTableWidget{{background:{_BG2};color:{_TEXT};"
                                         f"border:1px solid {_BORDE};border-radius:8px;}}")
        self.tbl_confirmar.horizontalHeader().setStretchLastSection(True)
        ly.addWidget(self.tbl_confirmar, 1)
        self.lbl_confirmar_estado = QLabel(""); self.lbl_confirmar_estado.setStyleSheet(f"color:{_DIM};")
        self.lbl_confirmar_estado.setWordWrap(True)
        ly.addWidget(self.lbl_confirmar_estado)
        return w

    def _preparar_confirmar(self):
        self.cmb_w_dep.clear()
        for d in _cam.departamentos() or []:
            self.cmb_w_dep.addItem(f"{d['nombre']} ({d['tipo_centro']})", d)
        self._seleccion = self._marcadas()
        self.tbl_confirmar.setRowCount(0)
        for c in self._seleccion:
            row = self.tbl_confirmar.rowCount(); self.tbl_confirmar.insertRow(row)
            self.tbl_confirmar.setItem(row, 0, QTableWidgetItem(c["ip"]))
            fab = c.get("fabricante") or ""
            nombre = f"Cámara {fab} {c['ip']}".replace("  ", " ").strip()
            self.tbl_confirmar.setItem(row, 1, QTableWidgetItem(nombre))

    # ── navegación ───────────────────────────────────────────────────────
    def _actualizar_paso(self):
        idx = self._stack.currentIndex()
        self.lbl_paso.setText(f"Paso {idx + 1}/3 — " + ["Buscar", "Credenciales", "Confirmar"][idx])
        # OCULTO (no solo deshabilitado) en el paso 1: no hay a dónde volver. Antes se dejaba
        # visible pero deshabilitado con `setEnabled(False)` — un botón deshabilitado que nunca se
        # vuelve a rehabilitar en ESTE paso concreto podía quedarse con el estado :hover/:disabled
        # de Qt mal repintado al reaparecer luego habilitado en el paso 2 (bug de QSS ya visto y
        # resuelto en otros sitios de la app con un repintado forzado tras `setEnabled`) — se evita
        # de raíz no tocando `setEnabled` en absoluto, solo la visibilidad.
        self.btn_atras.setVisible(idx > 0)
        if idx > 0:
            self.btn_atras.style().unpolish(self.btn_atras)
            self.btn_atras.style().polish(self.btn_atras)
        self.btn_siguiente.setText(
            "Buscar cámaras →" if idx == 0 else ("Siguiente →" if idx == 1 else "✔ Finalizar"))

    def _atras(self):
        if self._stack.currentIndex() > 0:
            self._stack.setCurrentIndex(self._stack.currentIndex() - 1)
            self._actualizar_paso()

    def _ir_manual(self):
        self.abrir_manual = True
        self.reject()

    def _siguiente(self):
        idx = self._stack.currentIndex()
        if idx == 0:
            if not self._encontradas:
                self._lanzar_busqueda()
                return
            self._stack.setCurrentIndex(1)
        elif idx == 1:
            if not self._marcadas():
                self.lbl_buscar_estado.setText("Marca al menos una cámara en el paso anterior.")
                self._stack.setCurrentIndex(0)
                self._actualizar_paso()
                return
            self._preparar_confirmar()
            self._stack.setCurrentIndex(2)
        else:
            self._finalizar()
            return
        self._actualizar_paso()

    def _finalizar(self):
        dep = self.cmb_w_dep.currentData()
        if not dep:
            self.lbl_confirmar_estado.setText("No hay ningún departamento disponible.")
            return
        usuario, contrasena = self.in_w_usuario.text(), self.in_w_pass.text()
        creadas, fallidas = 0, 0
        for row in range(self.tbl_confirmar.rowCount()):
            ip = self.tbl_confirmar.item(row, 0).text()
            nombre = (self.tbl_confirmar.item(row, 1).text() or ip).strip()
            cam = next((c for c in self._seleccion if c["ip"] == ip), None)
            puerto_onvif = 80
            if cam:
                from src.services.camaras.descubrimiento import puerto_de
                puerto_onvif = puerto_de(cam.get("xaddr"), 80)
            try:
                from src.db.empresa import empresa_actual_id
                emp = empresa_actual_id()
            except Exception:
                emp = None
            cid = _cam.crear_camara_onvif(nombre, ip, usuario, contrasena, id_empresa=emp,
                                          id_centro=dep["id_centro"], tipo_centro=dep["tipo_centro"],
                                          puerto_onvif=puerto_onvif)
            creadas += 1 if cid else 0
            fallidas += 0 if cid else 1
        self.lbl_confirmar_estado.setText(f"{creadas} cámara(s) añadida(s)" +
                                          (f", {fallidas} con error" if fallidas else "") + ".")
        self.accept()


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
        self._live_workers = {}   # id_camara -> (worker, hilo), tiles de la rejilla
        self._live_full = None    # (worker, hilo) de la vista en pantalla completa
        self._build()
        if getattr(self, "stack", None) is not None:
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

    def _puede(self, permiso) -> bool:
        try:
            return bool(autorizacion.puede(self.usuario, permiso))
        except Exception:
            return False

    # ── UI ───────────────────────────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        if not self._puede("camaras.ver"):
            lbl = QLabel("No tienes permiso para ver Videovigilancia.")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"color:{_DIM};font-size:14px;")
            root.addWidget(lbl, 1)
            self.stack = None
            return

        aviso = self._banner_prerrequisitos()
        if aviso is not None:
            root.addWidget(aviso)

        fila = QHBoxLayout(); fila.setContentsMargins(0, 0, 0, 0); fila.setSpacing(0)
        fila.addWidget(self._sidebar())
        # StackedActual (no QStackedWidget "a pelo"): sin esto el ancho mínimo de la ventana
        # reflejaba SIEMPRE el máximo de las 3 páginas (el reproductor, 864px, aunque la rejilla —
        # la página realmente visible al abrir — solo necesita 232px), forzando una ventana más
        # ancha que la pantalla real del usuario y provocando el fallo nativo de Windows al no
        # poder concederle esa geometría (mismo bug ya resuelto en Contabilidad/RRHH).
        self.stack = StackedActual()
        self.stack.addWidget(self._pagina_rejilla())      # 0
        self.stack.addWidget(self._pagina_reproductor())  # 1
        self.stack.addWidget(self._pagina_vivo())         # 2
        self.stack.currentChanged.connect(self._on_pagina_cambiada)
        cont = QWidget(); cl = QVBoxLayout(cont); cl.setContentsMargins(18, 16, 18, 16)
        cab = QHBoxLayout()
        tit = QLabel("📹  VIDEOVIGILANCIA")
        tit.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:20px;")
        cab.addWidget(tit); cab.addStretch()
        if self._volver:
            from src.gui.catalogo_gestion import _btn_x
            cab.addWidget(_btn_x(self._volver))
        cl.addLayout(cab); cl.addWidget(self.stack, 1)
        fila.addWidget(cont, 1)
        root.addLayout(fila, 1)

    def _banner_prerrequisitos(self):
        """Aviso VISIBLE (no degradación silenciosa) si falta ffmpeg y/o onvif-zeep."""
        try:
            avisos = _cam.prerrequisitos.avisos_pendientes()
        except Exception:
            avisos = []
        if not avisos:
            return None
        frame = QFrame()
        frame.setStyleSheet(f"background:{_BG2};border-bottom:2px solid {_AMBAR};")
        ly = QVBoxLayout(frame); ly.setContentsMargins(16, 8, 16, 8); ly.setSpacing(2)
        for texto in avisos:
            lbl = QLabel(f"⚠ {texto}"); lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color:{_AMBAR};font-size:12px;")
            ly.addWidget(lbl)
        return frame

    # ── Ciclo de vida del vídeo en vivo ────────────────────────────────────────
    def _on_pagina_cambiada(self, idx):
        if idx != 0:
            self._detener_workers_rejilla()
        if idx != 2:
            self._detener_worker_vivo()

    def _detener_workers_rejilla(self):
        for par in self._live_workers.values():
            _detener_worker(par)
        self._live_workers = {}

    def _detener_worker_vivo(self):
        if self._live_full is not None:
            _detener_worker(self._live_full)
            self._live_full = None

    def closeEvent(self, event):
        self._detener_workers_rejilla()
        self._detener_worker_vivo()
        super().closeEvent(event)

    def _sidebar(self):
        w = QFrame(); w.setFixedWidth(280); w.setStyleSheet(f"background:{_BG2};")
        ly = QVBoxLayout(w); ly.setContentsMargins(14, 18, 14, 14); ly.setSpacing(10)
        t = QLabel("CÁMARAS"); t.setStyleSheet(f"color:{_TEXT};font-size:16px;font-weight:900;letter-spacing:2px;")
        ly.addWidget(t)
        self.cb_dep = QComboBox()
        self.cb_dep.setStyleSheet(f"QComboBox{{background:{_BG};color:{_TEXT};border:1px solid {_BORDE};"
                                  "border-radius:8px;padding:6px 10px;}")
        # Sin esto, un departamento con nombre largo hacía que el combo (política de tamaño por
        # defecto: ajustarse al contenido MÁS ancho) pidiera hasta 460px — más que todo el sidebar
        # (280px fijo) y suficiente para que la VENTANA entera pidiera más ancho del que hay en
        # pantalla (bug real: Windows no puede darle esa geometría y termina en un fallo nativo).
        self.cb_dep.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.cb_dep.setMinimumContentsLength(14)
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
        self.btn_anadir = _btn("＋ Añadir", self._anadir)
        fila.addWidget(self.btn_anadir)
        self.btn_eliminar = _btn("🗑 Eliminar", self._eliminar, rojo=True)
        self.btn_eliminar.setProperty("sin_glow", True)   # sin el resplandor turquesa global (opt-out)
        self.btn_eliminar.setGraphicsEffect(None)
        fila.addWidget(self.btn_eliminar)
        ly.addLayout(fila)
        # `actualizar_fuente` no tenía ningún botón: la única forma de corregir una URL RTSP/ONVIF
        # mal configurada era eliminar la cámara entera (perdiendo su histórico de eventos/grabaciones
        # enlazadas) y volver a crearla — huella de la auditoría app-wide.
        self.btn_editar_fuente = _btn("🔗 Editar fuente", self._editar_fuente)
        ly.addWidget(self.btn_editar_fuente)
        if not self._puede("camaras.gestionar"):
            self.btn_anadir.setEnabled(False)
            self.btn_eliminar.setEnabled(False)
            self.btn_editar_fuente.setEnabled(False)
            self.btn_anadir.setToolTip("No tienes permiso para gestionar cámaras.")
            self.btn_eliminar.setToolTip("No tienes permiso para gestionar cámaras.")
            self.btn_editar_fuente.setToolTip("No tienes permiso para gestionar cámaras.")
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
        return w

    def _cambiar_pagina(self, d):
        total = max(1, (len(self._camaras) + 8) // 9)
        self._pagina = max(0, min(total - 1, self._pagina + d))
        self._pintar_rejilla()

    def _pintar_rejilla(self):
        self._detener_workers_rejilla()
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
            lbl = QLabel(); lbl.setFixedSize(280, 200)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            lbl_nombre = QLabel(cam.get("nombre") or "Cámara")
            lbl_nombre.setStyleSheet(f"color:{_DIM};font-size:11px;")
            tl.addWidget(lbl); tl.addWidget(lbl_nombre)
            lbl.mouseDoubleClickEvent = lambda _e, c=cam: self._abrir_vivo(c)
            self._tiles.append((lbl, cam))
            self.grid.addWidget(tile, i // 3, i % 3)
            self._arrancar_tile(lbl, cam)
        total = max(1, (len(self._camaras) + 8) // 9)
        self.lbl_pag.setText(f"Página {self._pagina + 1}/{total}")

    def _arrancar_tile(self, lbl, cam):
        """Vivo REAL en la rejilla (substream, bajo fps/CPU) — sustituye al mock sintético anterior.
        Cámaras 'simuladas' (demo, sin fuente real) muestran un aviso honesto, no vídeo inventado."""
        cid = cam.get("id")
        fuente = (cam.get("fuente") or "").strip()
        if not fuente or fuente == "simulado":
            lbl.setText("Cámara simulada\n(sin vídeo en vivo)")
            lbl.setStyleSheet(f"background:#12141a;color:{_DIM};font-size:11px;border-radius:6px;")
            return
        try:
            url = _cam.fuente_para(cam, "sub")
        except Exception:
            url = fuente
        worker, hilo = _iniciar_worker(url, fps=6)
        worker.frame_listo.connect(lambda img, w=lbl: self._pintar_frame(w, img))
        worker.sin_senal.connect(lambda motivo, w=lbl: self._pintar_sin_senal(w, motivo))
        self._live_workers[cid] = (worker, hilo)

    def _pintar_frame(self, lbl, img):
        try:
            pm = QPixmap.fromImage(img).scaled(
                lbl.width() or 280, lbl.height() or 200,
                Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            lbl.setPixmap(pm)
        except Exception:
            pass

    def _pintar_sin_senal(self, lbl, motivo):
        # `try/except` (no solo Exception de red): si la señal llega justo después de repintar la
        # rejilla, el tile ya pudo haberse borrado (`deleteLater`) — PyQt lanza RuntimeError sobre un
        # widget C++ ya destruido. Mismo criterio defensivo que `_pintar_frame`.
        try:
            lbl.setPixmap(QPixmap())
            lbl.setText(motivo or "SIN SEÑAL")
            lbl.setStyleSheet(f"background:#1a0000;color:{_ROJO};font-size:12px;font-weight:700;"
                              "border-radius:6px;")
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
        if not self._puede("camaras.gestionar"):
            if mostrar_mensaje:
                mostrar_mensaje(self, "Cámaras", "No tienes permiso para añadir cámaras.", "warning")
            return
        wiz = _AltaCamaraWizard(self)
        aceptado = wiz.exec() == QDialog.DialogCode.Accepted
        abrir_manual = getattr(wiz, "abrir_manual", False)
        if abrir_manual:
            self._anadir_manual()
        elif aceptado:
            self._cargar_camaras()

    def _anadir_manual(self):
        dep = self._dep()
        if not dep:
            return
        dlg = _AltaManualDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        datos = dlg.datos()
        if not datos["nombre"] or not datos["host"]:
            if mostrar_mensaje:
                mostrar_mensaje(self, "Cámaras", "Nombre e IP son obligatorios.", "warning")
            return
        _cam.crear_camara_onvif(datos["nombre"], datos["host"], datos["usuario"], datos["contrasena"],
                                id_empresa=self._id_empresa(), id_centro=dep["id_centro"],
                                tipo_centro=dep["tipo_centro"], puerto_onvif=datos["puerto_onvif"],
                                puerto_rtsp=datos["puerto_rtsp"])
        self._cargar_camaras()

    def _eliminar(self):
        if not self._puede("camaras.gestionar"):
            if mostrar_mensaje:
                mostrar_mensaje(self, "Cámaras", "No tienes permiso para eliminar cámaras.", "warning")
            return
        it = self.lst.currentItem()
        if not it:
            return
        _cam.eliminar_camara(it.data(Qt.ItemDataRole.UserRole), id_empresa=self._id_empresa())
        self._cargar_camaras()

    def _editar_fuente(self):
        if not self._puede("camaras.gestionar"):
            if mostrar_mensaje:
                mostrar_mensaje(self, "Cámaras", "No tienes permiso para editar cámaras.", "warning")
            return
        it = self.lst.currentItem()
        if it is None:
            if mostrar_mensaje:
                mostrar_mensaje(self, "Cámaras", "Selecciona antes una cámara en la lista.", "warning")
            return
        cid = it.data(Qt.ItemDataRole.UserRole)
        url, ok = _pedir_texto(
            self, "Editar fuente de la cámara",
            "Nueva URL RTSP/ONVIF (rtsp://usuario:contraseña@host:puerto/…):")
        if ok and url.strip():
            if _cam.actualizar_fuente(cid, url.strip(), id_empresa=self._id_empresa()):
                if mostrar_mensaje:
                    mostrar_mensaje(self, "Cámaras", "Fuente actualizada correctamente.", "success")
            elif mostrar_mensaje:
                mostrar_mensaje(self, "Cámaras", "No se pudo actualizar la fuente.", "error")
            self._cargar_camaras()

    def _renombrar(self, it):
        if not self._puede("camaras.gestionar"):
            if mostrar_mensaje:
                mostrar_mensaje(self, "Cámaras", "No tienes permiso para renombrar cámaras.", "warning")
            return
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
        self.fecha.setStyleSheet(
            f"QDateEdit{{background:{_BG2};color:{_TEXT};border:1px solid {_BORDE};"
            "border-radius:8px;padding:4px 8px 4px 8px;padding-right:26px;}"
            # ::drop-down/::down-arrow explícitos: sin ellos, Qt dibuja el botón/triángulo
            # NATIVOS del estilo activo (Fusion) en vez del mismo icono "⌄" cian que usa
            # `QComboBox::down-arrow` en toda la app (regla global en `estilo_global.py`) —
            # mismo tratamiento que el resto de desplegables de fecha/combo de la app.
            "QDateEdit::drop-down{border:none;width:24px;background:transparent;}"
            f"QDateEdit::down-arrow{{image:url({_ARROW_ICON});width:14px;height:14px;}}"
        )
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
        if not self._puede("camaras.ptz"):
            if mostrar_mensaje:
                mostrar_mensaje(self, "PTZ", "No tienes permiso para controlar el PTZ.", "warning")
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
        if not self._puede("camaras.grabaciones.descargar"):
            if mostrar_mensaje:
                mostrar_mensaje(self, "Clip", "No tienes permiso para descargar grabaciones.", "warning")
            return
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

    # ── Vivo en pantalla completa (mainstream) ──────────────────────────────────
    def _pagina_vivo(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(8)
        top = QHBoxLayout()
        top.addWidget(_btn("◀ Volver a la rejilla", lambda: self.stack.setCurrentIndex(0)))
        self.lbl_vivo_cam = QLabel(""); self.lbl_vivo_cam.setStyleSheet(f"color:{_CIAN};font-weight:900;")
        top.addWidget(self.lbl_vivo_cam); top.addStretch()
        top.addWidget(_btn("📼 Ver grabaciones de este día", self._ver_grabaciones_de_vivo))
        ly.addLayout(top)
        self.video_vivo = QLabel("Selecciona una cámara")
        self.video_vivo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_vivo.setStyleSheet(f"background:#000;color:{_DIM};border-radius:10px;")
        ly.addWidget(self.video_vivo, 1)
        return w

    def _abrir_vivo(self, cam):
        if not self._puede("camaras.ver"):
            if mostrar_mensaje:
                mostrar_mensaje(self, "Cámaras", "No tienes permiso para ver el vídeo en vivo.", "warning")
            return
        self._detener_worker_vivo()
        self._cam_sel = cam
        self.lbl_vivo_cam.setText("🎥  " + (cam.get("nombre") or "Cámara"))
        self.video_vivo.setPixmap(QPixmap())
        self.stack.setCurrentIndex(2)
        fuente = (cam.get("fuente") or "").strip()
        if not fuente or fuente == "simulado":
            self.video_vivo.setText("Cámara simulada (sin vídeo en vivo)")
            return
        self.video_vivo.setText("Conectando…")
        try:
            url = _cam.fuente_para(cam, "main")
        except Exception:
            url = fuente
        worker, hilo = _iniciar_worker(url, fps=15)
        worker.frame_listo.connect(self._pintar_frame_vivo)
        worker.sin_senal.connect(self._pintar_sin_senal_vivo)
        self._live_full = (worker, hilo)

    def _pintar_frame_vivo(self, img):
        try:
            pm = QPixmap.fromImage(img).scaled(
                self.video_vivo.width(), self.video_vivo.height(),
                Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.video_vivo.setPixmap(pm)
        except Exception:
            pass

    def _pintar_sin_senal_vivo(self, motivo):
        try:
            self.video_vivo.setPixmap(QPixmap())
            self.video_vivo.setText(motivo or "SIN SEÑAL")
        except Exception:
            pass

    def _ver_grabaciones_de_vivo(self):
        if self._cam_sel:
            self._abrir_reproductor(self._cam_sel.get("id"))
