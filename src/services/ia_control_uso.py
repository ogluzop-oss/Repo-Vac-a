"""
Control de uso y coste de IA (Anthropic) por empresa — Fase A (fundación).

Cubre los 3 puntos de llamada REALES a la API de Anthropic de todo el sistema (confirmado por
barrido exhaustivo): `utils/ai_translator.py` (traducción, feature `translate`),
`services/importacion/mapeo_ia.py` (mapeo de columnas del asistente de Migración, feature
`import_mapping`) y `services/contabilidad/factura_ocr_ia.py` (lectura de facturas por visión,
feature `invoice_ocr`). Los tres comparten el mismo patrón estructural (backend inyectable +
`_anthropic_backend()` perezoso) y los tres enrutan su `cliente.messages.create(...)` a través de
`ejecutar_tarea_ia()` para quedar auditados y limitados de la misma forma.

Dos planes por empresa (`empresas.ai_plan_type`):
  - `LIMITED` (por defecto): límite diario de SEGURIDAD en USD (`ai_daily_cost_limit_usd`).
    Al alcanzarlo, `empresas.ai_status` pasa a `BLOCKED_DAILY_LIMIT` (persistido — sobrevive a
    reinicios) y toda nueva llamada de IA se rechaza hasta el día siguiente (UTC) o hasta que un
    administrador cambie el plan/límite.
  - `PAY_AS_YOU_GO`: sin límite (Fase B factura el consumo real; aquí no se bloquea nunca).

Fase A entrega SOLO la fundación (esquema + calculadora + wrapper + los 3 puntos de llamada
retrofitados). Fase B (facturación) y Fase C (GUI/REST de administración) se construyen encima.

Zona horaria: el "día" del límite diario es SIEMPRE UTC, explícito — nunca se depende de la
`DEFAULT CURRENT_TIMESTAMP` de MariaDB (que usa el huso horario de sesión/servidor, no
necesariamente UTC). `ejecutar_tarea_ia` escribe `creado` con la hora UTC de Python
(`datetime.now(timezone.utc)`, naive tras quitar el tzinfo — la columna DATETIME no guarda huso) y
`verificar_acceso_ia` calcula el inicio del día también en UTC con el mismo reloj, de modo que el
límite es correcto con independencia de cómo esté configurado el servidor MariaDB o el SO.
"""

import datetime as _dt
import logging
import os

logger = logging.getLogger("ia_control_uso")


# ============================================================
# EXCEPCIONES (idioma del dominio, mismo patrón que GestionNominaError/GestionFiniquitoError)
# ============================================================
class LimiteUsoIAExcedido(Exception):
    """La empresa (plan LIMITED) alcanzó su límite diario de seguridad de coste de IA. El
    llamador decide cómo mostrarlo (la GUI muestra el mensaje; un backend degradable puede
    capturarla y devolver el resultado sin IA)."""


# ============================================================
# CALCULADORA DE PRECIOS (tarifas configurables por variable de entorno)
# ============================================================
def _precio_env(nombre_env: str, valor_defecto: float) -> float:
    """Lee un precio USD/1M tokens de una variable de entorno; si falta o no es numérica,
    usa el valor por defecto. Así las tarifas son actualizables sin tocar código (requisito
    explícito del negocio: los precios de Anthropic cambian con el tiempo)."""
    crudo = os.getenv(nombre_env)
    if crudo is None or not str(crudo).strip():
        return valor_defecto
    try:
        return float(crudo)
    except (TypeError, ValueError):
        logger.warning("Variable de entorno %s='%s' no es un número válido; se usa el "
                        "valor por defecto %.2f.", nombre_env, crudo, valor_defecto)
        return valor_defecto


