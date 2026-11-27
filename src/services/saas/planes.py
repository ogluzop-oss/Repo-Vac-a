"""
Catálogo de planes y módulos SaaS (FASE SAAS-A/B).

Define los 3 planes oficiales (BASIC / PLUS / PRO) con sus límites y módulos habilitados, y los
siembra (idempotente) en planes_saas/modulos_saas/plan_modulos. Fuente canónica del enforcement.
"""

import logging

from src.db.conexion import ensure_schema, obtener_conexion

logger = logging.getLogger("saas.planes")

# Módulos del ERP (codigo → nombre).
MODULOS = {
    "tpv": "TPV", "ventas": "Ventas", "compras": "Compras", "inventario": "Inventario",
    "clientes": "Clientes", "proveedores": "Proveedores", "facturacion": "Facturación",
    "correo": "Correo corporativo", "rrhh": "RRHH", "tesoreria": "Tesorería",
    "workflow": "Workflow/BPM", "scheduler": "Automatizaciones", "comunicaciones": "Comunicaciones",
    "bi": "Business Intelligence", "contabilidad": "Contabilidad",
    "aeat": "Modelos AEAT", "verifactu": "Verifactu",
    "facturae": "Facturae", "branding": "Branding", "multiempresa": "Multiempresa",
    "api": "API completa", "conectores": "Conectores premium",
    "automatizaciones": "Automatizaciones avanzadas", "admin_delegada": "Administración delegada",
    "forecasting": "Forecasting", "comparativas": "Comparativas multiempresa",
}

_BASE = ["tpv", "ventas", "compras", "inventario", "clientes", "proveedores", "facturacion", "correo"]
_PLUS = _BASE + ["rrhh", "tesoreria", "contabilidad", "workflow", "scheduler", "comunicaciones", "bi",
                 "aeat", "verifactu", "facturae", "forecasting"]
# PRO añade lo Enterprise: comparativas multiempresa, branding, api, conectores, etc.
_PRO = list(MODULOS.keys())


# `precio_anual`: 2 meses gratis frente al mensual (equivale a pagar 10 meses por 12, ~16,7% de
# descuento) — decisión de negocio explícita (2026-11-15), mismo criterio para los 3 planes. Vive
# aquí (no en `planes_saas`/BD) porque solo se usa para mostrar precio/ahorro en la web y para
# calcular el importe de la factura al activar (`alta_comercial._activar_plan_pagado`); el ciclo
# en sí (duración real de la suscripción) ya lo resuelve `suscripciones.CICLOS`.
#
# `precio_anual_financiado` (petición explícita, 2026-11-27): el pago anual EN 4 CUOTAS (primer
# año) ya NO lleva el mismo descuento que el pago íntegro — pasa de 2 meses gratis (`precio_anual`
# = `precio*10`) a solo 1 mes gratis (`precio*11`), para que financiar tenga un coste ligeramente
# mayor que pagar de una vez (un incentivo real a pagar el anual íntegro). Se usa SOLO para
# calcular la cuota trimestral del año 1 (`alta_comercial.confirmar_financiacion`/`sitio_oficial.
# _paypal_crear_plan_financiacion`) — el pago anual íntegro (`precio_anual`) y el ciclo normal a
# partir del año 2 de la financiación por Stripe NO cambian, siguen con los 2 meses gratis de
# siempre.
PLANES = {
    "BASIC": {"nombre": "Smart Manager", "precio": 29.0, "precio_anual": 290.0,
              "precio_anual_financiado": 319.0,
              "limites": {"max_empresas": 1, "max_tiendas": 1, "max_usuarios": 3,
                          "max_almacenes": 1, "max_correos": 3}, "modulos": _BASE},
    "PLUS": {"nombre": "Smart Manager Plus", "precio": 49.0, "precio_anual": 490.0,
             "precio_anual_financiado": 539.0,
             "limites": {"max_empresas": 1, "max_tiendas": 10, "max_usuarios": 50,
                         "max_almacenes": 20, "max_correos": 25}, "modulos": _PLUS},
    "PRO": {"nombre": "Smart Manager Pro", "precio": 149.0, "precio_anual": 1490.0,
            "precio_anual_financiado": 1639.0,
            "limites": {"max_empresas": 9999, "max_tiendas": 9999, "max_usuarios": 9999,
                        "max_almacenes": 9999, "max_correos": 9999}, "modulos": _PRO},
}


def sincronizar_planes(config=None) -> int:
    """Inserta (idempotente) planes, módulos y su relación. Devuelve nº de planes.

    `config` opcional (mismo dict que `obtener_conexion`): sincroniza en OTRA base de datos (SaaS,
    ver `services.provisioning.aprovisionar_tenant_nuevo`)."""
    ensure_schema(config=config)
    try:
        with obtener_conexion(config) as conn, conn.cursor() as cur:
            for cod, nom in MODULOS.items():
                cur.execute("INSERT IGNORE INTO modulos_saas (codigo, nombre) VALUES (%s,%s)", (cod, nom))
            for codigo, cfg in PLANES.items():
                lim = cfg["limites"]
                cur.execute("INSERT INTO planes_saas (codigo, nombre, precio_mensual, max_empresas, "
                            "max_tiendas, max_usuarios, max_almacenes, max_correos) "
                            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
                            "nombre=VALUES(nombre), precio_mensual=VALUES(precio_mensual), "
                            "max_empresas=VALUES(max_empresas), max_tiendas=VALUES(max_tiendas), "
                            "max_usuarios=VALUES(max_usuarios), max_almacenes=VALUES(max_almacenes), "
                            "max_correos=VALUES(max_correos)",
                            (codigo, cfg["nombre"], cfg["precio"], lim["max_empresas"], lim["max_tiendas"],
                             lim["max_usuarios"], lim["max_almacenes"], lim["max_correos"]))
                cur.execute("SELECT id FROM planes_saas WHERE codigo=%s", (codigo,))
                r = cur.fetchone()
                pid = r[0] if not isinstance(r, dict) else list(r.values())[0]
                for m in cfg["modulos"]:
                    cur.execute("INSERT IGNORE INTO plan_modulos (id_plan, codigo_modulo) VALUES (%s,%s)",
                                (pid, m))
            conn.commit()
        return len(PLANES)
    except Exception as e:
        logger.error("sincronizar_planes: %s", e)
        return 0


def plan(codigo: str) -> dict | None:
    return PLANES.get((codigo or "").upper())
