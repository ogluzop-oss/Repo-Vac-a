"""Portal de proveedor (Fase 2) — núcleo de servicios.

Cubre: cuentas/invitación + resolución de token + revocado; estado de pedido reportado por el proveedor;
stock declarado; RFQ/subasta inversa con adjudicación que CREA un pedido real (reutiliza el motor de
compras); mensajería bidireccional; scorecard; e interruptor degradable. `db`.
"""

import pytest

from src.db import compras as C
from src.db import proveedores as PROV
from src.services.compras import portal

pytestmark = pytest.mark.db


def _limpia(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("portal_mensajes", "portal_rfq_ofertas", "portal_rfq", "portal_proveedor_stock",
                  "portal_pedido_estado", "portal_proveedor_cuentas"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE l FROM compras_pedidos_lineas l JOIN compras_pedidos p "
                    "ON p.id_pedido=l.id_pedido WHERE p.id_empresa=%s", (emp,))
        cur.execute("DELETE FROM compras_pedidos WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM proveedores WHERE id_empresa=%s", (emp,))
        conn.commit()


def test_degradable_por_defecto():
    # Sin la variable de entorno, el enlace remoto NO está desplegado (modo local, preparado).
    assert portal.portal_activo() is False
    assert portal.modo() == "local"


def test_cuentas_invitacion_y_token(db, fab):
    emp = fab.empresa("EMP portal cuentas")
    fab.al_limpiar(lambda: _limpia(db, emp))
    prov = PROV.crear_proveedor("Prov Portal", id_empresa=emp)

    inv = portal.invitar_proveedor(prov, email="prov@x.com", id_empresa=emp)
    assert inv and inv["token"] and inv["estado"] == "invitado"

    # El token resuelve al tenant + proveedor (auth del lado remoto).
    r = portal.resolver_token(inv["token"])
    assert r and int(r["id_proveedor"]) == prov and r["estado"] == "invitado"

    # El proveedor entra → cuenta activa + ultima_conexion sellada.
    assert portal.marcar_conexion(inv["token"]) is True
    assert portal.estado_cuenta(prov, emp)["estado"] == "activo"

    # Re-invitar es idempotente: conserva el token.
    inv2 = portal.invitar_proveedor(prov, id_empresa=emp)
    assert inv2["token"] == inv["token"]

    # Revocar corta el acceso: el token deja de resolver.
    assert portal.revocar(prov, emp) is True
    assert portal.resolver_token(inv["token"]) is None


def test_estado_pedido_y_stock(db, fab):
    emp = fab.empresa("EMP portal estado")
    fab.al_limpiar(lambda: _limpia(db, emp))
    prov = PROV.crear_proveedor("Prov Estado", id_empresa=emp)
    pid = C.crear_pedido(id_proveedor=prov, id_empresa=emp,
                         lineas=[{"codigo": "ART1", "cantidad": 3, "precio_unitario": 1.0}])
    C.enviar_pedido(pid, emp)

    # El proveedor reporta el estado del pedido (upsert: se queda el último).
    assert portal.actualizar_estado_pedido(pid, "aceptado", id_proveedor=prov, id_empresa=emp)
    assert portal.actualizar_estado_pedido(pid, "en_reparto", nota="sale mañana", id_empresa=emp)
    e = portal.estado_pedido(pid, emp)
    assert e["estado_proveedor"] == "en_reparto" and e["nota"] == "sale mañana"
    assert portal.estados_pedidos(emp, ids=[pid]) == {pid: "en_reparto"}

    # Vista del proveedor: sus pedidos en curso con el estado portal.
    vista = portal.pedidos_de_proveedor(prov, emp)
    assert any(p["id_pedido"] == pid and p["estado_proveedor"] == "en_reparto" for p in vista)

    # Stock declarado por el proveedor (upsert por artículo/unidad).
    assert portal.set_stock(prov, "ART1", 120, unidad_medida="unidad", id_empresa=emp)
    assert portal.set_stock(prov, "ART1", 80, unidad_medida="unidad", id_empresa=emp)
    assert portal.stock_de(prov, "ART1", id_empresa=emp)[0]["stock"] == 80
    assert portal.stock_bolsa("ART1", emp)[prov] == 80


def test_rfq_subasta_inversa_y_adjudicacion(db, fab):
    emp = fab.empresa("EMP portal rfq")
    fab.al_limpiar(lambda: _limpia(db, emp))
    p1 = PROV.crear_proveedor("Oferta cara", id_empresa=emp)
    p2 = PROV.crear_proveedor("Oferta barata", id_empresa=emp)

    rid = portal.crear_rfq("ARTX", 100, unidad_medida="caja", id_empresa=emp)
    assert rid
    assert portal.responder_rfq(rid, p1, 5.0, id_empresa=emp)
    assert portal.responder_rfq(rid, p2, 4.0, id_empresa=emp)
    # Re-ofertar actualiza (no duplica).
    assert portal.responder_rfq(rid, p2, 3.5, id_empresa=emp)

    ofertas = portal.ofertas_de_rfq(rid, emp)
    assert len(ofertas) == 2
    assert float(ofertas[0]["precio"]) == 3.5 and ofertas[0]["id_proveedor"] == p2  # mejor primero

    # Adjudicar a la mejor oferta → crea+envía un pedido real con ese precio.
    res = portal.adjudicar_rfq(rid, p2, id_empresa=emp, usuario="Tester")
    assert res["ok"] and res["id_pedido"]
    ped = C.obtener_pedido(res["id_pedido"], emp)
    assert ped and ped["estado"] == "ENVIADO"
    assert any(float(l.get("precio_unitario")) == 3.5 for l in (ped.get("lineas") or []))
    # La RFQ queda adjudicada y ya no acepta más ofertas.
    assert portal.obtener_rfq(rid, emp)["estado"] == "adjudicada"
    assert portal.responder_rfq(rid, p1, 1.0, id_empresa=emp) is None


def test_mensajeria_bidireccional(db, fab):
    emp = fab.empresa("EMP portal msg")
    fab.al_limpiar(lambda: _limpia(db, emp))
    prov = PROV.crear_proveedor("Prov Chat", id_empresa=emp)

    portal.enviar_mensaje(prov, "¿Podéis servir mañana?", autor="empresa", id_empresa=emp)
    portal.enviar_mensaje(prov, "Sí, sin problema", autor="proveedor", id_empresa=emp)
    h = portal.hilo(prov, id_empresa=emp)
    assert [m["autor"] for m in h] == ["empresa", "proveedor"]

    # El mensaje del proveedor está sin leer hasta marcarlo.
    assert portal.no_leidos(emp, autor="proveedor") == 1
    assert portal.marcar_leido(prov, autor="proveedor", id_empresa=emp) == 1
    assert portal.no_leidos(emp, autor="proveedor") == 0


def test_scorecard_reutiliza_evaluacion(db, fab):
    emp = fab.empresa("EMP portal score")
    fab.al_limpiar(lambda: _limpia(db, emp))
    prov = PROV.crear_proveedor("Prov Score", id_empresa=emp)
    pid = C.crear_pedido(id_proveedor=prov, id_empresa=emp,
                         lineas=[{"codigo": "A", "cantidad": 1, "precio_unitario": 1.0}])
    C.enviar_pedido(pid, emp)
    portal.actualizar_estado_pedido(pid, "en_reparto", id_proveedor=prov, id_empresa=emp)

    sc = portal.scorecard(prov, emp)
    assert "valoracion_global" in sc and "portal" in sc
    assert sc["portal"]["en_reparto"] == 1
