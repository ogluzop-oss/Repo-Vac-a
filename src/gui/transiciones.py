"""
Transiciones globales de DESLIZAMIENTO al cambiar de pantalla (QStackedWidget) o de pestaña
(QTabWidget): la vista SALIENTE se desliza hacia la DERECHA y deja paso a la entrante.

Técnica basada en SNAPSHOT (no reparenta ni mueve los widgets vivos, así no rompe layouts ni foco):
al cambiar, se captura la vista anterior en un QLabel superpuesto y se anima ese overlay saliendo por
la derecha; la nueva vista ya está debajo. A prueba de fallos: cualquier error degrada a un cambio
instantáneo sin animación.

API:
    from src.gui.transiciones import instalar_transicion_tabs, instalar_transicion_stack
    instalar_transicion_tabs(qtabwidget)
    instalar_transicion_stack(qstackedwidget)
"""

import logging

from PyQt6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, Qt, QTimer
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QApplication, QLabel, QStackedWidget, QTabWidget, QWidget

logger = logging.getLogger("gui.transiciones")

_DUR = 240  # ms
_ESPERA_ASENTAMIENTO = 80  # ms — margen para que se asiente cualquier conflicto de geometría nativa
                           # de Windows (ver `abrir_dialogo_deslizante`) antes de empezar a animar


def _vivo(obj) -> bool:
    """True si `obj` sigue siendo un objeto Qt válido (su wrapper C++ no se ha destruido). Los
    callbacks `finished` de una QPropertyAnimation se disparan de forma ASÍNCRONA, FUERA del
    try/except de la función que arrancó la animación — si el widget objetivo (o su padre, p. ej. la
    ventana del módulo que se está abriendo) se ha destruido mientras tanto por cualquier motivo, un
    módulo especialmente lento en construirse puede dejar la animación "en vuelo" apuntando a un
    objeto ya liberado: tocarlo entonces revienta dentro del propio Qt6Widgets.dll (crash nativo, no
    una excepción de Python capturable) en vez de limpiamente. Comprobar esto ANTES de tocar el
    objeto es la mitigación estándar de PyQt para esta clase de fallo."""
    if obj is None:
        return False
    try:
        from PyQt6 import sip
        return not sip.isdeleted(obj)
    except Exception:
        return True


class StackedActual(QStackedWidget):
    """QStackedWidget cuyo tamaño depende SOLO de la página visible en cada momento, en vez del
    máximo de TODAS las páginas que ha contenido alguna vez (comportamiento por defecto de Qt:
    `sizeHint`/`minimumSizeHint` toman el máximo de TODOS los hijos, aunque estén ocultos). Sin
    esto, una página ancha (p. ej. un asistente con tablas/paneles grandes) deja "abultado" para
    siempre el tamaño mínimo del stack en cuanto se visita una vez, recortando el contenido de
    las demás páginas — aunque sean más estrechas — al quedar amarradas a un ancho que no es el
    suyo. Uso: sustituir `QStackedWidget()` por `StackedActual()` en cualquier navegación con
    páginas de anchos muy distintos entre sí."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.currentChanged.connect(lambda _i: self.updateGeometry())

    def sizeHint(self):
        w = self.currentWidget()
        return w.sizeHint() if w is not None else super().sizeHint()

    def minimumSizeHint(self):
        w = self.currentWidget()
        return w.minimumSizeHint() if w is not None else super().minimumSizeHint()


class TabsActual(QTabWidget):
    """Igual que `StackedActual` pero para `QTabWidget` (que internamente sufre el mismo problema:
    `sizeHint`/`minimumSizeHint` toman el máximo de TODAS las pestañas, no solo la visible). Uso:
    sustituir `QTabWidget()` por `TabsActual()` en cualquier ventana con pestañas de anchos muy
    distintos entre sí (p. ej. el Enterprise Shell, con pestañas construidas de golpe por
    lazy-loading tan pronto como se visitan)."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.currentChanged.connect(lambda _i: self.updateGeometry())

    def sizeHint(self):
        w = self.currentWidget()
        return w.sizeHint() if w is not None else super().sizeHint()

    def minimumSizeHint(self):
        w = self.currentWidget()
        return w.minimumSizeHint() if w is not None else super().minimumSizeHint()


def capturar_pantalla(widget) -> "QPixmap":
    """Como `widget.grab()`, pero con fondo SÓLIDO garantizado.

    `grab()` deja transparente cualquier zona que el propio widget no pinte
    explícitamente — habitual en un `QWidget` plano cuyo fondo solo viene de la hoja de
    estilo en cascada de la app (p. ej. `MenuPrincipal`, que da `background: transparent`
    a todos sus paneles internos y no pinta su propio fondo aparte). Un overlay hecho con
    ese `grab()` deja "asomar" el módulo real de debajo durante el deslizamiento (solo se
    ven opacos los botones/labels que sí se autopintan) en vez de taparlo por completo con
    la instantánea del menú. Aquí se rellena antes con el color de fondo de la app, así
    cualquier zona que el widget no pinte queda con ESE color, nunca transparente."""
    try:
        pm = QPixmap(widget.size())
        try:
            from assets.estilo_global import COLOR_FONDO_APP
            pm.fill(QColor(COLOR_FONDO_APP))
        except Exception:
            pm.fill(Qt.GlobalColor.black)
        widget.render(pm)
        return pm
    except Exception as e:
        logger.debug("capturar_pantalla: %s", e)
        try:
            return widget.grab()
        except Exception:
            return QPixmap()


