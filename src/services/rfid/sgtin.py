"""
Codificación/decodificación EPC SGTIN-96 (GS1 EPC Tag Data Standard) — API-First, sin PyQt.

Hasta ahora el único "EPC" que existía en el proyecto era una cadena opaca derivada de un hash
(`rfid_gateway.generar_epc_manual`, usada para etiquetar ESTANTERÍAS/satélites de infraestructura —
no se toca, sigue sirviendo para eso). Para vincular UNIDADES DE PRODUCTO concretas (EAN/GTIN de
`articulos.codigo` + un número de serie único por unidad física) hace falta una trama real,
estructuralmente conforme al estándar SGTIN-96 de GS1, para que cualquier lector/infraestructura
RFID compatible pueda decodificarla. Los códigos de este ERP usan el rango GS1 reservado a uso
interno/instore ('20'–'29', ver `src.utils.ean`), así que el "GS1 Company Prefix" aquí NO es un
prefijo realmente asignado por GS1 — pero la trama se construye con la MISMA aritmética de bits que
usa un EPC real (cabecera, filtro, partición, prefijo de empresa, referencia de artículo, serie).

Capa de 96 bits (MSB→LSB):
    header(8)=00110000 · filtro(3) · partición(3) · company_prefix(N) · item_reference(M) · serial(38)

donde N+M = 44 bits siempre, y los dígitos decimales de company_prefix + item_reference (que
INCLUYE el dígito indicador) suman 13 — ver `_PARTICIONES` (Tabla 14-2 del EPC TDS). El GTIN-13 de
`articulos.codigo` se convierte a GTIN-14 anteponiendo un dígito indicador '0' (mismo criterio GS1
para serializar un GTIN-13/UPC-12 sin empaquetado); el dígito de control del GTIN se DESCARTA al
codificar y se RECALCULA (vía `src.utils.ean.digito_control`) al decodificar — así nunca puede ir
desincronizado del resto del código.
"""

import logging

logger = logging.getLogger("rfid.sgtin")

HEADER_SGTIN96 = 0x30  # 00110000 — SGTIN-96, EPC TDS

# Partición → (bits company_prefix, dígitos company_prefix, bits item_reference, dígitos item_reference)
# Dígitos CP + dígitos IR (incluye el indicador) = 13 siempre; bits CP + bits IR = 44 siempre.
_PARTICIONES = {
    0: (40, 12, 4, 1),
    1: (37, 11, 7, 2),
    2: (34, 10, 10, 3),
    3: (30, 9, 14, 4),
    4: (27, 8, 17, 5),
    5: (24, 7, 20, 6),
    6: (20, 6, 24, 7),
}
_PARTICION_POR_CP_DIGITOS = {cp_d: p for p, (_, cp_d, _, _) in _PARTICIONES.items()}

SERIAL_BITS = 38
SERIAL_MAXIMO = (1 << SERIAL_BITS) - 1  # 274 877 906 943

FILTRO_TODOS_LOS_OTROS = 0
FILTRO_UNIDAD_POS = 1       # unidad de venta al por menor (por defecto en este asistente)
FILTRO_CAJA_COMPLETA = 2
FILTRO_PALET = 3


