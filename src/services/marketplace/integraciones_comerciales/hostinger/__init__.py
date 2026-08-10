"""
Marketplace · Integraciones Comerciales · **Adaptador HOSTINGER** (Fase WEB-14) — PRIMERA integración real.

Implementa el adaptador oficial de creación web con IA de Hostinger SOBRE la arquitectura del motor WEB-13
(sin modificarla): reutiliza `motor.adaptadores.HostingerAdapter` (contratos/capacidades/versión), los tipos
de error (`motor.errores`), los estados existentes y el Canal Web (`orquestador.registrar_web_creada`,
`canal_web.publicar/sincronizar`). Toda la lógica NUEVA vive AQUÍ (en el adaptador), no en el núcleo.

Honestidad (patrón degradable del ERP, como Fiscal/AEAT): las llamadas son REALES contra la API oficial de
Hostinger vía un transporte HTTP; `disponible()` es True SOLO con credenciales reales resueltas por el
`SecretManager` existente. Sin credenciales/API de partner, el adaptador NO simula éxito: devuelve errores
canónicos (`MISSING_CREDENTIALS`, …). El transporte es INYECTABLE (`transporte.set_transporte`) — es la
costura usada por las pruebas para verificar la orquestación sin red.
"""

from src.services.marketplace.integraciones_comerciales.hostinger import (  # noqa: F401
    auditoria, secretos, transporte)
from src.services.marketplace.integraciones_comerciales.hostinger.adaptador import \
    HostingerAdapter  # noqa: F401
from src.services.marketplace.integraciones_comerciales.hostinger.auditoria import (  # noqa: F401
    EVENTOS)


def registrar() -> None:
    """Registra el adaptador Hostinger REAL en el motor (punto de extensión público de WEB-13, sin tocar
    `motor/`). Idempotente."""
    from src.services.marketplace.integraciones_comerciales.motor.adaptadores import \
        registrar_adaptador
    registrar_adaptador("hostinger", HostingerAdapter)
