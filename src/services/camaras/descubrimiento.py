"""
Descubrimiento automático de cámaras (videovigilancia) — WS-Discovery (UDP multicast) + ONVIF.

WS-Discovery está implementado a mano con `socket`+`xml.etree` de la librería estándar (protocolo
simple: un único paquete SOAP de ida y vuelta por UDP multicast) — mismo criterio que el resto del
proyecto para protocolos bien entendidos (motor TOTP propio, cliente SOAP/mTLS propio de la AEAT): se
implementa y audita en casa en vez de añadir una dependencia extra. La autenticación/extracción de
perfiles SÍ usa `onvif-zeep` (única dependencia nueva, condicional — ver `ptz.py`).

Degradable y honesto en todo punto: sin red multicast, sin ONVIF instalado, o sin cámara alcanzable →
listas vacías / `{"ok": False, "motivo": "..."}` / `None`, NUNCA se inventa una IP, un fabricante o una
URL de stream.
"""

import logging
from urllib.parse import unquote, urlparse

logger = logging.getLogger("camaras.descubrimiento")

_MCAST_GRP = "239.255.255.250"
_MCAST_PORT = 3702

_PROBE_TEMPLATE = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope" '
    'xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing" '
    'xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery" '
    'xmlns:dn="http://www.onvif.org/ver10/network/wsdl">'
    '<e:Header>'
    '<w:MessageID>uuid:{msg_id}</w:MessageID>'
    '<w:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>'
    '<w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>'
    '</e:Header>'
    '<e:Body><d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe></e:Body>'
    '</e:Envelope>'
)


def _sin_ns(tag) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _parse_probematch(xml_bytes):
    """Extrae {'xaddr', 'uuid', 'scopes'} de una respuesta ProbeMatch. None si no es válida/relevante."""
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None
    xaddrs = uuid_val = scopes = None
    for el in root.iter():
        tag = _sin_ns(el.tag)
        if tag == "XAddrs" and el.text:
            xaddrs = el.text.strip()
        elif tag == "EndpointReference":
            for child in el:
                if _sin_ns(child.tag) == "Address" and child.text:
                    uuid_val = child.text.strip()
        elif tag == "Scopes" and el.text:
            scopes = el.text.strip()
    if not xaddrs:
        return None
    return {"xaddr": xaddrs.split()[0], "uuid": uuid_val, "scopes": scopes}


def _fabricante_de_scopes(scopes):
    """Mejor esfuerzo: el scope 'onvif://www.onvif.org/hardware/<modelo>' suele traer el modelo/hardware
    del dispositivo. Si no está presente, None (nunca se inventa un fabricante)."""
    if not scopes:
        return None
    for tok in scopes.split():
        if "/hardware/" in tok:
            try:
                return unquote(tok.rsplit("/hardware/", 1)[-1]) or None
            except Exception:
                return None
    return None


def puerto_de(xaddr, default=80) -> int:
    """Puerto ONVIF a partir del XAddr descubierto (ej. http://192.168.1.50:8080/onvif/device_service)."""
    try:
        p = urlparse(xaddr).port
        return int(p) if p else default
    except Exception:
        return default


def escanear_red(timeout_seg=10) -> list:
    """Sondeo WS-Discovery en la red local. Devuelve [{'ip','xaddr','uuid','fabricante'}, ...],
    deduplicado por UUID (o IP si no hay UUID). Degradable: [] si la red no permite multicast o
    cualquier error de socket — nunca lanza."""
    import select
    import socket
    import time
    import uuid as _uuid

    encontrados = {}
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)
        probe = _PROBE_TEMPLATE.format(msg_id=str(_uuid.uuid4())).encode("utf-8")
        sock.sendto(probe, (_MCAST_GRP, _MCAST_PORT))
        fin = time.time() + max(1, int(timeout_seg))
        while time.time() < fin:
            restante = fin - time.time()
            listos, _, _ = select.select([sock], [], [], min(0.5, max(0.05, restante)))
            if not listos:
                continue
            try:
                datos, (ip, _puerto) = sock.recvfrom(65535)
            except OSError:
                continue
            info = _parse_probematch(datos)
            if not info:
                continue
            clave = info.get("uuid") or ip
            if clave in encontrados:
                continue
            encontrados[clave] = {
                "ip": ip, "xaddr": info["xaddr"], "uuid": info.get("uuid"),
                "fabricante": _fabricante_de_scopes(info.get("scopes")),
            }
    except Exception as e:
        logger.debug("escanear_red: %s", e)
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
    return list(encontrados.values())


def _onvif_disponible() -> bool:
    try:
        from src.services.camaras.ptz import _onvif_disponible as _chk
        return _chk()
    except Exception:
        return False


def probar_conexion(host, usuario, contrasena, *, puerto_onvif=80) -> dict:
    """Autentica por ONVIF contra `host`. {'ok': True, 'fabricante', 'modelo'} o {'ok': False,
    'motivo': <razón real>} — honesto: nunca 'ok' sin haber hablado de verdad con la cámara."""
    if not _onvif_disponible():
        return {"ok": False, "motivo": "librería ONVIF no instalada (onvif-zeep)"}
    if not host:
        return {"ok": False, "motivo": "host vacío"}
    try:
        from onvif import ONVIFCamera
        cam = ONVIFCamera(host, int(puerto_onvif), usuario or "", contrasena or "")
        info = cam.devicemgmt.GetDeviceInformation()
        return {"ok": True, "motivo": "ok", "fabricante": getattr(info, "Manufacturer", None),
                "modelo": getattr(info, "Model", None)}
    except Exception as e:
        logger.debug("probar_conexion(%s): %s", host, e)
        return {"ok": False, "motivo": f"error ONVIF: {e}"}


def extraer_perfiles(host, usuario, contrasena, *, puerto_onvif=80) -> dict | None:
    """Consulta GetProfiles() y resuelve la StreamUri del perfil de MAYOR resolución (main) y del de
    MENOR (sub). Si solo hay un perfil, 'sub' queda None (degradable: el llamador usará main también
    para la rejilla). None si ONVIF no disponible, sin perfiles, o cualquier fallo de conexión."""
    if not _onvif_disponible() or not host:
        return None
    try:
        from onvif import ONVIFCamera
        cam = ONVIFCamera(host, int(puerto_onvif), usuario or "", contrasena or "")
        media = cam.create_media_service()
        perfiles = media.GetProfiles()
        if not perfiles:
            return None

        def _resolucion(p):
            try:
                return int(p.VideoEncoderConfiguration.Resolution.Width)
            except Exception:
                return 0

        ordenados = sorted(perfiles, key=_resolucion, reverse=True)

        def _uri(token):
            req = media.create_type("GetStreamUri")
            req.StreamSetup = {"Stream": "RTP-Unicast", "Transport": {"Protocol": "RTSP"}}
            req.ProfileToken = token
            return media.GetStreamUri(req).Uri

        main = _uri(ordenados[0].token)
        sub = _uri(ordenados[-1].token) if len(ordenados) > 1 else None
        return {"main": main, "sub": sub}
    except Exception as e:
        logger.debug("extraer_perfiles(%s): %s", host, e)
        return None
