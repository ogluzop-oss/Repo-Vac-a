"""
Tests · Módulo Canal Web (creación / publicación / administración de la tienda online).

Verifica el servicio `comercio_digital.canal_web`: estado (¿existe?), generación automática (endpoint +
token cifrado vía conexiones/Secret Manager, sin que el usuario los introduzca), config de negocio
(incluidos campos futuros almacenados sin lógica), publicar/despublicar/regenerar/sincronizar, métricas
(reutilizan publicaciones/pedidos/transacciones) y RBAC. Sin motores paralelos.
"""

import pytest

from src.services.comercio_digital import canal_web

pytestmark = pytest.mark.db

EMP = "T-CW"
GER = {"perfil": "GERENTE", "id": "g"}


@pytest.fixture()
def limpia(db):
    def _b():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM cd_canal_web WHERE id_empresa=%s", (EMP,))
            cur.execute("DELETE FROM cd_conexiones WHERE id_empresa=%s", (EMP,))
            conn.commit()
    _b()
    yield
    _b()


def test_estado_inicial_no_configurado(limpia):
    assert canal_web.existe(EMP) is False
    e = canal_web.estado(EMP)
    assert e["estado"] == "no_configurado" and e["existe"] is False


def test_crear_genera_endpoint_y_token_cifrado(limpia):
    cfg = {"nombre": "Mi Tienda", "dominio": "mitienda.example.com", "idioma": "es", "moneda": "EUR",
           "comercial": {"mostrar_stock": True, "permitir_compra": True, "click_collect": True},
           # Campos preparados para el futuro (se almacenan, sin lógica operativa todavía):
           "recogida": {"permitir": True, "tiempo_max_h": 24, "mensaje": "Recoge en 24h",
                        "horario": "L-V 9-20", "capacidad_por_tienda": 50, "puntos": ["Tienda 1"]}}
    r = canal_web.crear(cfg, id_empresa=EMP, usuario=GER)
    assert r["ok"] and r["estado"] == "publicado" and r["dominio"] == "mitienda.example.com"
    assert canal_web.existe(EMP) is True
    # La conexión "web" se creó automáticamente con credenciales CIFRADAS (el usuario no las introdujo).
    from src.services.comercio_digital import conexiones
    conf = conexiones.obtener("web", id_empresa=EMP)
    assert conf and conf.get("endpoint_base") == "https://mitienda.example.com"
    cred = conexiones.credenciales("web", id_empresa=EMP)
    assert cred.get("api_key")                                   # token generado y descifrable


def test_config_negocio_persiste_campos_futuros(limpia):
    cfg = {"nombre": "T", "recogida": {"tiempo_max_h": 24, "capacidad_por_tienda": 30}}
    canal_web.crear(cfg, id_empresa=EMP, usuario=GER)
    e = canal_web.estado(EMP)
    assert e["config_negocio"]["recogida"]["tiempo_max_h"] == 24
    assert e["config_negocio"]["recogida"]["capacidad_por_tienda"] == 30


def test_actualizar_config_fusiona(limpia):
    canal_web.crear({"nombre": "T", "color": "#000"}, id_empresa=EMP, usuario=GER)
    r = canal_web.actualizar_config({"color": "#00FFC6", "idioma": "en"}, id_empresa=EMP, usuario=GER)
    assert r["ok"] and r["config_negocio"]["color"] == "#00FFC6" and r["config_negocio"]["idioma"] == "en"
    assert r["config_negocio"]["nombre"] == "T"                  # no se pierde lo anterior


def test_publicar_despublicar_regenerar(limpia):
    canal_web.crear({"nombre": "T", "dominio": "t.example.com"}, id_empresa=EMP, usuario=GER)
    assert canal_web.despublicar(id_empresa=EMP, usuario=GER)["estado"] == "despublicado"
    assert canal_web.publicar(id_empresa=EMP, usuario=GER)["estado"] == "publicado"
    from src.services.comercio_digital import conexiones
    tok1 = conexiones.credenciales("web", id_empresa=EMP).get("api_key")
    assert canal_web.regenerar(id_empresa=EMP, usuario=GER)["ok"] is True
    tok2 = conexiones.credenciales("web", id_empresa=EMP).get("api_key")
    assert tok1 and tok2 and tok1 != tok2                        # token regenerado


