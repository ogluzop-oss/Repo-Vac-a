"""
Catálogo de permisos RBAC + roles del sistema y mapeo LEGACY (FASE 2 / FASE 12).

El catálogo (modulo.accion) es la fuente canónica que se SINCRONIZA a la tabla `permisos`
(global). Los roles del sistema (OPERARIO/GERENTE/ADMINISTRADOR/SUPERADMIN) se crean por
empresa y se enlazan a sus permisos, de modo que las instalaciones existentes siguen
funcionando con su `usuarios.perfil` mapeado automáticamente al nuevo modelo.
"""

import logging

from src.db.conexion import ensure_schema, obtener_conexion

logger = logging.getLogger("seguridad.catalogo")

# ── Catálogo canónico de permisos (modulo.accion) ─────────────────────────────
CATALOGO = [
    # Inventario / stock
    "inventario.ver", "inventario.crear", "inventario.editar", "inventario.eliminar",
    "inventario.ajustar",
    "stock.consultar_desde_tpv",  # UX-TPV-01: consulta de stock desde el TPV
    # Compras
    "compras.ver", "compras.crear", "compras.editar", "compras.aprobar", "compras.facturar",
    # Ventas / TPV
    "ventas.ver", "ventas.crear", "ventas.facturar", "ventas.devolver", "ventas.anular",
    # Clientes / proveedores
    "clientes.ver", "clientes.editar", "proveedores.ver", "proveedores.editar",
    # RRHH
    "rrhh.ver", "rrhh.editar", "rrhh.nominas.generar", "rrhh.contratos.firmar",
    # Contabilidad
    "contabilidad.ver", "contabilidad.asiento", "contabilidad.cierre",
    # Tesorería
    "tesoreria.ver", "tesoreria.movimientos", "tesoreria.remesas.generar",
    "tesoreria.remesas.ejecutar", "tesoreria.conciliar",
    # AEAT
    "aeat.ver", "aeat.generar", "aeat.presentar",
    # Fiscal
    "verifactu.emitir", "facturae.emitir",
    # Documentos
    "documentos.ver", "documentos.exportar", "documentos.eliminar",
    # Usuarios / seguridad
    "usuarios.ver", "usuarios.crear", "usuarios.editar", "usuarios.eliminar",
    "seguridad.roles", "seguridad.permisos", "seguridad.acl",
    # Auditoría / configuración
    "auditoria.ver", "configuracion.ver", "configuracion.editar",
    # Comunicaciones (rama COM)
    "notificaciones.ver", "mensajeria.usar", "correo.enviar", "correo.recibir",
    "scheduler.gestionar", "integraciones.usar", "calendario.gestionar",
    "tareas.gestionar", "webhooks.gestionar",
    # Business Intelligence (rama BI)
    "bi.ver", "bi.kpi", "bi.dashboard", "bi.forecasting", "bi.exportar", "bi.multiempresa",
    # SaaS / plataforma (rama SAAS)
    "saas.admin", "saas.licencias", "saas.suscripciones", "saas.tenants",
    "saas.portal", "saas.metricas", "saas.branding",
    # CRM comercial (BLOQUE 2)
    "crm.ver", "crm.leads", "crm.oportunidades", "crm.pipeline", "crm.actividades",
    "crm.forecast", "crm.crm_saas", "crm.admin",
    # Disaster Recovery (BLOQUE 2)
    "dr.ver", "dr.snapshot", "dr.restaurar", "dr.drills", "dr.admin",
    # MRP / Fabricacion (BLOQUE 3)
    "mrp.ver", "mrp.bom", "mrp.planificar", "mrp.admin",
    "fabricacion.ver", "fabricacion.crear", "fabricacion.liberar", "fabricacion.ejecutar",
    "fabricacion.finalizar", "fabricacion.costes",
    # Calidad (BLOQUE 3)
    "calidad.ver", "inspecciones.ver", "inspecciones.crear",
    "nc.ver", "nc.crear", "nc.gestionar", "capa.ver", "capa.gestionar",
    "auditorias.ver", "auditorias.gestionar", "calidad.admin",
    # GMAO (BLOQUE 4)
    "gmao.ver", "gmao.admin", "activos.ver", "activos.gestionar",
    "ot.ver", "ot.crear", "ot.ejecutar", "ot.finalizar",
    # SAT / Helpdesk (BLOQUE 4)
    "sat.ver", "sat.admin", "tickets.ver", "tickets.crear", "tickets.gestionar",
    "sla.ver", "sla.gestionar", "kb.ver", "kb.gestionar", "intervenciones.gestionar",
    # Finanzas avanzadas (BLOQUE 5)
    "finanzas.ver", "finanzas.admin", "presupuestos.ver", "presupuestos.gestionar",
    "financiacion.ver", "financiacion.gestionar", "credito.ver", "credito.gestionar",
    "finanzas.simulacion", "finanzas.kpis",
    # BI Corporativo (DW/OLAP/ejecutivo)
    "bi_corp.ver", "bi_corp.dw", "bi_corp.olap", "bi_corp.consolidado",
    "bi_corp.forecast", "bi_corp.alertas", "bi_corp.export", "bi_corp.ia", "bi_corp.admin",
    # Resiliencia / continuidad operativa (BLOQUE 7)
    "resiliencia.ver", "resiliencia.sync", "resiliencia.offline", "resiliencia.breakers",
    "resiliencia.watchdog", "resiliencia.chaos", "resiliencia.admin",
]

