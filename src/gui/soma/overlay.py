"""
SomaOverlay (Fase 2, revisado). El Espacio Conversacional visual de SOMA, como VENTANA TOP-LEVEL
SIEMPRE-ENCIMA (frameless + StaysOnTop + Tool), para superponerse sobre TODA la aplicación y estar
disponible desde CUALQUIER módulo (que en este ERP se abren como ventanas top-level maximizadas).
No modifica ningún layout existente. Dos modos:

  • REPOSO  → una ventanita (dock) con el personaje, abajo-centro de la pantalla, siempre visible y
              clicable; el ERP es plenamente interactivo. Pulsar el personaje INVOCA a SOMA.
  • ACTIVO  → la ventana cubre la pantalla: ATENÚA el ERP y lo deja NO interactivo (captador de clics);
              el personaje se sitúa centrado-abajo y aparece el panel conversacional. El primer clic
              fuera de SOMA CANCELA la conversación, oculta SOMA y restaura el ERP — sin propagarse.

Implementa el contrato `EspacioConversacional` del kernel. La GUI JAMÁS decide estados: los recibe.
"""

import logging

from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

from src.gui.soma.animaciones import ControladorAnimacion
from src.gui.soma.conversacion import SomaConversationPanel
from src.gui.soma.personaje import SomaCharacter

logger = logging.getLogger("gui.soma.overlay")

_DOCK = 120          # tamaño del personaje en reposo (px)
_MARGEN = 16
_CHAR_ACTIVO = 210   # tamaño del personaje en activo
_CONV_W = 600
_CONV_H = 430
_DIM_ALPHA = 120     # atenuación del ERP (0-255)
_CARD_W = 176        # tarjeta discreta de invocación (reposo): abajo-centro en TODAS las pantallas
_CARD_H = 46


