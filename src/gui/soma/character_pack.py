"""
Character Pack de SOMA (Fase 2). Carga las ilustraciones maestras del personaje de forma AGNÓSTICA
al formato (PNG · Sprite Sheet · GIF/APNG · PNG+transformaciones), detrás de un único punto. Si un
asset falta, entrega un placeholder dibujado para que la app funcione durante el desarrollo.

El personaje YA está diseñado por el usuario; este módulo SOLO lo integra (no lo genera ni altera).
La lógica de estados vive en el SomaKernel; aquí solo se resuelve "estado → recurso visual".
"""

import json
import logging
import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QMovie, QPainter, QPixmap

logger = logging.getLogger("gui.soma.character_pack")

# Carpeta oficial del pack.
_DIR = os.path.join(os.getcwd(), "assets", "soma")

# Mapa: estado del Kernel → clave de ilustración del pack (+ alternativas). Refleja el modelo de
# poses pedido: ESPERANDO(activo-inactivo)→feliz · HABLANDO(respondiendo)→explicando ·
# PROCESANDO(ejecutando)→procesando · PENSANDO→pensando · ESCUCHANDO(solo al hablarle)→escuchando.
ESTADO_A_ILUSTRACION = {
    "DORMIDO": ("dormido",),
    "APARECIENDO": ("escuchando", "feliz", "esperando"),
    "ESCUCHANDO": ("escuchando",),
    "PENSANDO": ("pensando", "procesando"),
    "PROCESANDO": ("procesando", "pensando"),
    "HABLANDO": ("explicando", "hablando"),
    "ESPERANDO": ("feliz", "esperando"),
    "CONFIRMACION": ("confirmacion", "feliz"),
    "ERROR": ("error",),
    "DESAPARECIENDO": ("feliz", "esperando", "dormido"),
}

BLINK = "parpadeo"


class RecursoPersonaje:
    """Recurso visual de un estado. Uniforma PNG/GIF/sprite tras `pixmap()` + `avanzar()`."""

    def __init__(self, clave):
        self.clave = clave
        self._pixmaps = []      # frames (sprite) o [pixmap] (estático)
        self._movie = None      # QMovie (gif/apng)
        self._idx = 0
        self.animado = False

    # ── Construcción ──
    def set_estatico(self, pixmap):
        self._pixmaps = [pixmap]
        self.animado = False
        return self

    def set_frames(self, pixmaps):
        self._pixmaps = list(pixmaps) or []
        self.animado = len(self._pixmaps) > 1
        return self

    def set_movie(self, movie):
        self._movie = movie
        self.animado = True
        try:
            movie.start()
        except Exception:
            pass
        return self

    # ── Consumo ──
    def pixmap(self) -> QPixmap:
        if self._movie is not None:
            try:
                return self._movie.currentPixmap()
            except Exception:
                return QPixmap()
        if not self._pixmaps:
            return QPixmap()
        return self._pixmaps[self._idx % len(self._pixmaps)]

    def avanzar(self):
        if self._movie is not None:
            return  # QMovie avanza solo
        if len(self._pixmaps) > 1:
            self._idx = (self._idx + 1) % len(self._pixmaps)


def _placeholder(clave, tam=360) -> QPixmap:
    """Placeholder dibujado (cuando falta el asset real). Estrella-círculo cian con el nombre."""
    pm = QPixmap(tam, tam)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#161B22"))
    p.setPen(QColor("#00FFC6"))
    p.drawEllipse(20, 20, tam - 40, tam - 40)
    p.setPen(QColor("#00FFC6"))
    p.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, f"SOMA\n[{clave}]")
    p.end()
    return pm


def _ruta(nombre):
    return os.path.join(_DIR, nombre)


def _soma_color():
    """Color de tintado de SOMA (del tema del usuario). '' → sin tintar (blanco)."""
    try:
        from src.utils import tema
        return tema.color("soma_color") or ""
    except Exception:
        return ""


