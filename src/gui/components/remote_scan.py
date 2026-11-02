"""
Escaneo remoto — botón reutilizable "📱" que delega un escaneo de código de barras/QR (o, en modo
`tipo="foto"`, una FOTO) al móvil del propio usuario, en vez de depender de un diálogo de cámara del PC
(torpe: los 3 existentes en el proyecto usan la webcam del ordenador). Consume
`POST/GET /api/v1/remote-scan/*` (`src/api/routers/escaneo_remoto.py`) por sondeo REST corto — sin
push/SSE, ver el docstring de `services/escaneo_remoto.py` para el porqué.

Uso (código) — se AÑADE junto a cualquier campo existente, sin tocar su lógica de búsqueda:

    from src.gui.components.remote_scan import agregar_boton_escaneo_movil
    boton = agregar_boton_escaneo_movil(
        parent, on_result=lambda v: (self.search_bar.setText(v), self._buscar()),
        contexto="mermas.buscar_articulo")
    layout.addWidget(boton)

Uso (foto) — mismo patrón, `on_result` recibe el `id_documento` de la foto ya guardada en el registro
documental (no una ruta local: la foto la toma y sube el MÓVIL, nunca el PC):

    from src.gui.components.remote_scan import agregar_boton_foto_movil
    boton = agregar_boton_foto_movil(
        parent, on_result=self._on_foto_movil, contexto="mermas.foto_evidencia")

Vive en `gui/components/` (regla de CLAUDE.md: todo widget compartido NUEVO va aquí, no copiado en
cada pantalla ni en `catalogo_gestion.py`).
"""

import logging
import os

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QDialog, QLabel, QPushButton

from src.gui.catalogo_gestion import _BG, _CIAN, _DIM, _FONT, _dialogo_frameless
from src.gui.foundation import tokens as T

try:
    from assets.estilo_global import mostrar_mensaje
except Exception:  # pragma: no cover
    mostrar_mensaje = None

logger = logging.getLogger("gui.remote_scan")

_POLL_MS = 1500
_MAX_INTENTOS = 130  # ~3.25 min a 1.5s/intento — algo más que el TTL de 3 min del servidor


def _base_url() -> str:
    puerto = int(os.environ.get("BACKEND_PORT", os.environ.get("PORT", "8090")))
    return f"http://127.0.0.1:{puerto}/api/v1"


def _token_desktop() -> str | None:
    """Token de acceso emitido AL VUELO para el usuario de la sesión de escritorio (que no tiene JWT
    propio — solo accede a BD directamente). No se persiste: solo vive mientras dura esta llamada.

    `centro_codigo` del token se resuelve con la TIENDA ACTIVA del proceso (`tienda_actual_id()`,
    la que fija "Cambiar de centro"), no con `usuarios.centro_codigo` a secas: un SUPERADMIN no
    tiene centro fijo propio (flota entre varios) — su `centro_codigo` de BD es NULL, así que sin
    este resolver la solicitud de escaneo remoto fallaba con "sin tienda/almacén asignado" incluso
    con una tienda activa recién seleccionada. Para un empleado normal (un único centro, fijado en
    el login — `db/usuario.py::login` ya hace `set_tienda_actual(centro_codigo)`) el resultado es
    el mismo de siempre: no cambia su comportamiento."""
    try:
        from src.db.usuario import sesion_global
        from src.seguridad import tokens
        usuario = sesion_global.usuario_actual
        if not usuario:
            return None
        centro = _centro_codigo_activo() or usuario.get("centro_codigo")
        if centro != usuario.get("centro_codigo"):
            usuario = {**usuario, "centro_codigo": centro}
        return tokens.emitir_access(usuario)
    except Exception as e:
        logger.error("_token_desktop: %s", e)
        return None


