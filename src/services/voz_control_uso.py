"""
Control de uso, coste y reventa de voz (ElevenLabs/SOMA) por empresa — Fase A (fundación).

Mismo patrón estructural que `services/ia_control_uso.py` (control de uso de IA/Anthropic), pero
para el ÚNICO punto de llamada real a ElevenLabs de todo el sistema:
`src/utils/soma_tts.py::SomaTTS._hablar_elevenlabs`. A diferencia de IA (que solo calcula coste
BRUTO del proveedor, sin margen), aquí el negocio SÍ quiere revender el uso con un margen sobre el
coste real — por eso este módulo, además de controlar el acceso, calcula también el PRECIO DE
VENTA de cada síntesis, reutilizando la MISMA fórmula de margen ya usada para precios de tienda
(`services/compras/precios_dinamicos.py::pvp_sugerido`), en vez de inventar una segunda fórmula.

No hay "plan" de voz (LIMITED/PAY_AS_YOU_GO) como en IA: el único control de seguridad es un
límite MENSUAL de caracteres por empresa (`empresas.voice_monthly_limit_chars`, NULL = sin
límite) — más simple porque no hay hoy una demanda de una modalidad "ilimitada explícita" distinta
de "sin límite configurado". El límite de MES (no de día, a diferencia de IA) porque ElevenLabs
cobra por plan mensual de caracteres, no por coste diario variable.

Zona horaria: el "mes" del límite es SIEMPRE UTC, reutilizando `ia_control_uso._inicio_mes_utc()`
(punto ÚNICO de ese cálculo en todo el sistema) — nunca se reimplementa un segundo cálculo de
límites de mes con un huso horario distinto.
"""

import datetime as _dt
import logging

from src.services.ia_control_uso import _inicio_mes_utc

logger = logging.getLogger("voz_control_uso")


# ============================================================
# EXCEPCIONES (mismo rol que LimiteUsoIAExcedido)
# ============================================================
class LimiteUsoVozExcedido(Exception):
    """La empresa alcanzó su límite mensual de seguridad de caracteres de voz (ElevenLabs). El
    llamador decide cómo mostrarlo — `soma_tts._hablar_elevenlabs` la captura y degrada a
    Edge TTS para ese turno, exactamente como cualquier otro fallo de la API."""


# ============================================================
# TARIFA (reventa con margen)
# ============================================================
def tarifa_actual() -> tuple:
    """(cost_basis_per_char_usd, margen_pct) de la fila única `voice_billing_config` (id=1).

    Si la fila no existe todavía (BD sin la migración 0285 aplicada en este proceso concreto, o
    borrada manualmente), devuelve la misma semilla que inserta la migración — nunca rompe el
    cálculo de coste por falta de configuración."""
    from src.db.conexion import obtener_conexion

    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT cost_basis_per_char_usd, margen_pct FROM voice_billing_config WHERE id=1"
        )
        fila = cur.fetchone()
    if not fila:
        logger.warning("tarifa_actual: voice_billing_config sin fila id=1; se usa la semilla "
                        "por defecto (coste=0.00003, margen=100%%).")
        return 0.00003, 100.0
    return float(fila[0]), float(fila[1])


