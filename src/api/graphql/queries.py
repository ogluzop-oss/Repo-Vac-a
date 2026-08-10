"""
GraphQL Enterprise · Queries (Fase IV · Bloque 1). Resolvers de SOLO LECTURA. Cada uno DELEGA en un
servicio existente (ccp / sdk / marketplace / observabilidad / scheduler / rules / bi / audit_replay).
NUNCA hay SQL ni acceso a `src.db` aquí: GraphQL→Servicios→Dominio→BD. Todos reciben `contexto` y
toman el tenant del contexto (aislamiento multiempresa).
"""

from __future__ import annotations

from src.api.graphql import context as _c
from src.api.graphql import registry


def _emp(ctx):
    return _c.id_empresa(ctx)


def _prep(_servicio):
    """Resolver PREPARADO (declarado): devuelve [] hasta cablear su servicio. Sin BD directa."""
    def _r(_ctx, **_kw):
        return []
    return _r


# ── Comunicaciones / CCP ───────────────────────────────────────────────────────
def _q_communications(ctx, limite=50, **_):
    try:
        from src.services import ccp
        return ccp.historial_comunicaciones(id_empresa=_emp(ctx), limite=int(limite))
    except Exception:
        return []


def _q_conversation(ctx, id=None, **_):
    try:
        from src.services import ccp
        return ccp.conversaciones.mensajes(id, id_empresa=_emp(ctx))
    except Exception:
        return []


def _q_contacts(ctx, q="", contexto=None, limite=25, **_):
    try:
        from src.services import ccp
        return ccp.buscar_destinatarios(_emp(ctx), q or "", contexto=contexto, limite=int(limite))
    except Exception:
        return []


def _q_templates(ctx, **_):
    try:
        from src.services import ccp
        return ccp.templates.listar_plantillas(id_empresa=_emp(ctx))
    except Exception:
        return []


def _q_campaigns(ctx, **_):
    try:
        from src.services import ccp
        return ccp.campanas.listar_campanas(id_empresa=_emp(ctx))
    except Exception:
        return []


def _q_timeline(ctx, com_id=None, **_):
    try:
        from src.services import ccp
        return ccp.timeline.de_comunicacion(com_id, id_empresa=_emp(ctx))
    except Exception:
        return []


# ── Plugins / Marketplace ──────────────────────────────────────────────────────
def _q_plugins(ctx, **_):
    try:
        from src import sdk
        return sdk.listar_instalados(_emp(ctx))
    except Exception:
        return []


def _q_marketplace(ctx, categoria=None, q="", **_):
    try:
        from src.services import marketplace
        return marketplace.catalogo(id_empresa=_emp(ctx), categoria=categoria, texto=q)
    except Exception:
        return []


# ── Observabilidad / KPIs / Scheduler / Rules / Audit ──────────────────────────
def _q_observability(_ctx, **_):
    try:
        from src.services.observabilidad import health
        return health.health()
    except Exception:
        return {"status": "unknown"}


def _q_kpis(ctx, **_):
    try:
        from src.services import bi
        return bi.listar_kpis(id_empresa=_emp(ctx)) if hasattr(bi, "listar_kpis") else []
    except Exception:
        return []


def _q_scheduler(ctx, **_):
    try:
        from src.services import scheduler_enterprise as sch
        for fn in ("listar_jobs", "listar", "catalogo"):
            if hasattr(sch, fn):
                return getattr(sch, fn)(id_empresa=_emp(ctx)) if fn != "catalogo" else getattr(sch, fn)()
        return []
    except Exception:
        return []


def _q_rules(ctx, **_):
    try:
        from src.services import rules
        for fn in ("listar_reglas", "listar"):
            if hasattr(rules, fn):
                return getattr(rules, fn)(id_empresa=_emp(ctx))
        return []
    except Exception:
        return []


def _q_audit_replay(ctx, com_id=None, **_):
    try:
        from src.services import audit_replay
        return audit_replay.reconstruir(id_empresa=_emp(ctx), com_id=com_id)
    except Exception:
        return []


