"""
Guard central de tenant (SEC-6).

NO modifica el modelo ni intercepta el driver (no rompe consultas globales legítimas). Ofrece
un analizador estático de SQL que detecta consultas sobre tablas multitenant que NO filtran por
id_empresa — para usar en tests de aislamiento y revisión continua. Complementa
saas.aislamiento (cobertura de esquema).
"""

import logging
import re

logger = logging.getLogger("seguridad.tenant_guard")

# Tablas con dimensión id_empresa que SIEMPRE deberían filtrarse en lecturas/mutaciones.
TABLAS_TENANT = {
    "ventas", "venta_items", "facturas_cliente", "compras_facturas", "clientes", "proveedores",
    "movimientos_stock", "stock_almacen", "contab_asientos", "contab_apuntes", "vencimientos",
    "movimientos_tesoreria", "cuentas_bancarias", "aeat_declaraciones", "wf_instancias",
    "wf_tareas", "notificaciones", "empresa_licencia", "suscripciones", "bi_kpi_valores",
}
_RE_TABLA = re.compile(r"\b(?:FROM|JOIN|UPDATE|INTO)\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE)


def analizar(sql: str) -> dict:
    """Devuelve {ok, tablas_tenant, filtra} indicando si una consulta sobre tablas tenant
    incluye una condición id_empresa. Heurístico (no sustituye RLS de BD)."""
    s = sql or ""
    tablas = {m.group(1).lower() for m in _RE_TABLA.finditer(s)}
    afectadas = tablas & TABLAS_TENANT
    if not afectadas:
        return {"ok": True, "tablas_tenant": [], "filtra": True}
    filtra = bool(re.search(r"id_empresa", s, re.IGNORECASE))
    return {"ok": filtra, "tablas_tenant": sorted(afectadas), "filtra": filtra}


def es_segura(sql: str) -> bool:
    return analizar(sql)["ok"]
