"""
Tests Etapa G · Fase G2: certificación y CONGELACIÓN de contratos públicos.

Fija el baseline de los contratos públicos certificados (API REST v1, esquemas de seguridad, SDK,
conectores Enterprise, catálogo de eventos, webhooks). Semántica SUPERSET (retrocompatible): añadir
contratos está permitido; **eliminar o renombrar** un contrato certificado ROMPE la prueba. Así queda
congelada la compatibilidad hacia atrás sin impedir extensiones aditivas.
"""

import pytest

pytestmark = pytest.mark.db

# ── Baseline CONGELADO (Release 1.0) ──────────────────────────────────────────
API_RUTAS_CONGELADAS = {
    "/audit/events", "/audit/replay", "/auth/login", "/auth/refresh", "/campaigns",
    "/campaigns/<int:cid>/process", "/commerce", "/commerce/health", "/communications",
    "/contacts", "/conversations", "/docs", "/openapi.json", "/recordings", "/recordings/dates",
    "/recordings/download", "/system/diagnostico", "/system/health", "/system/selftest",
    "/system/status", "/system/status/tenant", "/system/version", "/templates",
}
EVENTOS_CONGELADOS = {
    "AuditCreated", "CampaignFinished", "CampaignStarted", "CommunicationCreated",
    "CommunicationDelivered", "CommunicationFailed", "CommunicationSent", "ConsentChanged",
    "ContractSigned", "EmployeeCreated", "InvoiceGenerated", "InvoicePaid", "NotificationCreated",
    "NotificationRead", "PluginInstalled", "PluginRemoved", "PurchaseOrderApproved", "StockUpdated",
    "TransferCompleted", "WorkflowCompleted", "WorkflowStarted",
}
CONECTORES_CONGELADOS = {
    "sap", "salesforce", "woocommerce", "prestashop", "magento", "business_central", "dynamics365",
}
SDK_VERSION_CONGELADA = "1.0.0"


def _rutas_api():
    from src.api import crear_app
    app = crear_app()
    return {str(r).replace("/api/v1", "") for r in app.url_map.iter_rules()
            if str(r).startswith("/api/v1")}


def test_api_rutas_retrocompatibles():
    actuales = _rutas_api()
    faltan = API_RUTAS_CONGELADAS - actuales
    assert not faltan, f"contratos API eliminados/renombrados (ruptura): {faltan}"


def test_api_versionado_y_seguridad():
    from src.api import crear_app
    spec = crear_app().test_client().get("/api/v1/openapi.json").get_json()
    assert spec["openapi"].startswith("3.")
    assert spec["info"]["version"] == "v1"
    esquemas = set(spec["components"]["securitySchemes"])
    assert {"bearerAuth", "apiKey"} <= esquemas       # JWT + API Key congelados


def test_sdk_version_congelada():
    from src.services.api_publica import sdks
    assert sdks.VERSION == SDK_VERSION_CONGELADA
    assert set(sdks.DISTRIBUIBLES) == {"python", "javascript"}
    # los paquetes declaran la misma versión (retrocompat pip/npm)
    assert sdks.paquete("python")["version"] == SDK_VERSION_CONGELADA
    assert sdks.paquete("javascript")["version"] == SDK_VERSION_CONGELADA


def test_conectores_enterprise_congelados():
    from src.services.integraciones import enterprise
    actuales = set(enterprise.disponibles())
    faltan = CONECTORES_CONGELADOS - actuales
    assert not faltan, f"conectores eliminados (ruptura): {faltan}"


def test_eventbus_catalogo_retrocompatible():
    from src.services import eventbus
    actuales = set((eventbus.catalogo() or {}).keys())
    faltan = EVENTOS_CONGELADOS - actuales
    assert not faltan, f"eventos del catálogo eliminados (ruptura): {faltan}"


def test_webhooks_hmac_estable():
    from src.services import webhooks_salientes as wh
    # Firma HMAC-SHA256 determinista (contrato de integración con terceros).
    f1 = wh.firmar("secreto", b"payload")
    f2 = wh.firmar("secreto", b"payload")
    assert f1 == f2 and len(f1) == 64                 # hex SHA-256


def test_marketplace_contrato_firmas():
    from src.services.marketplace import firmas
    # Contrato del Marketplace: verificación de firma/checksum de manifests.
    assert hasattr(firmas, "verificar") and hasattr(firmas, "hash_manifest")
