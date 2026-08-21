"""
JobRegistry — catálogo Enterprise de Jobs (Bloque 1, Jobs Opt-In).

NO es un motor nuevo: es el CATÁLOGO declarativo que acompaña al `scheduler` existente. Aporta, para
cada job, los metadatos que el Scheduler no tenía (categoría, si es PESADO, prioridad, timeout,
reintentos y el permiso RBAC requerido) y sincroniza esos metadatos + la política opt-in en la tabla
`scheduler_jobs` (migr 0101), reutilizando los registradores de callables ya existentes en cada módulo.

Política: los jobs LIGEROS se habilitan por defecto; los PESADOS quedan deshabilitados (opt-in) hasta
que se activen desde el ERP. La marca `configurado` en `scheduler_jobs` protege la elección del usuario
frente a esta sincronización (nunca la sobrescribe).
"""

import importlib
import logging

logger = logging.getLogger("scheduler.registry")

# Metadatos por job: codigo → dict(nombre, categoria, pesado, intervalo_horas, prioridad, timeout_seg,
# max_reintentos, permiso). El permiso RBAC controla quién puede habilitarlo/ejecutarlo (None = admin).
CATALOGO = {
    # ── Ligeros (habilitados por defecto) ──
    "vencimientos": ("Marcar vencimientos vencidos", "finanzas", False, 24, "alta", 300, 1, None),
    "cobros_recordatorios": ("Facturación · recordatorios de cobro a clientes", "finanzas", False, 24, "normal", 300, 1, None),
    "camaras_retencion": ("Videovigilancia · purga de grabaciones antiguas", "sistema", False, 24, "baja", 600, 1, None),
    "saas_facturacion": ("SaaS · facturación automática de suscripciones vencidas", "finanzas", False, 24, "alta", 600, 2, None),
    "workflow_sla": ("Escalado SLA de aprobaciones", "workflow", False, 12, "alta", 300, 1, None),
    "backup": ("Backup programado", "sistema", False, 24, "alta", 1800, 1, None),
    "DR_BACKUP_VERIFY_DAILY": ("DR · verificación de backup", "dr", False, 24, "alta", 600, 2, "dr.ver"),
    "DR_RESTORE_TEST_WEEKLY": ("DR · test de restauración", "dr", False, 168, "normal", 1800, 1, "dr.ver"),
    "DR_CONSISTENCY_CHECK_MONTHLY": ("DR · consistencia", "dr", False, 720, "normal", 900, 1, "dr.ver"),
    "gemelo_consistencia": ("Gemelo · consistencia", "gemelo", False, 6, "normal", 300, 1, None),
    "sat_sla": ("SAT · control SLA de tickets", "sat", False, 4, "alta", 300, 2, "sat.ver"),
    "gmao_preventivo": ("GMAO · mantenimiento preventivo", "gmao", False, 24, "normal", 600, 1, "gmao.ver"),
    "crm_automatizacion": ("CRM · automatización comercial", "crm", False, 24, "normal", 300, 1, "crm.ver"),
    "BI_SNAPSHOT_DAILY": ("BI · snapshot diario", "bi", False, 24, "normal", 600, 1, None),
    "BI_SNAPSHOT_WEEKLY": ("BI · snapshot semanal", "bi", False, 168, "baja", 600, 1, None),
    "BI_SNAPSHOT_MONTHLY": ("BI · snapshot mensual", "bi", False, 720, "baja", 600, 1, None),
    "BI_SNAPSHOT_YEARLY": ("BI · snapshot anual", "bi", False, 8760, "baja", 600, 1, None),
    "fin_ratios": ("Finanzas · ratios a BI", "finanzas", False, 24, "normal", 600, 1, None),
    "fin_riesgo_credito": ("Finanzas · riesgo de crédito", "finanzas", False, 24, "normal", 600, 1, None),
    "fin_anomalias": ("Finanzas · anomalías", "finanzas", False, 24, "normal", 600, 1, None),
    "gobierno_escalado": ("Gobierno · escalado", "gobierno", False, 12, "normal", 300, 1, None),
    "automatizacion_diaria": ("Automatización · diaria", "automatizacion", False, 24, "normal", 600, 1, None),
    "automatizacion_semanal": ("Automatización · semanal", "automatizacion", False, 168, "baja", 600, 1, None),
    "automatizacion_mensual": ("Automatización · mensual", "automatizacion", False, 720, "baja", 600, 1, None),
    "distribucion_tick": ("Comunicaciones · distribución (tick)", "comunicaciones", False, 1, "normal", 300, 2, None),
    "distribucion_ventana": ("Comunicaciones · ventana de envío", "comunicaciones", False, 1, "baja", 300, 1, None),
    "distribucion_reintentos": ("Comunicaciones · reintentos", "comunicaciones", False, 2, "baja", 300, 2, None),
    "proveedores_renovaciones": ("Proveedores · renovaciones/vencimientos", "compras", False, 24, "normal", 300, 1, "compras.ver"),
    "compras_recurrentes": ("Compras · pedidos recurrentes", "compras", False, 24, "normal", 300, 1, "compras.ver"),
    "inventario_conteo_ciclico": ("Inventario · conteo cíclico por rotación", "inventario", False, 168, "baja", 300, 1, "inventario.ver"),
    "contratos_alertas_vencimiento": ("Contratos · alertas de vencimiento/renovación", "contratos", False, 24, "normal", 300, 1, None),
    "contab_asientos_recurrentes": ("Contabilidad · asientos recurrentes", "contabilidad", False, 24, "normal", 300, 1, "contabilidad.ver"),
    "bi_suscripciones_distribucion": ("BI · distribución de informes suscritos", "bi", False, 24, "baja", 600, 1, "bi.ver"),
    "calidad_calibraciones_alerta": ("Calidad · alerta de calibración de equipos", "calidad", False, 168, "normal", 300, 1, "calidad.ver"),
    "documental_retencion": ("Documentación · archivado por retención caducada", "documental", False, 168, "baja", 300, 1, None),
    "identidad_validacion_centros": ("Identidad · validación de integridad de centros", "identidad", False, 168, "baja", 300, 1, "identidad.ver"),
    "identidad_verificacion_terminales": ("Identidad · verificación de terminales", "identidad", False, 24, "baja", 300, 1, "identidad.ver"),
    "identidad_sincronizacion": ("Identidad · sincronización de identidades", "identidad", False, 24, "baja", 300, 1, "identidad.configurar"),
    # ── PESADOS / dependientes (opt-in, deshabilitados por defecto) ──
    "bi_corp_etl": ("BI Corporativo · ETL Data Warehouse", "bi", True, 24, "baja", 3600, 1, "bi.admin"),
    "bi_corp_alertas": ("BI Corporativo · alertas", "bi", True, 24, "baja", 900, 1, "bi.admin"),
    "resiliencia_sync": ("Resiliencia · sync offline→central", "resiliencia", True, 1, "normal", 900, 3, "dr.ver"),
    "resiliencia_watchdog": ("Resiliencia · watchdog", "resiliencia", True, 1, "normal", 300, 1, "dr.ver"),
    "resiliencia_metricas": ("Resiliencia · métricas", "resiliencia", True, 1, "baja", 300, 1, "dr.ver"),
    "cache_warmup": ("BI · warm-up de caché corporativa", "bi", True, 6, "baja", 1800, 1, "bi.admin"),
    "sat_email_ticket": ("SAT · email-to-ticket (IMAP)", "sat", True, 1, "normal", 300, 2, "sat.ver"),
    "SAAS_DUNNING": ("SaaS · recuperación de impagos", "saas", True, 24, "normal", 600, 2, "saas.admin"),
}

