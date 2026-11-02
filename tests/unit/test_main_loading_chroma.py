"""
Croma key en la animación de carga del login (`src.main.SmartManagerApp._on_frame_video_carga`,
camino de VÍDEO) y escalado a pantalla completa de los dos tipos de clip posibles
(`_ajustar_tamano_clip`).

Historia (3 bugs reales, misma animación, en orden): (1) el usuario sustituyó el fondo de
`assets/carga.mp4` por un VERDE croma — se retira en tiempo real con numpy vía `QVideoSink`
(`QVideoWidget`, la superficie de vídeo nativa, no admite transparencia real); (2) procesar croma
en tiempo real a resolución nativa costaba demasiado (~100ms/fotograma, "se corta") y reducirlo +
reescalar barato metía bloques de píxel visibles ("contorno verde"+"pixelado"); (3) arreglar ESO
(reescalado suave en los dos pasos) volvió a costar ~25-28ms/fotograma, de nuevo demasiado en
máquinas más lentas ("a trompicones"). La solución final evita competir con el reloj: el croma key
se hornea UNA SOLA VEZ, offline (`tools/generar_animacion_carga.py`), en un `assets/carga.webp`
animado con alfa real — en tiempo de ejecución la app vuelve al camino `QMovie` NATIVO
(`setMovie`, sin interceptar fotogramas en Python), mucho más barato. El camino de vídeo
(`_on_frame_video_carga`) se conserva para un futuro asset que solo exista en vídeo.

No se instancia `SmartManagerApp` completa (arranca un subproceso Flask + pool de BD + login —
demasiado pesado para un test unitario): se llama a los métodos SIN ligar (p. ej.
`SmartManagerApp._on_frame_video_carga(dummy, frame)`) sobre un objeto mínimo que solo aporta los
atributos que el método realmente toca, igual que se haría con un mock.
"""

import numpy as np
import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtGui import QImage
from PyQt6.QtMultimedia import QVideoFrame
from PyQt6.QtWidgets import QApplication, QLabel


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _VentanaDummy:
    """Objeto mínimo con solo lo que `_on_frame_video_carga` necesita de `SmartManagerApp`."""
    def __init__(self):
        self.loading_logo = QLabel()
        self._video_tam_destino = None


