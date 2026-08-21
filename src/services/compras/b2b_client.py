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

# Catálogo de PRESETS de plataformas B2B (autocompletado). Cada preset fija el endpoint base y el adaptador
# técnico ('rest' genérico o 'simulado'); `oauth` marca si la plataforma admite vinculación por OAuth.
PRESETS = {
    "consentio": {"label": "Consentio", "endpoint": "https://api.consentio.co/v1",
                  "adapter": "rest", "oauth": True},
    "choco":     {"label": "Choco", "endpoint": "https://api.choco.com/v1",
                  "adapter": "rest", "oauth": True},
    "prezo":     {"label": "Prezo", "endpoint": "https://api.prezo.io/v1",
                  "adapter": "rest", "oauth": False},
    "b2brouter": {"label": "B2Brouter (EDI / Factura electrónica)",
                  "endpoint": "https://app.b2brouter.net/api", "adapter": "rest", "oauth": False},
    "haddock":   {"label": "haddock", "endpoint": "https://api.haddock.app/v1",
                  "adapter": "rest", "oauth": False},
    "rest":      {"label": "REST Personalizado", "endpoint": "", "adapter": "rest", "oauth": False},
    "simulado":  {"label": "Simulado (pruebas)", "endpoint": "", "adapter": "simulado", "oauth": False},
}


def preset(nombre) -> dict:
    return PRESETS.get(nombre or "rest", PRESETS["rest"])


def _adapter_de(nombre) -> str:
    """Adaptador técnico ('rest'/'simulado') de un preset o nombre de conector."""
    if nombre in _REGISTRO:
        return nombre
    return preset(nombre).get("adapter", "rest")


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

    def probar(self) -> dict:
        """Prueba de conexión. Devuelve {ok, n, mensaje}."""
        if not self.configurado():
            return {"ok": False, "n": 0, "mensaje": "Faltan credenciales (endpoint / API Key)."}
        return {"ok": True, "n": 0, "mensaje": "Configurado."}


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

    def probar(self) -> dict:
        if not self.configurado():
            return {"ok": False, "n": 0, "mensaje": "Faltan credenciales (endpoint / API Key)."}
        try:
            import requests
        except Exception:
            return {"ok": False, "n": 0, "mensaje": "requests no disponible."}
        try:
            r = requests.get(f"{self.config['endpoint'].rstrip('/')}/catalog",
                             headers=self._headers(), timeout=15)
            if r.status_code == 200:
                data = r.json()
                items = data.get("items", data) if isinstance(data, dict) else data
                n = len(items or [])
                return {"ok": True, "n": n, "mensaje": f"Conexión exitosa ({n} artículos detectados)."}
            if r.status_code in (401, 403):
                return {"ok": False, "n": 0, "mensaje": "Credenciales incorrectas."}
            return {"ok": False, "n": 0, "mensaje": f"Servidor no disponible ({r.status_code})."}
        except Exception as e:
            logger.debug("probar: %s", e)
            return {"ok": False, "n": 0, "mensaje": "Credenciales incorrectas o servidor no disponible."}

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

    def probar(self) -> dict:
        return {"ok": True, "n": 0, "mensaje": "Conector simulado (sin datos reales)."}

    def enviar_orden_compra(self, payload_pedido: dict) -> dict:
        import uuid
        return {"ok": True, "id_externo": f"SIM-{uuid.uuid4().hex[:10].upper()}",
                "estado": "simulado", "mensaje": "Orden simulada (sin despacho real)."}


def _clase_de(cfg) -> type:
    """Clase adaptadora para una config (según el preset/proveedor)."""
    adapter = _adapter_de(cfg.get("proveedor") or "rest")
    return _REGISTRO.get(adapter) or _REGISTRO.get("rest") or ConectorB2B


def _conector(id_empresa=None) -> ConectorB2B:
    """Resuelve el conector configurado para la empresa; degrada a simulado sin credenciales."""
    try:
        from src.db import compras_b2b as cfgdb
        cfg = cfgdb.obtener_config(id_empresa)
    except Exception as e:
        logger.debug("config B2B no disponible: %s", e)
        cfg = {}
    inst = _clase_de(cfg)(cfg)
    return inst if inst.configurado() else _REGISTRO["simulado"](cfg)


# ── API pública (consumida por la GUI de Pedidos y Avanzado) ─────────────────
def disponible(id_empresa=None) -> bool:
    """True si hay un conector B2B realmente configurado (no el simulado)."""
    try:
        from src.db import compras_b2b as cfgdb
        cfg = cfgdb.obtener_config(id_empresa)
        return _clase_de(cfg)(cfg).configurado()
    except Exception:
        return False


def probar_conexion(config=None, id_empresa=None) -> dict:
    """Prueba de conexión en tiempo real. Si se pasa `config` (valores del formulario, sin guardar aún) se
    prueba esa; si no, la config guardada. Devuelve {ok, n, mensaje}."""
    if config is None:
        try:
            from src.db import compras_b2b as cfgdb
            config = cfgdb.obtener_config(id_empresa)
        except Exception:
            config = {}
    try:
        return _clase_de(config)(config).probar()
    except Exception as e:
        logger.error("probar_conexion: %s", e)
        return {"ok": False, "n": 0, "mensaje": "No se pudo probar la conexión."}


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
