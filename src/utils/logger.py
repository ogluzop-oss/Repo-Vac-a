"""
Sistema de logging centralizado de Smart Manager AI.

Un único punto configura TODO el logging de la aplicación:
  • Archivo rotativo  logs/smart_manager.log  (5 × 2 MB) en UTF-8.
  • Salida por consola (útil en desarrollo).
  • Captura GLOBAL de excepciones no controladas (sys.excepthook) y de los
    hilos (threading.excepthook) → ningún crash queda sin registrar.
  • Captura de los mensajes internos de Qt (qInstallMessageHandler).

Como la configuración actúa sobre el logger raíz, cualquier módulo que ya use
`logging.getLogger(__name__)` queda registrado automáticamente.

Loggers por subsistema (usa `get_logger(...)` o las constantes):
    app · db · soma · impresion · documentos · tpv · stock · sync · rfid · ui

Uso típico en un módulo:
    from src.utils.logger import LOG_DB
    try:
        ...
    except Exception:
        LOG_DB.exception("Fallo al guardar la venta")   # registra traza completa
"""

import logging
import logging.handlers
import os
import sys
import threading

_RAIZ = "smart_manager"
_configurado = False


def _dir_logs():
    """Carpeta de logs (escribible), junto a documentos/."""
    try:
        from src.utils import recursos
        base = recursos.dir_recursos()
    except Exception:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    d = os.path.join(base, "logs")
    os.makedirs(d, exist_ok=True)
    return d


class _JsonFormatter(logging.Formatter):
    """Formatter JSON estructurado (OBS-1): timestamp/nivel/módulo/mensaje + correlation_id."""
    def format(self, record):
        import json as _json
        base = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "nivel": record.levelname,
            "modulo": record.name,
            "mensaje": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", "-"),
        }
        if record.exc_info:
            base["exc"] = self.formatException(record.exc_info)
        return _json.dumps(base, ensure_ascii=False)


def configurar_logging(nivel=logging.INFO, consola=True):
    """Configura el logging global. Idempotente (llamar una vez al arranque).
    Si SM_LOG_JSON=1, usa formato JSON estructurado. Inyecta correlation_id en cada registro."""
    global _configurado
    if _configurado:
        return logging.getLogger(_RAIZ)

    if os.getenv("SM_LOG_JSON", "0") == "1":
        fmt = _JsonFormatter()
    else:
        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | [%(correlation_id)s] | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    # Filtro que añade correlation_id a todos los registros (OBS-2).
    try:
        from src.services.observabilidad.correlation import CorrelationFilter
        _cfilter = CorrelationFilter()
    except Exception:
        class _NF(logging.Filter):
            def filter(self, r):
                r.correlation_id = getattr(r, "correlation_id", "-"); return True
        _cfilter = _NF()

    root = logging.getLogger()
    root.setLevel(nivel)
    root.addFilter(_cfilter)

    # Archivo rotativo
    try:
        fichero = os.path.join(_dir_logs(), "smart_manager.log")
        fh = logging.handlers.RotatingFileHandler(
            fichero, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
        )
        fh.setLevel(nivel)
        fh.setFormatter(fmt)
        fh.addFilter(_cfilter)        # correlation_id en registros propagados
        root.addHandler(fh)
    except Exception:
        pass

    # Consola
    if consola:
        ch = logging.StreamHandler()
        ch.setLevel(nivel)
        ch.setFormatter(fmt)
        ch.addFilter(_cfilter)
        root.addHandler(ch)

    # Bajar el ruido de librerías muy verbosas.
    for ruidoso in ("PIL", "matplotlib", "urllib3", "comtypes", "asyncio"):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)

    instalar_captura_global()
    _configurado = True
    logging.getLogger(_RAIZ).info("Logging inicializado. Archivo: %s", _dir_logs())
    return logging.getLogger(_RAIZ)


def instalar_captura_global():
    """Registra cualquier excepción no controlada (hilo principal, hilos y Qt)."""
    log = logging.getLogger("%s.excepciones" % _RAIZ)

    def _hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        log.critical("EXCEPCIÓN NO CONTROLADA", exc_info=(exc_type, exc, tb))

    sys.excepthook = _hook

    # Hilos (Python 3.8+)
    if hasattr(threading, "excepthook"):
        def _thook(args):
            log.critical("EXCEPCIÓN EN HILO '%s'", getattr(args, "thread", None),
                         exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        threading.excepthook = _thook

    # Mensajes internos de Qt
    try:
        from PyQt6.QtCore import QtMsgType, qInstallMessageHandler
        qlog = logging.getLogger("%s.qt" % _RAIZ)
        _niveles = {
            QtMsgType.QtDebugMsg: logging.DEBUG,
            QtMsgType.QtInfoMsg: logging.INFO,
            QtMsgType.QtWarningMsg: logging.WARNING,
            QtMsgType.QtCriticalMsg: logging.ERROR,
            QtMsgType.QtFatalMsg: logging.CRITICAL,
        }

        def _qt_handler(mode, ctx, message):
            qlog.log(_niveles.get(mode, logging.INFO), "%s", message)

        qInstallMessageHandler(_qt_handler)
    except Exception:
        pass


def get_logger(subsistema="app"):
    """Devuelve el logger de un subsistema (hijo del logger raíz de la app)."""
    return logging.getLogger("%s.%s" % (_RAIZ, subsistema))


# Loggers por subsistema (atajos para importar directamente).
LOG_APP        = get_logger("app")
LOG_DB         = get_logger("db")
LOG_SOMA       = get_logger("soma")
LOG_IMPRESION  = get_logger("impresion")
LOG_DOCUMENTOS = get_logger("documentos")
LOG_TPV        = get_logger("tpv")
LOG_STOCK      = get_logger("stock")
LOG_SYNC       = get_logger("sync")
LOG_RFID       = get_logger("rfid")
LOG_UI         = get_logger("ui")