def _frame_sintetico(w, h, *, mitad_izq_rgb, mitad_der_rgb):
    """QVideoFrame de prueba: mitad izquierda de un color, mitad derecha de otro — sin pasar por
    la decodificación real de vídeo (eso ya se verificó aparte, extrayendo fotogramas reales de
    `assets/carga.mp4` con OpenCV y confirmando visualmente el resultado del croma key)."""
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[:, : w // 2, 0:3] = mitad_izq_rgb
    arr[:, w // 2 :, 0:3] = mitad_der_rgb
    arr[..., 3] = 255
    img = QImage(arr.tobytes(), w, h, QImage.Format.Format_RGBA8888).copy()
    return QVideoFrame(img)


def _pixmap_a_array(pixmap):
    img = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = img.width(), img.height()
    ptr = img.bits(); ptr.setsize(img.sizeInBytes())
    return np.frombuffer(ptr, np.uint8).reshape((h, w, 4)).copy()


def test_fondo_verde_croma_queda_transparente(app):
    """La mitad VERDE croma (fondo a retirar) debe quedar con alfa ~0 tras el procesado."""
    from src.main import SmartManagerApp
    dummy = _VentanaDummy()
    verde_croma = (13, 207, 56)        # medido de un fotograma real de assets/carga.mp4
    sujeto_azul = (45, 131, 164)       # medido de un fotograma real (la figura de la animación)
    frame = _frame_sintetico(20, 10, mitad_izq_rgb=verde_croma, mitad_der_rgb=sujeto_azul)

    SmartManagerApp._on_frame_video_carga(dummy, frame)

    pm = dummy.loading_logo.pixmap()
    assert pm is not None and not pm.isNull()
    arr = _pixmap_a_array(pm)
    alpha_fondo = arr[:, : arr.shape[1] // 2, 3]
    assert alpha_fondo.mean() < 10, f"el fondo croma debería quedar transparente, alfa medio={alpha_fondo.mean()}"


def test_sujeto_no_verde_se_mantiene_opaco(app):
    """El color del SUJETO (no-verde) no debe perder opacidad — solo se retira el fondo."""
    from src.main import SmartManagerApp
    dummy = _VentanaDummy()
    verde_croma = (13, 207, 56)
    sujeto_azul = (45, 131, 164)
    frame = _frame_sintetico(20, 10, mitad_izq_rgb=verde_croma, mitad_der_rgb=sujeto_azul)

    SmartManagerApp._on_frame_video_carga(dummy, frame)

    arr = _pixmap_a_array(dummy.loading_logo.pixmap())
    alpha_sujeto = arr[:, arr.shape[1] // 2 :, 3]
    assert alpha_sujeto.mean() > 245, \
        f"el sujeto (no-croma) no debería perder opacidad, alfa medio={alpha_sujeto.mean()}"


def test_degrada_con_honestidad_si_frame_invalido(app):
    """Un `QVideoFrame` inválido no debe lanzar ni pintar nada roto — simplemente se ignora."""
    from src.main import SmartManagerApp
    dummy = _VentanaDummy()
    SmartManagerApp._on_frame_video_carga(dummy, QVideoFrame())   # frame por defecto: inválido
    assert dummy.loading_logo.pixmap() is None or dummy.loading_logo.pixmap().isNull()


def test_ajustar_tamano_clip_video_usa_pantalla_completa(app):
    """Petición explícita: el vídeo debe cubrir TODO el overlay (w×h real)."""
    from PyQt6.QtWidgets import QWidget
    from src.main import SmartManagerApp

    class _VentanaDummyAjuste:
        def __init__(self):
            self.overlay = QWidget()
            self.overlay.resize(1366, 768)   # rectangular, no cuadrado — para distinguir el criterio
            self.loading_logo = QLabel()
            self._loading_movie = None
            self._loading_video_sink = object()   # cualquier valor no-None activa el camino de vídeo

    dummy = _VentanaDummyAjuste()
    SmartManagerApp._ajustar_tamano_clip(dummy)

    assert dummy._video_tam_destino == (1366, 768)
    assert (dummy.loading_logo.width(), dummy.loading_logo.height()) == (1366, 768)


def test_ajustar_tamano_clip_movie_no_escala_se_queda_en_su_tamano_nativo(app):
    """Bug real, 2ª vuelta de esta misma animación: a pantalla completa, `QMovie.setScaledSize()`
    ampliaba la estrella hasta cubrir toda la pantalla y el usuario la veía "pixelada" (el
    reescalado interno de `QMovie` por fotograma no es tan nítido como un reescalado puntual).
    Petición explícita: dejar de forzar ningún tamaño — el clip debe quedarse en su tamaño
    NATIVO/original, sin `setScaledSize` de por medio en absoluto."""
    from PyQt6.QtGui import QMovie
    from PyQt6.QtWidgets import QWidget
    from src.main import SmartManagerApp

    class _VentanaDummyAjuste:
        def __init__(self):
            self.overlay = QWidget()
            self.overlay.resize(1920, 1080)   # pantalla grande — NO debe influir en el tamaño del clip
            self.loading_logo = QLabel()
            self._loading_movie = QMovie("assets/carga.webp")   # nativo real: 1280x720
            self._loading_video_sink = None

    dummy = _VentanaDummyAjuste()
    dummy._loading_movie.jumpToFrame(0)   # decodifica el primer fotograma (sizeHint lo necesita)

    SmartManagerApp._ajustar_tamano_clip(dummy)

    assert not dummy._loading_movie.scaledSize().isValid(), (
        "no debe llamarse a setScaledSize() en absoluto — el clip se queda a su tamaño nativo")
    assert dummy.loading_logo.width() < 1920 and dummy.loading_logo.height() < 1080, (
        f"el clip no debe escalarse a pantalla completa: {dummy.loading_logo.size()} "
        f"vs overlay 1920x1080")


@pytest.mark.skipif(__import__("os").name != "nt", reason="DLL de FFmpeg solo se bundlea en Windows")
def test_silenciar_log_nativo_ffmpeg_baja_el_nivel_real_de_avutil():
    """Bug real reportado: FFmpeg (backend de Qt Multimedia) volcaba directamente a stdout/stderr
    el volcado de cada fichero abierto («Input #0, ...», sondeos de codecs de Windows) — texto que
    no pasa por `configurar_logging()`. Se silencia llamando a `av_log_set_level` sobre la MISMA
    DLL `avutil` que PyQt6 ya trae incluida. Aquí se comprueba, contra esa DLL real (no un mock),
    que la llamada deja el nivel en `AV_LOG_ERROR` (16) — confirmado antes manualmente: con el
    nivel por defecto se ve el volcado completo; con este nivel, desaparece (solo quedan los 2
    avisos que FFmpeg clasifica como error real, que es justo lo que se pretende conservar)."""
    import ctypes
    import glob
    import os as _os

    import PyQt6
    from src.main import _silenciar_log_nativo_ffmpeg

    _silenciar_log_nativo_ffmpeg()

    base = _os.path.join(_os.path.dirname(PyQt6.__file__), "Qt6", "bin")
    candidatos = glob.glob(_os.path.join(base, "avutil-*.dll"))
    assert candidatos, "la DLL avutil bundleada con PyQt6 no está donde se espera"
    avutil = ctypes.CDLL(candidatos[0])
    assert avutil.av_log_get_level() == 16   # AV_LOG_ERROR


def test_silenciar_log_nativo_ffmpeg_degrada_con_honestidad_si_falla(monkeypatch):
    """Si la DLL no se encuentra (p. ej. una versión futura de Qt la renombra), no debe lanzar
    — nunca debe bloquear el arranque de la app por esto."""
    import glob as _glob_mod
    from src import main as m

    monkeypatch.setattr(_glob_mod, "glob", lambda *a, **k: [])
    m._silenciar_log_nativo_ffmpeg()   # no debe lanzar ninguna excepción
