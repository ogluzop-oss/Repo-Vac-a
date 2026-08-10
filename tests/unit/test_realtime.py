"""
Tests · Tiempo real en RED (SSE sobre el Event Bus existente).

Incluye la PRUEBA E2E REAL (Fase 13) sin mocks: una operación publica un evento de dominio REAL en el Event
Bus existente → el hub lo entrega a un cliente conectado, CON AISLAMIENTO POR TENANT (empresa A no recibe
eventos de empresa B) y con filtro de canal. Y verifica la seguridad del endpoint SSE (JWT obligatorio,
tenant del token).
"""

import pytest

pytestmark = pytest.mark.db

EMP_A = "RT-A"
EMP_B = "RT-B"


def test_e2e_evento_real_por_tenant(db):
    """Evento real → Event Bus → hub → cliente autorizado. Empresa B NO recibe eventos de empresa A."""
    from src.services.eventbus import publish, realtime
    ca = realtime.registrar(EMP_A)
    cb = realtime.registrar(EMP_B)
    try:
        r = publish("stock.salida", id_empresa=EMP_A, id_tienda=1)
        assert r is not None, "el evento debe publicarse en el Event Bus real"
        ev = ca.cola.get(timeout=3)                       # A recibe su evento
        assert ev["tipo"] == "stock.salida" and str(ev["id_empresa"]) == EMP_A
        assert ev.get("uuid")                             # trae identificador (idempotencia)
        assert cb.cola.empty()                            # AISLAMIENTO: B no recibe eventos de A
    finally:
        realtime.desregistrar(ca)
        realtime.desregistrar(cb)


def test_filtro_por_canal(db):
    """Un cliente suscrito solo al canal 'stock' no recibe eventos del canal 'ventas'."""
    from src.services.eventbus import publish, realtime
    c = realtime.registrar(EMP_A, canales=["stock"])
    try:
        publish("ventas.finalizada", id_empresa=EMP_A, id_tienda=1)   # canal 'ventas' → NO
        publish("stock.entrada", id_empresa=EMP_A, id_tienda=1)       # canal 'stock' → SÍ
        ev = c.cola.get(timeout=3)
        assert ev["tipo"] == "stock.entrada"
        assert c.cola.empty()                             # el de 'ventas' no se entregó
    finally:
        realtime.desregistrar(c)


def test_sse_endpoint_seguridad_y_registro():
    """El endpoint SSE exige JWT y registra al cliente con el tenant del TOKEN (no del cliente)."""
    from flask import Blueprint, Flask
    from src.api.routers import realtime as rt_router
    from src.seguridad import tokens
    from src.services.eventbus import realtime

    app = Flask(__name__)
    bp = Blueprint("api", __name__)
    rt_router.registrar(bp)
    app.register_blueprint(bp)
    cli = app.test_client()

    # Sin token → 401 (nunca acceso anónimo a un canal privado).
    assert cli.get("/realtime/stream").status_code == 401

    # Con token válido → 200 + text/event-stream, y el hub registra una conexión de ESE tenant.
    tok = tokens.emitir_access({"id": 1, "id_empresa": "RT-SSE"})
    antes = realtime.conexiones_de("RT-SSE")
    resp = cli.get("/realtime/stream", headers={"Authorization": f"Bearer {tok}"})
    assert resp.status_code == 200
    assert resp.mimetype == "text/event-stream"
    assert realtime.conexiones_de("RT-SSE") == antes + 1   # cliente registrado para el tenant del token
    resp.close()
