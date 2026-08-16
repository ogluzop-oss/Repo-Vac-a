"""Lonja B2B (Fase M1) — mercado/subasta entre empresas.

Cubre: publicar listado; compra directa ATÓMICA + idempotente (sin doble venta, genera pedido real en el
comprador); puja ≥ mínima y que mejora la mejor; adjudicación a la ganadora con su pedido; conversión de
divisa. `db`.
"""

import pytest

from src.db import compras as C
from src.services import lonja

pytestmark = pytest.mark.db


def _limpia(db, emp_a, emp_b, vids):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for emp in (emp_a, emp_b):
            cur.execute("DELETE l FROM compras_pedidos_lineas l JOIN compras_pedidos p "
                        "ON p.id_pedido=l.id_pedido WHERE p.id_empresa=%s", (emp,))
            cur.execute("DELETE FROM compras_pedidos WHERE id_empresa=%s", (emp,))
            cur.execute("DELETE FROM proveedores WHERE id_empresa=%s", (emp,))
            cur.execute("DELETE FROM lonja_pujas WHERE id_empresa=%s", (emp,))
            cur.execute("DELETE FROM lonja_transacciones WHERE id_empresa=%s", (emp,))
        for vid in vids:
            cur.execute("DELETE FROM lonja_listados WHERE id_vendedor=%s", (vid,))
            cur.execute("DELETE FROM lonja_vendedores WHERE id=%s", (vid,))
        conn.commit()


def test_compra_directa_atomica_e_idempotente(db, fab):
    emp_a = fab.empresa("EMP lonja A")
    emp_b = fab.empresa("EMP lonja B")
    ven = lonja.alta_vendedor("Harinas del Sur", divisa="EUR")
    fab.al_limpiar(lambda: _limpia(db, emp_a, emp_b, [ven["id"]]))

    lid = lonja.publicar(ven["id"], "HAR-500", 0.65, puja_minima=0.70, cantidad=100)
    assert lid

    # La empresa A compra 100 (todo): confirmada + pedido real en su tenant.
    r = lonja.comprar_directo(lid, emp_a, 100, clave_idem="A-1")
    assert r["ok"] and r["id_transaccion"] and r["id_pedido"]
    ped = C.obtener_pedido(r["id_pedido"], emp_a)
    assert ped and ped["estado"] == "ENVIADO"

    # Idempotencia: reintentar la MISMA compra no descuenta ni duplica.
    r2 = lonja.comprar_directo(lid, emp_a, 100, clave_idem="A-1")
    assert r2["ok"] and r2.get("idempotente") and r2["id_transaccion"] == r["id_transaccion"]

    # Sin doble venta: la empresa B ya no puede comprar (agotado).
    r3 = lonja.comprar_directo(lid, emp_b, 1, clave_idem="B-1")
    assert r3["ok"] is False and r3["error"] in ("listado_no_disponible", "cantidad_insuficiente")
    assert lonja.obtener_listado(lid)["estado"] == "agotado"


def test_puja_minima_y_mejora(db, fab):
    emp_a = fab.empresa("EMP puja A")
    emp_b = fab.empresa("EMP puja B")
    ven = lonja.alta_vendedor("Aceites SA", divisa="EUR")
    fab.al_limpiar(lambda: _limpia(db, emp_a, emp_b, [ven["id"]]))
    lid = lonja.publicar(ven["id"], "ACE-750", 3.0, puja_minima=3.2, cantidad=10)

    # Por debajo de la mínima → rechazada.
    assert lonja.pujar(lid, emp_a, 3.1)["error"] == "por_debajo_minima"
    # Primera puja válida.
    assert lonja.pujar(lid, emp_a, 3.3)["ok"]
    # No mejora la mejor → rechazada.
    assert lonja.pujar(lid, emp_b, 3.3)["error"] == "no_mejora"
    # Mejora → se registra y la anterior queda superada.
    assert lonja.pujar(lid, emp_b, 3.5)["ok"]
    mp = lonja.mejor_puja(lid)
    assert float(mp["importe"]) == 3.5 and mp["id_empresa"] == emp_b


def test_adjudicacion_genera_pedido(db, fab):
    emp_a = fab.empresa("EMP adj A")
    emp_b = fab.empresa("EMP adj B")
    ven = lonja.alta_vendedor("Textil Norte", divisa="EUR")
    fab.al_limpiar(lambda: _limpia(db, emp_a, emp_b, [ven["id"]]))
    lid = lonja.publicar(ven["id"], "CAM-M", 5.0, puja_minima=5.0, cantidad=50)
    lonja.pujar(lid, emp_a, 5.5)
    lonja.pujar(lid, emp_b, 6.0)

    res = lonja.adjudicar(lid)
    assert res["ok"] and res["id_empresa_ganadora"] == emp_b and res["id_pedido"]
    ped = C.obtener_pedido(res["id_pedido"], emp_b)
    assert ped and ped["estado"] == "ENVIADO"
    assert lonja.obtener_listado(lid)["estado"] == "adjudicado"


def test_bolsa_unificada_mezcla_tarifa_y_lonja(db, fab):
    from src.services.compras import proveedores_pro as PP
    from src.db import proveedores as PROV
    emp = fab.empresa("EMP unif")
    prov = PROV.crear_proveedor("Prov Tarifa", id_empresa=emp)
    ven = lonja.alta_vendedor("Vendedor Lonja", divisa="EUR")

    def _cl():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM proveedor_precios_negociados WHERE id_empresa=%s", (emp,))
            cur.execute("DELETE FROM proveedores WHERE id_empresa=%s", (emp,))
            cur.execute("DELETE FROM lonja_listados WHERE id_vendedor=%s", (ven["id"],))
            cur.execute("DELETE FROM lonja_vendedores WHERE id=%s", (ven["id"],))
            conn.commit()
    fab.al_limpiar(_cl)

    PP.set_precio_negociado(prov, "UNIF-1", 4.0, unidad_medida="unidad", id_empresa=emp)
    lonja.publicar(ven["id"], "UNIF-1", 3.5, puja_minima=3.8, cantidad=20)

    res = lonja.bolsa_unificada("UNIF-1", id_empresa=emp)
    origenes = {f["origen"] for f in res["filas"]}
    assert origenes == {"tarifa", "lonja"}                      # ambas clasificadas
    # La oferta en vivo (3.5) sale por delante de la tarifa (4.0) al ordenar por precio de referencia.
    assert res["filas"][0]["origen"] == "lonja" and res["filas"][0]["precio"] == 3.5
    lonja_row = res["filas"][0]
    assert lonja_row["compra_directa"] and lonja_row["puja"] and lonja_row["disponible"] == 20
    assert lonja_row["puja_minima"] == 3.8


def test_conversion_divisa():
    # 1 USD = 0.90 EUR; convertir 100 USD → 90 EUR y viceversa.
    lonja.set_tasa("USD", 0.90)
    assert lonja.tasa("EUR") == 1.0
    assert lonja.convertir(100, "USD", "EUR") == 90.0
    assert lonja.convertir(90, "EUR", "USD") == 100.0