def _deslizar(old_widget, new_widget, duracion: int, snapshot_viejo=None):
    """Efecto filmstrip: el SALIENTE (snapshot) se va por la derecha y el ENTRANTE (widget vivo) entra
    desde la izquierda, a la vez. El entrante SIEMPRE se anima (garantiza que el efecto se vea, aunque el
    snapshot del saliente falle). Todo relativo al PADRE del entrante (el stack interno del QTabWidget o
    el propio QStackedWidget).

    `snapshot_viejo` (opcional, QPixmap ya capturado): para el caso en que saliente y entrante son el
    MISMO widget (su contenido se repinta en el sitio en vez de cambiar de página de un stack/pestaña —
    p. ej. el sidebar de carpetas de Correo) — ahí `old_widget.grab()` en caliente ya mostraría el
    contenido NUEVO, así que el llamador captura la instantánea ANTES de repintar y la pasa aquí; en ese
    caso pásese `old_widget=None` (no hay nada que capturar en caliente)."""
    try:
        if new_widget is None:
            logger.warning("[DESLIZAR] abortado: new_widget es None")
            return
        cont = new_widget.parentWidget()
        if cont is None:
            logger.warning("[DESLIZAR] abortado: %r no tiene parentWidget()", new_widget)
            return
        w = cont.width()
        if w <= 0 or cont.height() <= 0:
            logger.warning("[DESLIZAR] abortado: contenedor %r con geometria invalida (w=%s, h=%s) "
                           "-> el widget entrante %r NO se mueve/anima, se queda con la posicion "
                           "que tuviera de antes", cont, w, cont.height(), new_widget)
            return
        g = new_widget.geometry()
        logger.info("[DESLIZAR] old=%r new=%r cont=%r w=%s g=%s snapshot_previo=%s",
                   old_widget, new_widget, cont, w, g, snapshot_viejo is not None)
        # (a) Saliente: snapshot deslizándose a la DERECHA (best-effort).
        try:
            if old_widget is not None or snapshot_viejo is not None:
                pm = snapshot_viejo if snapshot_viejo is not None else old_widget.grab()
                if pm.isNull():
                    logger.warning("[DESLIZAR] snapshot del saliente NULO (old_widget=%r, "
                                  "snapshot_viejo_dado=%s) -> sin overlay de salida",
                                  old_widget, snapshot_viejo is not None)
                if not pm.isNull():
                    ov = QLabel(cont); ov.setPixmap(pm); ov.setGeometry(g)
                    # Puramente visual (una instantánea saliendo de escena): SIN esto, si la ventana
                    # nativa de este QLabel tarda en destruirse a nivel de SO tras `deleteLater()`
                    # (asentado asíncrono de Windows, igual que el de showMaximized() documentado
                    # arriba), un clic real del usuario que caiga en esa zona mientras el HWND
                    # "zombi" todavía existe se lo traga ESTE overlay en vez de llegar al widget vivo
                    # de debajo — botones que se VEN bien pero no responden a NINGÚN clic. Reproducido
                    # de forma determinista con WindowFromPoint/SendInput reales tras encadenar varias
                    # transiciones (p. ej. registrar una merma y cambiar de pestaña): el HWND fantasma
                    # no pertenece a ningún widget vivo (no aparece por `internalWinId()` en ningún
                    # widget de la app) pero sigue "ganando" el pixel en WindowFromPoint. Con esta
                    # bandera, Windows enruta el clic real al widget de debajo pase lo que pase con el
                    # ciclo de vida nativo de este overlay.
                    ov.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                    ov.raise_(); ov.show()
                    a1 = QPropertyAnimation(ov, b"pos", ov)
                    a1.setDuration(int(duracion))
                    a1.setStartValue(g.topLeft())
                    a1.setEndValue(QPoint(g.x() + w, g.y()))
                    a1.setEasingCurve(QEasingCurve.Type.InOutCubic)
                    def _limpiar_overlay(ov=ov):
                        vivo = _vivo(ov)
                        logger.info("[DESLIZAR] overlay saliente terminado, vivo=%s -> %s",
                                   vivo, "deleteLater()" if vivo else "ya destruido")
                        if vivo:
                            ov.deleteLater()
                    a1.finished.connect(_limpiar_overlay)
                    a1.start(); ov._a = a1
                    logger.info("[DESLIZAR] overlay saliente creado y animando (id=%s)", id(ov))
        except Exception:
            logger.error("[DESLIZAR] fallo creando/animando el overlay saliente", exc_info=True)
        # (b) Entrante: widget vivo entrando desde la IZQUIERDA (garantizado).
        new_widget.raise_()
        a2 = QPropertyAnimation(new_widget, b"pos", new_widget)
        a2.setDuration(int(duracion))
        a2.setStartValue(QPoint(g.x() - w, g.y()))
        a2.setEndValue(g.topLeft())
        a2.setEasingCurve(QEasingCurve.Type.InOutCubic)

        def _asentar():
            if not _vivo(new_widget):
                return
            # NO usar la `g` capturada al iniciar la animación: si la ventana contenedora se
            # redimensiona MIENTRAS dura (240ms) —p. ej. el asentado asíncrono de Windows/DWM tras
            # un showMaximized() frameless, el mismo riesgo que ya evita `deslizar_entrada_modulo`
            # para la transición de entrada de módulo, pero que esta transición de pestaña/stack no
            # cubría— `g.topLeft()` queda obsoleto: el widget entrante se "asienta" en una posición
            # que ya no coincide con el área real del contenedor. Qt sigue PINTÁNDOLO ahí con
            # normalidad (nada fuerza un repintado que lo delate), pero su geometría de impacto para
            # el ratón queda desplazada — los botones se VEN en su sitio y dejan de responder al
            # clic. Se recalcula contra el tamaño ACTUAL del contenedor en vez de mover a `gp`.
            try:
                cont2 = new_widget.parentWidget()
                if cont2 is not None and cont2.width() > 0 and cont2.height() > 0:
                    new_widget.setGeometry(0, 0, cont2.width(), cont2.height())
                    logger.info("[DESLIZAR] _asentar: %r -> geometry(0,0,%s,%s)",
                               new_widget, cont2.width(), cont2.height())
                else:
                    logger.warning("[DESLIZAR] _asentar: contenedor sin geometria valida -> "
                                  "move(%s) de reserva", g.topLeft())
                    new_widget.move(g.topLeft())
            except Exception:
                logger.error("[DESLIZAR] _asentar: fallo recalculando geometria, usando move(%s) "
                             "de reserva", g.topLeft(), exc_info=True)
                try:
                    new_widget.move(g.topLeft())
                except Exception:
                    logger.error("[DESLIZAR] _asentar: tambien fallo el move() de reserva",
                                 exc_info=True)

        a2.finished.connect(_asentar)
        a2.start()
        new_widget._a_in = a2
        logger.info("[DESLIZAR] entrante %r animando: %s -> %s (dur=%sms)",
                   new_widget, a2.startValue(), a2.endValue(), duracion)
    except Exception as e:
        logger.error("[DESLIZAR] excepcion no controlada: %s", e, exc_info=True)


