"""
Descubrimiento de cámaras (WS-Discovery + ONVIF) — DEGRADABLE y HONESTO: sin red multicast, sin
librería ONVIF o sin cámara alcanzable, nunca se inventa una IP/fabricante/URL de stream. No dependen
de base de datos (a diferencia del resto de `test_camaras*.py`): son llamadas de red/librería puras.
"""

from src.services.camaras import descubrimiento as DESC

_HOST_NO_RUTEABLE = "10.255.255.1"   # bloque TEST-NET-3 (RFC 5737 aplicado a un /24 reservado): nunca
                                     # responde en una red real, perfecto para probar el timeout


def test_escanear_red_degradable_sin_camaras():
    """Sin cámaras ONVIF reales en la red (o sin soporte multicast), la búsqueda no lanza y devuelve
    una lista (vacía en este entorno) en un tiempo acotado."""
    r = DESC.escanear_red(timeout_seg=2)
    assert isinstance(r, list)


def test_probar_conexion_honesto_host_inalcanzable():
    r = DESC.probar_conexion(_HOST_NO_RUTEABLE, "u", "p")
    assert isinstance(r, dict) and "ok" in r and "motivo" in r
    assert r["ok"] is False
    assert r["motivo"]                      # motivo real, nunca vacío
    if not DESC._onvif_disponible():
        assert "onvif" in r["motivo"].lower() or "ONVIF" in r["motivo"]


def test_probar_conexion_host_vacio():
    r = DESC.probar_conexion("", "u", "p")
    assert r == {"ok": False, "motivo": "host vacío"} or r["ok"] is False


def test_extraer_perfiles_honesto_host_inalcanzable():
    r = DESC.extraer_perfiles(_HOST_NO_RUTEABLE, "u", "p")
    assert r is None                        # nunca inventa una URI de stream


def test_parse_probematch_ignora_xml_sin_xaddrs():
    xml_sin_xaddrs = b"<Envelope xmlns='http://www.w3.org/2003/05/soap-envelope'><Body/></Envelope>"
    assert DESC._parse_probematch(xml_sin_xaddrs) is None


def test_parse_probematch_extrae_xaddr_uuid_scopes():
    xml = (
        b"<e:Envelope xmlns:e='http://www.w3.org/2003/05/soap-envelope' "
        b"xmlns:w='http://schemas.xmlsoap.org/ws/2004/08/addressing' "
        b"xmlns:d='http://schemas.xmlsoap.org/ws/2005/04/discovery'>"
        b"<e:Body><d:ProbeMatches><d:ProbeMatch>"
        b"<w:EndpointReference><w:Address>urn:uuid:abc-123</w:Address></w:EndpointReference>"
        b"<d:Types>dn:NetworkVideoTransmitter</d:Types>"
        b"<d:Scopes>onvif://www.onvif.org/hardware/ModeloX onvif://www.onvif.org/type/video</d:Scopes>"
        b"<d:XAddrs>http://192.168.1.50:8080/onvif/device_service</d:XAddrs>"
        b"</d:ProbeMatch></d:ProbeMatches></e:Body></e:Envelope>"
    )
    info = DESC._parse_probematch(xml)
    assert info is not None
    assert info["xaddr"] == "http://192.168.1.50:8080/onvif/device_service"
    assert info["uuid"] == "urn:uuid:abc-123"
    assert DESC._fabricante_de_scopes(info["scopes"]) == "ModeloX"


def test_puerto_de_extrae_puerto_del_xaddr():
    assert DESC.puerto_de("http://192.168.1.50:8080/onvif/device_service") == 8080
    assert DESC.puerto_de("http://192.168.1.50/onvif/device_service", default=80) == 80
    assert DESC.puerto_de("no-es-una-url") == 80
