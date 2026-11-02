"""
Guard de aislamiento multitenant (P2.2 + Bloque 4 "auditoría + guard centralizado").

Herramienta de GUARDIA (read-only): clasifica cada tabla según su mecanismo de aislamiento por tenant
y detecta FUGAS REALES (tablas de datos de empresa sin ningún aislamiento). NO reescribe consultas ni
altera esquemas — el aislamiento del ERP es mayormente estructural (id_empresa directo o vía tabla
padre); esta utilidad lo verifica de forma exhaustiva y reutilizable para escenarios multiempresa.

Clasificación:
  · DIRECTA   — la tabla tiene `id_empresa` (aislamiento directo).
  · VIA_PADRE — tabla de detalle/hija: se aísla al unir con su tabla padre (que sí filtra por empresa).
  · VIA_USUARIO — se aísla por `id_usuario` (el usuario pertenece a una empresa).
  · GLOBAL    — catálogo/sistema legítimamente compartido (no requiere aislamiento).
  · FUGA      — tabla de datos sin ningún mecanismo → requiere revisión.
"""

import logging

from src.db.conexion import obtener_conexion

logger = logging.getLogger("saas.aislamiento")

# Catálogos/sistema legítimamente GLOBALES (no requieren id_empresa).
GLOBALES = {
    "permisos", "planes_saas", "modulos_saas", "plan_modulos", "migraciones_aplicadas",
    "schema_migraciones", "bi_kpi_def", "eventos_tipo",
    # Catálogos fiscales de país (referencia global).
    "pais_fiscal", "configuracion_iva_pais", "regimen_fiscal_pais",
    # Catálogo IAE (epígrafes + deducciones sectoriales por epígrafe, migr. 0273): mismo criterio
    # que los catálogos fiscales de arriba — referencia nacional, no dato de una empresa concreta
    # (la asignación POR empresa vive en `fiscal_empresa_epigrafe`, que sí tiene id_empresa).
    "fiscal_iae_epigrafes", "fiscal_deducciones_sectoriales",
    # Infra/sistema (DR, no dato de empresa).
    "dr_drills",
    # Catálogo de familias a granel (báscula del TPV, `services.tpv.familias_granel_imagenes`/
    # `familias_granel_subfamilias`, migraciones 0306/0308): MISMO criterio, consciente, que
    # `productos_granel` (la tabla de productos a granel en sí) — `productos_granel` SÍ tiene la
    # columna `id_empresa` (añadida de forma genérica a toda tabla operativa por la Fase 0b de
    # `conexion.py`), pero su servicio real (`services.tpv.bulk_products_service`) no la usa en
    # NINGUNA de sus consultas: todo el catálogo a granel (productos, familias canónicas de
    # `familias_granel.py`, y por tanto también sus apartados/imágenes personalizados) es hoy
    # compartido entre empresas de la misma instalación, de forma consistente en todo el módulo —
    # no una fuga aislada de estas dos tablas. Aislar solo estas dos sin tocar el resto del módulo
    # dejaría una mezcla incoherente (parte del catálogo a granel por empresa, el resto global).
    "familias_granel_imagenes", "familias_granel_subfamilias",
}

# Tablas de DETALLE aisladas vía su tabla PADRE (que sí tiene id_empresa). Se aíslan al unir con ella.
VIA_PADRE = {
    "aeat_declaracion_lineas": "aeat_declaraciones",
    "compras_facturas_lineas": "compras_facturas",
    "compras_pedidos_lineas": "compras_pedidos",
    "compras_recepciones_lineas": "compras_recepciones",
    "pedidos_online_items": "pedidos_online",
    "proveedores_contactos": "proveedores",
    "proveedores_direcciones": "proveedores",
    "soma_mision_tareas": "soma_misiones",
    "wf_pasos": "wf_instancias",
    "wf_reglas": "wf_definiciones",
    "mfa_recovery_codes": "mfa_usuarios",
    "eventos_incidentes": "eventos",
    # Bultos de recepción logística (migr. 0313, desglose por bulto de un palé): hijas por FK de
    # `documentos_logisticos`/`documentos_logisticos_bultos` respectivamente (ambas con
    # id_empresa en la cadena) — confirmado en `db/logistica.py::generar_bultos_para_pale`/
    # `confirmar_recepcion_bulto`, que siempre resuelven el palé/documento padre filtrando por
    # `id_empresa` antes de tocar estas tablas de detalle.
    "documentos_logisticos_bultos": "documentos_logisticos",
    "documentos_logisticos_bultos_lineas": "documentos_logisticos_bultos",
}

# Tablas aisladas por USUARIO (el usuario pertenece a una empresa).
VIA_USUARIO = {"mfa_usuarios", "preferencias_usuario", "oauth_tokens"}


def _tiene_columna(cur, tabla, columna) -> bool:
    try:
        cur.execute(f"SHOW COLUMNS FROM {tabla} LIKE %s", (columna,))
        return cur.fetchone() is not None
    except Exception:
        return False


def clasificar(tabla, cur=None) -> str:
    """Devuelve el mecanismo de aislamiento de una tabla: directa|via_padre|via_usuario|global|fuga."""
    if tabla in GLOBALES:
        return "global"
    _cerrar = False
    if cur is None:
        conn = obtener_conexion(); cur = conn.__enter__().cursor(); _cerrar = True
    try:
        if _tiene_columna(cur, tabla, "id_empresa"):
            return "directa"
        if tabla in VIA_PADRE:
            return "via_padre"
        if tabla in VIA_USUARIO or _tiene_columna(cur, tabla, "id_usuario"):
            return "via_usuario"
        return "fuga"
    finally:
        if _cerrar:
            try:
                cur.close()
            except Exception:
                pass


def auditoria() -> dict:
    """Informe completo de aislamiento: clasifica TODAS las tablas y aísla las FUGAS reales."""
    res = {"directa": [], "via_padre": [], "via_usuario": [], "global": [], "fuga": []}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SHOW TABLES")
            tablas = [(r[0] if not isinstance(r, dict) else list(r.values())[0]) for r in cur.fetchall()]
            for t in tablas:
                res[clasificar(t, cur)].append(t)
    except Exception as e:
        logger.error("auditoria: %s", e)
    res["resumen"] = {k: len(v) for k, v in res.items() if isinstance(v, list)}
    return res


def tablas_sin_tenant() -> list:
    """FUGAS REALES: tablas de datos de empresa sin ningún mecanismo de aislamiento (compat. P2.2)."""
    return auditoria().get("fuga", [])


def verificar(tabla) -> bool:
    """True si la tabla está aislada por tenant (directa/vía padre/vía usuario) o es global declarada."""
    return clasificar(tabla) != "fuga"