def deslizar_entrada_modulo(pm_saliente, ventana_entrante, duracion: int = _DUR, revelar=None,
                            al_cubrir=None):
    """Anima la ENTRADA a un módulo desde el menú principal.

    `pm_saliente` es una instantánea (QPixmap) de la pantalla anterior —el menú— capturada ANTES de
    ocultarlo; `ventana_entrante` es la ventana/contenedor del módulo ya mostrado y con geometría. La
    instantánea se superpone sobre él y se desliza hacia la DERECHA, dejándolo ver debajo — mismo lenguaje
    visual que `_deslizar` (el saliente sale por la derecha).

    - `revelar` (opcional): ventana abierta con `windowOpacity(0)` para evitar el destello de la ventana
      nativa; se revela (`opacity=1`) UNA VEZ ya está cubierta por la instantánea (caso: módulo en ventana
      propia). Así el primer fotograma visible es el menú, nunca blanco ni el módulo.
    - `al_cubrir` (opcional): callback que se ejecuta con la instantánea YA puesta encima (p. ej. cambiar la
      página del stack raíz al módulo), de modo que el cambio ocurre DEBAJO del overlay y no se ve
      (caso: TPV embebido en el stack).

    A prueba de fallos: cualquier error degrada a mostrar el módulo (revelar/cubrir) sin animación."""
    def _revelar():
        if revelar is not None:
            try:
                revelar.setWindowOpacity(1.0)
            except Exception:
                pass

    def _cubrir():
        if al_cubrir is not None:
            try:
                al_cubrir()
            except Exception:
                pass
    try:
        ov = None
        if (ventana_entrante is not None and pm_saliente is not None and not pm_saliente.isNull()):
            # `showMaximized()` en una ventana frameless recién creada puede asentar su
            # geometría real de forma asíncrona en Windows/DWM: si el overlay se mide
            # justo antes de que eso termine, queda más pequeño que la ventana ya
            # maximizada y el módulo real "asoma" por los bordes durante el deslizamiento
            # (parpadeo VISTO DURANTE la animación, no antes). Se procesan eventos
            # pendientes una vez más aquí para dar tiempo a que el resize se asiente...
            try:
                QApplication.processEvents()
            except Exception:
                pass
            # ...y, si la ventana está maximizada, se usa la geometría del ÁREA DE TRABAJO
            # de su pantalla (la misma que `manejar_apertura` ya le fijó antes de
            # maximizarla) en vez de `width()/height()`: así el tamaño del overlay no
            # depende de si el SO ya terminó de asentar la ventana o no.
            w, h = ventana_entrante.width(), ventana_entrante.height()
            try:
                if ventana_entrante.isMaximized():
                    _scr = ventana_entrante.screen()
                    if _scr is not None:
                        _geo = _scr.availableGeometry()
                        w, h = _geo.width(), _geo.height()
            except Exception:
                pass
            if w > 0 and h > 0:
                ov = QLabel(ventana_entrante)
                ov.setPixmap(pm_saliente)
                ov.setScaledContents(True)   # la instantánea (tamaño del menú) cubre exactamente el módulo
                ov.setGeometry(0, 0, w, h)
                # Ver el comentario equivalente en `_deslizar`: overlay puramente visual, nunca debe
                # poder tragarse un clic real aunque su HWND nativo tarde en morir tras `deleteLater()`.
                ov.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                ov.raise_()
                ov.show()
                ov.repaint()                 # pinta la instantánea YA (antes de cubrir/revelar)
        _cubrir()                            # el cambio de pantalla ocurre DEBAJO del overlay (no se ve)
        _revelar()                           # revelar la ventana ya cubierta: sin destello ni módulo previo
        if ov is None:
            return
        ov.raise_()                          # asegurar que sigue por encima tras el cambio de página
        a = QPropertyAnimation(ov, b"pos", ov)
        a.setDuration(int(duracion))
        a.setStartValue(QPoint(0, 0))
        a.setEndValue(QPoint(ov.width(), 0))
        a.setEasingCurve(QEasingCurve.Type.InOutCubic)
        a.finished.connect(lambda ov=ov: _vivo(ov) and ov.deleteLater())
        a.start()
        ov._a = a                            # evita el GC de la animación
    except Exception as e:
        logger.debug("deslizar_entrada_modulo: %s", e)
        _cubrir()
        _revelar()