# Cortes de conectividad por pose (coords de píxel del sprite tal cual está en disco, 500x500).
# Bug conocido: en algunas ilustraciones, un dedo/guante/pie queda dibujado tan pegado al cuerpo que
# NO hay contorno oscuro que los separe en ese punto exacto (hueco en el line-art original) → el
# componente-blanco-más-grande de `_mascara_cuerpo` fusiona cuerpo+extremidad y el tinte se "derrama"
# sobre la mano/pie. No hay capas separadas para arreglarlo de raíz (sprite plano); en vez de tocar el
# PNG de arte, se corta la conexión SOLO para la fase de etiquetado (labeling), en la zona exacta donde
# se fusionan (verificado con `cv2.connectedComponents` sobre cada pose). El corte se usa SOLO para
# el labeling: una vez elegido el label del cuerpo, los píxeles blanco/crema originales dentro del
# rectángulo se restauran a la máscara final (ver `_mascara_cuerpo`), así no queda un parche sin
# tintar en el cuerpo — el corte deja de existir en cuanto termina la fase de etiquetado.
#
# 'escuchando' YA NO necesita corte: el usuario repintó el contorno oscuro del line-art en la
# costura mano↔cuerpo (~367-382, ~174-200) directamente en el PNG. Verificado con
# `cv2.connectedComponents` (connectivity=8) sobre la máscara blanco/crema actual SIN ningún corte:
# el cuerpo (componente más grande, 27138 px) y la mano (componente separado, ~2270 px) ya caen en
# labels distintos por sí solos — el hueco quedó cerrado en el arte. Mantener el rectángulo de corte
# aquí ya NO evita ninguna fusión (no hay fusión que evitar) y en cambio reintroduce el derrame: su
# paso de "restaurar" el rectángulo a la máscara final restaura ciegamente TODOS los píxeles
# blanco/crema originales dentro del rectángulo, incluidos ~286 que pertenecen al componente de la
# mano (no al del cuerpo) — es decir, tiñe un parche de la mano con el color del cuerpo.
#
# Segundo tipo de bug (distinto del anterior, mismo mecanismo de arreglo): el rombo/cometa decorativo
# del propio patrón de cinta del cuerpo, situado justo ENCIMA de la boca CERRADA (entre los ojos, en el
# "puente" de la cara), queda dibujado con un contorno oscuro que lo CIERRA POR COMPLETO en varias
# poses — así que `cv2.connectedComponents` lo aísla como su propio componente pequeño (~95-420 px,
# confirmado uno por uno) en vez de fusionarlo con el cuerpo, y se queda sin teñir aunque es
# claramente parte del CUERPO (el mismo rombo, ya teñido con normalidad, se repite varias veces más
# por el resto del patrón de cinta). No es un diente ni ningún otro rasgo facial — verificado
# visualmente pose a pose: la boca en todas las poses afectadas está CERRADA (una simple curva), sin
# ningún hueco/interior visible ahí dentro; el rombo queda POR ENCIMA de esa curva, no dentro de ella.
# Aquí no hace falta "cortar para el labeling" (el rombo YA está aislado por sí solo, no hay ninguna
# fusión indebida que deshacer) — se reutiliza el mismo mecanismo de "restaurar al final" solo para
# incorporar sus píxeles blanco/crema a la máscara final del cuerpo. Cada rectángulo es el bounding
# box EXACTO (sin margen) del label correspondiente, verificado individualmente con
# `cv2.connectedComponents` para confirmar que no se solapa con ningún otro elemento (ojos, boca,
# interior de boca abierta) — 'sorprendido' (boca "O" abierta) y 'proponiendo' en su variante de labio
# NO se tocan aquí porque ese candidato es un detalle de labio/encía DENTRO de una boca abierta, un
# elemento distinto, no este rombo.
_CORTES_CONECTIVIDAD = {
    "feliz":       [(240, 229, 264, 240)],
    "explicando":  [(250, 218, 276, 228)],
    "esperando":   [(231, 225, 254, 238)],
    "parpadeo":    [(231, 236, 269, 256)],
    "proponiendo": [(240, 231, 259, 241)],
}