def _centro_codigo_activo() -> str | None:
    """`codigo_tienda` de la tienda ACTIVA del proceso — delega en `db.tiendas.codigo_tienda_actual`
    (resolutor ÚNICO, reutilizado también por `services.rfid.hardware.resolver_gateway` para la
    config del lector RFID: mismo criterio "centro activo efectivo", no duplicado dos veces)."""
    try:
        from src.db import tiendas as tiendas_db
        return tiendas_db.codigo_tienda_actual()
    except Exception as e:
        logger.debug("_centro_codigo_activo: %s", e)
        return None


class _EsperandoEscaneoDialog(QDialog):
    """Diálogo modal simple: crea la solicitud, sondea su estado y se cierra sola al resolverse.
    `tipo`: 'codigo' (comportamiento original) o 'foto' (el móvil responde con una foto; `on_result`
    recibe el `id_documento` en vez de un valor escaneado — el sondeo es idéntico en ambos casos, el
    campo `valor_escaneado` es un string opaco para este diálogo)."""

    def __init__(self, contexto, on_result, parent=None, tipo="codigo"):
        super().__init__(parent)
        self._on_result = on_result
        self._contexto_valor = contexto
        self._tipo = tipo if tipo in ("codigo", "foto") else "codigo"
        self._id_solicitud = None
        self._intentos = 0
        self._resuelto = False

        titulo = "📸  FOTO REMOTA" if self._tipo == "foto" else "📱  ESCANEO REMOTO"
        body = _dialogo_frameless(self, titulo, ancho=360)
        self._lbl = QLabel("Creando solicitud…")
        self._lbl.setStyleSheet(
            f"color:{T.TEXT};font-family:'{_FONT}';font-size:13px;font-weight:900;")
        self._lbl.setWordWrap(True)
        self._lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.addWidget(self._lbl)

        sub_texto = ("Abre Smart Manager en tu móvil → haz la foto cuando te avise"
                     if self._tipo == "foto" else "Abre Smart Manager en tu móvil → Escaneo remoto")
        sub = QLabel(sub_texto)
        sub.setStyleSheet(f"color:{_DIM};font-family:'{_FONT}';font-weight:900;font-size:11px;")
        sub.setWordWrap(True)
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.addWidget(sub)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._sondear)

        QTimer.singleShot(0, self._crear_solicitud)

    def _crear_solicitud(self):
        import requests
        token = _token_desktop()
        if not token:
            self._lbl.setText("No se pudo identificar la sesión de escritorio.")
            return
        try:
            r = requests.post(
                f"{_base_url()}/remote-scan/requests",
                json={"contexto": self._contexto(), "tipo": self._tipo},
                headers={"Authorization": f"Bearer {token}"}, timeout=5)
            datos = r.json()
        except Exception as e:
            logger.error("crear_solicitud: %s", e)
            datos = {}
        if not datos.get("ok"):
            self._lbl.setText(datos.get("error") or "No se pudo crear la solicitud de escaneo.")
            return
        self._id_solicitud = datos["id"]
        self._lbl.setText("Esperando escaneo desde el móvil…")
        self._timer.start(_POLL_MS)

    def _contexto(self):
        return self._contexto_valor

    def _sondear(self):
        import requests
        if not self._id_solicitud:
            return
        self._intentos += 1
        if self._intentos > _MAX_INTENTOS:
            self._timer.stop()
            self._lbl.setText("Tiempo de espera agotado.")
            QTimer.singleShot(1200, self.reject)
            return
        token = _token_desktop()
        if not token:
            return
        try:
            r = requests.get(
                f"{_base_url()}/remote-scan/requests/{self._id_solicitud}",
                headers={"Authorization": f"Bearer {token}"}, timeout=5)
            fila = r.json() if r.ok else None
        except Exception as e:
            logger.debug("sondear: %s", e)
            return
        if not fila:
            return
        estado = fila.get("estado")
        if estado == "completado":
            self._timer.stop()
            self._resuelto = True
            valor = fila.get("valor_escaneado")
            self.accept()
            if self._on_result and valor:
                self._on_result(valor)
        elif estado in ("cancelado", "expirado"):
            self._timer.stop()
            self._lbl.setText("Solicitud cancelada." if estado == "cancelado" else "La solicitud caducó.")
            QTimer.singleShot(1200, self.reject)

    def reject(self):
        """Botón rojo ✕ de `_dialogo_frameless` (único cierre manual ahora que se quitó el botón
        "Cancelar" redundante): debe cancelar también la solicitud en el servidor, no solo cerrar la
        ventana — si no, quedaría una solicitud de escaneo "pendiente" huérfana esperando un móvil
        que ya nadie va a usar."""
        self._timer.stop()
        if self._id_solicitud and not self._resuelto:
            self._cancelar_en_servidor()
        super().reject()

    def _cancelar_en_servidor(self):
        import requests
        token = _token_desktop()
        if not token:
            return
        try:
            requests.post(
                f"{_base_url()}/remote-scan/requests/{self._id_solicitud}/cancel",
                headers={"Authorization": f"Bearer {token}"}, timeout=5)
        except Exception as e:
            logger.debug("cancelar_en_servidor: %s", e)

    def closeEvent(self, ev):
        self._timer.stop()
        super().closeEvent(ev)