def deslizar_refresco(widget, accion_refresco, duracion: int = _DUR):
    """Autotransición de DESLIZAMIENTO para refrescar un widget EN EL SITIO (mismo objeto, solo
    cambian sus datos) — a diferencia de `_deslizar`, pensado para DOS widgets distintos de un
    stack/tabs, aquí no hay una página "entrante" separada: el propio `widget` sigue siendo el
    mismo antes y después. Caso de uso: un panel con una única tabla persistente que cambia de
    filtro/categoría (p. ej. el Centro Documental, con 23 categorías compartiendo la misma
    `QTableWidget` en vez de una página por categoría) en lugar de navegar a una página nueva.

    Técnica (mismas primitivas que `_deslizar`/`deslizar_salida_y_cerrar`: `capturar_pantalla` +
    `QPropertyAnimation` con la misma duración/curva): se captura una instantánea de `widget` TAL
    COMO ESTÁ (el contenido "viejo"), se superpone, se ejecuta `accion_refresco()` (SÍNCRONO —
    debe dejar `widget` ya repintado con los datos NUEVOS antes de devolver el control) por
    DEBAJO de esa instantánea —así el refresco real ocurre tapado, sin parpadeo de tabla vacía a
    medio repintar—, y solo entonces se desliza la instantánea hacia la derecha para revelar el
    contenido ya actualizado — mismo lenguaje visual que el resto de la app (lo "saliente" sale
    por la derecha).

    A PRUEBA DE CLICS RÁPIDOS: si se llama de nuevo mientras la animación anterior de este mismo
    `widget` sigue en vuelo, esa instantánea anterior se retira DE INMEDIATO (oculta + programada
    para borrar, sin animar) antes de capturar la nueva — nunca queda una instantánea vieja
    "congelada" tapando datos ya actualizados por la llamada más reciente, y el contenido final
    siempre es el de la ÚLTIMA llamada (cada `accion_refresco` es síncrono, así que lo que hay
    bajo la instantánea nueva, en el momento de empezar a deslizarla, ya es siempre correcto).

    A prueba de fallos: si la instantánea falla (widget sin tamaño válido, excepción de render,
    sin padre), se ejecuta `accion_refresco()` sin animación."""
    estado = getattr(widget, "_refresco_deslizante", None)
    if estado is None:
        estado = {"ov": None, "anim": None}
        try:
            widget._refresco_deslizante = estado
        except Exception:
            pass

    # Retirar YA cualquier instantánea todavía en vuelo de una llamada anterior (clic rápido):
    # `stop()` no dispara `finished` (limpieza manual aquí) y `hide()` la quita de la vista al
    # instante, sin esperar al `deleteLater()` diferido.
    ov_previo = estado.get("ov")
    if ov_previo is not None and _vivo(ov_previo):
        try:
            anim_previo = estado.get("anim")
            if anim_previo is not None and _vivo(anim_previo):
                anim_previo.stop()
        except Exception:
            pass
        try:
            ov_previo.hide()
            ov_previo.deleteLater()
        except Exception:
            pass
    estado["ov"] = None
    estado["anim"] = None

    try:
        pm = capturar_pantalla(widget)
        if pm.isNull():
            raise ValueError("snapshot vacío")
        g = widget.geometry()
        cont = widget.parentWidget()
        if cont is None or g.width() <= 0 or g.height() <= 0:
            raise ValueError("geometría inválida")
    except Exception as e:
        logger.debug("deslizar_refresco (snapshot): %s", e)
        accion_refresco()
        return

    try:
        ov = QLabel(cont)
        ov.setPixmap(pm)
        ov.setGeometry(g)
        # Puramente visual: ver el comentario equivalente en `_deslizar` sobre por qué nunca debe
        # poder tragarse un clic real aunque su HWND nativo tarde en morir tras `deleteLater()`.
        ov.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        ov.raise_(); ov.show()
    except Exception as e:
        logger.debug("deslizar_refresco (overlay): %s", e)
        accion_refresco()
        return

    try:
        accion_refresco()   # el widget real, DEBAJO del overlay, ya queda con los datos nuevos
    except Exception as e:
        logger.debug("deslizar_refresco (accion_refresco): %s", e)
        try:
            ov.deleteLater()
        except Exception:
            pass
        estado["ov"] = None
        return

    try:
        ov.raise_()   # por si `accion_refresco` tocó el orden Z (p. ej. insertar filas)
        a = QPropertyAnimation(ov, b"pos", ov)
        a.setDuration(int(duracion))
        inicio = g.topLeft()
        a.setStartValue(inicio)
        a.setEndValue(QPoint(inicio.x() + g.width(), inicio.y()))
        a.setEasingCurve(QEasingCurve.Type.InOutCubic)

        def _fin(ov=ov, estado=estado):
            if _vivo(ov):
                ov.deleteLater()
            if estado.get("ov") is ov:   # nadie más lo ha sustituido entretanto
                estado["ov"] = None
                estado["anim"] = None

        a.finished.connect(_fin)
        estado["ov"] = ov
        estado["anim"] = a
        a.start()
    except Exception as e:
        logger.debug("deslizar_refresco (animación): %s", e)
        try:
            ov.deleteLater()
        except Exception:
            pass
        estado["ov"] = None
        estado["anim"] = None


def instalar_transicion_tabs(tabs, duracion: int = _DUR):
    """Instala la transición de deslizamiento en un QTabWidget (cambio de sub-pestaña). Idempotente."""
    try:
        if tabs.property("_trans_ok"):
            return tabs
        tabs.setProperty("_trans_ok", True)
        estado = {"w": tabs.currentWidget()}

        def _on_change(_idx):
            old = estado["w"]
            nuevo = tabs.currentWidget()
            estado["w"] = nuevo
            if nuevo is None or old is nuevo:
                return
            _deslizar(old, nuevo, duracion)

        tabs.currentChanged.connect(_on_change)
    except Exception as e:
        logger.debug("instalar_transicion_tabs: %s", e)
    return tabs


def instalar_transicion_stack(stack, duracion: int = _DUR):
    """Instala la transición de deslizamiento en un QStackedWidget (cambio de pantalla/sección). Idempotente."""
    try:
        if stack.property("_trans_ok"):
            return stack
        stack.setProperty("_trans_ok", True)
        estado = {"w": stack.currentWidget()}

        def _on_change(_idx):
            old = estado["w"]
            nuevo = stack.currentWidget()
            estado["w"] = nuevo
            if nuevo is None or old is nuevo:
                return
            _deslizar(old, nuevo, duracion)

        stack.currentChanged.connect(_on_change)
    except Exception as e:
        logger.debug("instalar_transicion_stack: %s", e)
    return stack


def instalar_transiciones_en(widget):
    """Propaga la transición a TODA la navegación de `widget` (una ventana/módulo): todos los QTabWidget
    (cambio de sub-pestaña) y los QStackedWidget de navegación (cambio de sección). Se EXCLUYEN los
    QStackedWidget INTERNOS de un QTabWidget (los gestiona su propio QTabWidget) para no duplicar la
    animación. Idempotente y a prueba de fallos: se puede llamar cada vez que se abre un módulo."""
    try:
        from PyQt6.QtWidgets import QStackedWidget, QTabWidget
        objetivos_tabs = list(widget.findChildren(QTabWidget))
        if isinstance(widget, QTabWidget):
            objetivos_tabs.append(widget)
        for tw in objetivos_tabs:
            instalar_transicion_tabs(tw)
        objetivos_stack = list(widget.findChildren(QStackedWidget))
        if isinstance(widget, QStackedWidget):
            objetivos_stack.append(widget)
        for st in objetivos_stack:
            if isinstance(st.parent(), QTabWidget):   # stack interno de un QTabWidget → NO animar aquí
                continue
            instalar_transicion_stack(st)
    except Exception as e:
        logger.debug("instalar_transiciones_en: %s", e)
    return widget


