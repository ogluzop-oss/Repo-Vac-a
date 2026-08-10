"""
Tests · Canal Web · Dominios (propio / subdominio / compra vía Adapter).

Verifica las 3 modalidades de publicación, el Adapter Pattern de registradores (provider-agnostic +
simulado degradable), la generación única de subdominios, la compra + asignación + DNS/HTTPS
(preparado), el cambio/renovación posterior, RBAC, eventos y multiempresa. Reutiliza canal_web/
conexiones/Event Bus. Sin motores paralelos.
"""

import pytest

from src.services.comercio_digital import canal_web, dominios
from src.services.comercio_digital.canal_web import gestion_dominios as DOM

pytestmark = pytest.mark.db

EMP = "T-CWD"
GER = {"perfil": "GERENTE", "id": "g"}


@pytest.fixture()
def limpia(db):
    def _b():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM cd_canal_dominios WHERE id_empresa=%s", (EMP,))
            cur.execute("DELETE FROM cd_canal_web WHERE id_empresa=%s", (EMP,))
            cur.execute("DELETE FROM cd_conexiones WHERE id_empresa=%s", (EMP,))
            conn.commit()
    _b()
    yield
    _b()


# ── Adapter Pattern registradores ─────────────────────────────────────────────
def test_adapter_provider_agnostic():
    d = dominios.descriptor()
    assert d["por_defecto"] == "simulado" and d["provider_agnostic"] is True
    assert {"cloudflare", "namecheap", "porkbun", "ovh", "ionos", "godaddy"} <= set(d["preparados"])
    ad = dominios.adaptador()
    from src.services.comercio_digital.dominios.adaptador import RegistrarAdapter
    assert isinstance(ad, RegistrarAdapter)
    props = ad.buscar("miempresa")
    assert props and all({"dominio", "disponible", "precio"} <= set(p) for p in props)


# ── Opción 1: dominio propio ──────────────────────────────────────────────────
def test_crear_dominio_propio(limpia):
    r = canal_web.crear({"nombre": "Mía"}, publicacion={"tipo": "propio", "dominio": "miempresa.com"},
                        id_empresa=EMP, usuario=GER)
    assert r["ok"] and r["tipo"] == "propio" and r["dominio"] == "miempresa.com"
    act = DOM.dominio_activo(EMP)
    assert act and act["dominio"] == "miempresa.com" and act["tipo"] == "propio"


def test_dominio_propio_invalido(limpia):
    r = canal_web.crear({"nombre": "X"}, publicacion={"tipo": "propio", "dominio": "no valido"},
                        id_empresa=EMP, usuario=GER)
    assert r["ok"] is False and "inválido" in r.get("motivo", "")


# ── Opción 2: subdominio gratuito (único) ─────────────────────────────────────
def test_crear_subdominio_unico(limpia):
    r1 = canal_web.crear({"nombre": "Empresa"}, publicacion={"tipo": "subdominio", "nombre": "Empresa"},
                         id_empresa=EMP, usuario=GER)
    assert r1["ok"] and r1["tipo"] == "subdominio" and r1["dominio"] == "empresa.smartmanager.ai"
    # Un segundo canal del mismo nombre en OTRA empresa obtiene -2 (dominio único global).
    r2 = canal_web.crear({"nombre": "Empresa"}, publicacion={"tipo": "subdominio", "nombre": "Empresa"},
                         id_empresa="T-CWD-2", usuario=GER)
    assert r2["dominio"] == "empresa-2.smartmanager.ai"
    with __import__("src.db.conexion", fromlist=["obtener_conexion"]).obtener_conexion() as c:
        cur = c.cursor(); cur.execute("DELETE FROM cd_canal_dominios WHERE id_empresa='T-CWD-2'")
        cur.execute("DELETE FROM cd_canal_web WHERE id_empresa='T-CWD-2'"); c.commit()


# ── Opción 3: comprar dominio vía Adapter + publicación automática ────────────
def test_comprar_dominio_y_publica(limpia):
    props = canal_web.buscar_dominios("comprita", id_empresa=EMP, usuario=GER)
    assert props["ok"] and props["resultados"]
    disp = next(p["dominio"] for p in props["resultados"] if p["disponible"])
    r = canal_web.crear({"nombre": "Comprita"},
                        publicacion={"tipo": "comprado", "dominio": disp}, id_empresa=EMP, usuario=GER)
    assert r["ok"] and r["tipo"] == "comprado" and r["dominio"] == disp
    act = DOM.dominio_activo(EMP)
    assert act and act["tipo"] == "comprado" and act["referencia"] and act["precio"]
    # DNS + HTTPS quedan configurados (simulado) tras la compra.
    assert act["estado_dns"] in ("configurado", "manual") and act["estado_https"] in ("activo", "pendiente")


# ── DNS / HTTPS / cambio / renovación ─────────────────────────────────────────
def test_cambio_dominio_posterior(limpia):
    canal_web.crear({"nombre": "T"}, publicacion={"tipo": "subdominio", "nombre": "T"},
                    id_empresa=EMP, usuario=GER)
    r = canal_web.cambiar_dominio("nuevodominio.com", id_empresa=EMP, usuario=GER)
    assert r["ok"] and r["dominio"] == "nuevodominio.com"
    assert DOM.dominio_activo(EMP)["dominio"] == "nuevodominio.com"
    # El dominio activo se refleja en el canal.
    assert canal_web.estado(EMP)["dominio"] == "nuevodominio.com"


def test_renovar_dominio(limpia):
    canal_web.crear({"nombre": "T"}, publicacion={"tipo": "propio", "dominio": "reno.com"},
                    id_empresa=EMP, usuario=GER)
    r = canal_web.renovar_dominio("reno.com", id_empresa=EMP, usuario=GER)
    assert r["ok"] and r["fecha_expiracion"]


# ── RBAC + eventos + panel ────────────────────────────────────────────────────
def test_rbac_comprar_denegado(limpia):
    r = canal_web.comprar_dominio("x.com", id_empresa=EMP, usuario={"perfil": "SIN", "id": "x"})
    assert r.get("error") == "forbidden" and r.get("permiso") == "canal_web.dominios.comprar"


def test_panel_incluye_dominios(limpia):
    canal_web.crear({"nombre": "T"}, publicacion={"tipo": "subdominio", "nombre": "T"},
                    id_empresa=EMP, usuario=GER)
    p = canal_web.panel(EMP)
    assert "dominio_activo" in p and "dominios" in p
    assert p["metricas"]["subdominios"] >= 1
    assert p["dominio_activo"]["tipo"] == "subdominio"


def test_eventos_dominios_catalogados():
    from src.services import eventbus
    cat = set((eventbus.catalogo() or {}).keys())
    assert {"CanalWebDominioBuscado", "CanalWebDominioComprado", "CanalWebSubdominioCreado",
            "CanalWebDominioAsignado", "CanalWebDNSConfigurado", "CanalWebHTTPSConfigurado"} <= cat
    from src.services.seguridad.catalogo import CATALOGO
    assert {"canal_web.dominios.ver", "canal_web.dominios.comprar", "canal_web.dominios.renovar",
            "canal_web.dominios.transferir", "canal_web.dominios.administrar"} <= set(CATALOGO)
