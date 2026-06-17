"""
Transporte mTLS para AEAT (C3.5.2) — SSLContext EN MEMORIA (decisión D3).

Construye el contexto TLS de cliente a partir del `ProveedorClaves` (certificado +
clave descifrados en memoria por la custodia C3.5.1), SIN escribir PEM ni ficheros
temporales en disco. Devuelve un `transporte` (callable) compatible con
`EmisorVerifactu`, de modo que el envío real reutiliza todo el flujo ya existente.

El certificado de cliente (sello de empresa, D5) viaja como objeto `cryptography`
→ `pyOpenSSL` → contexto urllib3. Sin transporte/cert válido, no hay sesión y el
emisor permanece `disponible()=False` (el worker deja el registro en espera).
"""

import logging
import ssl

logger = logging.getLogger("fiscal.emisor.tls")


def contexto_mtls(proveedor_claves):
    """Contexto SSL de cliente con el certificado/clave en memoria. None si falla."""
    if proveedor_claves is None or not proveedor_claves.disponible():
        return None
    key = proveedor_claves.clave_privada()
    cert = proveedor_claves.certificado()
    if key is None or cert is None:
        return None
    try:
        import OpenSSL.crypto as oC
        from urllib3.contrib.pyopenssl import PyOpenSSLContext
        ctx = PyOpenSSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx._ctx.use_certificate(oC.X509.from_cryptography(cert))
        ctx._ctx.use_privatekey(oC.PKey.from_cryptography_key(key))
        for extra in proveedor_claves.cadena() or []:
            try:
                ctx._ctx.add_extra_chain_cert(oC.X509.from_cryptography(extra))
            except Exception:
                pass
        ctx._ctx.check_privatekey()          # clave y certificado deben casar
        return ctx
    except Exception as e:
        logger.error("No se pudo construir el contexto mTLS en memoria: %s", e)
        return None


def session_mtls(proveedor_claves):
    """`requests.Session` con el contexto mTLS montado para HTTPS. None si falla."""
    ctx = contexto_mtls(proveedor_claves)
    if ctx is None:
        return None
    try:
        import requests
        from requests.adapters import HTTPAdapter

        class _AdaptadorMTLS(HTTPAdapter):
            def __init__(self, contexto, **kw):
                self._contexto = contexto
                super().__init__(**kw)

            def init_poolmanager(self, *a, **kw):
                kw["ssl_context"] = self._contexto
                return super().init_poolmanager(*a, **kw)

        s = requests.Session()
        s.mount("https://", _AdaptadorMTLS(ctx))
        return s
    except Exception as e:
        logger.error("No se pudo crear la sesión mTLS: %s", e)
        return None


def transporte_mtls(proveedor_claves):
    """Devuelve un `transporte(url, cuerpo:bytes, cfg)->(status:int, texto:str)` mTLS
    para `EmisorVerifactu`, o None si no hay certificado válido."""
    s = session_mtls(proveedor_claves)
    if s is None:
        return None

    def _transporte(url, cuerpo, cfg):
        r = s.post(url, data=cuerpo,
                   headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""},
                   timeout=int((cfg or {}).get("timeout", 30)))
        return r.status_code, r.text

    return _transporte


def revisar_caducidad(id_empresa=None, dias_aviso: int = 30) -> dict:
    """Alerta de caducidad del certificado activo. Devuelve {dias, estado, aviso}."""
    from src.services.fiscal import certificados as C
    dias = C.dias_para_caducar(id_empresa)
    if dias is None:
        return {"dias": None, "estado": "sin_certificado", "aviso": True}
    if dias < 0:
        logger.warning("Certificado fiscal CADUCADO (empresa=%s)", id_empresa)
        return {"dias": dias, "estado": "caducado", "aviso": True}
    if dias <= dias_aviso:
        logger.warning("Certificado fiscal caduca en %d días (empresa=%s)", dias, id_empresa)
        return {"dias": dias, "estado": "por_caducar", "aviso": True}
    return {"dias": dias, "estado": "vigente", "aviso": False}