def instalar_cierre_deslizante(dialog, duracion: int = _DUR):
    """Anima la SALIDA de un QDialog de PANTALLA COMPLETA (mismo lenguaje visual que el resto: se
    desliza hacia la derecha) justo antes de cerrarlo de verdad — para cualquier vía de cierre
    (Aceptar/Cancelar/✕/Escape), todas pasan por `QDialog.done()` internamente en Qt, así que ese es
    el único punto que hace falta envolver. Idempotente (no se instala dos veces en el mismo diálogo).
    A prueba de fallos: si algo falla, cierra al instante sin animación.

    Mismo diseño que `deslizar_salida_y_cerrar` (ver su docstring para el porqué, incluidos los dos
    diseños descartados): el overlay es una ventana de nivel superior PROPIA (sin padre,
    `WindowStaysOnTopHint`), colocada sobre `dialog` y mostrada ANTES de cerrarlo de verdad
    (`original_done`) — así el cierre real ocurre tapado, sin parpadeo, y luego el overlay se desliza
    revelando lo que quede debajo."""
    try:
        if dialog.property("_cierre_deslizante_ok"):
            return
        dialog.setProperty("_cierre_deslizante_ok", True)
    except Exception:
        return
    estado = {"cerrando": False}
    original_done = dialog.done

    def _done(resultado):
        if estado["cerrando"]:
            original_done(resultado)
            return
        estado["cerrando"] = True
        try:
            pm = capturar_pantalla(dialog)
            if pm.isNull():
                raise ValueError("snapshot vacío")
            geo = dialog.geometry()
        except Exception as e:
            logger.debug("instalar_cierre_deslizante (snapshot): %s", e)
            original_done(resultado)
            return

        ov = None
        try:
            ov = QWidget(None)
            ov.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool |
                              Qt.WindowType.WindowStaysOnTopHint)
            ov.setGeometry(geo)
            lbl = QLabel(ov)
            lbl.setPixmap(pm)
            lbl.setScaledContents(True)
            lbl.setGeometry(0, 0, geo.width(), geo.height())
            ov.show()
            ov.repaint()
        except Exception as e:
            logger.debug("instalar_cierre_deslizante (overlay previo): %s", e)
            if ov is not None:
                try:
                    ov.close(); ov.deleteLater()
                except Exception:
                    pass
            original_done(resultado)
            return

        def _continuar():
            try:
                original_done(resultado)
            except Exception as e:
                logger.debug("instalar_cierre_deslizante (done): %s", e)
                try:
                    ov.close(); ov.deleteLater()
                except Exception:
                    pass
                return
            try:
                # Ver el comentario equivalente en `deslizar_salida_y_cerrar`: `original_done` puede
                # reactivar una ventana detrás y ganarle el primer plano al overlay un instante.
                ov.raise_()
                ov.repaint()
            except Exception:
                pass

            def _iniciar_animacion():
                try:
                    a = QPropertyAnimation(ov, b"pos", ov)
                    a.setDuration(int(duracion))
                    inicio = ov.pos()
                    a.setStartValue(inicio)
                    a.setEndValue(QPoint(inicio.x() + geo.width(), inicio.y()))
                    a.setEasingCurve(QEasingCurve.Type.InOutCubic)
                    a.finished.connect(lambda ov=ov: _vivo(ov) and ov.deleteLater())
                    ov._a_salida_deslizante = a
                    a.start()
                except Exception as e:
                    logger.debug("instalar_cierre_deslizante (animación): %s", e)
                    try:
                        ov.close(); ov.deleteLater()
                    except Exception:
                        pass

            # Un tick más antes del primer fotograma animado — ver el comentario equivalente en
            # `deslizar_salida_y_cerrar`.
            QTimer.singleShot(0, _iniciar_animacion)

        # Margen breve para que la ventana top-level del overlay se asiente a nivel de SO antes de
        # cerrar `dialog` de verdad — ver el comentario equivalente en `deslizar_salida_y_cerrar`.
        QTimer.singleShot(30, _continuar)

    dialog.done = _done


