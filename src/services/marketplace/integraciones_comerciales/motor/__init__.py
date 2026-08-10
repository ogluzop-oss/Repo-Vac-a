"""
Marketplace · Integraciones Comerciales · **MOTOR Enterprise** (Fase WEB-13).

Arquitectura EXCLUSIVAMENTE preparatoria para conectar cualquier plataforma de comercio electrónico sin
rediseñar Smart Manager. **NADA se conecta**: no hay OAuth, API Keys, HTTP, webhooks, polling, colas reales
ni sincronización. Todo son contratos/metadatos/registros desacoplados y dirigidos por CAPACIDADES (nunca por
ramificando por plataforma). Las fases WEB-14/15/16… solo implementarán los adaptadores concretos sin tocar esta
arquitectura.

Submódulos:
  · `capacidades`  — `ConnectorCapabilities` + matriz declarativa por plataforma.
  · `pipeline`     — pipeline de sincronización (VALIDAR→…→FINALIZAR), dirigido por capacidades.
  · `importacion`  — interfaces de importación (productos/clientes/pedidos/stock/precios/estados/…).
  · `exportacion`  — interfaces de exportación (stock/pedidos/estados/clientes/precios).
  · `colas`        — contrato de cola + backends preparados (Local/Redis/SQS/RabbitMQ).
  · `deteccion`    — detección automática de plataforma por firmas (sin HTTP).
  · `validacion`   — sistema de validación (URL/credenciales/versión/API/permisos/estado/SSL).
  · `errores`      — tipos de error canónicos (no se lanzan en esta fase).
  · `versiones`    — API/Connector/Minimum/Maximum version.
  · `adaptadores`  — adaptadores preparados (Hostinger/WooCommerce/Shopify/… vacíos).
  · `auditoria`    — eventos canónicos INTEGRATION_* (reutiliza `log_auditoria`).
"""

from src.services.marketplace.integraciones_comerciales.motor import (  # noqa: F401
    adaptadores, auditoria, capacidades, colas, deteccion, errores,
    exportacion, importacion, pipeline, validacion, versiones)
from src.services.marketplace.integraciones_comerciales.motor.adaptadores import (  # noqa: F401
    ADAPTADORES, AdaptadorConector, adaptador)
from src.services.marketplace.integraciones_comerciales.motor.auditoria import (  # noqa: F401
    EVENTOS, registrar_evento)
from src.services.marketplace.integraciones_comerciales.motor.capacidades import (  # noqa: F401
    CAPACIDADES_NOMBRES, ConnectorCapabilities, capacidades, matriz)
from src.services.marketplace.integraciones_comerciales.motor.colas import (  # noqa: F401
    BACKENDS, ColaTrabajos, cola)
from src.services.marketplace.integraciones_comerciales.motor.deteccion import \
    detectar  # noqa: F401
from src.services.marketplace.integraciones_comerciales.motor.errores import (  # noqa: F401
    CODIGOS, CodigoError, IntegracionError)
from src.services.marketplace.integraciones_comerciales.motor.pipeline import (  # noqa: F401
    PASOS, PipelineSincronizacion)
from src.services.marketplace.integraciones_comerciales.motor.validacion import (  # noqa: F401
    COMPROBACIONES, Validador)
from src.services.marketplace.integraciones_comerciales.motor.versiones import \
    VersionInfo  # noqa: F401

ESTADO = "PREPARADO"


def descriptor() -> dict:
    """Resumen del motor (para diagnóstico/UI): nada conectado, todo preparado."""
    return {
        "estado": ESTADO,
        "capacidades": CAPACIDADES_NOMBRES,
        "pipeline": PASOS,
        "colas": tuple(BACKENDS),
        "errores": CODIGOS,
        "eventos": EVENTOS,
        "adaptadores": tuple(ADAPTADORES),
        "matriz_capacidades": matriz(),
    }