# Roles del sistema (codigo → conjunto de permisos). SUPERADMIN es comodín (todo).
ROLES_SISTEMA = {
    "SUPERADMIN": {"nombre": "Superadministrador", "permisos": "*"},
    "ADMINISTRADOR": {"nombre": "Administrador", "permisos": "*"},
    "GERENTE": {"nombre": "Gerente", "permisos": [
        "inventario.ver", "inventario.crear", "inventario.editar", "inventario.ajustar",
        "stock.consultar_desde_tpv",
        "compras.ver", "compras.crear", "compras.editar", "compras.aprobar", "compras.facturar",
        "ventas.ver", "ventas.crear", "ventas.facturar", "ventas.devolver", "ventas.anular",
        "clientes.ver", "clientes.editar", "proveedores.ver", "proveedores.editar",
        "rrhh.ver", "rrhh.editar", "rrhh.nominas.generar", "rrhh.contratos.firmar",
        "contabilidad.ver", "contabilidad.asiento", "contabilidad.cierre",
        "tesoreria.ver", "tesoreria.movimientos", "tesoreria.remesas.generar",
        "tesoreria.remesas.ejecutar", "tesoreria.conciliar",
        "aeat.ver", "aeat.generar", "aeat.presentar", "verifactu.emitir", "facturae.emitir",
        "documentos.ver", "documentos.exportar", "documentos.eliminar",
        "auditoria.ver", "configuracion.ver",
        "notificaciones.ver", "mensajeria.usar", "correo.enviar", "correo.recibir",
        "scheduler.gestionar", "integraciones.usar", "calendario.gestionar",
        "tareas.gestionar", "webhooks.gestionar",
        "bi.ver", "bi.kpi", "bi.dashboard", "bi.forecasting", "bi.exportar",
        "saas.portal", "saas.branding",
        "crm.ver", "crm.leads", "crm.oportunidades", "crm.pipeline", "crm.actividades",
        "crm.forecast", "crm.crm_saas", "crm.admin", "dr.ver",
        "mrp.ver", "mrp.bom", "mrp.planificar", "mrp.admin",
        "fabricacion.ver", "fabricacion.crear", "fabricacion.liberar", "fabricacion.ejecutar",
        "fabricacion.finalizar", "fabricacion.costes",
        "calidad.ver", "inspecciones.ver", "inspecciones.crear", "nc.ver", "nc.crear",
        "nc.gestionar", "capa.ver", "capa.gestionar", "auditorias.ver", "auditorias.gestionar",
        "calidad.admin",
        "gmao.ver", "gmao.admin", "activos.ver", "activos.gestionar", "ot.ver", "ot.crear",
        "ot.ejecutar", "ot.finalizar", "sat.ver", "sat.admin", "tickets.ver", "tickets.crear",
        "tickets.gestionar", "sla.ver", "sla.gestionar", "kb.ver", "kb.gestionar",
        "intervenciones.gestionar",
        "finanzas.ver", "finanzas.admin", "presupuestos.ver", "presupuestos.gestionar",
        "financiacion.ver", "financiacion.gestionar", "credito.ver", "credito.gestionar",
        "finanzas.simulacion", "finanzas.kpis",
        "bi_corp.ver", "bi_corp.dw", "bi_corp.olap", "bi_corp.consolidado", "bi_corp.forecast",
        "bi_corp.alertas", "bi_corp.export", "bi_corp.ia", "bi_corp.admin",
        "resiliencia.ver", "resiliencia.sync", "resiliencia.offline", "resiliencia.breakers",
        "resiliencia.watchdog", "resiliencia.chaos", "resiliencia.admin",
    ]},
    "OPERARIO": {"nombre": "Operario", "permisos": [
        "inventario.ver", "stock.consultar_desde_tpv",
        "ventas.ver", "ventas.crear", "ventas.facturar", "ventas.devolver",
        "clientes.ver", "compras.ver", "documentos.ver",
        "notificaciones.ver", "mensajeria.usar", "calendario.gestionar", "tareas.gestionar",
        "crm.ver", "crm.leads", "crm.actividades",
    ]},
}