def test_sincronizar_degradable(limpia):
    canal_web.crear({"nombre": "T"}, id_empresa=EMP, usuario=GER)
    r = canal_web.sincronizar(id_empresa=EMP, usuario=GER)
    assert r["ok"] is True                                        # degradable: no rompe
    assert canal_web.estado(EMP).get("ultima_sync") is not None


def test_metricas_y_panel(limpia):
    canal_web.crear({"nombre": "T"}, id_empresa=EMP, usuario=GER)
    p = canal_web.panel(EMP)
    assert "metricas" in p and {"productos_publicados", "pedidos_pendientes",
                                "reservas_activas"} <= set(p["metricas"])


def test_rbac_crear_denegado(limpia):
    r = canal_web.crear({"nombre": "T"}, id_empresa=EMP, usuario={"perfil": "SIN", "id": "x"})
    assert r.get("error") == "forbidden" and r.get("permiso") == "canal_web.crear"


def test_descriptor_y_rbac_catalogo():
    d = canal_web.descriptor()
    assert d["motor_nuevo"] is False and d["secretos_en_claro"] is False
    assert "conexiones (Secret Manager)" in d["reutiliza"]
    from src.services.seguridad.catalogo import CATALOGO
    assert {"canal_web.ver", "canal_web.crear", "canal_web.administrar"} <= set(CATALOGO)


def test_presencia_canal_web_editor_unico(limpia, db):
    """Rearquitectura CD · Fase 2: Canal Web es el ÚNICO editor de la MARCA/PRESENCIA de la web propia,
    reutilizando `web_tienda` (la MISMA fila `web_config` que sirve el storefront). Sin motor nuevo."""
    from src.db import web_tienda
    try:
        r = canal_web.guardar_presencia(id_empresa=EMP, usuario=GER, activa=1, nombre="Tienda F2",
                                        color="#101010", moneda="USD", logo_url="http://x/l.png",
                                        descripcion="slogan")
        assert r["ok"] is True
        cp = canal_web.config_presencia(EMP)
        assert cp["nombre"] == "Tienda F2" and cp["color"] == "#101010" and cp["moneda"] == "USD"
        # Fuente ÚNICA compartida con el storefront (web_config vía web_tienda).
        wc = web_tienda.obtener_config(EMP)
        assert wc["nombre"] == "Tienda F2" and int(wc["activa"]) == 1
    finally:
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM web_config WHERE id_empresa=%s", (EMP,))
            conn.commit()


def test_presencia_rbac_denegado(limpia):
    r = canal_web.guardar_presencia(id_empresa=EMP, usuario={"perfil": "SIN", "id": "x"}, nombre="X")
    assert r.get("error") == "forbidden" and r.get("permiso") == "canal_web.administrar"


def test_web_config_fuente_unica_sincronizada(limpia, db):
    """Rearquitectura CD · Fase 4: `web_config` es la fuente ÚNICA de marca/activación; las operaciones
    del canal (crear/publicar/despublicar/actualizar) la mantienen sincronizada, sin duplicidad con
    `config_negocio`. En particular DESPUBLICAR retira el escaparate (activa=0)."""
    from src.db import web_tienda
    try:
        canal_web.crear({"nombre": "T4"}, publicacion={"tipo": "subdominio", "nombre": "t4sync"},
                        id_empresa=EMP, usuario=GER)
        wc = web_tienda.obtener_config(EMP)
        assert wc["nombre"] == "T4" and int(wc["activa"]) == 1
        canal_web.despublicar(id_empresa=EMP, usuario=GER)
        assert int(web_tienda.obtener_config(EMP)["activa"]) == 0
        canal_web.publicar(id_empresa=EMP, usuario=GER)
        assert int(web_tienda.obtener_config(EMP)["activa"]) == 1
        canal_web.actualizar_config({"nombre": "T4 v2"}, id_empresa=EMP, usuario=GER)
        assert web_tienda.obtener_config(EMP)["nombre"] == "T4 v2"
    finally:
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM web_config WHERE id_empresa=%s", (EMP,))
            cur.execute("DELETE FROM cd_canal_dominios WHERE id_empresa=%s", (EMP,))
            conn.commit()