def _mascara_cuerpo(arr, clave=None):
    """Máscara booleana del CUERPO-estrella = el componente BLANCO conexo MÁS GRANDE del sprite. Así el
    tinte NO afecta a guantes, blanco de los ojos, pajarita, zapatos, cejas, pupilas, boca ni pestañas (son
    componentes blancos pequeños separados, o píxeles de color/negros). `arr` es RGBA uint8 (H,W,4)."""
    import numpy as np
    r, g, b, al = (arr[..., 0].astype(int), arr[..., 1].astype(int),
                   arr[..., 2].astype(int), arr[..., 3])
    mx = np.maximum(np.maximum(r, g), b)
    sat = mx - np.minimum(np.minimum(r, g), b)
    # Cuerpo-candidato = opaco + CLARO + poco/moderadamente saturado. Captura el cuerpo tanto BLANCO (poses
    # despiertas) como CREMA/beige (p. ej. 'dormido', sat≈33-46) y también guantes/ojos-blancos; pero EXCLUYE
    # los accesorios saturados (pajarita roja sat≈121, zapatos marrón sat≈115, cejas) y los contornos oscuros.
    # Guantes y ojos quedan como componentes SEPARADOS (los aíslan los contornos oscuros/brazos) → el cuerpo,
    # mucho mayor, es el componente elegido.
    blanco = (al > 128) & (mx > 150) & (sat < 90)
    if not blanco.any():
        return None
    etiquetado = blanco
    cortes = _CORTES_CONECTIVIDAD.get(clave)
    if cortes:
        etiquetado = blanco.copy()
        for (x0, y0, x1, y1) in cortes:
            etiquetado[y0:y1, x0:x1] = False
    try:
        import cv2
        n, labels = cv2.connectedComponents(etiquetado.astype(np.uint8), connectivity=8)
    except Exception:
        try:
            from scipy import ndimage
            labels, n = ndimage.label(etiquetado)
            n += 1
        except Exception:
            return blanco               # sin etiquetado: tinta todo lo blanco (mejor que todo el sprite)
    if n <= 1:
        cuerpo = etiquetado
    else:
        cuentas = np.bincount(labels.ravel())
        cuentas[0] = 0                    # fondo
        cuerpo = labels == int(cuentas.argmax())
    if cortes:
        # El corte solo debía servir para el LABELING (evitar que `connectedComponents` fusione
        # mano+cuerpo); NO debe quitarse del tinte final o deja un parche sin tintar en el cuerpo
        # (bug: el corte anterior excluía el rectángulo también de la máscara final). Se restauran
        # aquí los píxeles blanco/crema originales dentro del rectángulo de corte a la máscara del
        # cuerpo ya elegido — la propia mano queda fuera porque su componente/label es otro y no se
        # toca (solo se restauran los píxeles DENTRO del rectángulo, no todo el label de la mano).
        for (x0, y0, x1, y1) in cortes:
            cuerpo[y0:y1, x0:x1] |= blanco[y0:y1, x0:x1]
    return cuerpo


