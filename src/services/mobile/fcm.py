"""
FCMGateway — puente DEGRADABLE con Firebase Cloud Messaging (mismo patrón que
`services/esl/gateway.ESLGateway`: `modo_simulado` sin proyecto/credencial, HTTP real cuando hay
`project_id` + *service account*).

Se implementa el protocolo HTTP v1 de FCM a mano (JWT firmado con `PyJWT` + intercambio OAuth2 +
`POST .../messages:send` con `requests`) en vez de instalar el SDK `firebase-admin` — mismo criterio que
el cliente SOAP/mTLS de la AEAT y WS-Discovery de cámaras: protocolo bien documentado, cero dependencias
nuevas (`PyJWT`/`cryptography` ya están en requirements.txt). El envío HTTP se hace por un `transport`
inyectable (por defecto `requests`), lo que permite probar el gateway SIN red ni coste. NUNCA se marca un
envío como entregado sin confirmación real de FCM; en simulado se documenta como simulado.
"""

import logging
import time

logger = logging.getLogger("mobile.fcm")

_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_TOKEN_URL = "https://oauth2.googleapis.com/token"


def _http_transport(metodo, url, headers, cuerpo, es_form=False):
    """Transporte HTTP real (degradable). Devuelve (status_code|None, texto)."""
    try:
        import requests
    except Exception:
        return None, "requests no disponible"
    try:
        if es_form:
            r = requests.request(metodo, url, data=cuerpo, headers=headers, timeout=6)
        else:
            r = requests.request(metodo, url, json=cuerpo, headers=headers, timeout=6)
        return r.status_code, (r.text or "")
    except Exception as e:
        return None, str(e)


class FCMGateway:
    def __init__(self, project_id=None, service_account_json=None, modo_simulado=True, transport=None):
        self.project_id = (project_id or "").strip() or None
        self._service_account = service_account_json
        self._transport = transport   # inyectable (tests); None → HTTP real
        self._access_token = None
        self._access_token_exp = 0
        # Simulado si se pide explícito o si falta proyecto/credencial (no se inventa un envío real).
        self.modo_simulado = bool(modo_simulado or not self.project_id or not self._service_account)

    def _transporte(self):
        return self._transport or _http_transport

    def _jwt_firmado(self):
        import jwt as pyjwt
        cred = self._service_account
        ahora = int(time.time())
        claims = {
            "iss": cred["client_email"],
            "scope": _SCOPE,
            "aud": _TOKEN_URL,
            "iat": ahora,
            "exp": ahora + 3600,
        }
        return pyjwt.encode(claims, cred["private_key"], algorithm="RS256")

    def _obtener_access_token(self):
        """Intercambia el JWT del service account por un access token OAuth2 (cacheado en memoria hasta
        que expire, con margen de 60s). Devuelve None si algo falla — nunca inventa un token."""
        ahora = time.time()
        if self._access_token and ahora < self._access_token_exp - 60:
            return self._access_token
        try:
            assertion = self._jwt_firmado()
        except Exception as e:
            logger.error("firmar JWT service account FCM: %s", e)
            return None
        cuerpo = {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        }
        status, texto = self._transporte()(
            "POST", _TOKEN_URL, {"Content-Type": "application/x-www-form-urlencoded"}, cuerpo,
            es_form=True)
        if status != 200:
            logger.error("token-exchange FCM falló (status=%s): %s", status, texto)
            return None
        import json
        try:
            datos = json.loads(texto)
            self._access_token = datos["access_token"]
            self._access_token_exp = ahora + int(datos.get("expires_in", 3600))
            return self._access_token
        except Exception as e:
            logger.error("parseo respuesta token-exchange FCM: %s", e)
            return None

    def enviar(self, token_dispositivo, titulo, cuerpo, datos=None):
        """Envía una notificación push a un dispositivo. Devuelve {'ok': bool, 'motivo'|'detalle': str}.
        Honesto: nunca inventa éxito; `motivo` describe el fallo real cuando `ok` es False."""
        if self.modo_simulado:
            logger.debug("[FCM SIM] push %s ← %s / %s", token_dispositivo, titulo, cuerpo)
            return {"ok": True, "detalle": "simulado"}
        access_token = self._obtener_access_token()
        if not access_token:
            return {"ok": False, "motivo": "no se pudo obtener access token OAuth2"}
        mensaje = {
            "message": {
                "token": token_dispositivo,
                "notification": {"title": titulo, "body": cuerpo},
                "data": {str(k): str(v) for k, v in (datos or {}).items() if v is not None},
            }
        }
        url = f"https://fcm.googleapis.com/v1/projects/{self.project_id}/messages:send"
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        status, texto = self._transporte()("POST", url, headers, mensaje)
        if status == 200:
            return {"ok": True, "detalle": "enviado"}
        return {"ok": False, "motivo": f"FCM status={status}: {texto}"}
