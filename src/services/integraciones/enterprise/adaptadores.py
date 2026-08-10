"""
Conectores Enterprise oficiales (Etapa E · Fase E2) — SAP, Salesforce, WooCommerce, PrestaShop,
Magento, Business Central, Dynamics 365.

NO son un framework nuevo: cada conector es una subclase del `RestChannelAdapter` existente (Adapter
Pattern provider-agnostic, transporte HTTP real inyectable). Solo cambian el mapeo (traducción pura) y
las rutas de la API externa; el dominio NO cambia. Las credenciales se resuelven en runtime vía
`comercio_digital.conexiones` (cifradas con el Secret Manager Enterprise) — nunca en código. Degradable:
sin endpoint/credenciales el transporte no llama (comportamiento heredado del RestChannelAdapter).
"""

from __future__ import annotations

from src.services.comercio_digital.canales.rest_adapter import RestChannelAdapter


# ══════════════════════════════════════════════════════════════════════════════
# eCommerce
# ══════════════════════════════════════════════════════════════════════════════
class WooCommerceAdapter(RestChannelAdapter):
    """WooCommerce REST API v3 (WordPress). Auth básica (consumer key/secret) o Bearer."""
    canal = "woocommerce"
    tipo_auth_defecto = "basic"

    def __init__(self, *, transporte=None):
        super().__init__("woocommerce", transporte=transporte,
                         ruta_push="/wp-json/wc/v3/products", ruta_pull="/wp-json/wc/v3/orders")

    def traducir_saliente(self, mensaje: dict) -> dict:
        m = dict(mensaje or {})
        return {"name": m.get("nombre") or m.get("name"), "sku": m.get("sku") or m.get("codigo"),
                "regular_price": _precio(m), "stock_quantity": m.get("stock"), "type": "simple"}

    def traducir_entrante(self, payload: dict) -> dict:
        p = dict(payload or {})
        return {"externo_id": p.get("id"), "estado": p.get("status"), "total": p.get("total"),
                "cliente": (p.get("billing") or {}).get("email"), "lineas": p.get("line_items", [])}


class PrestaShopAdapter(RestChannelAdapter):
    """PrestaShop Webservice API. Auth básica (la API key va como usuario)."""
    canal = "prestashop"
    tipo_auth_defecto = "basic"

    def __init__(self, *, transporte=None):
        super().__init__("prestashop", transporte=transporte,
                         ruta_push="/api/products", ruta_pull="/api/orders")

    def traducir_saliente(self, mensaje: dict) -> dict:
        m = dict(mensaje or {})
        return {"product": {"reference": m.get("codigo") or m.get("sku"),
                            "name": m.get("nombre") or m.get("name"),
                            "price": _precio(m), "quantity": m.get("stock")}}

    def traducir_entrante(self, payload: dict) -> dict:
        p = dict(payload or {})
        o = p.get("order", p)
        return {"externo_id": o.get("id"), "estado": o.get("current_state"),
                "total": o.get("total_paid"), "cliente": o.get("id_customer")}


class MagentoAdapter(RestChannelAdapter):
    """Magento 2 REST API (`/rest/V1`). Auth Bearer (token de integración/OAuth)."""
    canal = "magento"
    tipo_auth_defecto = "apikey"

    def __init__(self, *, transporte=None):
        super().__init__("magento", transporte=transporte,
                         ruta_push="/rest/V1/products", ruta_pull="/rest/V1/orders")

    def traducir_saliente(self, mensaje: dict) -> dict:
        m = dict(mensaje or {})
        return {"product": {"sku": m.get("codigo") or m.get("sku"),
                            "name": m.get("nombre") or m.get("name"),
                            "price": _precio(m), "status": 1, "type_id": "simple",
                            "extension_attributes": {"stock_item": {"qty": m.get("stock"),
                                                                    "is_in_stock": bool(m.get("stock"))}}}}

    def traducir_entrante(self, payload: dict) -> dict:
        p = dict(payload or {})
        return {"externo_id": p.get("entity_id") or p.get("increment_id"), "estado": p.get("status"),
                "total": p.get("grand_total"), "cliente": p.get("customer_email"),
                "lineas": p.get("items", [])}