class SomaOverlay(QWidget):
    def __init__(self, app=None):
        super().__init__(None)
        self._app = app
        self._modo = "reposo"
        self._kernel = None
        # Ventana top-level, sin marco, SIEMPRE por encima, sin entrada en la barra de tareas.
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)  # el dock no roba foco

        self._character = SomaCharacter(self)
        self._controlador = ControladorAnimacion(self._character)
        self._conversacion = SomaConversationPanel(self)
        self._conversacion.setVisible(False)
        self._conversacion.enviado.connect(self._on_enviado)
        self._conversacion.usuario_escribe.connect(self._on_usuario_escribe)

        # Tarjeta DISCRETA de invocación (reposo): SOMA permanece oculto (sin personaje) hasta que se
        # pronuncia la wake word o se pulsa esta tarjeta. Sutil pero visible, abajo-centro de la pantalla.
        self._card = QLabel("🌸  Asistente SOMA", self)
        self._card.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._card.setCursor(Qt.CursorShape.PointingHandCursor)
        self._card.setStyleSheet(self._card_ss(hover=False))

        # Badge de propuestas (contador estilo WhatsApp) sobre el personaje en reposo.
        self._propuestas = 0
        self._badge = QLabel("", self)
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.setStyleSheet(
            "background:#F23645;color:white;border:2px solid white;border-radius:13px;"
            "font-weight:900;font-size:12px;")
        self._badge.setFixedSize(26, 26)
        self._badge.setVisible(False)

        self._controlador.iniciar_microanimaciones()
        self._aplicar_layout()

        # SOMA NO debe mostrarse cuando el ERP no está activo (minimizado, cerrado o con el foco en
        # otra aplicación): al ser una ventana siempre-encima, hay que ocultarla según el estado de
        # la app. Así el personaje nunca flota sobre el escritorio ni sobre otros programas.
        #
        # Se escuchan DOS señales complementarias porque `applicationStateChanged` NO es fiable en
        # Windows para ventanas `Tool` siempre-encima (a menudo no se emite al hacer Alt-Tab a otro
        # programa, y SOMA se quedaba flotando sobre la otra aplicación). `focusWindowChanged` sí se
        # emite: un QWindow no nulo = una ventana de ESTA app tiene el foco; `None` = el foco pasó a
        # otro programa/escritorio. La combinación cierra el hueco.
        self._app_activa = True
        # Gate de SESIÓN: SOMA solo existe con sesión iniciada. En la pantalla de login/selector (sin
        # sesión) el personaje NO debe aparecer BAJO NINGÚN CONCEPTO. main.py lo conmuta al iniciar/cerrar
        # sesión (set_sesion_activa). Se muestra únicamente si HAY sesión Y la app está en primer plano.
        self._sesion_activa = True
        _qapp = QApplication.instance()
        if _qapp is not None:
            for _sig, _slot in (("applicationStateChanged", self._on_app_state),
                                ("focusWindowChanged", self._on_focus_window)):
                try:
                    getattr(_qapp, _sig).connect(_slot)
                except Exception:
                    pass

        # Fallback ROBUSTO (Windows): las señales de Qt de arriba NO siempre se emiten al pasar el foco a
        # OTRO programa (p. ej. VSCode) desde una ventana `Tool` siempre-encima, y SOMA se quedaba flotando
        # sobre esa otra app. Por eso se SONDEA además la ventana en primer plano del SO: si pertenece a otro
        # proceso, la app NO está activa y SOMA se oculta. Barato (~2/seg) y determinista.
        from PyQt6.QtCore import QTimer
        self._timer_foco = QTimer(self)
        self._timer_foco.setInterval(500)
        self._timer_foco.timeout.connect(self._verificar_foreground)
        self._timer_foco.start()

    def _verificar_foreground(self):
        es_nuestro = self._foreground_es_nuestro()
        if es_nuestro is not None and es_nuestro != self._app_activa:
            self._set_app_activa(es_nuestro)

    @staticmethod
    def _foreground_es_nuestro():
        """¿La ventana en PRIMER PLANO del SO pertenece a ESTE proceso? True/False en Windows; None en otros
        SO o si no se puede determinar (para no forzar el ocultado y dejar mandar a las señales de Qt)."""
        try:
            import ctypes
            import os
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return False               # sin ventana en primer plano (escritorio) → no es nuestra
            pid = ctypes.c_ulong(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            return pid.value == os.getpid()
        except Exception:
            return None                    # p. ej. no-Windows: dejar decidir a applicationState/focusWindow

    def _on_app_state(self, state):
        self._set_app_activa(state == Qt.ApplicationState.ApplicationActive)

    def _on_focus_window(self, win):
        # win no nulo → una ventana de esta app tiene el foco; None → el foco salió a otro programa.
        self._set_app_activa(win is not None)

    def _set_app_activa(self, activa):
        self._app_activa = bool(activa)
        self._sincronizar_visibilidad()

    def set_sesion_activa(self, activa):
        """Conmuta el gate de SESIÓN. main.py llama a False al cerrar sesión (SOMA desaparece del login)
        y a True al iniciarla. Evita que el personaje quede flotando en el login tras un logout."""
        self._sesion_activa = bool(activa)
        self._sincronizar_visibilidad()

    def _sincronizar_visibilidad(self):
        """Punto ÚNICO de visibilidad de SOMA: se ve SOLO si hay sesión activa Y la app está en primer
        plano. Cualquier camino de show()/raise_() debe pasar por aquí para que el personaje nunca
        aparezca en el login ni sobre otros programas."""
        if self._sesion_activa and self._app_activa:
            if not self.isVisible():
                self.show()
            self._aplicar_layout()
            self.raise_()
        else:
            # Sin sesión, o ERP inactivo/minimizado/foco en otro programa → replegar y ESCONDER a SOMA.
            if self._modo == "activo" and self._kernel is not None:
                try:
                    self._kernel.ocultar()
                except Exception:
                    pass
            self.hide()

    # ── Integración con el SomaKernel ─────────────────────────────────────────
    def conectar_kernel(self, kernel):
        self._kernel = kernel
        try:
            kernel.maquina.suscribir(self._on_estado_kernel)
            kernel.set_espacio(self)
        except Exception as e:
            logger.debug("conectar_kernel: %s", e)
        self._controlador.aplicar_estado(kernel.estado)

    def _on_estado_kernel(self, anterior, nuevo):
        self._controlador.aplicar_estado(nuevo)   # la GUI SOLO representa

    # ── Contrato EspacioConversacional (lo llama el kernel) ───────────────────
    def mostrar(self, *, motivo=None):
        self._ir_activo(motivo)

    def ocultar(self):
        self._ir_reposo()

    def mostrar_estado(self, estado):
        self._controlador.aplicar_estado(estado)

    def mostrar_mensaje_usuario(self, texto):
        self._conversacion.agregar_usuario(texto)

    def mostrar_respuesta(self, texto, *, datos=None):
        # Respuesta enriquecida: texto + visual (tabla/KPIs/lista) + referencias (fuentes).
        fuentes = visual = None
        if isinstance(datos, dict):
            fuentes = datos.get("fuentes")
            visual = datos.get("visual")
        if fuentes or visual:
            self._conversacion.agregar_soma_rico(texto, fuentes=fuentes, visual=visual)
        else:
            self._conversacion.agregar_soma(texto)

    def esta_visible(self):
        return self._modo == "activo"

    def mostrar_workspace(self, mision):
        # Workspace de Misión dentro del overlay (sin ventanas nuevas).
        self._conversacion.mostrar_workspace(mision)

    def proponer(self, total: int = 1):
        """SOMA tiene propuesta(s): NO invade la pantalla. Muestra un badge con contador y la pose
        'proponiendo' (mano levantada) en reposo. El usuario abre la propuesta al pulsar el personaje."""
        self._propuestas = max(0, int(total))
        if self._propuestas <= 0:
            self.reset_propuestas()
            return
        # Asegura que SOMA esté visible en reposo (sin abrir la conversación), PERO solo si hay sesión y
        # la app está en primer plano: una propuesta proactiva NUNCA debe hacer aparecer al personaje en
        # el login ni sobre otro programa. Si no procede, se guarda el badge/pose y se mostrará al volver.
        if not self.isVisible() and self._app_activa and self._sesion_activa:
            self.show()
        try:
            self._character.mostrar_pose("proponiendo")
        except Exception:
            pass
        self._badge.setText("9+" if self._propuestas > 9 else str(self._propuestas))
        self._badge.setVisible(True)
        self._badge.raise_()
        self._aplicar_layout()

    def reset_propuestas(self):
        self._propuestas = 0
        self._badge.setVisible(False)
        # Restaura la pose al estado actual del kernel (o a reposo feliz).
        try:
            estado = self._kernel.estado if self._kernel is not None else "ESPERANDO"
            self._controlador.aplicar_estado(estado)
        except Exception:
            pass

    # ── Transiciones de modo ──────────────────────────────────────────────────
    def _ir_activo(self, motivo=None):
        if self._modo == "activo":
            return
        self._modo = "activo"
        self._conversacion.setVisible(True)
        self._aplicar_layout()
        self.raise_()
        self.update()
        # Por VOZ (wake) el trabajador va a dictar → mantener ESCUCHANDO más tiempo (6 s de margen).
        # Por CLIC, asentar en FELIZ enseguida (250 ms) si no dice nada.
        demora = 6000 if motivo == "wake_word" else 250
        self._controlador.secuencia_aparicion(al_terminar=lambda: self._programar_reposo_feliz(demora))
        self._conversacion.foco_entrada()
        self.activateWindow()

    def _ir_reposo(self):
        if self._modo == "reposo":
            return
        self._modo = "reposo"
        self._conversacion.setVisible(False)
        self._controlador.secuencia_desaparicion()
        self._aplicar_layout()
        self.update()

    def _programar_reposo_feliz(self, demora=250):
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(int(demora), self._asentar_feliz)

    def _asentar_feliz(self):
        if self._modo != "activo" or self._kernel is None:
            return
        if self._kernel.estado == "ESCUCHANDO" and not self._conversacion.hay_texto():
            self._kernel.en_espera()   # → ESPERANDO (feliz)

    # ── Invocación / cancelación ──────────────────────────────────────────────
    def _invocar(self):
        if self._kernel is None:
            return
        # Si hay propuestas pendientes, abrirlas (SOMA las presenta); si no, invocación normal.
        if self._propuestas > 0 and hasattr(self._kernel, "abrir_propuestas"):
            self._kernel.abrir_propuestas()
        else:
            self._kernel.activar(motivo="clic_personaje")

    def _cancelar(self):
        if self._kernel is not None:
            self._kernel.ocultar()

    # ── Conversación → estados (la GUI reporta eventos; el kernel decide) ─────
    def _on_usuario_escribe(self, activo):
        if self._kernel is None or self._modo != "activo":
            return
        if self._kernel.estado in ("PENSANDO", "PROCESANDO", "HABLANDO"):
            return
        if activo:
            self._kernel.al_escuchar()
        else:
            self._kernel.en_espera()

    def _on_enviado(self, texto):
        # Conversación REAL: el kernel enruta a CopilotService (o fast-path de navegación) y decide
        # los estados; el overlay solo representa. Ya no hay respuesta simulada.
        if self._kernel is not None:
            self._kernel.procesar(texto, origen="texto")

    # ── Captador de clics ─────────────────────────────────────────────────────
    def mousePressEvent(self, e):
        if self._modo == "reposo":
            self._invocar()
            e.accept()
            return
        pos = e.position().toPoint()
        if self._character.geometry().contains(pos) or self._conversacion.geometry().contains(pos):
            e.accept()
            return
        self._cancelar()
        e.accept()

    # ── Atenuación del ERP (solo en activo) ───────────────────────────────────
    def paintEvent(self, _e):
        if self._modo != "activo":
            return
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, _DIM_ALPHA))
        p.end()

    # ── Geometría (relativa a la PANTALLA; independiente de la ventana activa) ─
    def _rect_ref(self) -> QRect:
        scr = self.screen() or QApplication.primaryScreen()
        return scr.availableGeometry() if scr else QRect(0, 0, 1280, 800)

    @staticmethod
    def _card_ss(hover: bool) -> str:
        """Estilo de la tarjeta de invocación: sutil en reposo (fondo oscuro + contorno/texto turquesa),
        con hover swap (se rellena de turquesa) para que se note clicable sin invadir la pantalla."""
        fondo = "#00FFC6" if hover else "#12212B"
        color = "#0D1117" if hover else "#00FFC6"
        return (f"QLabel{{background:{fondo};color:{color};border:2px solid #00FFC6;border-radius:14px;"
                f"font-weight:900;font-size:13px;padding:0 10px;font-family:'Segoe UI';}}")

    def enterEvent(self, e):   # noqa: N802 (API Qt): hover de la tarjeta (solo en reposo)
        if self._modo == "reposo":
            self._card.setStyleSheet(self._card_ss(hover=True))
        super().enterEvent(e)

    def leaveEvent(self, e):   # noqa: N802 (API Qt)
        if self._modo == "reposo":
            self._card.setStyleSheet(self._card_ss(hover=False))
        super().leaveEvent(e)

    def _aplicar_layout(self):
        r = self._rect_ref()
        if self._modo == "reposo":
            # REPOSO: SOMA oculto. Solo la tarjeta discreta abajo-centro (invocable por clic o wake word).
            x = r.x() + (r.width() - _CARD_W) // 2
            y = r.y() + r.height() - _CARD_H - _MARGEN
            self.setGeometry(x, y, _CARD_W, _CARD_H)
            self._character.setVisible(False)
            self._card.setVisible(True)
            self._card.setGeometry(0, 0, _CARD_W, _CARD_H)
            self._conversacion.setVisible(False)
            # Badge de propuestas en la esquina superior derecha de la tarjeta.
            if self._propuestas > 0:
                self._badge.move(_CARD_W - self._badge.width() - 2, 2)
                self._badge.setVisible(True)
                self._badge.raise_()
            else:
                self._badge.setVisible(False)
        else:
            # ACTIVO: aparece el personaje (+ panel conversacional); la tarjeta se oculta.
            self._card.setVisible(False)
            self._character.setVisible(True)
            self.setGeometry(r)
            W, H = r.width(), r.height()
            cx = (W - _CHAR_ACTIVO) // 2
            cy = H - _CHAR_ACTIVO - 28
            self._character.setGeometry(cx, cy, _CHAR_ACTIVO, _CHAR_ACTIVO)
            conv_w = min(_CONV_W, W - 80)
            conv_h = min(_CONV_H, max(160, cy - 40))
            self._conversacion.setGeometry((W - conv_w) // 2, cy - conv_h - 8, conv_w, conv_h)
            self._badge.setVisible(False)   # en activo no se muestra el badge
        self.raise_()

    def showEvent(self, e):
        super().showEvent(e)
        self._aplicar_layout()
