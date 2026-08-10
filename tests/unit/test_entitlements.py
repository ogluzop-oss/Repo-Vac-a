"""
Tests · Entitlements / Capabilities (Fase 16). Verifica: matriz central BASIC/PRO/PLUS, PLUS=ilimitado, legacy
sin restricción, cuotas + OVER_LIMIT no destructivo, require/auditoría, aislamiento multi-tenant, y
compatibilidad hacia atrás de las APIs de licensing. Sin AWS, sin despliegue.
"""

import pytest

pytestmark = pytest.mark.db


@pytest.fixture()
def limpia(db):
    def _b():
        with db.obtener_conexion() as c:
            cur = c.cursor()
            cur.execute("DELETE FROM empresa_licencia WHERE id_empresa LIKE 'ENT-%%'")
            c.commit()
    _b()
    yield
    _b()


def _plan(id_empresa, codigo, estado="activa"):
    from src.services.saas import licensing as L
    L.asignar_plan(id_empresa, codigo, estado=estado)


# ── Matriz / PLUS ilimitado ───────────────────────────────────────────────────
def test_matriz_plus_todo_ilimitado():
    from src.services.saas import entitlements as E
    m = E.matriz()
    assert all(v is True for k, v in m["PLUS"].items() if k in E.BOOLEANS)
    assert all(m["PLUS"][k] is E.UNLIMITED for k in E.LIMITES)


# ── BASIC ─────────────────────────────────────────────────────────────────────
def test_basic_restringido(limpia):
    from src.services.saas import entitlements as E
    _plan("ENT-BASIC", "BASIC")
    assert E.has("tpv.avanzado", "ENT-BASIC") is False
    assert E.has("api.access", "ENT-BASIC") is False
    assert E.has("ia.forecasting.ml", "ENT-BASIC") is False
    assert E.limit("usuarios.max", "ENT-BASIC") == 5
    assert E.limit("tiendas.max", "ENT-BASIC") == 1
    assert E.limit("almacenes.max", "ENT-BASIC") == 1
    assert E.limit("correo.buzones.max", "ENT-BASIC") == 1


# ── PRO ───────────────────────────────────────────────────────────────────────
def test_pro_capacidades(limpia):
    from src.services.saas import entitlements as E
    _plan("ENT-PRO", "PRO")
    assert E.has("tpv.avanzado", "ENT-PRO") is True
    assert E.has("ia.forecasting.ml", "ENT-PRO") is True
    assert E.has("api.access", "ENT-PRO") is True
    assert E.has("realtime.distributed", "ENT-PRO") is True
    # Reservado a PLUS:
    assert E.has("ia.retraining", "ENT-PRO") is False
    assert E.has("mobile.app", "ENT-PRO") is False
    assert E.limit("usuarios.max", "ENT-PRO") == 50
    assert E.limit("tiendas.max", "ENT-PRO") == 10


# ── PLUS = acceso total ───────────────────────────────────────────────────────
def test_plus_acceso_total(limpia):
    from src.services.saas import entitlements as E
    _plan("ENT-PLUS", "PLUS")
    for cap in E.BOOLEANS:
        assert E.has(cap, "ENT-PLUS") is True, cap
    for cap in E.LIMITES:
        assert E.limit(cap, "ENT-PLUS") is E.UNLIMITED, cap
        assert E.puede_crear(cap, "ENT-PLUS") is True     # ilimitado → siempre se puede crear


# ── Legacy sin licencia = sin restricción ─────────────────────────────────────
def test_legacy_sin_restriccion(limpia):
    from src.services.saas import entitlements as E
    assert E.plan_actual("ENT-LEGACY") == "PLUS"           # sin licencia → acceso total (comportamiento actual)
    assert E.has("api.access", "ENT-LEGACY") is True
    assert E.limit("usuarios.max", "ENT-LEGACY") is E.UNLIMITED


