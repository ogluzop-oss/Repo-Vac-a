"""
Validación de NIF-IVA intracomunitario (VAT number UE) y consulta REAL al servicio público VIES.

Mismo criterio que `utils/nif_cif.py` (algoritmos de control REALES, nunca aproximados) y que
`services/camaras/descubrimiento.py` (protocolo bien entendido → se implementa en casa en vez de
sumar una dependencia nueva): la consulta a VIES usa el endpoint REST oficial de la Comisión
Europea (`ec.europa.eu/taxation_customs/vies/rest-api`) con `requests`, que ya es dependencia
dura del proyecto (cliente HTTP de la API/gateway RFID) — no hace falta SOAP/zeep para esto
(`zeep` solo llega como dependencia transitiva OPCIONAL de `onvif-zeep`, condicional a cámaras).

Checksum REAL implementado (algoritmo oficial de cada país, documentado en el docstring de cada
función) para 6 países como mínimo — DE, FR, IT, PT, NL, BE — más ES por REUTILIZACIÓN directa del
motor ya existente en `utils/nif_cif.py` (el NIF-IVA español es simplemente "ES" + DNI/NIE/CIF; no
se duplica el algoritmo). Para el resto de países de la UE se aplica una comprobación GENÉRICA de
longitud/formato, devuelta siempre con `metodo="formato"` — nunca se etiqueta como "checksum" algo
que no se ha comprobado dígito a dígito.

Degradación honesta: si el servicio VIES no responde (red/timeout/mantenimiento), `consultar_vies`
devuelve `ok=False` con el motivo real — NUNCA fabrica un "válido"/"inválido" que no venga de
verdad del servicio (mismo principio ya aplicado esta sesión a NIF/CIF y a los certificados AEAT).
"""

import logging
import re

logger = logging.getLogger("utils.vies")

_TIMEOUT = 10
_VIES_REST_URL = "https://ec.europa.eu/taxation_customs/vies/rest-api/check-vat-number"

# Longitud del NIF-IVA (SIN el prefijo de país) por Estado miembro — comprobación de FORMATO
# (fallback honesto para los países sin checksum real implementado más abajo). Fuente: longitudes
# fijas publicadas en la especificación técnica pública de VIES.
_LONGITUDES_UE = {
    "AT": (9,), "BE": (10,), "BG": (9, 10), "CY": (9,), "CZ": (8, 9, 10), "DE": (9,),
    "DK": (8,), "EE": (9,), "EL": (9,), "ES": (9,), "FI": (8,), "FR": (11,), "HR": (11,),
    "HU": (8,), "IE": (8, 9), "IT": (11,), "LT": (9, 12), "LU": (8,), "LV": (11,), "MT": (8,),
    "NL": (12,), "PL": (10,), "PT": (9,), "RO": (2, 3, 4, 5, 6, 7, 8, 9, 10), "SE": (12,),
    "SI": (8,), "SK": (10,),
}

# Países con checksum REAL implementado en este módulo. El resto usa el fallback de formato.
_CON_CHECKSUM_REAL = ("DE", "FR", "IT", "PT", "NL", "BE", "ES")

_RE_PREFIJO = re.compile(r"^([A-Z]{2})(.*)$")


def normalizar_nif_iva(valor: str | None) -> str:
    """Quita espacios/guiones/puntos y pasa a mayúsculas (mismo criterio que
    `nif_cif.normalizar_nif_cif`)."""
    return re.sub(r"[\s\-.]", "", (valor or "")).upper()


def _detectar_pais(valor_norm: str):
    """Separa prefijo de país (2 letras) del resto. 'GR' (ISO-3166 de Grecia) se normaliza a
    'EL' (prefijo que usa VIES/la UE para Grecia)."""
    m = _RE_PREFIJO.match(valor_norm)
    if not m:
        return None, valor_norm
    prefijo, resto = m.group(1), m.group(2)
    if prefijo == "GR":
        prefijo = "EL"
    if prefijo in _LONGITUDES_UE:
        return prefijo, resto
    return None, valor_norm


# ── Checksums REALES por país (algoritmo oficial, documentado) ───────────────

