"""
Bascula de recuento automatico (Gestion de Caja / arqueo) - Smart Manager AI.

Integra una bascula CONTADORA de monedas/billetes durante el arqueo de caja (apertura,
cierre, cambio de cajero, caja fuerte - todos los popups que reutilizan
`_ConteoEfectivoDialog` en `src/gui/gestion_usuarios.py`).

Flujo real de hardware (confirmado con el usuario, clase de dispositivo comercial tipo
Cassida/Ratiotec/AccuBanker/Kobotech): el cajero conecta la bascula, pesa cada denominacion
POR SEPARADO en el propio aparato (esto ocurre en el hardware, fuera de esta app) y el
dispositivo calcula el recuento exacto el mismo (peso -> unidades, con sus propias tablas
internas de peso unitario por moneda/billete). Nuestro software NUNCA hace esa division: solo
LEE por puerto serie el informe de recuento YA CALCULADO que la bascula emite, y lo vuelca en
la tabla de arqueo cuando el cajero pulsa "Transferir recuento".

Reutiliza la primitiva de bajo nivel existente (`pyserial`, la misma libreria que ya usa
`SerialScaleDriver` en `src/services/tpv/scale_service.py` para pesar producto a granel en el
TPV) en vez de anadir una segunda dependencia de hardware: no hace falta un ScaleDriver nuevo
porque el patron de lectura es distinto (un informe multi-linea puntual bajo demanda, no un
flujo continuo de un unico peso), asi que este modulo abre su propia conexion `serial.Serial`
de corta duracion (abrir -> pedir informe -> leer -> cerrar) igual que hace
`SerialScaleDriver.connect()` internamente.

=========================================================================================
PROTOCOLO ASUMIDO (documentado - no hay modelo de hardware concreto en este repo; si el
dispositivo real emite un formato distinto, adaptar solo `_solicitar_informe()` y
`_candidatos_linea()` mas abajo, el resto del modulo no deberia cambiar):
=========================================================================================
  - Tras pedir el informe (ver `_solicitar_informe`), la bascula responde con un bloque ASCII
    de texto por el puerto serie, normalmente UNA LINEA POR DENOMINACION, con dos o tres
    campos:
        <denominacion>,<cantidad>
        <denominacion>,<cantidad>,<subtotal>
    Se toleran variantes de separador (coma, punto y coma, tabulador, barra vertical),
    simbolo de moneda opcional pegado al valor (se descarta) y separador decimal coma O
    punto (formato europeo vs. anglosajon).
  - Puede haber lineas de cabecera/pie (fecha, total, checksum, "END", etc.): se ignoran sin
    mas, ya que no producen ningun par denominacion/cantidad valido para la divisa activa.
  - Fin de transmision: se asume por silencio (la bascula deja de enviar bytes durante
    `_SILENCIO_FIN_S` segundos) dentro de una ventana total `_VENTANA_LECTURA_S`.
Esto sigue el mismo criterio que el resto del proyecto para protocolos serie/de red simples y
bien entendidos sin libreria de terceros dedicada (ver comentarios de
`src/services/camaras/descubrimiento.py` sobre WS-Discovery/ONVIF, o el motor TOTP propio):
no se inventa una libreria de protocolo, se implementa el subconjunto ASCII tolerante que
describen los manuales tipicos de esta familia de basculas contadoras.

Degradacion honesta (mismo patron que `src/utils/rfid_gateway.py` y
`src/services/camaras/prerrequisitos.py`: detectar ausencia/fallo de hardware y avisar, nunca
fabricar datos en silencio):
  - Sin bascula configurada          -> estado 'no_configurada'  (aviso INFO, intentar_conectar)
  - Configurada pero sin respuesta   -> estado 'error_conexion'  (aviso ERROR, intentar_conectar)
  - Conectada pero informe ilegible  -> estado 'error_lectura'   (aviso ERROR, leer_recuento)
  - Conectada y leida                -> estado 'ok'              (recuento real disponible)
`leer_recuento()` NUNCA devuelve un recuento fabricado: si no se puede extraer NINGUN par
denominacion/cantidad valido de la respuesta, reporta 'error_lectura' con un detalle honesto.

Config (variables de entorno - mismo estilo que el resto de flags de hardware/simulacion del
proyecto, p. ej. `SMART_MANAGER_PERFIL_TACTIL`, `TERMINAL_ROL`):

  SMART_MANAGER_BASCULA_RECUENTO_PUERTO
      Puerto serie configurado (ej. 'COM5'). Vacio/ausente = bascula no configurada.
  SMART_MANAGER_BASCULA_RECUENTO_BAUD
      Baudios de conexion (por defecto 9600).
  SMART_MANAGER_BASCULA_RECUENTO_SIMULAR
      SOLO para desarrollo/pruebas sin hardware real (no se lee en produccion real salvo que
      alguien la fije a proposito): 'ok' fuerza una conexion simulada EXITOSA (y un recuento de
      PRUEBA generado localmente, ver `_recuento_prueba_dev`, NUNCA usado en el camino real);
      'fail' fuerza un fallo de conexion/lectura simulado. Cualquier otro valor/ausente ->
      comportamiento real (intenta conectar y leer de verdad si hay puerto configurado, o
      reporta 'no_configurada' si no lo hay).
"""
from __future__ import annotations

