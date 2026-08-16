"""API del Portal de proveedor (lado proveedor). Auth por token de portal (X-Portal-Token); cada
proveedor solo ve/toca SUS datos. Endpoints preparados y degradables (modo 'local')."""

import pytest

pytestmark = pytest.mark.db


@pytest.fixture
def cliente(db):
    pytest.importorskip("flask")
    from src.api import crear_app   # Enterprise REST API (donde vive routers/portal_proveedor)
    return crear_app().test_client()


def _limpia(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("portal_mensajes", "portal_rfq_ofertas", "portal_rfq", "portal_proveedor_stock",
                  "portal_pedido_estado", "portal_proveedor_cuentas", "proveedor_precios_negociados"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE l FROM compras_pedidos_lineas l JOIN compras_pedidos p "
                    "ON p.id_pedido=l.id_pedido WHERE p.id_empresa=%s", (emp,))
        cur.execute("DELETE FROM compras_pedidos WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM proveedores WHERE id_empresa=%s", (emp,))
        conn.commit()


def _h(tok):
    return {"X-Portal-Token": tok}


def test_portal_api_flujo_proveedor(db, fab, cliente):
    from src.db import proveedores as PROV
    from src.db import compras as C
    from src.services.compras import portal

    emp = fab.empresa("EMP API portal")
    fab.al_limpiar(lambda: _limpia(db, emp))
    prov = PROV.crear_proveedor("Prov API", id_empresa=emp)
    tok = portal.invitar_proveedor(prov, id_empresa=emp)["token"]

    # Sin token → 401.
    assert cliente.get("/api/v1/portal-proveedor/me").status_code == 401

    # /me identifica al proveedor y reporta el modo (local: preparado, no desplegado).
    r = cliente.get("/api/v1/portal-proveedor/me", headers=_h(tok))
    assert r.status_code == 200 and int(r.get_json()["id_proveedor"]) == prov
    assert r.get_json()["modo"] == "local"

    # El proveedor sube una tarifa y la recupera.
    assert cliente.put("/api/v1/portal-proveedor/tarifas", headers=_h(tok),
                       json={"codigo": "ARTP", "precio": 2.5, "unidad_medida": "caja"}).status_code == 200
    data = cliente.get("/api/v1/portal-proveedor/tarifas", headers=_h(tok)).get_json()["data"]
    assert any(t["codigo_articulo"] == "ARTP" and float(t["precio"]) == 2.5 for t in data)

    # Declara stock.
    assert cliente.put("/api/v1/portal-proveedor/stock", headers=_h(tok),
                       json={"codigo": "ARTP", "stock": 50}).status_code == 200
    assert portal.stock_bolsa("ARTP", emp)[prov] == 50

    # Pedido enviado por la empresa → el proveedor cambia su estado.
    pid = C.crear_pedido(id_proveedor=prov, id_empresa=emp,
                         lineas=[{"codigo": "ARTP", "cantidad": 4, "precio_unitario": 2.5}])
    C.enviar_pedido(pid, emp)
    assert cliente.put(f"/api/v1/portal-proveedor/pedidos/{pid}/estado", headers=_h(tok),
                       json={"estado": "aceptado", "nota": "ok"}).status_code == 200
    peds = cliente.get("/api/v1/portal-proveedor/pedidos", headers=_h(tok)).get_json()["data"]
    assert any(p["id_pedido"] == pid and p["estado_proveedor"] == "aceptado" for p in peds)

    # RFQ abierta → el proveedor la ve y oferta.
    rid = portal.crear_rfq("ARTP", 100, id_empresa=emp)
    abiertas = cliente.get("/api/v1/portal-proveedor/rfq", headers=_h(tok)).get_json()["data"]
    assert any(x["id"] == rid for x in abiertas)
    assert cliente.post(f"/api/v1/portal-proveedor/rfq/{rid}/oferta", headers=_h(tok),
                        json={"precio": 1.9}).status_code == 200
    assert len(portal.ofertas_de_rfq(rid, emp)) == 1

    # Mensajería: el proveedor escribe y la empresa lo recibe sin leer.
    assert cliente.post("/api/v1/portal-proveedor/mensajes", headers=_h(tok),
                        json={"cuerpo": "Pedido en preparación"}).status_code == 200
    assert portal.no_leidos(emp, autor="proveedor") == 1

    # Token revocado → 401.
    portal.revocar(prov, emp)
    assert cliente.get("/api/v1/portal-proveedor/me", headers=_h(tok)).status_code == 401
