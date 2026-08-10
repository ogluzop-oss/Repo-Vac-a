"""
Tests · SAT / Helpdesk OPERATIVO (cierre de brecha funcional).

Verifica el ciclo real que ahora expone la GUI operativa, ejecutando los servicios existentes:
Ticket (abierto→asignado→en_proceso→resuelto→cerrado) con técnico, comentario e intervención asociada;
y la BOLSA DE HORAS prepago (crear → consumir → saldo decrementado), que es la facturación real del SAT.
Comprueba también que las transiciones inválidas se rechazan sin romper. Sin motores ni tablas nuevas.
"""

import pytest

pytestmark = pytest.mark.db

EMP = "T-SAT-1"


@pytest.fixture()
def limpia(db):
    def _b():
        with db.obtener_conexion() as c:
            cur = c.cursor()
            for tab in ("sat_consumo_horas", "sat_bolsas_horas", "ticket_comentarios",
                        "asignaciones_ticket", "intervenciones", "tickets"):
                cur.execute(f"DELETE FROM {tab} WHERE id_empresa=%s", (EMP,))
            c.commit()
    _b()
    yield
    _b()


def test_ciclo_ticket_con_intervencion(limpia):
    from src.services.sat import intervenciones, tickets

    # 1) Alta de ticket (incidencia de cliente).
    tid = tickets.crear_ticket("No arranca la máquina", descripcion="Avería crítica",
                               prioridad="alta", id_empresa=EMP)
    assert tid and tickets.obtener(tid)["estado"] == "abierto"

    # 2) Asignar técnico (INT) → abierto → asignado.
    assert tickets.asignar(tid, 1, id_empresa=EMP)["ok"]
    assert tickets.obtener(tid)["estado"] == "asignado"

    # 3) Ciclo: asignado → en_proceso → resuelto → cerrado.
    assert tickets.cambiar_estado(tid, "en_proceso", id_empresa=EMP)["ok"]
    # transición inválida (en_proceso → abierto) rechazada sin romper.
    assert tickets.cambiar_estado(tid, "abierto", id_empresa=EMP)["ok"] is False
    assert tickets.cambiar_estado(tid, "resuelto", id_empresa=EMP)["ok"]
    assert tickets.cambiar_estado(tid, "cerrado", id_empresa=EMP)["ok"]
    assert tickets.obtener(tid)["estado"] == "cerrado"

    # 4) Comentario + intervención asociada al ticket.
    assert tickets.comentar(tid, "Sustituido el relé de arranque", autor=1, id_empresa=EMP)
    iid = intervenciones.registrar_intervencion(id_ticket=tid, tecnico=1, tipo="visita",
                                                descripcion="Reparación in situ", horas=2, id_empresa=EMP)
    assert iid
    ivs = intervenciones.listar(id_ticket=tid, id_empresa=EMP)
    assert any(x["id"] == iid for x in ivs)


def test_bolsa_horas_consumo(limpia):
    """Facturación real del SAT: bolsa de horas prepago consumida desde un ticket."""
    from src.services.sat import sat_pro, tickets
    tid = tickets.crear_ticket("Soporte contratado", id_empresa=EMP)
    bid = sat_pro.crear_bolsa_horas(10, id_cliente=1, id_empresa=EMP)
    assert bid
    r = sat_pro.consumir_horas(bid, 3, id_ticket=tid, concepto="Intervención", id_empresa=EMP)
    assert isinstance(r, dict) and r.get("ok") is not False   # consumo aceptado
    saldo = sat_pro.saldo_bolsa(bid, id_empresa=EMP)
    # el saldo restante es 7h (10 - 3), leído del servicio oficial.
    val = saldo.get("saldo") if isinstance(saldo, dict) else saldo
    assert float(val) == pytest.approx(7.0)