import logging
import random
import re
import time

from src.services.tpv.scale_service import SerialScaleDriver  # reutilizado por
# `intentar_conectar` para el sondeo de conexion (ver mas abajo); `leer_recuento` abre su
# propia `serial.Serial` de corta duracion para el informe multi-linea (ver docstring del modulo).

logger = logging.getLogger("tpv.bascula_recuento")

ENV_PUERTO = "SMART_MANAGER_BASCULA_RECUENTO_PUERTO"
ENV_BAUD = "SMART_MANAGER_BASCULA_RECUENTO_BAUD"
ENV_SIMULAR = "SMART_MANAGER_BASCULA_RECUENTO_SIMULAR"

# Tiempos de la ventana de lectura del informe de recuento (ver docstring del modulo).
_TIMEOUT_PUERTO_S = 0.5       # timeout de cada lectura individual del puerto serie
_VENTANA_LECTURA_S = 3.0      # tiempo maximo total esperando el informe completo
_SILENCIO_FIN_S = 0.6         # silencio tras el cual se asume que el informe ha terminado

# Comando de sondeo enviado para solicitar el informe de recuento. Documentado como suposicion:
# ENQ (0x05) es una convencion de sondeo serie muy extendida en periféricos de esta familia; si
# la bascula ya envia el informe automaticamente al terminar el ciclo de pesaje (sin necesidad de
# sondeo), este byte se ignora sin más en el dispositivo y la lectura posterior lo capta igual.
_COMANDO_SOLICITUD_INFORME = b"\x05"

_RE_NUM = re.compile(r"[-+]?\d+(?:[.,]\d+)?")
# "digito,dosdigitos" al final del numero -> muy probablemente un decimal de centimos en coma
# europea (0,50) y NO un separador de campo seguido de una cantidad de dos cifras.
_RE_DECIMAL_COMA_CENTIMOS = re.compile(r"(\d+),(\d{2})(?!\d)")


def _puerto_configurado() -> str:
    import os
    return (os.getenv(ENV_PUERTO) or "").strip()


def _baud_configurado() -> int:
    import os
    try:
        return int(os.getenv(ENV_BAUD, "9600"))
    except (TypeError, ValueError):
        return 9600


def _modo_prueba_forzado() -> str:
    import os
    return (os.getenv(ENV_SIMULAR) or "").strip().lower()


def intentar_conectar() -> dict:
    """
    Intenta conectar con la bascula de recuento configurada.

    Devuelve {'estado': 'no_configurada' | 'error_conexion' | 'conectada', 'detalle': str}.
    Nunca fabrica una conexion inexistente: si no hay puerto configurado, ni siquiera lo
    intenta (igual que `prerrequisitos.avisos_pendientes` con ffmpeg/onvif ausentes).
    """
    forzado = _modo_prueba_forzado()
    if forzado == "ok":
        return {"estado": "conectada",
                "detalle": "Conexion simulada (modo de pruebas, sin hardware real)."}
    if forzado == "fail":
        return {"estado": "error_conexion",
                "detalle": "Fallo de conexion simulado (modo de pruebas, sin hardware real)."}

    puerto = _puerto_configurado()
    if not puerto:
        return {"estado": "no_configurada", "detalle": "No hay puerto de bascula configurado."}

    driver = SerialScaleDriver(puerto, _baud_configurado())
    try:
        ok = driver.connect()
    except Exception as exc:  # pragma: no cover - defensivo, igual que el resto del proyecto
        return {"estado": "error_conexion", "detalle": str(exc)}
    finally:
        try:
            driver.disconnect()
        except Exception:
            pass

    if ok:
        return {"estado": "conectada", "detalle": f"Bascula detectada en {puerto}."}
    return {"estado": "error_conexion", "detalle": f"Sin respuesta de la bascula en {puerto}."}