def codificar_sgtin96(codigo_articulo, numero_serie, *, prefijo_digitos=7, filtro=FILTRO_UNIDAD_POS):
    """Construye la trama SGTIN-96 para una unidad física de `codigo_articulo` (GTIN-13 interno de
    13 dígitos numéricos, `articulos.codigo`) con el `numero_serie` indicado.

    Devuelve dict {epc_hex, epc_uri, company_prefix, item_reference, serial, particion, filtro} o
    None si algún dato de entrada es inválido (degradación honesta: nunca lanza, nunca inventa una
    trama a partir de un código que no es un GTIN de 13 dígitos)."""
    codigo = str(codigo_articulo or "").strip()
    if len(codigo) != 13 or not codigo.isdigit():
        logger.warning("codificar_sgtin96: código no es un GTIN-13 numérico (%r)", codigo_articulo)
        return None
    if prefijo_digitos not in _PARTICION_POR_CP_DIGITOS:
        logger.warning("codificar_sgtin96: prefijo_digitos inválido (%r)", prefijo_digitos)
        return None
    try:
        serial = int(numero_serie)
    except (TypeError, ValueError):
        logger.warning("codificar_sgtin96: numero_serie inválido (%r)", numero_serie)
        return None
    if serial < 0 or serial > SERIAL_MAXIMO:
        logger.warning("codificar_sgtin96: numero_serie fuera de rango (%r)", numero_serie)
        return None

    particion = _PARTICION_POR_CP_DIGITOS[prefijo_digitos]
    cp_bits, cp_digitos, ir_bits, ir_digitos = _PARTICIONES[particion]

    gtin14 = "0" + codigo  # indicador '0' (sin empaquetado) + GTIN-13 completo (con su dígito de control)
    company_prefix_str = gtin14[1:1 + cp_digitos]
    # Referencia de artículo = indicador + resto de dígitos del GTIN hasta antes del dígito de control.
    item_reference_str = gtin14[0] + gtin14[1 + cp_digitos:13]
    if len(item_reference_str) != ir_digitos:
        logger.warning("codificar_sgtin96: partición/longitud inconsistente para %r", codigo_articulo)
        return None
    company_prefix = int(company_prefix_str)
    item_reference = int(item_reference_str)

    valor = HEADER_SGTIN96
    valor = (valor << 3) | (filtro & 0b111)
    valor = (valor << 3) | (particion & 0b111)
    valor = (valor << cp_bits) | (company_prefix & ((1 << cp_bits) - 1))
    valor = (valor << ir_bits) | (item_reference & ((1 << ir_bits) - 1))
    valor = (valor << SERIAL_BITS) | (serial & ((1 << SERIAL_BITS) - 1))

    epc_hex = f"{valor:024X}"
    epc_uri = f"urn:epc:id:sgtin:{company_prefix_str}.{item_reference_str}.{serial}"
    return {
        "epc_hex": epc_hex,
        "epc_uri": epc_uri,
        "company_prefix": company_prefix,
        "item_reference": item_reference,
        "serial": serial,
        "particion": particion,
        "filtro": filtro,
        "codigo_articulo": codigo,
    }


def decodificar_sgtin96(epc_hex):
    """Decodifica una trama SGTIN-96 hex (24 caracteres) → dict {codigo_articulo (GTIN-13
    reconstruido con dígito de control recalculado), numero_serie, particion, filtro, company_prefix,
    item_reference} o None si la trama no es un SGTIN-96 válido (cabecera distinta, longitud
    incorrecta, partición desconocida) — nunca lanza, nunca inventa un artículo."""
    txt = (epc_hex or "").strip().upper()
    if len(txt) != 24 or not all(c in "0123456789ABCDEF" for c in txt):
        return None
    try:
        valor = int(txt, 16)
    except ValueError:
        return None

    serial = valor & ((1 << SERIAL_BITS) - 1)
    resto = valor >> SERIAL_BITS

    # Necesitamos la partición para saber cuántos bits tiene cada campo — pero la partición está
    # DESPUÉS del header+filtro y ANTES de company_prefix/item_reference, así que primero hay que
    # extraer header+filtro+partición (14 bits) del extremo alto, usando el ancho TOTAL restante
    # (44 bits de cp+ir) que es fijo para cualquier partición.
    resto_sin_serial_bits = 96 - SERIAL_BITS  # 58
    cabecera_filtro_particion = resto >> 44
    header = cabecera_filtro_particion >> 6
    if header != HEADER_SGTIN96:
        return None
    filtro = (cabecera_filtro_particion >> 3) & 0b111
    particion = cabecera_filtro_particion & 0b111
    if particion not in _PARTICIONES:
        return None
    cp_bits, cp_digitos, ir_bits, ir_digitos = _PARTICIONES[particion]

    cp_e_ir = resto & ((1 << 44) - 1)
    company_prefix = cp_e_ir >> ir_bits
    item_reference = cp_e_ir & ((1 << ir_bits) - 1)

    company_prefix_str = str(company_prefix).zfill(cp_digitos)
    item_reference_str = str(item_reference).zfill(ir_digitos)
    if len(company_prefix_str) > cp_digitos or len(item_reference_str) > ir_digitos:
        return None  # desbordó los dígitos esperados: trama inconsistente, no un SGTIN de esta app

    indicador = item_reference_str[0]
    resto_item = item_reference_str[1:]
    doce = (company_prefix_str + resto_item)[:12]
    if len(doce) != 12:
        return None
    from src.utils.ean import digito_control
    try:
        control = digito_control(doce)
    except ValueError:
        return None
    codigo_articulo = f"{doce}{control}"

    return {
        "codigo_articulo": codigo_articulo,
        "numero_serie": serial,
        "particion": particion,
        "filtro": filtro,
        "company_prefix": company_prefix,
        "item_reference": item_reference,
        "indicador": indicador,
    }
