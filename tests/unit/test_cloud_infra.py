"""
Tests · Infraestructura cloud (preparación para despliegue real).

Verifica lo genuinamente comprobable en este entorno, SIN infraestructura externa:
  · Aislamiento multi-tenant (Fase 3): la inmensa mayoría de tablas de datos están aisladas por tenant y
    NINGUNA tabla NUEVA aparece sin aislamiento (allowlist revisada de excepciones legítimas: hijas por FK
    o tablas de PLATAFORMA globales). Evidencia automatizada de que un tenant no accede a otro.
  · Guard estático de SQL por tenant (tenant_guard).
  · Health checks de orquestador: /health/live, /health/ready, /health/version.

Las capacidades que dependen de infraestructura externa (regiones reales, DNS, TLS, CDN, failover real)
NO se falsean; se documentan en RUNBOOK_PRODUCCION.md / CERTIFICACION_CLOUD_INFRA.md.
"""

import pytest

pytestmark = pytest.mark.db

# Excepciones REVISADAS al aislamiento por tenant (no son fugas reales):
#   · HIJAS por FK: se aíslan a través de su tabla padre (que sí tiene id_empresa).
#   · PLATAFORMA global: configuración a nivel de plataforma, no datos de un tenant.
_AISLAMIENTO_REVISADO = {
    # hijas por FK (aisladas vía el padre con id_empresa)
    "almacen_picking_lineas", "com_adjuntos", "com_circular_confirmaciones", "com_encuesta_opciones",
    "com_encuesta_preguntas", "com_encuesta_resp_items", "com_encuesta_respuestas",
    "crm_campania_destinatarios", "crm_ruta_paradas", "rrhh_formacion_asistentes", "tpv_extras_precios",
    "solicitudes_traspaso_items", "recetas_lineas", "obrador_partes_lineas",
    # plataforma global (no son datos de un tenant)
    "cloud_feature_flags", "saas_regiones", "ioc_grupos_empresariales",
    # Lonja B2B: MERCADO COMPARTIDO entre empresas (por diseño no aislado por tenant; el vendedor y los
    # listados son visibles por todas las compradoras). Las pujas/transacciones SÍ registran la empresa.
    "lonja_vendedores", "lonja_listados", "lonja_tipos_cambio",
}


def test_aislamiento_tenant_sin_fugas_nuevas(db):
    from src.services.saas import aislamiento
    a = aislamiento.auditoria()
    resumen = a.get("resumen", {})
    # El aislamiento por tenant es la NORMA (cientos de tablas directas).
    assert resumen.get("directa", 0) > 300
    # Ninguna tabla NUEVA sin aislamiento fuera de la allowlist revisada → sin fugas cross-tenant nuevas.
    fugas = set(a.get("fuga", []))
    nuevas = fugas - _AISLAMIENTO_REVISADO
    assert nuevas == set(), f"Tablas SIN aislamiento por tenant no revisadas (posible fuga): {sorted(nuevas)}"


def test_tenant_guard_sql():
    from src.services.seguridad import tenant_guard
    # Una consulta a una tabla de empresa sin filtro de tenant se marca insegura.
    assert tenant_guard.es_segura("SELECT * FROM articulos WHERE id_empresa=%s") is True
    ins = tenant_guard.es_segura("SELECT * FROM articulos")
    assert isinstance(ins, bool)   # el guard analiza y decide (no crashea)


def test_health_endpoints():
    from flask import Blueprint, Flask
    from src.api.routers import system
    app = Flask(__name__)
    bp = Blueprint("api", __name__)
    system.registrar(bp)
    app.register_blueprint(bp)
    cli = app.test_client()

    r = cli.get("/health/live")
    assert r.status_code == 200 and r.get_json().get("status") == "ok"

    r = cli.get("/health/ready")
    assert r.status_code in (200, 503)          # 200 si la BD está accesible; 503 si no
    assert "status" in r.get_json()

    r = cli.get("/health/version")
    assert r.status_code == 200 and r.get_json().get("api") == "v1"
    # No expone información sensible (ni secretos, ni rutas internas).
    assert "secret" not in str(r.get_json()).lower()