# ─── Lectura REAL del informe de recuento ──────────────────────────────────────

def leer_recuento(denominaciones: list) -> dict:
    """
    Lee por puerto serie el recuento por denominacion YA CALCULADO por la bascula (ver
    protocolo asumido en el docstring del modulo) y lo mapea a las denominaciones reales de la
    divisa activa (`denominaciones`, tal cual las produce `src.utils.divisas.denominaciones()`).

    Devuelve:
      {'estado': 'ok', 'recuento': {valor_denominacion: cantidad, ...}, 'detalle': str}
      {'estado': 'error_lectura', 'recuento': None, 'detalle': str}

    Nunca fabrica cantidades: si el sondeo falla, se agota el tiempo de espera, o la respuesta
    no contiene NINGUN par denominacion/cantidad reconocible para la divisa activa, se devuelve
    'error_lectura' con un detalle honesto (nunca datos aleatorios/inventados en el camino real).
    """
    forzado = _modo_prueba_forzado()
    if forzado == "ok":
        return {"estado": "ok", "recuento": _recuento_prueba_dev(denominaciones),
                "detalle": "Recuento simulado (modo de pruebas, sin hardware real)."}
    if forzado == "fail":
        return {"estado": "error_lectura", "recuento": None,
                "detalle": "No se pudo leer el recuento de la bascula (fallo simulado, modo "
                           "de pruebas, sin hardware real)."}

    puerto = _puerto_configurado()
    if not puerto:
        return {"estado": "error_lectura", "recuento": None,
                "detalle": "No se pudo leer el recuento de la bascula: no hay puerto "
                           "configurado."}

    try:
        import serial
    except Exception as exc:
        return {"estado": "error_lectura", "recuento": None,
                "detalle": f"No se pudo leer el recuento de la bascula: libreria serie no "
                           f"disponible ({exc})."}

    try:
        conexion = serial.Serial(puerto, _baud_configurado(), timeout=_TIMEOUT_PUERTO_S)
    except Exception as exc:
        return {"estado": "error_lectura", "recuento": None,
                "detalle": f"No se pudo leer el recuento de la bascula: {exc}"}

    try:
        try:
            conexion.write(_COMANDO_SOLICITUD_INFORME)
        except Exception:
            pass  # algunas basculas envian el informe sin necesidad de sondeo explicito
        crudo = _leer_informe_crudo(conexion)
    except Exception as exc:
        return {"estado": "error_lectura", "recuento": None,
                "detalle": f"No se pudo leer el recuento de la bascula: {exc}"}
    finally:
        try:
            conexion.close()
        except Exception:
            pass

    if not crudo.strip():
        return {"estado": "error_lectura", "recuento": None,
                "detalle": "No se pudo leer el recuento de la bascula: no se recibio ningun "
                           "dato por el puerto serie."}

    recuento = _parsear_informe_recuento(crudo, denominaciones)
    if not recuento:
        return {"estado": "error_lectura", "recuento": None,
                "detalle": "No se pudo leer el recuento de la bascula: la respuesta no "
                           "contenia ninguna denominacion reconocida para la divisa activa."}

    return {"estado": "ok", "recuento": recuento,
            "detalle": f"Recuento leido correctamente de {puerto}."}


def _leer_informe_crudo(conexion) -> str:
    """
    Lee todas las lineas disponibles del puerto serie hasta que la bascula deja de enviar datos
    (silencio de `_SILENCIO_FIN_S` tras haber recibido algo) o se agota la ventana total
    `_VENTANA_LECTURA_S`. `conexion` es un `serial.Serial` ya abierto con timeout por lectura.
    """
    fin_ventana = time.monotonic() + _VENTANA_LECTURA_S
    lineas: list[str] = []
    ultimo_dato = None
    while time.monotonic() < fin_ventana:
        bruto = conexion.readline()
        if bruto:
            lineas.append(bruto.decode("ascii", errors="ignore"))
            ultimo_dato = time.monotonic()
        elif ultimo_dato is not None and (time.monotonic() - ultimo_dato) > _SILENCIO_FIN_S:
            break  # ya llego informe y ahora hay silencio -> se asume fin de transmision
    return "\n".join(lineas)


def _normalizar_linea(linea: str) -> str:
    """Descarta simbolos de moneda y cualquier caracter que no sea digito/separador util."""
    return re.sub(r"[^0-9.,;\t|+\- ]", "", linea)