def _q_workflow(ctx, **_):
    try:
        from src.services import workflow
        for fn in ("listar_instancias", "listar", "bandeja"):
            if hasattr(workflow, fn):
                return getattr(workflow, fn)(id_empresa=_emp(ctx))
        return []
    except Exception:
        return []


def _q_commerce(_ctx, **_):
    """Descriptor de la Plataforma de Comercio Digital (Fase 1). Resuelve vía servicio, no BD."""
    try:
        from src.services import comercio_digital
        return comercio_digital.descriptor()
    except Exception:
        return {}


# ── Registro de todas las queries (nombre → resolver + servicio de destino) ─────
def registrar_todo():
    Q = registry.registrar_query
    # Wired (resuelven vía servicio real)
    Q("communications", _q_communications, tipo="[Communication]",
      args={"limite": "Int"}, servicio="ccp.historial_comunicaciones", permiso="comunicaciones.ver")
    Q("conversation", _q_conversation, tipo="[Message]", args={"id": "ID!"},
      servicio="ccp.conversaciones.mensajes", permiso="comunicaciones.ver")
    Q("contacts", _q_contacts, tipo="[Contact]",
      args={"q": "String", "contexto": "String", "limite": "Int"},
      servicio="ccp.buscar_destinatarios", permiso="comunicaciones.ver")
    Q("templates", _q_templates, tipo="[Template]", servicio="ccp.templates.listar_plantillas",
      permiso="comunicaciones.ver")
    Q("campaigns", _q_campaigns, tipo="[Campaign]", servicio="ccp.campanas.listar_campanas",
      permiso="comunicaciones.ver")
    Q("timeline", _q_timeline, tipo="[TimelineEntry]", args={"comId": "ID"},
      servicio="ccp.timeline.de_comunicacion", permiso="comunicaciones.ver")
    Q("plugins", _q_plugins, tipo="[Plugin]", servicio="sdk.listar_instalados",
      permiso="plugins.ver")
    Q("marketplace", _q_marketplace, tipo="[MarketItem]",
      args={"categoria": "String", "q": "String"}, servicio="marketplace.catalogo",
      permiso="marketplace.ver")
    Q("observability", _q_observability, tipo="Health", servicio="observabilidad.health")
    Q("kpis", _q_kpis, tipo="[Kpi]", servicio="bi.listar_kpis", permiso="bi.ver")
    Q("scheduler", _q_scheduler, tipo="[Job]", servicio="scheduler_enterprise.listar_jobs",
      permiso="scheduler.ver")
    Q("rules", _q_rules, tipo="[Rule]", servicio="rules.listar_reglas", permiso="rules.ver")
    Q("auditReplay", _q_audit_replay, tipo="[AuditEvent]", args={"comId": "ID"},
      servicio="audit_replay.reconstruir", permiso="auditoria.ver")
    Q("workflow", _q_workflow, tipo="[WorkflowInstance]", servicio="workflow.listar_instancias",
      permiso="workflow.ver")
    Q("commerce", _q_commerce, tipo="CommerceDescriptor", servicio="comercio_digital.descriptor",
      permiso="comercio.ver")
    # Preparadas (declaradas; se cablearán a su servicio de dominio, nunca a SQL desde GraphQL)
    for nombre, tipo, serv in [
        ("empresas", "[Company]", "empresa.servicio"),
        ("tiendas", "[Store]", "identidad.tiendas"),
        ("usuarios", "[User]", "usuario.servicio"),
        ("clientes", "[Customer]", "clientes.servicio"),
        ("proveedores", "[Supplier]", "compras.proveedores"),
        ("stock", "[StockItem]", "inventario.servicio"),
        ("productos", "[Product]", "catalogo.servicio"),
        ("pedidos", "[Order]", "ventas.pedidos"),
        ("facturas", "[Invoice]", "facturacion.servicio"),
    ]:
        Q(nombre, _prep(serv), tipo=tipo, servicio=serv, permiso=f"{nombre}.ver")


__all__ = ["registrar_todo"]
