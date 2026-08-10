"""
Tests Etapa F · Fase F3: alta disponibilidad / recuperación.

Verifica el orquestador `resiliencia.recuperacion` que COMPONE las primitivas existentes: recuperación
de Outbox (watchdog), Scheduler (procesar_pendientes), Inbox (idempotente), Event Bus (replay SIN
reentrega) y estado HA (nodos/heartbeat/failover/edge). Garantía de seguridad: NO reentrega eventos
(evita doble procesamiento). Degradable, multiempresa, sin motores nuevos.
"""

import pytest

from src.services.resiliencia import recuperacion

pytestmark = pytest.mark.db


def test_recuperar_scheduler(db):
    r = recuperacion.recuperar_scheduler("T-F3", aplicar=True)
    assert set(r) >= {"ejecutados", "vencidos", "fallidos"}
    assert isinstance(r["ejecutados"], int) and isinstance(r["vencidos"], int)


def test_recuperar_outbox_reutiliza_watchdog(db):
    r = recuperacion.recuperar_outbox("T-F3", aplicar=True)
    assert "acciones" in r and isinstance(r["acciones"], list)


def test_recuperar_eventbus_replay_sin_reentrega(db):
    r = recuperacion.recuperar_eventbus("T-F3")
    assert r["metodo"] == "replay"
    assert r["reentrega"] is False                        # SEGURIDAD: no reentrega eventos
    assert isinstance(r["reconstruibles"], int)


def test_recuperar_inbox_idempotente(db):
    r = recuperacion.recuperar_inbox("T-F3")
    assert r["idempotente"] is True and isinstance(r["backlog"], int)


def test_estado_ha_nodos_y_failover(db):
    from src.platform.cloud import nodes
    nodes.registrar("nodo-f3-test", region="eu")
    try:
        ha = recuperacion.estado_ha("T-F3")
        assert ha["nodos"] >= 1
        assert isinstance(ha["stale"], list)
        assert "failover_candidatos" in ha
    finally:
        nodes.dar_de_baja("nodo-f3-test")


def test_recuperar_todo_compone_todo(db):
    r = recuperacion.recuperar_todo("T-F3", aplicar=True)
    assert r["id_empresa"] == "T-F3"
    for clave in ("outbox", "scheduler", "inbox", "eventbus", "ha"):
        assert clave in r and isinstance(r[clave], dict)
    # La garantía de no-reentrega se propaga.
    assert r["eventbus"]["reentrega"] is False


def test_descriptor_seguridad(db):
    d = recuperacion.descriptor()
    assert d["motor_nuevo"] is False
    assert d["reentrega_eventos"] is False
    assert "eventbus.replay" in d["reutiliza"]
    assert set(d["operaciones"]) >= {"recuperar_outbox", "recuperar_scheduler", "recuperar_inbox",
                                     "recuperar_eventbus", "estado_ha", "recuperar_todo"}