def _a_float(token) -> float | None:
    if token is None:
        return None
    txt = str(token).strip()
    if not txt:
        return None
    try:
        return float(txt.replace(",", "."))
    except ValueError:
        return None


def _candidatos_linea(linea: str) -> list:
    """
    Genera 1 o 2 interpretaciones candidatas de una linea del informe como lista de floats
    [denominacion, cantidad, (subtotal opcional)].

    Con separador explicito e inequivoco (tabulador, punto y coma o barra) la coma dentro de un
    campo solo puede ser separador decimal -> una unica interpretacion.

    Con la coma como UNICO separador disponible la lectura es ambigua (separador de campo vs.
    decimal en formato europeo: "0,50,12" vs. "5,10"), asi que se generan AMBAS lecturas
    posibles; `_parsear_informe_recuento` acepta la primera cuyo primer valor coincide con una
    denominacion real de la divisa activa (heuristica documentada, ver protocolo del modulo).
    """
    limpia = _normalizar_linea(linea).strip()
    if not limpia:
        return []

    for sep in ("\t", ";", "|"):
        if sep in limpia:
            campos = [_a_float(c) for c in limpia.split(sep) if c.strip()]
            campos = [c for c in campos if c is not None]
            return [campos] if campos else []

    if "," not in limpia:
        valores = [v for v in (_a_float(t) for t in _RE_NUM.findall(limpia)) if v is not None]
        return [valores] if valores else []

    candidatos = []

    # Candidato A: la coma es puramente separador de campo (denominacion sin decimales, o el
    # informe ya usa punto para decimales y coma solo como separador).
    campos_a = [_a_float(c) for c in limpia.split(",") if c.strip()]
    campos_a = [c for c in campos_a if c is not None]
    if campos_a:
        candidatos.append(campos_a)

    # Candidato B: protege un "digito,dosdigitos" como decimal de centimos antes de partir por
    # las comas restantes (formato europeo: "0,50,12" -> denominacion 0.50, cantidad 12).
    protegida = _RE_DECIMAL_COMA_CENTIMOS.sub(lambda m: f"{m.group(1)}.{m.group(2)}", limpia,
                                               count=1)
    if protegida != limpia:
        campos_b = [_a_float(c) for c in protegida.split(",") if c.strip()]
        campos_b = [c for c in campos_b if c is not None]
        if campos_b:
            candidatos.append(campos_b)

    return candidatos


def _parsear_informe_recuento(crudo: str, denominaciones: list) -> dict:
    """
    Extrae {valor_denominacion: cantidad} del informe crudo, aceptando SOLO pares cuya
    denominacion coincide (con tolerancia de redondeo) con una denominacion real de
    `denominaciones` (la lista de la divisa activa que ya usa la tabla de arqueo) y cuya
    cantidad es un entero no negativo. Cualquier linea que no cumpla esto (cabeceras, pies,
    checksums, denominaciones ajenas a la divisa activa, cantidades no enteras) se ignora.
    """
    valores_validos = [float(d["valor"]) for d in denominaciones]
    recuento: dict = {}
    for linea in crudo.splitlines():
        linea = linea.strip()
        if not linea:
            continue
        for candidato in _candidatos_linea(linea):
            if len(candidato) < 2:
                continue
            denom, cantidad = candidato[0], candidato[1]
            if denom is None or cantidad is None:
                continue
            if cantidad < 0 or abs(cantidad - round(cantidad)) > 1e-6:
                continue  # la cantidad debe ser un entero (unidades contadas)
            coincidencia = next(
                (v for v in valores_validos if abs(v - denom) < 0.005), None
            )
            if coincidencia is None:
                continue
            recuento[coincidencia] = int(round(cantidad))
            break  # interpretacion valida encontrada, no probar el otro candidato de la linea
        else:
            logger.debug("Linea de informe de bascula ignorada (sin denominacion reconocida): %r",
                         linea)
    return recuento


def _recuento_prueba_dev(denominaciones: list) -> dict:
    """
    SOLO para desarrollo/pruebas manuales sin hardware (`SMART_MANAGER_BASCULA_RECUENTO_SIMULAR
    =ok`): genera cantidades aleatorias plausibles. El camino real (`leer_recuento`, cuando NO
    hay simulacion forzada) NUNCA llama a esta funcion ni fabrica cantidades de ningun tipo.
    """
    return {den["valor"]: random.randint(0, 30) for den in denominaciones}