def iniciar_escaneo_movil(parent, on_result, *, contexto: str = "generico", tipo: str = "codigo") -> None:
    """Abre DIRECTAMENTE el diálogo de escaneo remoto (sin crear ningún botón) — para reutilizar como
    manejador de clic de un botón YA EXISTENTE (p. ej. el antiguo "📷 SCAN" que abría la webcam del PC:
    tras la Fase de retirada de escaneo por webcam, el escaneo remoto es el ÚNICO método, así que estos
    botones ahora llaman aquí en vez de abrir un diálogo de cámara). Mismo comportamiento que el botón
    "📱" de `agregar_boton_escaneo_movil`, extraído para poder dispararlo desde cualquier otro control."""
    dlg = _EsperandoEscaneoDialog(contexto, on_result, parent, tipo=tipo)
    dlg.exec()


def agregar_boton_escaneo_movil(parent, on_result, *, contexto: str = "generico") -> QPushButton:
    """Crea (sin añadir a ningún layout) el botón "📱" que abre el diálogo de escaneo remoto. `on_result`
    se llama con el valor escaneado (str) cuando el móvil completa la solicitud."""
    return _crear_boton(parent, "📱", "Escanear con el móvil",
                        lambda: iniciar_escaneo_movil(parent, on_result, contexto=contexto))


def agregar_boton_foto_movil(parent, on_result, *, contexto: str = "generico") -> QPushButton:
    """Crea (sin añadir a ningún layout) el botón "📸" que pide una FOTO al móvil del propio usuario en
    vez de un código escaneado. `on_result` se llama con el `id_documento` (str) de la foto ya guardada
    en el registro documental cuando el móvil completa la solicitud."""
    return _crear_boton(parent, "📸", "Hacer foto con el móvil",
                        lambda: iniciar_escaneo_movil(parent, on_result, contexto=contexto, tipo="foto"))


def _crear_boton(parent, icono: str, tooltip: str, on_click) -> QPushButton:
    boton = QPushButton(icono, parent)
    boton.setToolTip(tooltip)
    boton.setCursor(Qt.CursorShape.PointingHandCursor)
    # 46x46 con padding:0 explícito: sin esto, el padding interno por defecto de QPushButton (varía
    # según el estilo de la plataforma) recorta el emoji dentro de un tamaño fijo pequeño, dejando
    # visible solo una porción — el bug de "icono cortado" reportado.
    boton.setFixedSize(46, 46)
    boton.setStyleSheet(
        f"QPushButton{{background:{_BG};color:{_CIAN};border:2px solid {_CIAN};border-radius:10px;"
        f"font-size:20px;padding:0;margin:0;}}"
        f"QPushButton:hover{{background:{_CIAN};color:{_BG};}}"
    )
    boton.clicked.connect(on_click)
    return boton
