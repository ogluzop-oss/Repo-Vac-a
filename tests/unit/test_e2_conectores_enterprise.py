"""
Tests Etapa E · Fase E2: conectores Enterprise (SAP/Salesforce/WooCommerce/PrestaShop/Magento/
Business Central/Dynamics 365).

Verifica que cada conector es una subclase del `RestChannelAdapter` existente (Adapter Pattern,
provider-agnostic), que traduce de forma pura, que transporta por HTTP con transporte inyectable (sin
red), que se resuelve la conexión/credenciales vía `conexiones` (Secret Manager) sin credenciales en
código, que degrada sin conexión, que se auto-registran en el registry Enterprise + `platform.registry`
y que NO tocan el dominio.
"""

import pytest

from src.services.comercio_digital.canales.rest_adapter import RestChannelAdapter
from src.services.integraciones import enterprise

EMP = "T-E2-CONN"
_ECOMMERCE = {"woocommerce", "prestashop", "magento"}
_ERP_CRM = {"sap", "salesforce", "business_central", "dynamics365"}
_TODOS = _ECOMMERCE | _ERP_CRM


class _Resp:
    def __init__(self, code=200, data=None):
        self.status_code = code
        self._data = data if data is not None else {}
        self.text = ""

    @property
    def content(self):
        return b"x"

    def json(self):
        return self._data


class _FakeHTTP:
    """Transporte HTTP inyectable: captura llamadas, no toca la red."""
    def __init__(self, get_data=None):
        self.calls = []
        self._get_data = get_data if get_data is not None else {"items": [
            {"id": 1, "status": "processing", "total": "10", "entity_id": 5}]}

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append(("POST", url, json, headers))
        return _Resp(200, {"id": 999, "status": "created"})

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(("GET", url, params, headers))
        return _Resp(200, self._get_data)


@pytest.fixture()
def limpia_conexiones(db):
    def _borra():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM cd_conexiones WHERE id_empresa=%s", (EMP,))
            conn.commit()
    _borra()
    yield
    _borra()


# ── Catálogo / auto-registro ──────────────────────────────────────────────────
def test_los_7_conectores_registrados():
    disp = enterprise.disponibles()
    assert _TODOS <= set(disp)
    assert disp["salesforce"]["categoria"] == "crm"
    assert disp["woocommerce"]["categoria"] == "ecommerce"
    assert disp["sap"]["categoria"] == "erp"


def test_auto_registro_en_platform_registry():
    from src.platform import registry
    # El registry es estado global en memoria; re-sincronizamos (idempotente) para independencia de
    # orden de tests. En arranque real basta con importar el paquete (auto-registro).
    enterprise.sincronizar_platform()
    nombres = set(registry.nombres())
    assert {"cd_canal_woocommerce", "cd_canal_sap", "cd_canal_salesforce"} <= nombres


def test_catalogo_central_integraciones_incluye_enterprise():
    from src.services import integraciones
    disp = integraciones.disponibles()
    assert all(disp.get(c) == "enterprise" for c in _TODOS)


# ── Adapter Pattern / provider-agnostic ───────────────────────────────────────
def test_todos_son_restchanneladapter_provider_agnostic():
    for codigo in _TODOS:
        ad = enterprise.adaptador(codigo)
        assert isinstance(ad, RestChannelAdapter)               # reutiliza el Adapter Pattern
        assert ad.descriptor()["provider_agnostic"] is True


def test_traduccion_pura_por_proveedor():
    from src.services.integraciones.enterprise import adaptadores as A
    woo = A.WooCommerceAdapter().traducir_saliente(
        {"codigo": "ART1", "nombre": "Leche", "precio": 1.5, "stock": 10})
    assert woo["sku"] == "ART1" and woo["name"] == "Leche" and woo["regular_price"] == "1.5"
    sap = A.SAPAdapter().traducir_saliente({"codigo": "P9", "nombre": "Prod", "precio": 3})
    assert sap["Product"] == "P9" and sap["ProductDescription"] == "Prod"
    sf = A.SalesforceAdapter().traducir_entrante({"Id": "500x", "Status": "Activated", "TotalAmount": 99})
    assert sf["externo_id"] == "500x" and sf["estado"] == "Activated" and sf["total"] == 99


# ── Transporte real (HTTP) con transporte inyectado + conexión cifrada ─────────
def test_enviar_usa_endpoint_y_mapeo(limpia_conexiones):
    from src.services.comercio_digital import conexiones
    conexiones.registrar("woocommerce", nombre="default", id_empresa=EMP, tipo_auth="none",
                         endpoint_base="https://shop.example.com")
    ft = _FakeHTTP()
    res = enterprise.enviar("woocommerce",
                            {"codigo": "ART1", "nombre": "Leche", "precio": 1.5, "stock": 10},
                            id_empresa=EMP, transporte=ft)
    assert res["ok"] is True and ft.calls
    metodo, url, payload, _h = ft.calls[0]
    assert metodo == "POST" and url == "https://shop.example.com/wp-json/wc/v3/products"
    assert payload["sku"] == "ART1" and payload["name"] == "Leche"


def test_recibir_traduce_entrantes(limpia_conexiones):
    from src.services.comercio_digital import conexiones
    conexiones.registrar("magento", nombre="default", id_empresa=EMP, tipo_auth="none",
                         endpoint_base="https://magento.example.com")
    ft = _FakeHTTP(get_data={"items": [{"entity_id": 77, "status": "processing",
                                        "grand_total": "42.0", "customer_email": "a@b.c"}]})
    out = enterprise.recibir("magento", id_empresa=EMP, transporte=ft)
    assert out and out[0]["externo_id"] == 77 and out[0]["total"] == "42.0"
    assert ft.calls[0][1] == "https://magento.example.com/rest/V1/orders"


def test_degradable_sin_conexion():
    # Sin conexión registrada → el adaptador NO llama a la red y degrada limpio.
    res = enterprise.enviar("sap", {"codigo": "X"}, id_empresa="T-E2-NO-CONN")
    assert res["ok"] is False and res.get("degradado") is True


def test_conector_desconocido():
    assert enterprise.enviar("proveedor_inexistente", {})["estado"] == "desconocido"
    assert enterprise.adaptador("proveedor_inexistente") is None


# ── Garantías arquitectónicas (sin credenciales en código, sin motor, sin dominio) ──
def test_descriptor_garantias():
    d = enterprise.descriptor()
    assert d["secretos_en_claro"] is False
    assert d["motor_nuevo"] is False
    assert d["modifica_dominio"] is False
    assert d["provider_agnostic"] is True and d["multiempresa"] is True
    assert "secret_manager" in d["reutiliza"]
    assert set(d["conectores"]) >= _TODOS


def test_registrar_conexion_no_credenciales_en_claro(limpia_conexiones):
    # La fachada delega en el registro cifrado; el tipo de auth por defecto lo aporta el conector.
    ok = enterprise.registrar_conexion("salesforce", id_empresa=EMP,
                                       endpoint_base="https://na.salesforce.com")
    assert ok is True
    conf = None
    from src.services.comercio_digital import conexiones
    conf = conexiones.obtener("salesforce", id_empresa=EMP)
    assert conf and conf["tipo_auth"] == "oauth2"               # default del SalesforceAdapter