class AIPriceCalculator:
    """Clasifica un modelo Claude arbitrario en un TIER de precio ('sonnet' o 'haiku') y calcula
    el coste USD estimado de una llamada a partir de sus tokens reales (`response.usage`).

    Las tarifas NUNCA están hardcodeadas de forma rígida: se leen de variables de entorno con
    valores por defecto sensatos (precios de Anthropic a la fecha de esta fase), para que un
    cambio de precio no requiera desplegar código nuevo.
    """

    # (env var input, env var output, defecto input, defecto output) por tier.
    _TIERS = {
        "sonnet": ("SMART_AI_PRICE_SONNET_INPUT_PER_1M", "SMART_AI_PRICE_SONNET_OUTPUT_PER_1M",
                   3.00, 15.00),
        "haiku": ("SMART_AI_PRICE_HAIKU_INPUT_PER_1M", "SMART_AI_PRICE_HAIKU_OUTPUT_PER_1M",
                  1.00, 5.00),
    }

    @classmethod
    def precios_tier(cls, tier: str) -> tuple:
        """(precio_input_por_1M, precio_output_por_1M) USD para el tier dado, ya resueltos
        contra las variables de entorno (o sus valores por defecto)."""
        env_in, env_out, def_in, def_out = cls._TIERS[tier]
        return _precio_env(env_in, def_in), _precio_env(env_out, def_out)

    @staticmethod
    def clasificar_modelo(modelo: str) -> str:
        """Clasifica el STRING de modelo (p. ej. 'claude-sonnet-4-6', 'claude-haiku-4-5-20251001',
        o cualquier nombre futuro) en 'sonnet' o 'haiku' por subcadena — robusto a renombrados de
        modelo (NO es una lista de coincidencia exacta que se rompa con el próximo modelo). Si no
        reconoce ninguna de las dos palabras clave, asume 'sonnet' (la tarifa más cara/conservadora)
        y avisa con un warning — nunca infra-estima el coste de un modelo desconocido en silencio."""
        m = (modelo or "").lower()
        if "haiku" in m:
            return "haiku"
        if "sonnet" in m:
            return "sonnet"
        logger.warning(
            "AIPriceCalculator.clasificar_modelo: modelo '%s' no reconocido (no contiene "
            "'sonnet' ni 'haiku'); se asume tarifa sonnet-tier (más conservadora) por defecto.",
            modelo,
        )
        return "sonnet"

    @classmethod
    def calcular_coste(cls, modelo: str, input_tokens: int, output_tokens: int,
                        cached_input_tokens: int = 0) -> float:
        """Coste estimado en USD de una llamada, dados sus tokens reales.

        Simplificación deliberada sobre `cached_input_tokens`: Anthropic aplica un descuento
        real a los tokens leídos de caché, pero el descuento exacto varía (escritura vs lectura
        de caché, TTL, etc.) y no hay certeza suficiente de la tarifa aplicable en estos 3 puntos
        de llamada como para arriesgar infra-cobrar (y por tanto infra-bloquear) el límite diario
        de seguridad. Por ahora los tokens de caché se registran en `ai_usage_logs` a efectos
        INFORMATIVOS/de auditoría (columna `cached_input_tokens`) pero NO se tarifican aparte ni
        se restan del coste — se tratan como coste cero adicional (ya están implícitamente fuera
        de `input_tokens`, que es lo único que se cobra). Fase B puede refinar esto si se necesita
        precisión de facturación real."""
        tier = cls.clasificar_modelo(modelo)
        precio_input, precio_output = cls.precios_tier(tier)
        return (input_tokens / 1_000_000) * precio_input + (output_tokens / 1_000_000) * precio_output


# ============================================================
# RESOLUCIÓN DE TENANT (compartida por los 3 puntos de llamada reales)
# ============================================================
def resolver_tenant_actual() -> tuple:
    """Resuelve `(id_empresa, id_usuario)` de la sesión de escritorio ACTIVA en el hilo actual.

    Punto ÚNICO de resolución para los 3 backends Anthropic de este sistema (`ai_translator`,
    `mapeo_ia`, `factura_ocr_ia`): ninguno de los tres recibe hoy `id_empresa` como parámetro
    explícito en su función pública, y los tres se invocan SIEMPRE desde una sesión de
    escritorio activa (nunca en un contexto batch/anónimo) — así que resolverlo aquí, en el
    punto de llamada real a Anthropic, es equivalente a threadear el parámetro por toda la
    cadena de llamadas, pero con muchísimo menor radio de impacto (cero cambios de firma en
    funciones públicas ya usadas por `migracion_gui.py`/`calculadora_fiscal_wizard.py`/i18n).
    Mismo criterio que `services/importacion/motor.py::_emp()`, que ya resuelve
    `empresa_actual_id()` exactamente así para esta misma familia de funciones. Los 3 backends
    usan esta misma función — no 3 estrategias distintas para el mismo problema estructural."""
    id_empresa = None
    try:
        from src.db.empresa import empresa_actual_id
        id_empresa = empresa_actual_id()
    except Exception:
        pass
    id_usuario = None
    try:
        from src.db.usuario import sesion_global
        if sesion_global.usuario_actual:
            id_usuario = sesion_global.usuario_actual.get("id")
    except Exception:
        pass
    return id_empresa, id_usuario


