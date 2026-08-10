"""
Tests · Portal Web para Empleados / Back Office (Fase WEB-04). Arquitectura PREPARADA: navegación declarativa,
acceso que COMPONE RBAC+Entitlements+licencia+rol (sin permisos propios), layout/sidebar/navbar, router REST
montado en la API existente (reutiliza requiere_auth/JWT/tenant). Multiempresa; sin negocio nuevo.
"""

import pytest


# ── Navegación: secciones declarativas ────────────────────────────────────────
def test_navegacion_secciones():
    from src.portal_web import navegacion
    claves = {s["clave"] for s in navegacion.SECCIONES}
    esperadas = {"inicio", "clientes", "articulos", "pedidos", "encargos", "reservas", "stock",
                 "reabastecimiento", "logistica", "caja", "rrhh", "documentos", "configuracion"}
    assert esperadas <= claves
    for s in navegacion.SECCIONES:
        assert {"clave", "titulo", "icono", "servicio", "acciones"} <= set(s)
    d = navegacion.descriptor()
    assert d["modulo"] == "portal_web" and d["tipo"] == "back_office"
    assert "canal_web" in d["independiente_de"] and d["no_por"] == "dominio"


# ── Acceso: compone RBAC + Entitlements + licencia + rol (no permisos propios) ─
def test_acceso_rol_configuracion():
    from src.portal_web import acceso, navegacion
    conf = navegacion.seccion("configuracion")
    # Sólo roles admin/gerente/superadmin ven Configuración.
    assert acceso.puede_ver(conf, {"perfil": "ADMINISTRADOR"}) is True
    assert acceso.puede_ver(conf, {"perfil": "OPERARIO"}) is False


def test_acceso_entitlement_logistica(monkeypatch):
    from src.portal_web import acceso, navegacion
    log = navegacion.seccion("logistica")   # capability = multi_tienda.enabled
    from src.services.saas import entitlements
    # Con la capability → visible; sin ella → oculta. Se controla vía el resolver central (no propio).
    monkeypatch.setattr(entitlements, "has", lambda cap, id_empresa=None: cap != "multi_tienda.enabled")
    assert acceso.puede_ver(log, {"perfil": "GERENTE"}) is False
    monkeypatch.setattr(entitlements, "has", lambda cap, id_empresa=None: True)
    assert acceso.puede_ver(log, {"perfil": "GERENTE"}) is True


def test_secciones_visibles_legacy():
    from src.portal_web import acceso
    # Empresa sin licencia (legacy) → módulos habilitados; un ADMIN ve todo (incluida configuración).
    vis = {s["clave"] for s in acceso.secciones_visibles({"perfil": "ADMINISTRADOR"}, "PW-LEGACY")}
    assert {"inicio", "clientes", "articulos", "pedidos", "stock", "documentos", "configuracion"} <= vis
    # Un OPERARIO NO ve configuración (rol), pero sí las operativas.
    vis_op = {s["clave"] for s in acceso.secciones_visibles({"perfil": "OPERARIO"}, "PW-LEGACY")}
    assert "configuracion" not in vis_op and "pedidos" in vis_op


# ── Layout / sidebar / navbar ─────────────────────────────────────────────────
def test_layout_estructura():
    from src.portal_web import layout
    lay = layout.layout({"id": 1, "nombre": "Ana", "perfil": "GERENTE"}, "PW-1", id_tienda=3)
    assert lay["tipo"] == "back_office"
    assert lay["navbar"]["id_empresa"] == "PW-1" and lay["navbar"]["id_tienda"] == 3
    assert "secciones" in lay["sidebar"] and lay["contenido"]["reutilizable_movil"] is True


# ── Sesión: reutiliza auth existente (sin sistema propio) ─────────────────────
def test_sesion_reutiliza_auth():
    from src.portal_web import sesion
    m = sesion.metodos_autenticacion()
    assert m["login"] and m["fuente_tenant"] == "token"      # tenant del token, nunca dominio
    assert set(m) >= {"jwt", "mfa", "webauthn"}


# ── Router REST montado en la API existente (reutiliza requiere_auth) ─────────
def test_router_portal_montado():
    pytest.importorskip("flask")
    from src.api import crear_api
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(crear_api("v1"))
    cli = app.test_client()

    # Público: descriptor + live (sin exponer negocio).
    assert cli.get("/api/v1/portal/live").status_code == 200
    d = cli.get("/api/v1/portal/descriptor")
    assert d.status_code == 200 and d.get_json()["modulo"] == "portal_web"
    # Navegación exige JWT (reutiliza requiere_auth): sin token → 401.
    assert cli.get("/api/v1/portal/navegacion").status_code == 401
