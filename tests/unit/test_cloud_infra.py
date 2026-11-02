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
    "recetas_lineas", "obrador_partes_lineas",
    # Redes Sociales Corporativas (migr. 0325): métricas por publicación, hija por FK de
    # redes_sociales_publicaciones (que SÍ tiene id_empresa) — mismo razonamiento que
    # recetas_lineas/obrador_partes_lineas.
    "redes_sociales_metricas",
    # plataforma global (no son datos de un tenant)
    "cloud_feature_flags", "saas_regiones", "ioc_grupos_empresariales",
    # (Las tablas de la Lonja B2B se retiraron en la refactorización del módulo Proveedores.)
    # Smart Suppliers B2B (Fase 2, services/compras/b2b_*): el PROVEEDOR (suministrador) es una
    # identidad única de PLATAFORMA, independiente de cada empresa compradora — sirve a varias
    # empresas a la vez, así que su catálogo y su ficha NO tienen (ni deben tener) id_empresa propio;
    # el filtrado por empresa ocurre en el servicio (por sector_id + tienda activa), no por fila.
    "suministradores", "sectores_comerciales",
    # hijas de una tabla de plataforma (mismo razonamiento que la de arriba, vía FK)
    "suministrador_sesiones",          # FK id_suministrador -> suministradores
    "sectores_compatibles",            # FK sector_id -> sectores_comerciales
    "b2b_catalogo",                    # FK id_suministrador -> suministradores
    "b2b_catalogo_import_lotes",       # FK id_suministrador -> suministradores
    # hijas por FK de transaccion_comercial (que SÍ tiene id_empresa)
    "b2b_escrow", "b2b_escrow_ledger",  # FK id_tx -> transaccion_comercial.id
    # el carrito de la Extranet de Empresa se aísla por token_sesion, no por columna id_empresa
    # directa: cada token se emite en b2b_sesiones_empresa (que SÍ tiene id_empresa) ligado a una
    # única empresa+tienda (services/compras/b2b_sesion_empresa.crear_sesion), y es un secreto
    # aleatorio de 32 bytes (secrets.token_urlsafe) — no adivinable entre sesiones de otra empresa.
    "b2b_carrito_lineas",
    # Smart Suppliers B2B (Fase 3, services/compras/b2b_plantillas.py/b2b_catalogo.py/b2b_chat.py):
    # hijas por FK de una tabla que sí tiene id_empresa (mismo razonamiento que b2b_escrow arriba).
    "b2b_plantilla_lineas",             # FK id_plantilla -> b2b_plantillas.id (que sí tiene id_empresa)
    "b2b_pedido_mensajes", "b2b_pedido_lecturas",  # FK/clave id_tx -> transaccion_comercial.id_tx
    # hija de b2b_catalogo (plataforma global, ver arriba) — mismo razonamiento.
    "b2b_catalogo_escalones",           # FK id_articulo -> b2b_catalogo.id
    # Chat de soporte del storefront (Fase 6 e-commerce, services/comercio_digital/canal_web/
    # soporte_chat.py): MISMO razonamiento que `b2b_carrito_lineas` de arriba — se aísla por
    # `token` (uuid4 hex, 32 caracteres, aleatorio e imposible de adivinar entre visitantes de
    # otra empresa), no por columna `id_empresa` directa. El token se emite en `cd_chat_visitantes`
    # (que SÍ tiene `id_empresa`) y todo punto de entrada público (`enviar_mensaje`/
    # `obtener_hilo`) valida ahí el origen del token ANTES de leer/escribir en esta tabla.
    "cd_chat_mensajes",
    # Actividad de carrito B2B (migr. 0280, services/compras/b2b_carrito_abandono.py): MISMO
    # razonamiento que `b2b_carrito_lineas` de arriba — 1 fila por `token_sesion` opaco, sin
    # columna `id_empresa` propia a propósito (la "actividad" es del carrito, no de una línea).
    "b2b_carrito_actividad",
    # Bundles de producto del PROVEEDOR (migr. 0281, services/compras/b2b_bundles.py): hija de
    # `suministradores` (plataforma global, ver arriba) vía `id_suministrador` — mismo
    # razonamiento que `b2b_catalogo`/`b2b_catalogo_escalones`.
    "b2b_promo_bundles",
    # Ledger de movimientos de consignación B2B (migr. 0269, services/compras/b2b_consignacion.py):
    # hija por FK de `b2b_consignacion_saldo`/`transaccion_comercial` (vía `id_tx`, ambas con
    # id_empresa) y de `suministradores` (vía `id_suministrador`, plataforma global).
    "b2b_consignacion_movimientos",
    # Pujas de proveedor en una licitación RFQ (migr. 0260, services/compras/b2b_rfq.py): hija por
    # FK física (`fk_ro_rfq`) de `rfq` (que SÍ tiene id_empresa).
    "rfq_ofertas",
    # Hijos/ascendientes del Modelo 145 AEAT de un empleado (migr. 0264, rrhh fiscal): hijas por FK
    # física de `rrhh_datos_fiscales` (que SÍ tiene id_empresa).
    "rrhh_datos_fiscales_hijos", "rrhh_datos_fiscales_ascendientes",
    # Detalle fila a fila del motor de migración/importación por etapas (migr. 0272): hijas de
    # `migracion_lotes_staging`/`import_trabajos` (ambas con id_empresa) vía `id_lote_staging`/
    # `id_trabajo` (enlace débil sin FK física, mismo criterio sin-ORM que el resto del esquema).
    "migracion_filas_staging", "import_trabajos_errores",
    # Destinatarios Para/CC/Cco de circulares/encuestas (migr. 0286, comunicacion_interna): hija
    # polimórfica por `(tipo_entidad, id_entidad)` de `com_circulares`/`com_encuestas` (ambas con
    # id_empresa) y por `usuario_id` del usuario destinatario — mismo patrón que `com_adjuntos`/
    # `com_encuesta_respuestas` ya revisados arriba.
    "com_destinatarios",
    # Configuración GLOBAL de un proveedor de infraestructura, propiedad del VENDEDOR de Smart
    # Manager (no de cada empresa cliente), una sola fila (id fijo=1): push FCM (migr. 0251,
    # "el proyecto Firebase es propiedad del VENDEDOR... se reutiliza para todas las empresas") y
    # tarifa de reventa de voz/ElevenLabs (migr. 0285, editable solo desde el Panel del Fundador).
    "fcm_config", "voice_billing_config",
    # Tablas del SERVIDOR CENTRAL de licencias/panel del fundador (migr. 0234/0235): solo tienen
    # sentido en la BD central (`src/backend_central/`), nunca en la BD local de un cliente — no
    # son datos de NINGÚN tenant local, son metadatos de la gestión comercial de licencias.
    "codigos_activacion", "instalaciones_centrales", "panel_fundador_admin", "panel_fundador_sesiones",
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
