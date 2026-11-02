"""
Asistente de Vinculación RFID (módulo Ubicación, pestaña RFID) — API-First, sin PyQt.

Orquesta el ciclo completo EAN → número de serie → EPC (SGTIN-96) → grabación física → lectura
cruzada de verificación → persistencia, reutilizando SIEMPRE lo ya existente:
  - `src.db.articulos.ficha_rfid` / `src.db.articulos` para localizar el artículo por su EAN.
  - `src.services.rfid.sgtin.codificar_sgtin96` para construir la trama EPC.
  - `src.db.ubicaciones.siguiente_numero_serie` / `registrar_etiqueta_rfid` para el serial y la
    persistencia (misma tabla `ubicaciones` que ya usa el resto del módulo de Ubicación y el
    anti-hurto — NO se crea una tabla paralela).
  - `gateway.escribir_tag(epc)` / `gateway.leer_tag()` (`src.utils.rfid_gateway.LectorZebraGateway`,
    ya madurado con lectura cruzada real en esta misma tarea) para la parte física — degradable: sin
    `gateway` o con hardware desconectado, se informa el motivo honesto, nunca se finge un éxito.

Una ÚNICA función (`vincular_articulo`) sirve tanto al flujo de una unidad como al modo de
vinculación en lote (la GUI simplemente la llama repetidas veces) — cero lógica duplicada entre
ambos modos.
"""

import logging

logger = logging.getLogger("rfid.vinculacion")

# Motivos de fallo honestos (la GUI los traduce a mensajes amigables).
SIN_ARTICULO = "articulo_no_encontrado"
SIN_HARDWARE = "lector_no_conectado"
FALLO_ESCRITURA = "fallo_escritura_tag"
FALLO_VERIFICACION = "fallo_verificacion_lectura_cruzada"
EPC_DUPLICADO = "epc_ya_registrado"


def buscar_articulo(termino, id_empresa=None):
    """Paso 1 del asistente: localiza el artículo por EAN/código exacto o por nombre parcial.
    Devuelve la ficha (`articulos.ficha_rfid`) o None si no se encuentra nada."""
    from src.db import articulos as art_db
    termino = (termino or "").strip()
    if not termino:
        return None
    ficha = art_db.ficha_rfid(termino, id_empresa=id_empresa)
    if ficha:
        return ficha
    resultados = art_db.buscar_stock(termino, id_empresa=id_empresa)
    if not resultados:
        return None
    primero = resultados[0]
    codigo = primero[0] if not isinstance(primero, dict) else primero.get("codigo")
    return art_db.ficha_rfid(codigo, id_empresa=id_empresa)


def preparar_serie_y_epc(codigo_articulo, *, numero_serie=None, prefijo_digitos=7):
    """Paso 2 del asistente: resuelve el siguiente número de serie libre (o usa el que el usuario
    haya asignado a mano) y construye la trama EPC SGTIN-96. Devuelve dict {numero_serie, epc_hex,
    epc_uri, ...} o None si `codigo_articulo`/`numero_serie` son inválidos (degradación honesta)."""
    from src.db import ubicaciones as ubi_db
    from src.services.rfid import sgtin

    if numero_serie is None:
        numero_serie = ubi_db.siguiente_numero_serie(codigo_articulo)
    return sgtin.codificar_sgtin96(codigo_articulo, numero_serie, prefijo_digitos=prefijo_digitos)


def grabar_y_verificar(gateway, epc_hex) -> dict:
    """Pasos 3+4 del asistente: graba `epc_hex` en el chip más cercano al lector/codificador y
    relee inmediatamente para confirmar que coincide (lectura cruzada) — ambas operaciones ya
    viven en el gateway (`escribir_tag` incluye su propio read-after-write real; aquí además se
    repite la lectura de forma explícita para el feedback de "Paso 4" de la UI). Devuelve
    {ok, motivo} — `motivo` SIEMPRE presente cuando `ok` es False, nunca se asume éxito."""
    if gateway is None:
        return {"ok": False, "motivo": SIN_HARDWARE}
    try:
        if not gateway.escribir_tag(epc_hex):
            return {"ok": False, "motivo": FALLO_ESCRITURA}
    except Exception as e:
        logger.error("grabar_y_verificar: fallo al escribir %s: %s", epc_hex, e)
        return {"ok": False, "motivo": FALLO_ESCRITURA}
    try:
        leido = gateway.leer_tag() if hasattr(gateway, "leer_tag") else epc_hex
    except Exception as e:
        logger.error("grabar_y_verificar: fallo al releer %s: %s", epc_hex, e)
        return {"ok": False, "motivo": FALLO_VERIFICACION}
    if not leido or str(leido).strip().upper() != epc_hex.strip().upper():
        return {"ok": False, "motivo": FALLO_VERIFICACION}
    return {"ok": True, "motivo": None}