def _tintar(pm, color_hex, clave=None):
    """Tinta SOLO el CUERPO en forma de estrella hacia `color_hex` (por multiplicación: el blanco toma el
    color y los contornos internos oscuros se conservan). Guantes, ojos, pajarita, zapatos, cejas, boca y
    pestañas quedan INTACTOS. Respeta el canal alfa. Best-effort: ante cualquier fallo devuelve el original."""
    if pm is None or pm.isNull() or not color_hex:
        return pm
    try:
        import numpy as np
        from PyQt6.QtGui import QImage
        qimg = pm.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
        w, h = qimg.width(), qimg.height()
        ptr = qimg.bits(); ptr.setsize(qimg.sizeInBytes())
        arr = np.frombuffer(ptr, np.uint8).reshape((h, w, 4)).copy()
        cuerpo = _mascara_cuerpo(arr, clave)
        if cuerpo is None or not cuerpo.any():
            return pm
        col = QColor(color_hex)
        for canal, comp in ((0, col.red()), (1, col.green()), (2, col.blue())):
            c = arr[..., canal]
            c[cuerpo] = (c[cuerpo].astype(int) * comp // 255).astype(np.uint8)   # multiply, alfa intacto
        out = QImage(arr.tobytes(), w, h, QImage.Format.Format_RGBA8888).copy()
        return QPixmap.fromImage(out)
    except Exception as e:
        logger.debug("tintar SOMA: %s", e)
        return pm


def _cargar_clave(clave) -> RecursoPersonaje:
    """Carga un recurso por clave probando formatos por prioridad; placeholder si no hay nada."""
    rec = RecursoPersonaje(clave)
    # 1) GIF / APNG
    for ext in ("gif", "apng"):
        ruta = _ruta(f"{clave}.{ext}")
        if os.path.exists(ruta):
            try:
                return rec.set_movie(QMovie(ruta))
            except Exception as e:
                logger.debug("movie %s: %s", ruta, e)
    tinte = _soma_color()
    # 2) Sprite sheet + json
    hoja, meta = _ruta(f"{clave}.sheet.png"), _ruta(f"{clave}.json")
    if os.path.exists(hoja) and os.path.exists(meta):
        try:
            frames = _cargar_sprite(hoja, meta)
            if frames:
                return rec.set_frames([_tintar(fr, tinte, clave) for fr in frames])
        except Exception as e:
            logger.debug("sprite %s: %s", hoja, e)
    # 3) PNG estático
    png = _ruta(f"{clave}.png")
    if os.path.exists(png):
        pm = QPixmap(png)
        if not pm.isNull():
            return rec.set_estatico(_tintar(pm, tinte, clave))
    # 4) Placeholder
    logger.debug("asset SOMA no encontrado para '%s' → placeholder", clave)
    return rec.set_estatico(_placeholder(clave))


def _cargar_sprite(hoja_ruta, meta_ruta):
    hoja = QPixmap(hoja_ruta)
    with open(meta_ruta, encoding="utf-8") as f:
        meta = json.load(f)
    frames = []
    for fr in meta.get("frames", []):
        x, y, w, h = fr["x"], fr["y"], fr["w"], fr["h"]
        frames.append(hoja.copy(x, y, w, h))
    return frames


class CharacterPack:
    """Punto único de acceso al pack. Cachea recursos por clave."""

    def __init__(self):
        self._cache = {}

    def recurso(self, clave) -> RecursoPersonaje:
        if clave not in self._cache:
            self._cache[clave] = _cargar_clave(clave)
        return self._cache[clave]

    def para_estado(self, estado) -> RecursoPersonaje:
        """Devuelve el recurso de la primera ilustración disponible para un estado del Kernel."""
        claves = ESTADO_A_ILUSTRACION.get(str(estado).upper(), ("esperando",))
        for clave in claves:
            if os.path.exists(_ruta(f"{clave}.png")) or os.path.exists(_ruta(f"{clave}.gif")) \
               or os.path.exists(_ruta(f"{clave}.sheet.png")):
                return self.recurso(clave)
        # Ninguna disponible → placeholder de la primera clave (para dev)
        return self.recurso(claves[0])

    def parpadeo(self) -> RecursoPersonaje | None:
        if os.path.exists(_ruta(f"{BLINK}.png")):
            return self.recurso(BLINK)
        return None

    def disponible(self) -> bool:
        """True si hay al menos un asset real (no solo placeholders)."""
        try:
            return any(n.endswith((".png", ".gif", ".apng")) for n in os.listdir(_DIR))
        except Exception:
            return False


_pack = None


def pack() -> CharacterPack:
    global _pack
    if _pack is None:
        _pack = CharacterPack()
    return _pack