def abrir_dialogo_deslizante(dialog, origen, duracion: int = _DUR):
    """Abre un QDialog de PANTALLA COMPLETA (nunca uno pequeño) con la MISMA animación de
    deslizamiento de entrada/salida que el resto de la app: al abrir, `origen` (lo que había detrás,
    normalmente la ventana que lo abre) se desliza fuera dejando ver el diálogo; al cerrar (por
    cualquier vía), el propio diálogo se desliza fuera. Bloquea igual que `dialog.exec()` — devuelve
    su resultado. A prueba de fallos: si la animación de entrada falla, el diálogo se ve igual, solo
    sin efecto.

    El diálogo se MUESTRA aquí mismo (`dialog.show()`), cubierto de inmediato por el overlay de
    entrada, y se fuerza su primer pintado real con `dialog.repaint()` (SOLO este widget, síncrono)
    antes de arrancar la animación — así el pintado más costoso (todos sus widgets apareciendo por
    primera vez) ocurre ENTERO mientras el overlay ya lo tapa, en vez de competir por CPU con los
    primeros fotogramas de la animación. Se usa `repaint()` del diálogo, NUNCA
    `QApplication.processEvents()`: éste vacía la cola de TODA la aplicación, no solo la de este
    diálogo — puede sacar a relucir un pintado pendiente de OTRA ventana (p. ej. un fotograma sin
    terminar de aplicar el frameless/maximizado a la ventana TPV de origen) durante la propia
    animación, viéndose como una ventanita nativa suelta encima. `dialog.exec()` ya no necesita volver
    a mostrarlo — Qt no repite el show() si el diálogo ya está visible, solo entra en su bucle modal.

    ESPERA DE ASENTAMIENTO (`_ESPERA_ASENTAMIENTO` ms) antes de arrancar el propio deslizamiento:
    algunos campos (`_ScrollCombo`/`_FechaFilter`, usados en Buscar/Reimprimir ticket Y en Devolución
    de ticket — ver sus definiciones) provocan en Windows un conflicto real de geometría nativa nada
    más realizarse (`QWindowsWindow::setGeometry: Unable to set geometry...`, visible en el log de la
    app), que consume CPU justo al mostrar el diálogo. El overlay ya cubre el diálogo por completo en
    ese instante (`repaint()` ya lo pintó), así que ese conflicto no se ve — pero si la animación
    arrancara EN ESE MISMO instante, competiría por CPU con él y se vería a trompicones. Este margen
    deja que se resuelva primero, con el overlay quieto (sin cambio visual), antes de deslizar.

    REAFIRMACIÓN TRAS EL ASENTAMIENTO (bug real, `_PreciosBolsasDialog` abriendo pequeño pese al
    `showEvent` + la reafirmación de arriba): el conflicto nativo que describe el párrafo anterior no
    es solo cosmético — en Windows puede dejar el HWND frameless con una geometría MENOR que la
    pedida, y eso ocurre DESPUÉS de que `showEvent()` ya disparó (que reafirma una vez, pero
    demasiado pronto: nada más `show()`, antes de que ese conflicto nativo se resuelva). Sin volver a
    reafirmar la geometría una vez pasado `_ESPERA_ASENTAMIENTO` (que es precisamente el margen que ya
    se da para que ese conflicto se resuelva), el diálogo se quedaba con la geometría pequeña que dejó
    el HWND al asentarse, aunque `showEvent()` la hubiera corregido un instante antes. Deliberadamente
    NO se usa `QApplication.processEvents()` para forzar ese asentamiento (ver el porqué arriba,
    mismo motivo que evita usarlo para el primer pintado): el propio `QTimer.singleShot` ya cede el
    control al bucle de eventos real durante `_ESPERA_ASENTAMIENTO`, que es cuando ese conflicto se
    resuelve por sí solo — ahí, justo antes de arrancar la animación, es el único punto correcto para
    reafirmar.

    SIN FOTOGRAMA VISIBLE HASTA ASENTAR (bug real: parpadeo al tamaño pequeño DURANTE la propia
    animación de entrada): la reafirmación de arriba corrige la geometría a tiempo de que la
    ANIMACIÓN arranque ya con el tamaño bueno — pero entre el `show()` de más abajo y esa reafirmación
    (la ventana de `_ESPERA_ASENTAMIENTO`) el diálogo YA está en pantalla, al tamaño que el HWND haya
    asentado en ese instante (potencialmente el pequeño). El overlay que lo cubre es HIJO del propio
    diálogo (`QLabel(dialog)`), así que su área visible queda recortada al tamaño real del HWND — si
    éste es el pequeño, el overlay (pensado para tapar el diálogo entero) también se ve pequeño, y el
    usuario alcanza a ver esa ventana chica un instante antes de que la segunda reafirmación la
    corrija. Para que no haya NINGÚN fotograma así, el diálogo se mantiene con `setWindowOpacity(0.0)`
    (invisible pero YA mostrado — `show()` no se repite) desde antes de este `show()` hasta que
    `_reafirmar_tras_asentamiento` ha corregido la geometría (de él y de su overlay); solo entonces se
    restaura la opacidad y arranca el deslizamiento, ya con la geometría definitiva. Mientras el
    diálogo está invisible, lo único que ve el usuario es `origen` tal cual estaba — visualmente
    idéntico al propio overlay (que no es más que una instantánea de `origen`), así que ocultar el
    diálogo entero en vez de solo taparlo no cambia nada perceptible. Reafirmar TAMBIÉN se sigue
    haciendo con el mismo `QTimer.singleShot` (nunca `processEvents()`, mismo motivo de siempre); la
    opacidad es ortogonal a eso, solo evita que se vea lo que hay DEBAJO de esa corrección mientras
    llega. A prueba de fallos: cualquier excepción en el camino restaura la opacidad de inmediato
    (`_revelar()`), para no dejar el diálogo modal abierto pero invisible.

    FUERA DE PANTALLA ADEMÁS DE OPACIDAD 0 (bug real: diálogos de contenido pesado —p. ej. la
    báscula de venta a granel, con decenas de botones de producto con imagen— se veían "encoger y
    volver a su tamaño" justo antes de deslizar, pese a lo de arriba): cuanto más tarda el primer
    `repaint()` real (más widgets/imágenes que pintar de golpe), más margen hay para que el
    compositor de Windows presente igualmente un fotograma del HWND mientras la opacidad 0 todavía
    no ha terminado de propagarse — `setWindowOpacity` depende de que el driver/compositor respete
    la ventana en capas (layered window) a tiempo, y con un primer pintado lo bastante largo esa
    garantía deja de ser absoluta. Mientras se asienta, el diálogo vive además DESPLAZADO fuera de
    cualquier pantalla real (mismo tamaño que le corresponda, solo la X trasladada bien lejos) — así,
    aunque algún fotograma se presente con la opacidad todavía sin aplicar, cae fuera del área visible
    de cualquier monitor y no se ve. `_revelar()` es el único punto que lo trae de vuelta a su
    posición real, a la vez que restaura la opacidad — nunca por separado, para que el primer
    fotograma en la posición correcta ya sea también el primero a opacidad 1."""
    instalar_cierre_deslizante(dialog, duracion)
    try:
        snap = capturar_pantalla(origen) if origen is not None else None
    except Exception:
        snap = None

    # Reafirmar la geometría a pantalla completa SIEMPRE, fuera del bloque condicionado a la
    # instantánea de `origen`: antes esta corrección vivía DENTRO de `if snap is not None and not
    # snap.isNull()`, así que si `capturar_pantalla(origen)` fallaba (excepción de render, `origen`
    # con tamaño degenerado en ese instante, etc.) el diálogo se quedaba con la geometría puesta en su
    # propio `__init__` vía `QApplication.primaryScreen()` — la pantalla PRIMARIA del SO, que no tiene
    # por qué ser la pantalla donde vive de verdad el TPV (equipo con pantalla de cliente,
    # `_customer_display`) ni haber asentado ya su tamaño real a nivel de SO bajo `FramelessWindowHint`
    # (creación diferida del HWND nativo). `dialog.screen()` es la pantalla REAL de este diálogo, y
    # reafirmar contra su ÁREA DE TRABAJO (la misma fuente de verdad, sea cual sea el estado de
    # asentado) es lo que de verdad evita que el diálogo abra más pequeño que la pantalla.
    geo = dialog.geometry()
    try:
        scr = dialog.screen() or QApplication.primaryScreen()
        geo = scr.availableGeometry() if scr is not None else dialog.rect()
    except Exception as e:
        logger.debug("abrir_dialogo_deslizante geometría: %s", e)

    def _version_oculta(g):
        # Misma anchura/altura, trasladada bien lejos de cualquier disposición de monitores
        # razonable (ver docstring "FUERA DE PANTALLA ADEMÁS DE OPACIDAD 0").
        return QRect(g.x() - 6000, g.y(), g.width(), g.height())

    try:
        geo_oculta_inicial = _version_oculta(geo)
        if dialog.geometry() != geo_oculta_inicial:
            dialog.setGeometry(geo_oculta_inicial)
    except Exception as e:
        logger.debug("abrir_dialogo_deslizante geometría oculta: %s", e)

    # Invisible hasta asentar (ver docstring "SIN FOTOGRAMA VISIBLE HASTA ASENTAR"): nada se ve de
    # este diálogo hasta que la geometría quede definitiva y `_revelar()` restaure la opacidad.
    _opacidad_restaurada = [False]
    _geo_final = [geo]

    def _revelar():
        if _opacidad_restaurada[0]:
            return
        _opacidad_restaurada[0] = True
        try:
            if _vivo(dialog):
                dialog.setGeometry(_geo_final[0])
                dialog.setWindowOpacity(1.0)
        except Exception as e:
            logger.debug("abrir_dialogo_deslizante revelar: %s", e)

    try:
        dialog.setWindowOpacity(0.0)
    except Exception as e:
        logger.debug("abrir_dialogo_deslizante ocultar: %s", e)

    def _reafirmar_tras_asentamiento(ov=None):
        """Segunda reafirmación, tras `_ESPERA_ASENTAMIENTO` (ver docstring): corrige la geometría
        si el conflicto nativo de Windows la dejó pequeña DESPUÉS de `showEvent()`. Sigue aplicando
        la versión OCULTA (fuera de pantalla) de esa geometría corregida — `_revelar()` es quien
        trae el diálogo a su posición real, nunca esta función. Si hay overlay (`ov`, la instantánea
        de `origen`), se redimensiona con ella para seguir cubriendo el diálogo entero — si no, el
        overlay quedaría más pequeño que el diálogo ya corregido y se vería el contenido real
        asomando por los bordes durante el deslizamiento."""
        if not _vivo(dialog):
            return
        try:
            scr2 = dialog.screen() or QApplication.primaryScreen()
            geo2 = scr2.availableGeometry() if scr2 is not None else None
            if geo2 is not None:
                _geo_final[0] = geo2
                geo2_oculta = _version_oculta(geo2)
                if dialog.geometry() != geo2_oculta:
                    dialog.setGeometry(geo2_oculta)
                if ov is not None and _vivo(ov):
                    ov.setGeometry(0, 0, geo2.width(), geo2.height())
        except Exception as e:
            logger.debug("abrir_dialogo_deslizante reafirmar: %s", e)

    if snap is not None and not snap.isNull():
        try:
            ov = QLabel(dialog)
            ov.setPixmap(snap)
            ov.setScaledContents(True)
            ov.setGeometry(0, 0, geo.width(), geo.height())
            ov.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            dialog.show()
            ov.raise_(); ov.show(); ov.repaint()
            dialog.repaint()
            a = QPropertyAnimation(ov, b"pos", ov)
            a.setDuration(int(duracion))
            a.setStartValue(QPoint(0, 0))
            a.setEndValue(QPoint(ov.width(), 0))
            a.setEasingCurve(QEasingCurve.Type.InOutCubic)
            a.finished.connect(lambda ov=ov: _vivo(ov) and ov.deleteLater())
            dialog._a_entrada_deslizante = a

            def _asentar_y_animar(ov=ov, a=a):
                _reafirmar_tras_asentamiento(ov)
                # Geometría ya definitiva: revelar ANTES de animar, nunca durante ni después — así el
                # primer fotograma visible ya es el correcto (overlay a tamaño bueno, en posición
                # (0,0), indistinguible de `origen`), y el deslizamiento arranca desde ahí.
                _revelar()
                if _vivo(a):
                    # El ancho pudo cambiar en la reafirmación: recalcula el punto de salida.
                    a.setEndValue(QPoint(ov.width(), 0))
                    a.start()
            QTimer.singleShot(_ESPERA_ASENTAMIENTO, _asentar_y_animar)
        except Exception as e:
            logger.debug("abrir_dialogo_deslizante entrada: %s", e)
            _revelar()
    else:
        dialog.show()

        def _asentar_sin_overlay():
            _reafirmar_tras_asentamiento()
            _revelar()
        QTimer.singleShot(_ESPERA_ASENTAMIENTO, _asentar_sin_overlay)
    return dialog.exec()