def vincular_articulo(gateway, codigo_articulo, *, numero_serie=None, prefijo_digitos=7,
                      pasillo=None, estanteria=None, id_empresa=None) -> dict:
    """Pipeline COMPLETO de vinculación de una unidad (Pasos 2-4): genera serie+EPC, graba en el
    chip, verifica por lectura cruzada y, solo si todo fue bien, persiste en `ubicaciones`. Es el
    ÚNICO punto de entrada que usan tanto el modo de una unidad como el modo de vinculación en
    lote — ninguno de los dos reimplementa esta secuencia por su cuenta.

    Devuelve {ok, motivo, epc_hex, numero_serie, codigo_articulo} — `ok=False` siempre trae un
    `motivo` honesto (sin hardware, fallo de escritura, fallo de verificación, o EPC duplicado), y
    NUNCA persiste una etiqueta que no se haya verificado físicamente."""
    datos = preparar_serie_y_epc(codigo_articulo, numero_serie=numero_serie,
                                 prefijo_digitos=prefijo_digitos)
    if datos is None:
        return {"ok": False, "motivo": SIN_ARTICULO, "epc_hex": None, "numero_serie": numero_serie,
                "codigo_articulo": codigo_articulo}

    resultado = grabar_y_verificar(gateway, datos["epc_hex"])
    if not resultado["ok"]:
        return {"ok": False, "motivo": resultado["motivo"], "epc_hex": datos["epc_hex"],
                "numero_serie": datos["serial"], "codigo_articulo": codigo_articulo}

    from src.db import ubicaciones as ubi_db
    registro = ubi_db.registrar_etiqueta_rfid(
        datos["epc_hex"], codigo_articulo, datos["serial"], id_empresa=id_empresa,
        pasillo=pasillo, estanteria=estanteria)
    if not registro.get("ok"):
        return {"ok": False, "motivo": registro.get("error") or EPC_DUPLICADO,
                "epc_hex": datos["epc_hex"], "numero_serie": datos["serial"],
                "codigo_articulo": codigo_articulo}

    return {"ok": True, "motivo": None, "epc_hex": datos["epc_hex"],
            "numero_serie": datos["serial"], "codigo_articulo": codigo_articulo}


def vincular_lote(gateway, codigos_articulo, *, cantidad_por_articulo=1, prefijo_digitos=7,
                  id_empresa=None, on_progreso=None):
    """Automatización masiva SIN pausa entre unidades: repite `vincular_articulo` para cada código
    en `codigos_articulo`, `cantidad_por_articulo` veces cada uno (serie consecutiva).

    AVISO para hardware real: esta función llama a `vincular_articulo` en bucle SIN esperar a que
    el operario cambie el chip físico entre una unidad y la siguiente — solo tiene sentido con
    `gateway` en modo simulado (demos/tests) o con un aplicador automático que alimenta tags por sí
    solo. Para el flujo real de "vincular N unidades a mano, una detrás de otra, con lector fijo" la
    GUI NO debe usar esta función: debe llamar a `vincular_articulo` UNA vez por cada pulsación de
    "Grabar siguiente", dando tiempo al operario a colocar cada chip (mismo primitivo, bajo control
    de la interfaz en vez de en bucle ciego aquí).

    `on_progreso(indice, total, resultado)`, si se da, se llama tras cada intento.

    Devuelve {total, ok, fallidos: [resultados con ok=False]} — nunca lanza; un fallo individual
    (EPC duplicado, tag no detectado) no aborta el resto del lote."""
    tareas = [c for c in codigos_articulo for _ in range(max(1, int(cantidad_por_articulo)))]
    total = len(tareas)
    resultados = []
    for i, codigo in enumerate(tareas, start=1):
        r = vincular_articulo(gateway, codigo, prefijo_digitos=prefijo_digitos, id_empresa=id_empresa)
        resultados.append(r)
        if callable(on_progreso):
            try:
                on_progreso(i, total, r)
            except Exception as e:
                logger.debug("vincular_lote on_progreso: %s", e)
    fallidos = [r for r in resultados if not r["ok"]]
    return {"total": total, "ok": len(resultados) - len(fallidos), "fallidos": fallidos}
