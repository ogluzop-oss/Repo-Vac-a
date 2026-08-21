"""
Conector B2B AGNÓSTICO para aprovisionamiento externo (Consentio / Choco / REST / EDI).

Capa desacoplada que la pestaña Pedidos usa para consultar catálogo remoto en tiempo real y despachar
órdenes de compra a una plataforma externa. Interfaz única + adaptadores enchufables (registro por nombre,
mismo patrón que las pasarelas de pago). DEGRADABLE: sin credenciales configuradas devuelve catálogo vacío
y las órdenes no se despachan (el pedido ERP se crea igual). Los secretos se leen de la config cifrada del
módulo (ver `db/compras_b2b`), que la pestaña Avanzado gestiona (Fase 4).

API pública (lo que consume la GUI):
- `obtener_catalogo(filtro_articulo=None, proveedor_id=None, id_empresa=None) -> list[dict]`
- `enviar_orden_compra(payload_pedido, id_empresa=None) -> dict`
"""

import logging

logger = logging.getLogger("compras.b2b_client")

# nombre -> clase adaptadora
_REGISTRO: dict = {}


def registrar(nombre):
    def deco(clase):
        clase.nombre = nombre
        _REGISTRO[nombre] = clase
        return clase
    return deco


class ConectorB2B:
    """Contrato común de un conector B2B (Consentio/Choco/REST/EDI)."""

    nombre = "base"

    def __init__(self, config: dict):
        self.config = config or {}

    def configurado(self) -> bool:
        return bool(self.config.get("endpoint") and self.config.get("api_key"))

    def es_sandbox(self) -> bool:
        return (self.config.get("entorno") or "sandbox").lower() != "produccion"

    def obtener_catalogo(self, filtro_articulo=None, proveedor_id=None) -> list:
        """Lista de {codigo, nombre, proveedor, precio, divisa, unidad, stock, proveedor_id, ref_externa}."""
        return []

    def enviar_orden_compra(self, payload_pedido: dict) -> dict:
        """Despacha la orden. Devuelve {ok, id_externo, estado, mensaje}."""
        return {"ok": False, "id_externo": None, "estado": "no_enviado",
                "mensaje": "Conector B2B no configurado."}


@registrar("rest")
class ConectorREST(ConectorB2B):
    """Conector genérico REST/JSON (sirve para Consentio/Choco u otros proveedores con API REST).
    Endpoints esperables (parametrizables por config): GET {endpoint}/catalog · POST {endpoint}/orders."""

    nombre = "rest"

    def _headers(self):
        return {"Authorization": f"Bearer {self.config.get('api_key','')}",
                "Content-Type": "application/json"}

    def obtener_catalogo(self, filtro_articulo=None, proveedor_id=None) -> list:
        if not self.configurado():
            return []
        try:
            import requests
        except Exception:
            return []
        params = {}
        if filtro_articulo:
            params["q"] = filtro_articulo
        if proveedor_id:
            params["supplier"] = proveedor_id
        try:
            r = requests.get(f"{self.config['endpoint'].rstrip('/')}/catalog", params=params,
                             headers=self._headers(), timeout=20)
            if r.status_code != 200:
                logger.warning("B2B catalog %s: %s", r.status_code, r.text[:150])
                return []
            data = r.json()
            items = data.get("items", data) if isinstance(data, dict) else data
            return [self._normaliza(x) for x in (items or [])]
        except Exception as e:
            logger.warning("obtener_catalogo: %s", e)
            return []

    @staticmethod
    def _normaliza(x: dict) -> dict:
        return {
            "codigo": x.get("sku") or x.get("codigo") or x.get("id"),
            "nombre": x.get("name") or x.get("nombre") or x.get("sku"),
            "proveedor": x.get("supplier_name") or x.get("proveedor") or "B2B",
            "proveedor_id": x.get("supplier_id") or x.get("proveedor_id"),
            "precio": float(x.get("price") or x.get("precio") or 0),
            "divisa": (x.get("currency") or x.get("divisa") or "EUR"),
            "unidad": x.get("unit") or x.get("unidad") or "unidad",
            "stock": x.get("stock") if x.get("stock") is not None else x.get("available"),
            "ref_externa": x.get("id") or x.get("ref"),
        }

    def enviar_orden_compra(self, payload_pedido: dict) -> dict:
        if not self.configurado():
            return {"ok": False, "id_externo": None, "estado": "no_enviado",
                    "mensaje": "Conector B2B no configurado."}
        try:
            import requests
            r = requests.post(f"{self.config['endpoint'].rstrip('/')}/orders", json=payload_pedido,
                              headers=self._headers(), timeout=25)
            if r.status_code in (200, 201):
                j = r.json()
                return {"ok": True, "id_externo": j.get("id") or j.get("order_id"),
                        "estado": j.get("status") or "enviado", "mensaje": "Orden despachada."}
            return {"ok": False, "id_externo": None, "estado": "rechazado",
                    "mensaje": f"La plataforma respondió {r.status_code}."}
        except Exception as e:
            logger.warning("enviar_orden_compra: %s", e)
            return {"ok": False, "id_externo": None, "estado": "error", "mensaje": str(e)}


@registrar("simulado")
class ConectorSimulado(ConectorB2B):
    """Conector de desarrollo/pruebas: sin red, catálogo vacío y órdenes simuladas (honesto)."""

    nombre = "simulado"

    def configurado(self) -> bool:
        return True

    def enviar_orden_compra(self, payload_pedido: dict) -> dict:
        import uuid
        return {"ok": True, "id_externo": f"SIM-{uuid.uuid4().hex[:10].upper()}",
                "estado": "simulado", "mensaje": "Orden simulada (sin despacho real)."}


def _conector(id_empresa=None) -> ConectorB2B:
    """Resuelve el conector configurado para la empresa; degrada a simulado sin credenciales."""
    try:
        from src.db import compras_b2b as cfgdb
        cfg = cfgdb.obtener_config(id_empresa)
    except Exception as e:
        logger.debug("config B2B no disponible: %s", e)
        cfg = {}
    nombre = (cfg.get("proveedor") or "rest")
    clase = _REGISTRO.get(nombre) or _REGISTRO.get("rest")
    inst = clase(cfg) if clase else ConectorB2B(cfg)
    return inst if inst.configurado() else _REGISTRO["simulado"](cfg)


# ── API pública (consumida por la GUI de Pedidos) ────────────────────────────
def disponible(id_empresa=None) -> bool:
    """True si hay un conector B2B realmente configurado (no el simulado)."""
    try:
        from src.db import compras_b2b as cfgdb
        cfg = cfgdb.obtener_config(id_empresa)
        clase = _REGISTRO.get(cfg.get("proveedor") or "rest") or ConectorB2B
        return clase(cfg).configurado()
    except Exception:
        return False


def obtener_catalogo(filtro_articulo=None, proveedor_id=None, id_empresa=None) -> list:
    try:
        return _conector(id_empresa).obtener_catalogo(filtro_articulo, proveedor_id) or []
    except Exception as e:
        logger.error("obtener_catalogo: %s", e)
        return []


def enviar_orden_compra(payload_pedido: dict, id_empresa=None) -> dict:
    try:
        return _conector(id_empresa).enviar_orden_compra(payload_pedido)
    except Exception as e:
        logger.error("enviar_orden_compra: %s", e)
        return {"ok": False, "id_externo": None, "estado": "error", "mensaje": str(e)}
