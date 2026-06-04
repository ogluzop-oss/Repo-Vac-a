import secrets
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from PyQt6.QtCore import QObject, pyqtSignal

_PORT = 7847
_tokens: dict = {}
_lock = threading.Lock()
_server: HTTPServer | None = None


class _WebhookSignals(QObject):
    propuesta_actualizada = pyqtSignal()


# Initialized on the main thread when iniciar_servidor() is first called.
webhook_signals: _WebhookSignals | None = None


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def generar_urls(propuesta_id: int) -> tuple[str, str]:
    ip = get_local_ip()
    tok_ap = secrets.token_urlsafe(16)
    tok_de = secrets.token_urlsafe(16)
    with _lock:
        _tokens[tok_ap] = (propuesta_id, "aprobado")
        _tokens[tok_de] = (propuesta_id, "cancelado")
    base = f"http://{ip}:{_PORT}"
    return f"{base}/aprobar?token={tok_ap}", f"{base}/denegar?token={tok_de}"


class _Handler(BaseHTTPRequestHandler):
    _PAGE = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<style>body{{font-family:Arial,sans-serif;display:flex;align-items:center;"
        "justify-content:center;height:100vh;margin:0;background:#0E1117;color:#fff}}"
        ".box{{text-align:center;padding:40px;border-radius:16px;background:#161B22;"
        "border:2px solid {color}}}"
        "h2{{color:{color};margin-bottom:8px}}p{{color:#8B949E}}</style></head>"
        "<body><div class='box'><h2>{icon} {titulo}</h2><p>{msg}</p></div></body></html>"
    )

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        token = qs.get("token", [""])[0]
        with _lock:
            entry = _tokens.pop(token, None)

        if entry is None:
            self._html(400, "#FF4B4B", "❌", "Enlace inválido",
                       "Este enlace ya fue usado o no es válido.")
            return

        propuesta_id, nuevo_estado = entry
        try:
            from src.db.reabastecimiento import cambiar_estado_propuesta
            ok = cambiar_estado_propuesta(propuesta_id, nuevo_estado)
        except Exception:
            ok = False

        if ok and webhook_signals is not None:
            webhook_signals.propuesta_actualizada.emit()

        if nuevo_estado == "aprobado":
            if ok:
                self._html(200, "#00FFC6", "✅", "Propuesta APROBADA",
                           f"La propuesta #{propuesta_id} ha sido aprobada correctamente.")
            else:
                self._html(500, "#FF4B4B", "❌", "Error",
                           "No se pudo actualizar la propuesta. Inténtalo de nuevo.")
        else:
            if ok:
                self._html(200, "#FF4B4B", "❌", "Propuesta DENEGADA",
                           f"La propuesta #{propuesta_id} ha sido denegada.")
            else:
                self._html(500, "#FF4B4B", "❌", "Error",
                           "No se pudo actualizar la propuesta. Inténtalo de nuevo.")

    def _html(self, code, color, icon, titulo, msg):
        body = self._PAGE.format(color=color, icon=icon, titulo=titulo, msg=msg)
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, *_):
        pass


def iniciar_servidor():
    global _server, webhook_signals
    if _server is not None:
        return
    if webhook_signals is None:
        webhook_signals = _WebhookSignals()
    try:
        _server = HTTPServer(("0.0.0.0", _PORT), _Handler)
        threading.Thread(target=_server.serve_forever, daemon=True).start()
    except OSError:
        pass