# ── OVER_LIMIT (downgrade) no destructivo ─────────────────────────────────────
def test_over_limit_clasificacion():
    from src.services.saas import entitlements as E
    assert E._clasificar(3, 5)["estado"] == "OK" and E._clasificar(3, 5)["disponible"] == 2
    assert E._clasificar(5, 5)["estado"] == "AT_LIMIT" and E._clasificar(5, 5)["ok"] is False
    over = E._clasificar(20, 5)                              # downgrade PRO(20 usuarios) → BASIC(5)
    assert over["estado"] == "OVER_LIMIT" and over["ok"] is False and over["disponible"] == 0
    assert E._clasificar(99, E.UNLIMITED)["estado"] == "OK"  # PLUS


def test_estado_cuota_no_escribe(limpia):
    from src.services.saas import entitlements as E
    _plan("ENT-Q", "BASIC")
    est = E.estado_cuota("usuarios.max", "ENT-Q")           # empresa nueva → usado 0
    assert est["limite"] == 5 and est["estado"] == "OK" and est["ok"] is True
    # estado_cuota es de SOLO LECTURA: repetir no cambia nada.
    assert E.estado_cuota("usuarios.max", "ENT-Q")["usado"] == est["usado"]


# ── require + auditoría ───────────────────────────────────────────────────────
def test_require_denegado(limpia):
    from src.services.saas import entitlements as E
    from src.services.saas.licensing import LicenciaError
    _plan("ENT-R", "BASIC")
    with pytest.raises(LicenciaError):
        E.require("api.access", id_empresa="ENT-R")        # BASIC no incluye api.access → deniega + audita
    # PLUS no deniega ninguna capacidad:
    _plan("ENT-R2", "PLUS")
    assert E.require("api.access", id_empresa="ENT-R2") is True


# ── Multi-tenant aislado ──────────────────────────────────────────────────────
def test_multitenant_aislado(limpia):
    from src.services.saas import entitlements as E
    _plan("ENT-A", "BASIC")
    _plan("ENT-B", "PLUS")
    assert E.has("api.access", "ENT-A") is False            # A no usa el plan de B
    assert E.has("api.access", "ENT-B") is True
    assert E.limit("usuarios.max", "ENT-A") == 5
    assert E.limit("usuarios.max", "ENT-B") is E.UNLIMITED


# ── Compatibilidad hacia atrás (APIs antiguas intactas) ───────────────────────
def test_backward_compat_licensing(limpia):
    from src.services.saas import licensing as L
    _plan("ENT-BC", "BASIC")
    # APIs antiguas siguen funcionando:
    assert L.modulo_habilitado("tpv", "ENT-BC") is True     # tpv está en los módulos base de BASIC
    info = L.limite_disponible("max_usuarios", "ENT-BC")
    assert set(info) == {"limite", "usado", "disponible", "ok"}
    # Nuevas fachadas delegan en entitlements:
    assert L.capability_habilitada("api.access", "ENT-BC") is False
    assert L.estado_cuota("usuarios.max", "ENT-BC")["limite"] == 5


def test_validar_operacion_capability(limpia):
    from src.services.saas import licensing as L
    from src.services.saas.licensing import LicenciaError
    _plan("ENT-VO", "BASIC")
    with pytest.raises(LicenciaError):
        L.validar_operacion(capability="api.access", id_empresa="ENT-VO")
    _plan("ENT-VO2", "PLUS")
    assert L.validar_operacion(capability="api.access", id_empresa="ENT-VO2") is True


# ── RBAC ≠ entitlements (coexisten) ───────────────────────────────────────────
def test_snapshot(limpia):
    from src.services.saas import entitlements as E
    _plan("ENT-SNAP", "PRO")
    s = E.snapshot("ENT-SNAP")
    assert s["plan"] == "PRO"
    assert s["booleans"]["tpv.avanzado"] is True and s["booleans"]["mobile.app"] is False
    assert s["limites"]["usuarios.max"] == 50
