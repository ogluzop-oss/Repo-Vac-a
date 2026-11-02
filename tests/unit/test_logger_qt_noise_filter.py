"""
`src.utils.logger.instalar_captura_global` — filtro de ruido Qt conocido e inofensivo.

Bug real reportado: "sigue apareciendo mucho texto" en la terminal — el backend FFmpeg de Qt
Multimedia emite, al destruir un `QMediaPlayer`/`QVideoSink`, una serie de warnings
`QObject::disconnect: wildcard call disconnects from destroyed signal of QFFmpeg::...` sobre SUS
PROPIAS clases internas (nada que la app conecte/desconecte, nada que la app pueda arreglar, no
indica ningún fallo real). Se filtran en el manejador de mensajes de Qt (`qInstallMessageHandler`)
en vez de dejarlos llegar al logger — pero SOLO ese patrón exacto, cualquier otro mensaje de Qt
debe seguir viéndose con normalidad (nunca silenciar ruido real por error).
"""

import logging

import pytest

pytest.importorskip("PyQt6.QtCore")

from PyQt6.QtCore import QtMsgType


@pytest.fixture
def qt_handler():
    """Instala el manejador real (`instalar_captura_global`) y devuelve la función `_qt_handler`
    capturada directamente desde `qInstallMessageHandler` — sin reimplementar la lógica en el
    test, se prueba la MISMA función que corre en producción."""
    from PyQt6.QtCore import qInstallMessageHandler
    from src.utils import logger as m

    capturado = {}
    original = qInstallMessageHandler

    def _espia(fn):
        capturado["handler"] = fn
        return original(fn)

    import src.utils.logger as logger_mod
    # `instalar_captura_global` importa `qInstallMessageHandler` localmente desde PyQt6.QtCore
    # dentro de su propio cuerpo — se parchea el símbolo en el módulo real de PyQt6.QtCore para
    # interceptar la función que de verdad registra, sin tocar la lógica de `_qt_handler` en sí.
    import PyQt6.QtCore as _qtcore
    prev = _qtcore.qInstallMessageHandler
    _qtcore.qInstallMessageHandler = _espia
    try:
        logger_mod.instalar_captura_global()
    finally:
        _qtcore.qInstallMessageHandler = prev
    assert "handler" in capturado, "instalar_captura_global no registró ningún manejador Qt"
    return capturado["handler"]


def test_filtra_el_ruido_conocido_de_qffmpeg_disconnect(qt_handler, caplog):
    with caplog.at_level(logging.WARNING, logger="smart_manager.qt"):
        qt_handler(QtMsgType.QtWarningMsg, None,
                   "QObject::disconnect: wildcard call disconnects from destroyed signal of "
                   "QFFmpeg::VideoRenderer::unnamed")
    assert caplog.records == [], "el ruido conocido de QFFmpeg no debe llegar al logger"


def test_no_filtra_otros_mensajes_de_qt(qt_handler, caplog):
    """Solo ese patrón EXACTO se descarta — cualquier otro warning/error real de Qt debe seguir
    pasando con normalidad (nunca silenciar de más)."""
    with caplog.at_level(logging.WARNING, logger="smart_manager.qt"):
        qt_handler(QtMsgType.QtWarningMsg, None, "Algún otro aviso real de Qt sin relación.")
    assert len(caplog.records) == 1
    assert "Algún otro aviso real de Qt" in caplog.records[0].message


def test_no_filtra_otro_disconnect_que_no_sea_de_qffmpeg(qt_handler, caplog):
    """La guarda es por el texto exacto del patrón QFFmpeg — un disconnect de OTRA clase (que sí
    podría ser un bug real de la app) no debe filtrarse."""
    with caplog.at_level(logging.WARNING, logger="smart_manager.qt"):
        qt_handler(QtMsgType.QtWarningMsg, None,
                   "QObject::disconnect: wildcard call disconnects from destroyed signal of "
                   "MiPropiaClase::unnamed")
    assert len(caplog.records) == 1