def deslizar_salida_y_cerrar(widget, cerrar_fn, duracion: int = _DUR):
    """Anima la SALIDA de una ventana hija a PANTALLA COMPLETA que es un `QWidget` plano (no un
    QDialog) — p. ej. las abiertas con `TPVWindow._abrir_ventana_completa` (Facturas, Stock, Buscar/
    Reimprimir ticket, Devolución...).

    El overlay es una ventana de nivel superior PROPIA (sin padre, `WindowStaysOnTopHint`), NO un hijo
    de `widget`: se coloca encima de `widget`, en su misma posición y tamaño de pantalla, y se muestra
    ANTES de cerrar nada. Solo ENTONCES se llama a `cerrar_fn` (el cierre real:
    `close()`+`deleteLater()`+volver al padre, que YA se encarga de dejarlo visible/activo) — ese cierre
    ocurre tapado por el overlay, así que cualquier parpadeo/transparencia del cierre real de `widget`
    (un `QDialog`/`QWidget` nativo cerrándose de verdad no es instantáneo a nivel de SO) queda oculto
    detrás. Recién entonces se anima el propio overlay saliendo, revelando lo que `cerrar_fn` ya dejó
    visible debajo — no hace falta que esta función sepa qué es.

    Dos diseños anteriores descartados, cada uno con su propio defecto real:
    - Overlay hijo de `widget`: al deslizarlo, dejaba ver la propia ventana viva e inmóvil debajo —
      efecto "ventana duplicada".
    - Cerrar `widget` ANTES de montar el overlay (hijo del padre): entre que `widget` desaparece de
      verdad y el overlay llega a cubrir ese hueco, había un instante sin nada cubriendo esa zona de
      pantalla — se veía como un parpadeo/transparencia justo antes de empezar a deslizar.
    Con el overlay ya cubriendo ANTES de tocar `widget`, no hay hueco en ningún momento.

    A prueba de fallos: si algo falla, cierra al instante sin efecto."""
    try:
        pm = capturar_pantalla(widget)
        if pm.isNull():
            raise ValueError("snapshot vacío")
        geo = widget.geometry()
    except Exception as e:
        logger.debug("deslizar_salida_y_cerrar (snapshot): %s", e)
        cerrar_fn()
        return

    ov = None
    try:
        ov = QWidget(None)
        ov.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool |
                          Qt.WindowType.WindowStaysOnTopHint)
        ov.setGeometry(geo)
        lbl = QLabel(ov)
        lbl.setPixmap(pm)
        lbl.setScaledContents(True)
        lbl.setGeometry(0, 0, geo.width(), geo.height())
        ov.show()
        ov.repaint()
    except Exception as e:
        logger.debug("deslizar_salida_y_cerrar (overlay previo): %s", e)
        if ov is not None:
            try:
                ov.close(); ov.deleteLater()
            except Exception:
                pass
        cerrar_fn()
        return

    # `widget.hide()` AQUÍ, síncrono, en el mismo tick que el overlay ya lo cubre — no se deja en
    # manos de `cerrar_fn` (llamado más abajo, DIFERIDO 30ms): para el caso normal (Facturas/Stock...)
    # `cerrar_fn` hace `close()` igualmente, así que esto es redundante pero inofensivo. Pero cuando
    # `cerrar_fn` NO cierra `widget` — porque quien lo cierra de verdad es código EXTERNO que corre
    # justo después de que esta función entera retorne (caso Gestión Caja → TPV: `ejecutar_regreso()`
    # llama a este callback y LUEGO, por su cuenta, a `self.close()`) — sin este hide síncrono, ese
    # cierre externo llega DESPUÉS y más lento que un simple hide (un `close()` de ventana nativa
    # implica más trabajo de SO), dejando un hueco real bajo el overlay pese a que ya está "encima".
    try:
        widget.hide()
    except Exception as e:
        logger.debug("deslizar_salida_y_cerrar (hide previo): %s", e)
        cerrar_fn()
        return

    def _continuar():
        try:
            cerrar_fn()
        except Exception as e:
            logger.debug("deslizar_salida_y_cerrar (cerrar_fn): %s", e)
            try:
                ov.close(); ov.deleteLater()
            except Exception:
                pass
            return
        try:
            # `cerrar_fn` normalmente hace `show()`/`raise_()`/`activateWindow()` sobre lo que queda
            # detrás (p. ej. reactivar el TPV) — esa activación de ventana puede ganarle el primer
            # plano al overlay un instante, pese a `WindowStaysOnTopHint`: se veía como un parpadeo
            # transparente mostrando lo de detrás ANTES de que la animación llegara a arrancar. Se
            # reafirma aquí que el overlay sigue encima y se repinta justo antes de animar.
            ov.raise_()
            ov.repaint()
        except Exception:
            pass

        def _iniciar_animacion():
            try:
                a = QPropertyAnimation(ov, b"pos", ov)
                a.setDuration(int(duracion))
                inicio = ov.pos()
                a.setStartValue(inicio)
                a.setEndValue(QPoint(inicio.x() + geo.width(), inicio.y()))
                a.setEasingCurve(QEasingCurve.Type.InOutCubic)
                a.finished.connect(lambda ov=ov: _vivo(ov) and ov.deleteLater())
                ov._a_salida_deslizante = a
                a.start()
            except Exception as e:
                logger.debug("deslizar_salida_y_cerrar (animación): %s", e)
                try:
                    ov.close(); ov.deleteLater()
                except Exception:
                    pass

        # Un tick más ANTES de la primera imagen animada: le da tiempo al compositor de Windows a
        # asentar de verdad el reordenamiento Z que acaba de provocar `raise_()` (la activación de
        # ventana de `cerrar_fn` puede tardar un pelín más que un simple `raise_()` en resolverse del
        # todo) — sin esto, el primer fotograma de la propia animación podía nacer ya con el hueco.
        QTimer.singleShot(0, _iniciar_animacion)

    # Margen breve entre "el overlay ya está mostrado" y "cerrar de verdad": crear una ventana de
    # nivel superior NUEVA (el propio overlay) también tarda un pelín en asentarse a nivel de SO
    # (mismo tipo de latencia de composición ya visto en `_ESPERA_ASENTAMIENTO`, aquí mucho más corta
    # porque el overlay es una superficie opaca simple, sin los widgets problemáticos de los diálogos)
    # — sin este margen, quedaba un resto de parpadeo justo al principio.
    QTimer.singleShot(30, _continuar)