def _checksum_de(numero: str) -> bool:
    """Alemania (USt-IdNr): 9 dígitos. ISO 7064 MOD 11,10 — el algoritmo oficial publicado por
    el Bundeszentralamt für Steuern: se itera un 'producto' arrancando en 10; por cada uno de
    los 8 primeros dígitos, suma = (dígito + producto) % 10 (si sale 0, se toma 10), y el nuevo
    producto = (2 × suma) % 11. El dígito de control = 11 − producto final (10 → 0)."""
    if not re.fullmatch(r"\d{9}", numero):
        return False
    producto = 10
    for c in numero[:8]:
        suma = (int(c) + producto) % 10
        if suma == 0:
            suma = 10
        producto = (2 * suma) % 11
    control = 11 - producto
    if control == 10:
        control = 0
    return control == int(numero[8])


def _checksum_fr(numero: str) -> bool:
    """Francia: 2 caracteres de control + 9 dígitos de SIREN. Caso general (control NUMÉRICO,
    inmensa mayoría de los casos): clave = (12 + 3 × (SIREN mod 97)) mod 97; el control debe
    ser esa clave en 2 dígitos. Existe una variante histórica minoritaria con letras en el
    control (regla distinta, no pública de forma simple) — esa variante NO se aproxima aquí;
    se resuelve como formato-only en `validar_nif_iva_detalle`, nunca como checksum fallido."""
    if not re.fullmatch(r"\d{2}\d{9}", numero):
        return False
    control, siren = numero[:2], numero[2:]
    clave = (12 + 3 * (int(siren) % 97)) % 97
    return int(control) == clave


def _checksum_it(numero: str) -> bool:
    """Italia (Partita IVA): 11 dígitos. Dígito de control = variante de Luhn (mismo esquema
    que el CIF español de `nif_cif.py`): los 10 primeros dígitos, posiciones pares (2ª,4ª,...)
    se doblan (si el resultado > 9 se le restan 9); se suman todas; control = (10 − total%10)%10."""
    if not re.fullmatch(r"\d{11}", numero):
        return False
    total = 0
    for i, c in enumerate(numero[:10]):
        d = int(c)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    control = (10 - (total % 10)) % 10
    return control == int(numero[10])


def _checksum_pt(numero: str) -> bool:
    """Portugal (NIF/NIPC): 9 dígitos. Mód-11 con pesos 9..2 sobre los 8 primeros dígitos;
    resto = suma % 11; control = 0 si resto es 0 o 1, si no 11 − resto (algoritmo oficial)."""
    if not re.fullmatch(r"\d{9}", numero):
        return False
    total = sum(int(c) * w for c, w in zip(numero[:8], range(9, 1, -1)))
    resto = total % 11
    control = 0 if resto in (0, 1) else 11 - resto
    return control == int(numero[8])


def _checksum_nl(numero: str) -> bool:
    """Países Bajos: 9 dígitos + 'B' + 2 dígitos de sucursal. 'Elfproef' (mód-11) oficial sobre
    los 9 dígitos del NIF: pesos 9..2 para los 8 primeros, menos el 9º dígito (peso −1); válido
    únicamente si el resultado es múltiplo EXACTO de 11 (resto 0 — sin ninguna excepción: para
    cada combinación de 8 primeros dígitos existe un único 9º dígito que lo cumple)."""
    if not re.fullmatch(r"\d{9}B\d{2}", numero):
        return False
    digitos = numero[:9]
    total = sum(int(c) * w for c, w in zip(digitos[:8], range(9, 1, -1))) - int(digitos[8])
    return total % 11 == 0


def _checksum_be(numero: str) -> bool:
    """Bélgica: 10 dígitos. Control (últimos 2 dígitos) = 97 − (los 8 primeros dígitos mód 97)
    (algoritmo oficial del BTW-nummer/numéro de TVA belga)."""
    if not re.fullmatch(r"\d{10}", numero):
        return False
    base, control = int(numero[:8]), int(numero[8:10])
    return control == (97 - (base % 97))


def _checksum_es(numero: str) -> bool:
    """España: NO se reinventa — el NIF-IVA español es 'ES' + DNI/NIE/CIF; se reutiliza el motor
    REAL ya existente (`utils/nif_cif.validar_documento_fiscal`), sin duplicar el algoritmo."""
    from src.utils import nif_cif
    ok, _tipo = nif_cif.validar_documento_fiscal(numero)
    return ok


_VALIDADORES_CHECKSUM = {
    "DE": _checksum_de, "FR": _checksum_fr, "IT": _checksum_it,
    "PT": _checksum_pt, "NL": _checksum_nl, "BE": _checksum_be, "ES": _checksum_es,
}