# Registradores de CALLABLES existentes (módulo, función). Se invocan para poblar `scheduler.REGISTRO`
# reutilizando el código ya escrito en cada dominio; la política opt-in se aplica después.
REGISTRADORES = [
    ("src.services.scheduler", "registrar_jobs_por_defecto"),   # vencimientos/workflow_sla/backup + seguros
    ("src.services.dr.dr_drills", "registrar_jobs_dr"),
    ("src.services.gemelo.consistencia", "registrar_jobs_gemelo"),
    ("src.services.sat.contratos_sla", "registrar_jobs_sat"),
    ("src.services.gmao.planes", "registrar_jobs_gmao"),
    ("src.services.crm.automatizacion", "registrar_jobs_crm"),
    ("src.services.bi.snapshots", "registrar_jobs_bi"),
    ("src.services.finanzas.dashboard", "registrar_jobs_finanzas"),
    ("src.services.bi_corp.dw", "registrar_jobs_dw"),
    ("src.services.bi_corp.alertas", "registrar_jobs_alertas"),
    ("src.services.resiliencia.sync_engine", "registrar_jobs_sync"),
    ("src.services.resiliencia.resilience_watchdog", "registrar_jobs_watchdog"),
    ("src.services.resiliencia.cache_manager", "registrar_jobs_cache"),
    ("src.services.resiliencia.resilience_dashboard", "registrar_jobs_dashboard"),
    ("src.services.sat.email_ticket", "registrar_jobs_email"),
    ("src.services.saas.dunning", "registrar_job_dunning"),
    ("src.services.compras.proveedores_pro", "registrar_jobs_proveedores"),
    ("src.services.compras.compras_pro", "registrar_jobs_compras"),
    ("src.services.inventario.stock_pro", "registrar_jobs_inventario"),
    ("src.services.contratos.contratos_pro", "registrar_jobs_contratos"),
    ("src.services.contabilidad.plantillas", "registrar_jobs_contabilidad"),
    ("src.services.bi.suscripciones", "registrar_jobs_bi_suscripciones"),
    ("src.services.calidad.calidad_pro", "registrar_jobs_calidad"),
    ("src.services.documental.dms_pro", "registrar_jobs_documental"),
    ("src.services.identidad.identidad", "registrar_jobs_identidad"),
]

