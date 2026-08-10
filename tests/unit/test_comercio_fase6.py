"""
Tests PCD · Fase 6 (RFC-CD-001/002/005): Channel Adapter Framework + Sync Engine.

Verifica SOLO infraestructura: contrato de adaptador (traducción pura, sin lógica de negocio ni
conocimiento del dominio), catálogo de plugins, instalación vía Marketplace (no sistema paralelo),
Outbox idempotente con reintentos, Inbox de deduplicación, push/pull/webhook, reutilización de Event
Bus/Scheduler/Observabilidad por capacidades, y las restricciones (no stock/reservas/availability/
fulfillment/IA).
"""

import inspect
import uuid

import pytest

EMP = "T-SYNC-A"


@pytest.fixture()
def limpio(db):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM cd_sync_outbox WHERE id_empresa=%s", (EMP,))
        cur.execute("DELETE FROM cd_sync_inbox WHERE id_empresa=%s", (EMP,))
        conn.commit()
    # catálogo de adaptadores limpio + adaptador de referencia cargado
    from src.services.comercio_digital import canales
    for c in list(canales.adaptadores()):
        canales.desregistrar(c)
    canales.registrar_adaptador(canales.ReferenceAdapter())
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM cd_sync_outbox WHERE id_empresa=%s", (EMP,))
        cur.execute("DELETE FROM cd_sync_inbox WHERE id_empresa=%s", (EMP,))
        conn.commit()


def test_contrato_adaptador_traduccion_pura():
    from src.services.comercio_digital.canales import adaptador as ad
    a = ad.ReferenceAdapter()
    # Traducción ida y vuelta (identidad de referencia).
    ext = a.traducir_saliente({"sku": "X", "precio": 10})
    assert ext == {"externo": {"sku": "X", "precio": 10}}
    assert a.traducir_entrante(ext) == {"sku": "X", "precio": 10}
    # Publica SOLO su contrato (no registra/descubre/enruta servicios).
    c = a.contrato()
    assert c.nombre == "cd_canal_referencia" and "eventbus" in c.transportes


def test_adaptador_no_conoce_dominio():
    """N5: el adaptador no importa dominio/inventario/workflow/rules/IA/availability/fulfillment."""
    from src.services.comercio_digital.canales import adaptador as ad
    src = inspect.getsource(ad)
    imports = [l for l in src.splitlines() if l.strip().startswith(("import ", "from "))]
    prohibidos = ("availability", "fulfillment", "reservas", "workflow", "rules", "agents_platform",
                  "transacciones", "kardex", "stock")
    for p in prohibidos:
        assert not any(p in l for l in imports), f"adaptador acopla a {p}"


def test_catalogo_plugins_y_marketplace(limpio):
    from src.services.comercio_digital import canales
    assert "referencia" in canales.adaptadores()
    assert isinstance(canales.obtener("referencia"), canales.ChannelAdapter)
    # Instalación SOLO vía Marketplace (capacidad): no hay sistema paralelo en canales.
    src = inspect.getsource(canales)
    assert "marketplace" in src and "capabilities" in src
    d = canales.descriptor()
    assert d["registra_servicios"] is False and d["enruta_servicios"] is False
    assert d["conoce_dominio"] is False and d["mueve_stock"] is False


def test_outbox_idempotente(limpio):
    from src.services.comercio_digital import sync
    k = "idem-" + uuid.uuid4().hex[:8]
    o1 = sync.encolar("referencia", "catalogo.push", {"sku": "X"}, id_empresa=EMP, idempotencia_key=k)
    o2 = sync.encolar("referencia", "catalogo.push", {"sku": "X"}, id_empresa=EMP, idempotencia_key=k)
    assert o1 and o1 == o2                       # dedup: misma clave → misma fila, no se duplica


def test_push_procesa_outbox_via_adaptador(limpio):
    from src.services.comercio_digital import canales, sync
    sync.encolar("referencia", "catalogo.push", {"sku": "A"}, id_empresa=EMP,
                 idempotencia_key="a1")
    res = sync.procesar_salientes("referencia", id_empresa=EMP)
    assert res["enviados"] == 1 and res["errores"] == 0
    # El adaptador (canal simulado) recibió el mensaje traducido: Dominio → Adaptador → Canal.
    buzon = canales.obtener("referencia")._buzon
    assert buzon and buzon[0] == {"externo": {"sku": "A"}}
    # Reprocesar no reenvía (ya no está PENDIENTE).
    assert sync.procesar_salientes("referencia", id_empresa=EMP)["enviados"] == 0


def test_push_sin_adaptador_reintenta(limpio):
    from src.services.comercio_digital import canales, sync
    sync.encolar("inexistente", "x", {"a": 1}, id_empresa=EMP, idempotencia_key="z1")
    res = sync.procesar_salientes("inexistente", id_empresa=EMP)
    assert res["sin_adaptador"] == 1 and res["errores"] == 1
    canales.desregistrar("inexistente")          # nada que limpiar, defensivo


def test_pull_y_deduplicacion(limpio):
    from src.services.comercio_digital import canales, sync
    ref = canales.obtener("referencia")
    ref._buzon = [{"id": "EXT-1", "externo": {"pedido": 1}}, {"id": "EXT-2", "externo": {"pedido": 2}}]
    r1 = sync.recibir_entrantes("referencia", id_empresa=EMP)
    assert r1["recibidos"] == 2 and r1["duplicados"] == 0 and len(r1["comandos"]) == 2
    # Segunda pasada: mismos external_id → todo duplicado (Inbox dedup).
    r2 = sync.recibir_entrantes("referencia", id_empresa=EMP)
    assert r2["recibidos"] == 0 and r2["duplicados"] == 2


def test_webhook_dedup(limpio):
    from src.services.comercio_digital import sync
    w1 = sync.procesar_webhook("referencia", {"externo": {"x": 1}}, id_empresa=EMP, external_id="WH-9")
    w2 = sync.procesar_webhook("referencia", {"externo": {"x": 1}}, id_empresa=EMP, external_id="WH-9")
    assert w1["ok"] and w1["duplicado"] is False
    assert w2["ok"] and w2["duplicado"] is True


def test_sync_reutiliza_capacidades_y_restricciones():
    """El Sync Engine no acopla motores ni viola las restricciones de la fase."""
    from src.services.comercio_digital import sync
    src = inspect.getsource(sync) + inspect.getsource(sync.outbox) + inspect.getsource(sync.inbox)
    imports = [l for l in src.splitlines() if l.strip().startswith(("import ", "from "))]
    for p in ("from src.services.eventbus", "from src.services.scheduler", "from src.services.rules",
              "availability", "fulfillment", "agents_platform"):
        assert not any(p in l for l in imports), f"sync acopla a {p}"
    assert "capabilities" in inspect.getsource(sync)      # usa la fachada
    d = sync.descriptor()
    assert d["mueve_stock"] is False and d["crea_reservas"] is False
    assert d["consulta_availability"] is False and d["llama_fulfillment"] is False and d["usa_ia"] is False
    # Scheduler: se registra el job por la capacidad (no hilos/temporizadores propios).
    assert "registrar_jobs" in dir(sync)


def test_aislamiento_multiempresa_outbox(limpio, db):
    from src.services.comercio_digital import sync
    sync.encolar("referencia", "x", {"a": 1}, id_empresa=EMP, idempotencia_key="e1")
    # Otra empresa no ve pendientes de EMP.
    assert sync.outbox.pendientes("referencia", "T-SYNC-OTRA") == []
    assert len(sync.outbox.pendientes("referencia", EMP)) == 1