# ============================================================
# VERIFICACIÓN DE ACCESO / EJECUCIÓN CONTROLADA
# ============================================================
def _inicio_dia_utc() -> _dt.datetime:
    """Medianoche (00:00:00) de HOY en UTC, como datetime naive (comparable directamente con la
    columna DATETIME `ai_usage_logs.creado`, que este módulo escribe siempre en hora UTC)."""
    hoy_utc = _dt.datetime.now(_dt.timezone.utc).date()
    return _dt.datetime.combine(hoy_utc, _dt.time.min)


def _inicio_mes_utc() -> _dt.datetime:
    """Medianoche (00:00:00) del día 1 del MES en curso, en UTC, como datetime naive — mismo
    criterio que `_inicio_dia_utc` (comparable directamente con `ai_usage_logs.creado`). Punto
    ÚNICO de este cálculo: lo reutiliza `services/saas/ia_plan.py::resumen_uso_ia` para el gasto
    mensual, en vez de reimplementar el mismo límite de mes con un huso horario distinto."""
    hoy_utc = _dt.datetime.now(_dt.timezone.utc).date()
    return _dt.datetime.combine(hoy_utc.replace(day=1), _dt.time.min)


def verificar_acceso_ia(id_empresa: str) -> None:
    """Verifica que `id_empresa` puede seguir consumiendo la API de Anthropic AHORA MISMO.

    - Plan `PAY_AS_YOU_GO`: sin límite, no-op (aparte de auto-sanar un bloqueo obsoleto, ver
      abajo).
    - Plan `LIMITED`: suma `ai_usage_logs.estimated_cost_usd` de la empresa desde las 00:00:00
      UTC de HOY; si alcanza/supera `ai_daily_cost_limit_usd`, persiste
      `empresas.ai_status='BLOCKED_DAILY_LIMIT'` y lanza `LimiteUsoIAExcedido`.

    Auto-sanado (el bloqueo NUNCA queda pegado más allá de su causa real): si al entrar aquí
    `ai_status` ya es `BLOCKED_DAILY_LIMIT` pero la condición que lo causó ya no se cumple —
    ha empezado un nuevo día UTC, el plan cambió a `PAY_AS_YOU_GO`, o un administrador ya
    reseteó el gasto/límite — se restaura `ai_status='ACTIVE'` en esta misma llamada.

    NOTA DE IMPLEMENTACIÓN: `db.conexion.obtener_conexion()` envuelve CUALQUIER excepción que
    escape de su bloque `with` (incluida una deliberada de dominio) en un `ConnectionError`
    genérico (ver su `except Exception` de cierre) — por eso esta función SOLO lee/escribe
    dentro del `with` y siempre lanza `LimiteUsoIAExcedido` DESPUÉS de haber salido de él, para
    que el tipo de excepción real llegue intacto al llamador."""
    from src.db.conexion import obtener_conexion

    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT ai_plan_type, ai_daily_cost_limit_usd, ai_status FROM empresas "
            "WHERE id_empresa=%s",
            (id_empresa,),
        )
        fila = cur.fetchone()
        if not fila:
            logger.warning("verificar_acceso_ia: empresa '%s' no encontrada; se permite sin "
                            "límite (la validación de existencia es responsabilidad de quien "
                            "gestiona empresas, Fase C).", id_empresa)
            return
        plan, limite, estado = fila[0], float(fila[1]), fila[2]

        if plan == "PAY_AS_YOU_GO":
            if estado == "BLOCKED_DAILY_LIMIT":
                cur.execute("UPDATE empresas SET ai_status='ACTIVE' WHERE id_empresa=%s",
                            (id_empresa,))
                conn.commit()
            return

        cur.execute(
            "SELECT COALESCE(SUM(estimated_cost_usd), 0) FROM ai_usage_logs "
            "WHERE id_empresa=%s AND creado >= %s",
            (id_empresa, _inicio_dia_utc()),
        )
        gastado_hoy = float(cur.fetchone()[0] or 0)
        bloqueado = gastado_hoy >= limite

        if bloqueado and estado != "BLOCKED_DAILY_LIMIT":
            cur.execute("UPDATE empresas SET ai_status='BLOCKED_DAILY_LIMIT' WHERE id_empresa=%s",
                        (id_empresa,))
            conn.commit()
        elif not bloqueado and estado == "BLOCKED_DAILY_LIMIT":
            # El bloqueo de un día/causa anterior ya no aplica (nuevo día UTC, límite subido,
            # reset manual...) → se restaura antes de seguir permitiendo llamadas.
            cur.execute("UPDATE empresas SET ai_status='ACTIVE' WHERE id_empresa=%s",
                        (id_empresa,))
            conn.commit()

    if bloqueado:
        raise LimiteUsoIAExcedido(
            f"Has alcanzado el límite diario de seguridad para uso de IA "
            f"(${limite:.2f} USD/día). Puedes esperar a mañana o cambiar al plan de "
            f"consumo ilimitado desde los ajustes de la empresa."
        )