def instalar_pestanas_lazy(tabs, entradas):
    """Registra pestañas de `tabs` (QTabWidget) con carga perezosa (lazy loading): añade un
    placeholder por cada `(titulo, factory)` de `entradas` y construye el contenido real —
    `factory()`, una función sin argumentos que devuelve el QWidget de esa pestaña — la primera
    vez que el usuario la visita, sustituyendo el placeholder sin perder su posición ni su título.

    Pensado para módulos con varias pestañas caras de construir (consultas a BD o ventanas
    completas embebidas durante su propio __init__): antes había que construirlas TODAS antes de
    mostrar el módulo. La pestaña que ya está visible al llamar a esta función (`tabs.currentIndex()`,
    normalmente la 0, añadida por el propio módulo ANTES de llamar aquí) se construye de inmediato;
    el resto solo al visitarlas. Idempotente por pestaña; a prueba de fallos (una `factory` que
    lance una excepción simplemente no se atrapa aquí — debe degradar internamente, como ya hacen
    `_construir_tab_*` en los módulos que usan esto)."""
    pendientes = {}
    for titulo, factory in entradas:
        idx = tabs.addTab(QWidget(), titulo)
        pendientes[idx] = factory

    def _asegurar(idx):
        factory = pendientes.pop(idx, None)
        if factory is None:
            return
        nuevo = factory()
        # El contenido real se construye AHORA, después de que el módulo llamara a
        # `instalar_transiciones_en` sobre sí mismo — un QTabWidget propio que viva dentro de
        # `nuevo` (p. ej. el de SATDashboardWindow embebido en CRM) nunca llegó a existir en
        # aquel momento, así que ese barrido nunca lo encontró. Se repite aquí, solo sobre el
        # widget recién construido, para que sus propias sub-pestañas también deslicen.
        try:
            instalar_transiciones_en(nuevo)
        except Exception as e:
            logger.debug("instalar_pestanas_lazy._asegurar: %s", e)
        titulo_tab = tabs.tabText(idx)
        viejo = tabs.widget(idx)
        tabs.blockSignals(True)   # removeTab/insertTab también emiten currentChanged
        try:
            tabs.removeTab(idx)
            tabs.insertTab(idx, nuevo, titulo_tab)
            tabs.setCurrentIndex(idx)
        finally:
            tabs.blockSignals(False)
        if viejo is not None:
            viejo.deleteLater()

    tabs.currentChanged.connect(_asegurar)
    _asegurar(tabs.currentIndex())