def _formato_valido(pais: str, resto: str) -> bool:
    longs = _LONGITUDES_UE.get(pais)
    if not longs:
        return False
    return len(resto) in longs and resto.isalnum()


def validar_nif_iva_detalle(valor, pais=None) -> dict:
    """Detalle completo de la validación: `{ok, pais, metodo, mensaje}`.

    `metodo` distingue SIEMPRE si el resultado viene de un checksum real ('checksum') o de una
    comprobación de longitud/formato sin verificar dígito a dígito ('formato') — nunca se
    presenta lo segundo como si fuera lo primero (honestidad, mismo principio que en toda la
    sesión: IA heurística vs ML, certificado real vs simulado AEAT, etc.)."""
    v = normalizar_nif_iva(valor)
    if pais:
        detectado = pais.strip().upper()
        resto = v[len(detectado):] if v.startswith(detectado) else v
    else:
        detectado, resto = _detectar_pais(v)
    if not detectado or detectado not in _LONGITUDES_UE:
        return {"ok": False, "pais": detectado, "metodo": None,
                "mensaje": "Prefijo de país no reconocido como miembro de la UE."}
    # FR: el control alfabético es un caso histórico minoritario con regla propia no aproximada
    # aquí — se resuelve como formato-only en vez de forzar un checksum incorrecto.
    if detectado == "FR" and not re.fullmatch(r"\d{11}", resto):
        ok = _formato_valido(detectado, resto)
        return {"ok": ok, "pais": detectado, "metodo": "formato",
                "mensaje": "Control alfabético (variante histórica poco común): solo se comprueba "
                           "el formato, sin checksum real disponible para este caso."}
    if detectado in _VALIDADORES_CHECKSUM:
        ok = _VALIDADORES_CHECKSUM[detectado](resto)
        return {"ok": ok, "pais": detectado, "metodo": "checksum",
                "mensaje": "Checksum oficial verificado." if ok else "Checksum inválido."}
    ok = _formato_valido(detectado, resto)
    return {"ok": ok, "pais": detectado, "metodo": "formato",
            "mensaje": ("Formato correcto (longitud), SIN checksum real disponible para este "
                        "país — no verificado dígito a dígito." if ok else "Formato incorrecto.")}


def validar_formato_nif_iva(valor, pais=None) -> tuple[bool, str]:
    """(ok, país detectado/confirmado). Ver `validar_nif_iva_detalle` si se necesita distinguir
    checksum-verificado de formato-sin-verificar (p.ej. para no afirmar más certeza de la real)."""
    d = validar_nif_iva_detalle(valor, pais)
    return bool(d["ok"]), (d.get("pais") or "")


def consultar_vies(pais, nif_iva) -> dict:
    """Consulta REAL al servicio público VIES (REST API oficial de la Comisión Europea, sin
    credenciales) — sustituye el desplegable manual `clientes.validacion_vies` por una
    comprobación de verdad. Devuelve `{ok, valido, nombre, direccion, error}`:

    - `ok=True`  → la consulta se completó de verdad contra VIES (`valido` refleja su respuesta).
    - `ok=False` → NO se pudo verificar (red/timeout/servicio caído/mantenimiento programado,
      que VIES sufre con frecuencia) — `valido` queda `None`. NUNCA se fabrica un True/False que
      no venga realmente del servicio (mismo principio que Verifactu: nunca simular un resultado
      que no ha ocurrido de verdad)."""
    import requests
    pais_n = (pais or "").strip().upper()
    numero = normalizar_nif_iva(nif_iva)
    if pais_n and numero.startswith(pais_n):
        numero = numero[len(pais_n):]
    if not pais_n or not numero:
        return {"ok": False, "valido": None, "nombre": None, "direccion": None,
                "error": "País o número de NIF-IVA vacío."}
    try:
        resp = requests.post(_VIES_REST_URL,
                             json={"countryCode": pais_n, "vatNumber": numero},
                             timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json() or {}
        return {"ok": True, "valido": bool(data.get("valid")),
                "nombre": (data.get("name") or "").strip() or None,
                "direccion": (data.get("address") or "").strip() or None,
                "error": None}
    except Exception as e:
        logger.warning("consultar_vies(%s, %s): %s", pais, nif_iva, e)
        return {"ok": False, "valido": None, "nombre": None, "direccion": None,
                "error": f"No se pudo verificar contra VIES: {e}"}
