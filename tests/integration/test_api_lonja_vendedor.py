"""API del portal del VENDEDOR de la Lonja (token X-Lonja-Token). Preparada y degradable; cada vendedor
solo ve/toca lo suyo."""

import pytest

pytestmark = pytest.mark.db


@pytest.fixture
def cliente(db):
    pytest.importorskip("flask")
    from src.api import crear_app
    return crear_app().test_client()


def _h(tok):
    return {"X-Lonja-Token": tok}


def test_lonja_vendedor_api(db, fab, cliente):
    from src.services import lonja
    ven = lonja.alta_vendedor("API Vendedor", divisa="EUR")
    tok = ven["token"]

    def _cl():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM lonja_listados WHERE id_vendedor=%s", (ven["id"],))
            cur.execute("DELETE FROM lonja_vendedores WHERE id=%s", (ven["id"],))
            conn.commit()
    fab.al_limpiar(_cl)

    # Sin token → 401.
    assert cliente.get("/api/v1/lonja-vendedor/me").status_code == 401

    # /me y cambio de DIVISA (el vendedor define su moneda de referencia).
    assert cliente.get("/api/v1/lonja-vendedor/me", headers=_h(tok)).get_json()["divisa"] == "EUR"
    assert cliente.put("/api/v1/lonja-vendedor/divisa", headers=_h(tok),
                       json={"divisa": "USD"}).status_code == 200
    assert cliente.get("/api/v1/lonja-vendedor/me", headers=_h(tok)).get_json()["divisa"] == "USD"

    # Publicar un listado (precio de compra directa + puja mínima + cantidad).
    rp = cliente.post("/api/v1/lonja-vendedor/listados", headers=_h(tok),
                      json={"codigo": "API-1", "precio": 2.0, "puja_minima": 2.2, "cantidad": 10})
    assert rp.status_code == 200 and rp.get_json()["id"]
    lid = rp.get_json()["id"]
    data = cliente.get("/api/v1/lonja-vendedor/listados", headers=_h(tok)).get_json()["data"]
    assert any(x["id"] == lid for x in data)

    # Retirar el listado.
    assert cliente.delete(f"/api/v1/lonja-vendedor/listados/{lid}", headers=_h(tok)).status_code == 200
    assert lonja.obtener_listado(lid)["estado"] == "retirado"


def test_panel_vendedor_html(db, cliente):
    # El panel web del vendedor se sirve (público; lo autentican los endpoints con el token).
    from src.services import lonja
    assert "<html" in lonja.panel_html() and "X-Lonja-Token" in lonja.panel_html()
    pg = cliente.get("/api/v1/lonja-vendedor/panel")
    assert pg.status_code == 200 and b"Portal del Vendedor" in pg.data
