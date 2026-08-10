"""
Tests PCD · Etapa B · Fase B7: Logística comercial (transportistas).

Verifica que los envíos se integran como adaptadores provider-agnostic (degradable a 'simulado'):
etiqueta + tracking; el ciclo de la Transacción PAGADA→PREPARANDO→ENVIADA→ENTREGADA; que al enviar se
CONSUME la reserva (sin mover stock físico); incidencias; y aislamiento multiempresa.
"""

import inspect

import pytest

EMP = "T-ENV-A"
COD = "ENV1"


@pytest.fixture()
def pagado(db):
    """Deja una Transacción PAGADA con reserva (checkout + pago simulado) lista para enviar."""
    def _clean(cur):
        for t in ("cd_envios", "cd_pagos", "transaccion_decisiones", "transaccion_eventos",
                  "transaccion_lineas", "transaccion_comercial", "cd_reservas"):
            try:
                cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (EMP,))
            except Exception:
                pass
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        _clean(cur)
        cur.execute("DELETE FROM articulos WHERE codigo=%s AND id_empresa=%s", (COD, EMP))
        cur.execute("INSERT INTO articulos (codigo, id_empresa, nombre, precio, Stock_central) "
                    "VALUES (%s,%s,'Envio Test',30.0,10)", (COD, EMP))
        conn.commit()
    from src.services.comercio_digital import checkout, pagos
    r = checkout.confirmar(id_empresa=EMP, origen="web",
                           lineas=[{"codigo": COD, "cantidad": 2, "precio_unitario": 30.0}])
    pagos.iniciar(r["id_tx"], proveedor="simulado", id_empresa=EMP)
    pagos.confirmar(r["id_tx"], id_empresa=EMP)
    yield r["id_tx"]
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        _clean(cur)
        cur.execute("DELETE FROM articulos WHERE codigo=%s AND id_empresa=%s", (COD, EMP))
        conn.commit()


def _reservado(emp):
    from src.services.comercio_digital.inventario import reservas
    return reservas.reservado(COD, emp, "central")


def test_crear_envio_etiqueta_y_preparando(pagado):
    from src.services.comercio_digital import envios, transacciones
    r = envios.crear_envio(pagado, transportista="simulado", id_empresa=EMP, direccion="C/ Falsa 1")
    assert r["ok"] and r["tracking"].startswith("SIMTRK-") and r["etiqueta"]
    assert envios.etiqueta(r["id_envio"], id_empresa=EMP).endswith(".pdf")
    # La Transacción pasa a PREPARANDO.
    assert transacciones.obtener(pagado, EMP)["estado"] == "PREPARANDO"


def test_enviar_consume_reserva_sin_mover_stock(pagado, db):
    from src.services.comercio_digital import envios, transacciones
    assert _reservado(EMP) == 2                       # reserva activa (checkout hard)
    r = envios.crear_envio(pagado, transportista="simulado", id_empresa=EMP)
    env = envios.marcar_enviado(r["id_envio"], id_empresa=EMP)
    assert env["ok"] and env["reservas_consumidas"] == 1
    assert transacciones.obtener(pagado, EMP)["estado"] == "ENVIADA"
    assert _reservado(EMP) == 0                        # reserva consumida (ya no bloquea ATP)
    # El stock físico NO lo mueve esta capa (política única).
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT Stock_central FROM articulos WHERE codigo=%s AND id_empresa=%s", (COD, EMP))
        s = cur.fetchone()
    assert int(list(s.values())[0] if isinstance(s, dict) else s[0]) == 10


def test_tracking_e_incidencia(pagado):
    from src.services.comercio_digital import envios
    r = envios.crear_envio(pagado, transportista="simulado", id_empresa=EMP)
    t = envios.rastrear(r["id_envio"], id_empresa=EMP)
    assert t["ok"] and t["eventos"]                    # eventos de seguimiento
    inc = envios.registrar_incidencia(r["id_envio"], "Dirección incorrecta", id_empresa=EMP)
    assert inc["estado"] == "incidencia"
    assert envios.listar(pagado, id_empresa=EMP)[0]["estado"] == "incidencia"


def test_entregado_cierra_ciclo(pagado):
    from src.services.comercio_digital import envios, transacciones
    r = envios.crear_envio(pagado, transportista="simulado", id_empresa=EMP)
    envios.marcar_enviado(r["id_envio"], id_empresa=EMP)
    d = envios.marcar_entregado(r["id_envio"], id_empresa=EMP)
    assert d["ok"] and transacciones.obtener(pagado, EMP)["estado"] == "ENTREGADA"


def test_provider_agnostic_no_motor():
    from src.services.comercio_digital import envios
    from src.services.comercio_digital.envios import adaptador
    dom = inspect.getsource(envios)
    assert "requests" not in dom                       # el dominio no habla HTTP
    assert "import requests" in inspect.getsource(adaptador)   # el adaptador sí
    d = envios.descriptor()
    assert d["mueve_stock"] is False and d["provider_agnostic"] is True and d["crea_motor_nuevo"] is False


def test_aislamiento_multiempresa(pagado):
    from src.services.comercio_digital import envios
    r = envios.crear_envio(pagado, transportista="simulado", id_empresa=EMP)
    assert envios.listar(pagado, id_empresa=EMP)
    assert envios.listar(pagado, id_empresa="T-ENV-OTRA") == []