# ============================================================
# VERIFICACIÓN DE ACCESO
# ============================================================
def verificar_acceso_voz(id_empresa: str) -> None:
    """Verifica que `id_empresa` puede seguir sintetizando voz (ElevenLabs) AHORA MISMO.

    Suma `voice_usage_logs.character_count` desde el inicio del MES en curso (UTC, vía
    `ia_control_uso._inicio_mes_utc()`, **reutilizada**) y la compara con
    `empresas.voice_monthly_limit_chars`. Si el límite es NULL, NUNCA bloquea (sin límite
    configurado, por diseño — mismo criterio que un plan PAY_AS_YOU_GO en IA, pero sin necesitar
    una columna de "plan" separada). Si el límite no es NULL y ya se alcanzó/superó, lanza
    `LimiteUsoVozExcedido`.

    NOTA DE IMPLEMENTACIÓN: igual que `ia_control_uso.verificar_acceso_ia`, `obtener_conexion()`
    envuelve cualquier excepción que escape de su bloque `with` en un `ConnectionError` genérico
    — por eso esta función lanza `LimiteUsoVozExcedido` DESPUÉS de haber salido del `with`, para
    que el tipo de excepción real llegue intacto al llamador."""
    from src.db.conexion import obtener_conexion

    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT voice_monthly_limit_chars FROM empresas WHERE id_empresa=%s",
            (id_empresa,),
        )
        fila = cur.fetchone()
        if not fila:
            logger.warning("verificar_acceso_voz: empresa '%s' no encontrada; se permite sin "
                            "límite (la validación de existencia es responsabilidad de quien "
                            "gestiona empresas).", id_empresa)
            return
        limite = fila[0]
        if limite is None:
            return   # sin límite configurado: nunca bloquea, por diseño.
        limite = int(limite)

        cur.execute(
            "SELECT COALESCE(SUM(character_count), 0) FROM voice_usage_logs "
            "WHERE id_empresa=%s AND creado >= %s",
            (id_empresa, _inicio_mes_utc()),
        )
        usado_mes = int(cur.fetchone()[0] or 0)
        bloqueado = usado_mes >= limite

    if bloqueado:
        raise LimiteUsoVozExcedido(
            f"Se ha alcanzado el límite mensual de seguridad de caracteres de voz "
            f"({limite} caracteres/mes). SOMA seguirá hablando con la voz neuronal estándar "
            f"hasta que el límite se amplíe o comience el próximo mes."
        )


# ============================================================
# REGISTRO DE USO (coste + precio de venta)
# ============================================================
def registrar_uso_voz(id_empresa, id_usuario, voice_id: str, character_count: int) -> dict:
    """Calcula y registra el coste/importe facturable de UNA síntesis real de ElevenLabs.

    `cost_basis_usd = character_count * cost_basis_per_char_usd` (coste real del proveedor).

    `billed_amount_usd`: MISMA fórmula de margen que `services/compras/precios_dinamicos.py::
    pvp_sugerido` (coste × (1 + margen_pct/100)) — pero calculada aquí a la precisión de la propia
    columna (DECIMAL(12,8)) en vez de llamar a `pvp_sugerido` directamente, porque esa función
    REDONDEA a 2 decimales (pensada para un precio de venta al público, p. ej. 19,99€) — aplicado a
    una sola síntesis de voz (a menudo unos pocos céntimos de céntimo: una frase corta de SOMA
    puede costar $0.0005) ese redondeo deja `billed_amount_usd` en 0.00 sistemáticamente, perdiendo
    el importe real. Mismo criterio que `ai_usage_logs`/`facturacion_ia.py`: el redondeo a 2
    decimales ocurre SOLO al fijar el importe de la FACTURA (`facturacion_voz.py`, sobre el
    acumulado), nunca fila a fila.

    BEST-EFFORT (try/except, nunca rompe la síntesis real que ya se reprodujo) — mismo criterio
    que `ia_control_uso._registrar_uso` dentro de `ejecutar_tarea_ia`. Devuelve el dict registrado
    (o uno con importes a 0.0 si el registro falló, para que el llamador nunca reciba `None`)."""
    character_count = max(0, int(character_count or 0))
    try:
        cost_basis_per_char_usd, margen_pct = tarifa_actual()
        cost_basis_usd = round(character_count * cost_basis_per_char_usd, 8)
        billed_amount_usd = round(cost_basis_usd * (1 + margen_pct / 100.0), 8)

        from src.db.conexion import obtener_conexion
        creado_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO voice_usage_logs "
                "(id_empresa, id_usuario, voice_id, character_count, cost_basis_usd, "
                "billed_amount_usd, creado) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, id_usuario, voice_id, character_count, cost_basis_usd,
                 billed_amount_usd, creado_utc),
            )
            conn.commit()
        return {
            "character_count": character_count,
            "cost_basis_usd": cost_basis_usd,
            "billed_amount_usd": billed_amount_usd,
        }
    except Exception as e:
        logger.error("registrar_uso_voz: fallo AL REGISTRAR (best-effort, no afecta la síntesis "
                     "real) el uso de voz de empresa=%s: %s", id_empresa, e)
        return {"character_count": character_count, "cost_basis_usd": 0.0, "billed_amount_usd": 0.0}
