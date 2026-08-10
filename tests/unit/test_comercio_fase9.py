"""
Tests PCD · Fase 9 (gobernanza transversal): RBAC · SaaS · CCP · Observabilidad.

Verifica que la PCD se integra con las capacidades Enterprise de gobierno SOLO por la fachada de
capacidades (no motores nuevos, no imports directos), de forma degradable y sin regresión: RBAC
delegado, límites SaaS (cuotas) en creación, comunicación de comercio vía CCP (no bloqueante),
métricas/salud de Observabilidad, y contrato con health.
"""

import inspect

import pytest


def test_rbac_delegado():
    from src.services.comercio_digital import gobernanza as g
    assert g.puede({"perfil": "ADMINISTRADOR"}, "comercio.ver") is True        # sin id → legacy
    assert g.puede({"id": "s", "perfil": "SUPERADMIN"}, "comercio.ver") is True
    # C0.P1: OPERARIO gana comercio.ver (operativa de venta) pero NO comercio.admin → RBAC deniega.
    assert g.puede({"id": "u1", "perfil": "OPERARIO"}, "comercio.ver") is True
    assert g.puede({"id": "u1", "perfil": "OPERARIO"}, "comercio.admin") is False
    with pytest.raises(g.PermisoDenegado):
        g.exigir({"id": "u1", "perfil": "OPERARIO"}, "comercio.admin")


def test_saas_limite_degradable():
    from src.services.comercio_digital import gobernanza as g
    # Sin límite configurado → permitido (no rompe comportamiento existente).
    assert g.dentro_de_limite("cd_publicaciones", id_empresa="T-GOB-A") is True


def test_ccp_y_observabilidad_no_bloquean():
    from src.services.comercio_digital import gobernanza as g
    assert g.notificar_cliente("CommercePagada", id_empresa="T-GOB-A", com_id="tx1",
                               estado="PAGADA") in (True, False)   # degradable, nunca lanza
    assert g.metrica("commerce_test") in (True, False)
    s = g.salud()
    assert s["status"] in ("ok", "degraded") and "capacidades" in s


def test_gobernanza_solo_capacidades_no_motor():
    from src.services.comercio_digital import gobernanza as g
    src = inspect.getsource(g)
    imports = [l for l in src.splitlines() if l.strip().startswith(("import ", "from "))]
    for prohibido in ("from src.services.autorizacion", "from src.services.saas_global",
                      "from src.services.ccp", "from src.services.observabilidad"):
        assert not any(prohibido in l for l in imports), f"gobernanza acopla a {prohibido}"
    assert "from src.platform import capabilities" in src
    d = g.descriptor()
    assert d["es_motor"] is False and "comercio.ver" in d["permisos"]


def test_descriptor_incluye_gobernanza_y_contrato_health():
    from src.services import comercio_digital as cd
    d = cd.descriptor()
    assert "gobernanza" in d and d["gobernanza"]["servicio"] == "cd_gobernanza"
    # El contrato agregado expone health (Observabilidad para el Service Registry).
    agg = [c for c in cd.contratos() if c.nombre == "comercio_digital"][0]
    assert callable(agg.health)
    salud = agg.health()
    assert salud["status"] in ("ok", "degraded")


def test_rest_commerce_rbac_y_sin_regresion():
    import src.api.routers.commerce as commerce
    src = inspect.getsource(commerce)
    assert 'requiere_auth("comercio.ver")' in src        # RBAC cableado
    assert "from src.db" not in src and "SELECT " not in src
    # La lectura NO se bloquea por SaaS (los límites se aplican en creación): sin 403 por feature.
    assert "403" not in src


def test_transaccion_transiciona_con_hook_ccp(db):
    """La transición de transacción sigue funcionando; el hook CCP es no bloqueante (Strangler)."""
    from src.services.comercio_digital import transacciones as tx
    EMP = "T-GOB-TX"
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("transaccion_decisiones", "transaccion_eventos", "transaccion_lineas",
                  "transaccion_comercial"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (EMP,))
        conn.commit()
    tid = tx.crear(id_empresa=EMP, lineas=[{"codigo": "X", "cantidad": 1, "precio_unitario": 1}])
    r = tx.transicionar(tid, "CONFIRMADA", actor="u", id_empresa=EMP)
    assert r["ok"] is True and r["hasta"] == "CONFIRMADA"
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("transaccion_decisiones", "transaccion_eventos", "transaccion_lineas",
                  "transaccion_comercial"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (EMP,))
        conn.commit()


def test_publicacion_respeta_limite_saas(db):
    """crear_publicacion sigue funcionando (límite no alcanzado → permitido, sin regresión)."""
    from src.services.comercio_digital import publicaciones as ppl
    EMP = "T-GOB-PUB"
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM cd_publicaciones WHERE id_empresa=%s", (EMP,))
        conn.commit()
    pid = ppl.crear_publicacion("X", contenido={"nombre": "y"}, id_empresa=EMP)
    assert pid is not None
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE v, p FROM cd_publicaciones p LEFT JOIN cd_publicacion_versiones v "
                    "ON v.id_publicacion=p.id_publicacion WHERE p.id_empresa=%s", (EMP,))
        conn.commit()