PERFILES_LEGACY = tuple(ROLES_SISTEMA.keys())


def sincronizar_catalogo() -> int:
    """Inserta (idempotente) el catálogo de permisos en `permisos`. Devuelve nº presentes."""
    ensure_schema()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            for cod in CATALOGO:
                modulo = cod.split(".", 1)[0]
                accion = cod.split(".", 1)[1]
                cur.execute("INSERT IGNORE INTO permisos (codigo, modulo, accion) VALUES (%s,%s,%s)",
                            (cod, modulo, accion))
            conn.commit()
            cur.execute("SELECT COUNT(*) FROM permisos")
            r = cur.fetchone()
            return r[0] if not isinstance(r, dict) else list(r.values())[0]
    except Exception as e:
        logger.error("sincronizar_catalogo: %s", e)
        return 0


def sincronizar_roles_sistema(id_empresa) -> dict:
    """Crea (idempotente) los roles del sistema de una empresa y les asigna sus permisos.
    Mapea automáticamente OPERARIO/GERENTE/ADMINISTRADOR/SUPERADMIN al nuevo modelo (FASE 12)."""
    ensure_schema()
    sincronizar_catalogo()
    res = {"roles": 0, "asignaciones": 0}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, codigo FROM permisos")
            permisos = {(r[1] if not isinstance(r, dict) else r["codigo"]):
                        (r[0] if not isinstance(r, dict) else r["id"]) for r in cur.fetchall()}
            for codigo, cfg in ROLES_SISTEMA.items():
                cur.execute("INSERT IGNORE INTO roles (id_empresa, codigo, nombre, es_sistema) "
                            "VALUES (%s,%s,%s,1)", (id_empresa, codigo, cfg["nombre"]))
                cur.execute("SELECT id FROM roles WHERE id_empresa=%s AND codigo=%s",
                            (id_empresa, codigo))
                rid = cur.fetchone()
                rid = rid[0] if not isinstance(rid, dict) else list(rid.values())[0]
                res["roles"] += 1
                codigos = CATALOGO if cfg["permisos"] == "*" else cfg["permisos"]
                for cod in codigos:
                    pid = permisos.get(cod)
                    if pid:
                        cur.execute("INSERT IGNORE INTO roles_permisos (id_empresa, id_rol, id_permiso) "
                                    "VALUES (%s,%s,%s)", (id_empresa, rid, pid))
                        res["asignaciones"] += cur.rowcount
            conn.commit()
        return res
    except Exception as e:
        logger.error("sincronizar_roles_sistema: %s", e)
        return res


def permisos_de_perfil(perfil: str) -> set:
    """Permisos del rol de sistema (para el fallback LEGACY sin BD de roles)."""
    cfg = ROLES_SISTEMA.get((perfil or "").upper())
    if not cfg:
        return set()
    return set(CATALOGO) if cfg["permisos"] == "*" else set(cfg["permisos"])