def ejecutar_tarea_ia(id_empresa, id_usuario, feature_name: str, fn_llamada):
    """Punto ÚNICO de ejecución para cualquier llamada real a la API de Anthropic que deba
    contar para el control de uso/coste por empresa.

    1) `verificar_acceso_ia(id_empresa)` — propaga `LimiteUsoIAExcedido` si el plan LIMITED ya
       agotó su límite diario (el llamador decide cómo mostrarlo).
    2) Ejecuta `fn_llamada()` — callable de CERO argumentos que hace el
       `cliente.messages.create(...)` real y devuelve el objeto `Message` de Anthropic tal cual
       (sin reducirlo a texto); cualquier error de la llamada real (red, rate-limit...) se
       propaga sin envolver.
    3) Registra el uso real en `ai_usage_logs` (tokens de `response.usage` + coste vía
       `AIPriceCalculator.calcular_coste`). BEST-EFFORT: si el INSERT de auditoría falla, se
       registra el error en el log pero NUNCA rompe la respuesta real que el llamador está
       esperando — mismo criterio que `db/kardex.registrar_movimiento` (la auditoría nunca debe
       tumbar la operación real).
    4) Devuelve el `Message` original, intacto, para que el llamador siga extrayendo
       `.content[0].text` (o lo que necesite) exactamente como ya hacía.

    `id_usuario` puede ser `None` (algún punto de llamada podría no tener sesión de usuario
    resoluble en el futuro); la columna `ai_usage_logs.id_usuario` lo admite NULL.
    """
    verificar_acceso_ia(id_empresa)
    respuesta = fn_llamada()
    try:
        _registrar_uso(id_empresa, id_usuario, feature_name, respuesta)
    except Exception as e:
        logger.error("ejecutar_tarea_ia: fallo AL REGISTRAR (best-effort, no afecta la "
                     "respuesta) el uso de IA de empresa=%s feature=%s: %s",
                     id_empresa, feature_name, e)
    return respuesta


def _registrar_uso(id_empresa, id_usuario, feature_name, respuesta):
    usage = getattr(respuesta, "usage", None)
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    cached_tokens = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    modelo = getattr(respuesta, "model", "") or ""
    coste = AIPriceCalculator.calcular_coste(modelo, input_tokens, output_tokens, cached_tokens)

    from src.db.conexion import obtener_conexion
    creado_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO ai_usage_logs "
            "(id_empresa, id_usuario, feature_name, model_used, input_tokens, output_tokens, "
            "cached_input_tokens, estimated_cost_usd, creado) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (id_empresa, id_usuario, feature_name, modelo, input_tokens, output_tokens,
             cached_tokens, coste, creado_utc),
        )
        conn.commit()