_CAMPOS = ("nombre", "categoria", "pesado", "intervalo_horas", "prioridad", "timeout_seg",
           "max_reintentos", "permiso")


def meta(codigo) -> dict:
    """Metadatos del catálogo para un job (o valores por defecto si no está catalogado)."""
    t = CATALOGO.get(codigo)
    if t:
        return dict(zip(_CAMPOS, t))
    return {"nombre": codigo, "categoria": "otros", "pesado": False, "intervalo_horas": 24,
            "prioridad": "normal", "timeout_seg": 300, "max_reintentos": 1, "permiso": None}


def catalogo() -> list:
    """Lista completa del catálogo (para GUI/documentación)."""
    return [dict(codigo=c, **meta(c)) for c in CATALOGO]


def registrar_callables(id_empresa=None):
    """Reutiliza los registradores de cada dominio para poblar `scheduler.REGISTRO` (callables) y crear
    las filas base. Best-effort: un módulo ausente no rompe. NO decide el estado activo (eso lo hace
    `sincronizar`, respetando la marca `configurado`)."""
    for mod, fn in REGISTRADORES:
        try:
            getattr(importlib.import_module(mod), fn)(id_empresa=id_empresa)
        except Exception as e:
            logger.debug("registrar_callables %s.%s: %s", mod, fn, e)


def sincronizar(id_empresa=None):
    """Aplica metadatos del catálogo + política opt-in a `scheduler_jobs`, SIN sobrescribir lo que el
    usuario haya configurado (`configurado=1`). Los pesados quedan deshabilitados por defecto."""
    from src.db.conexion import obtener_conexion
    from src.services.scheduler import _emp
    emp = _emp(id_empresa)
    registrar_callables(emp)
    try:
        with obtener_conexion() as c, c.cursor() as cur:
            for codigo, t in CATALOGO.items():
                m = dict(zip(_CAMPOS, t))
                pesado = 1 if m["pesado"] else 0
                activo_defecto = 0 if m["pesado"] else 1
                # Solo fija activo/metadatos donde el usuario NO ha configurado (configurado=0).
                cur.execute(
                    "UPDATE scheduler_jobs SET categoria=%s, pesado=%s, prioridad=%s, timeout_seg=%s, "
                    "max_reintentos=%s, activo=%s WHERE id_empresa<=>%s AND codigo=%s AND configurado=0",
                    (m["categoria"], pesado, m["prioridad"], m["timeout_seg"], m["max_reintentos"],
                     activo_defecto, emp, codigo))
            c.commit()
    except Exception as e:
        logger.debug("sincronizar catálogo: %s", e)