# ══════════════════════════════════════════════════════════════════════════════
# ERP / CRM
# ══════════════════════════════════════════════════════════════════════════════
class SAPAdapter(RestChannelAdapter):
    """SAP S/4HANA (OData API, p. ej. API_PRODUCT_SRV / API_SALES_ORDER_SRV). Auth básica u OAuth2."""
    canal = "sap"
    tipo_auth_defecto = "oauth2"

    def __init__(self, *, transporte=None):
        super().__init__("sap", transporte=transporte,
                         ruta_push="/sap/opu/odata/sap/API_PRODUCT_SRV/A_Product",
                         ruta_pull="/sap/opu/odata/sap/API_SALES_ORDER_SRV/A_SalesOrder")

    def traducir_saliente(self, mensaje: dict) -> dict:
        m = dict(mensaje or {})
        return {"Product": m.get("codigo") or m.get("sku"),
                "ProductDescription": m.get("nombre") or m.get("name"),
                "Price": _precio(m), "StockQuantity": m.get("stock")}

    def traducir_entrante(self, payload: dict) -> dict:
        p = dict(payload or {})
        return {"externo_id": p.get("SalesOrder"), "estado": p.get("OverallSDProcessStatus"),
                "total": p.get("TotalNetAmount"), "cliente": p.get("SoldToParty")}


class SalesforceAdapter(RestChannelAdapter):
    """Salesforce REST API (`/services/data/vXX.0/sobjects`). Auth OAuth2 Bearer."""
    canal = "salesforce"
    tipo_auth_defecto = "oauth2"

    def __init__(self, *, transporte=None):
        super().__init__("salesforce", transporte=transporte,
                         ruta_push="/services/data/v59.0/sobjects/Product2",
                         ruta_pull="/services/data/v59.0/sobjects/Order")

    def traducir_saliente(self, mensaje: dict) -> dict:
        m = dict(mensaje or {})
        return {"ProductCode": m.get("codigo") or m.get("sku"),
                "Name": m.get("nombre") or m.get("name"), "IsActive": True,
                "Description": m.get("descripcion")}

    def traducir_entrante(self, payload: dict) -> dict:
        p = dict(payload or {})
        return {"externo_id": p.get("Id"), "estado": p.get("Status"),
                "total": p.get("TotalAmount"), "cliente": p.get("AccountId")}


class BusinessCentralAdapter(RestChannelAdapter):
    """Microsoft Dynamics 365 Business Central (API `/api/v2.0`). Auth OAuth2 Bearer."""
    canal = "business_central"
    tipo_auth_defecto = "oauth2"

    def __init__(self, *, transporte=None):
        super().__init__("business_central", transporte=transporte,
                         ruta_push="/api/v2.0/items", ruta_pull="/api/v2.0/salesOrders")

    def traducir_saliente(self, mensaje: dict) -> dict:
        m = dict(mensaje or {})
        return {"number": m.get("codigo") or m.get("sku"),
                "displayName": m.get("nombre") or m.get("name"),
                "unitPrice": _precio(m), "inventory": m.get("stock")}

    def traducir_entrante(self, payload: dict) -> dict:
        p = dict(payload or {})
        return {"externo_id": p.get("number") or p.get("id"), "estado": p.get("status"),
                "total": p.get("totalAmountIncludingTax"), "cliente": p.get("customerNumber")}


class Dynamics365Adapter(RestChannelAdapter):
    """Microsoft Dynamics 365 (CE/CRM Web API `/api/data/v9.2`). Auth OAuth2 Bearer."""
    canal = "dynamics365"
    tipo_auth_defecto = "oauth2"

    def __init__(self, *, transporte=None):
        super().__init__("dynamics365", transporte=transporte,
                         ruta_push="/api/data/v9.2/products", ruta_pull="/api/data/v9.2/salesorders")

    def traducir_saliente(self, mensaje: dict) -> dict:
        m = dict(mensaje or {})
        return {"productnumber": m.get("codigo") or m.get("sku"),
                "name": m.get("nombre") or m.get("name"), "price": _precio(m),
                "quantityonhand": m.get("stock")}

    def traducir_entrante(self, payload: dict) -> dict:
        p = dict(payload or {})
        return {"externo_id": p.get("salesorderid") or p.get("ordernumber"),
                "estado": p.get("statuscode"), "total": p.get("totalamount"),
                "cliente": p.get("_customerid_value")}


def _precio(m: dict):
    v = m.get("precio", m.get("price"))
    return str(v) if v is not None else None


# Catálogo (clase, categoría, descripción) para el auto-registro en el registry Enterprise.
CATALOGO = [
    (WooCommerceAdapter, "ecommerce", "WooCommerce (WordPress) REST API v3"),
    (PrestaShopAdapter, "ecommerce", "PrestaShop Webservice API"),
    (MagentoAdapter, "ecommerce", "Magento 2 REST API"),
    (SAPAdapter, "erp", "SAP S/4HANA OData API"),
    (SalesforceAdapter, "crm", "Salesforce REST API"),
    (BusinessCentralAdapter, "erp", "Microsoft Dynamics 365 Business Central API"),
    (Dynamics365Adapter, "crm", "Microsoft Dynamics 365 (CE/CRM) Web API"),
]


__all__ = ["WooCommerceAdapter", "PrestaShopAdapter", "MagentoAdapter", "SAPAdapter",
           "SalesforceAdapter", "BusinessCentralAdapter", "Dynamics365Adapter", "CATALOGO"]
