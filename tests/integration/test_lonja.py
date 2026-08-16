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


def test_subasta_caduca_por_defecto(db, fab):
    import datetime as dt
    emp = fab.empresa("EMP dur")
    ven = lonja.alta_vendedor("Dur SA", divisa="EUR")
    fab.al_limpiar(lambda: _limpia(db, emp, emp, [ven["id"]]))
    # Sin fecha_limite explícita → CADUCA por la duración por defecto (~24 h).
    lid = lonja.publicar(ven["id"], "DUR-1", 10.0, puja_minima=10.0, cantidad=5)
    l = lonja.obtener_listado(lid)
    assert l["fecha_limite"] is not None
    horas = (l["fecha_limite"] - dt.datetime.now()).total_seconds() / 3600
    assert 23 < horas < 25


def test_incremento_minimo(db, fab):
    emp_a = fab.empresa("EMP inc A")
    emp_b = fab.empresa("EMP inc B")
    ven = lonja.alta_vendedor("Inc SA", divisa="EUR")
    fab.al_limpiar(lambda: _limpia(db, emp_a, emp_b, [ven["id"]]))
    lid = lonja.publicar(ven["id"], "INC-1", 10.0, puja_minima=5.0, cantidad=5, incremento_minimo=1.0)
    assert lonja.pujar(lid, emp_a, 5.0)["ok"]
    assert lonja.pujar(lid, emp_b, 5.5)["error"] == "incremento_insuficiente"   # 5.5 < 5 + 1
    assert lonja.pujar(lid, emp_b, 6.0)["ok"]


def test_precio_reserva_desierta(db, fab):
    emp = fab.empresa("EMP res")
    ven = lonja.alta_vendedor("Res SA", divisa="EUR")
    fab.al_limpiar(lambda: _limpia(db, emp, emp, [ven["id"]]))
    lid = lonja.publicar(ven["id"], "RES-1", 20.0, puja_minima=5.0, cantidad=1, precio_reserva=10.0)
    lonja.pujar(lid, emp, 8.0)   # por debajo del precio de reserva
    assert lonja.adjudicar(lid)["error"] == "reserva_no_alcanzada"
    # Al cerrar la subasta vencida sin alcanzar reserva → queda 'desierta'.
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("UPDATE lonja_listados SET fecha_limite=DATE_SUB(NOW(), INTERVAL 1 MINUTE) WHERE id=%s",
                    (lid,))
        conn.commit()
    lonja.cerrar_subastas_vencidas()
    assert lonja.obtener_listado(lid)["estado"] == "desierta"


def test_gating_tipo_comercio(db, fab):
    from src.services.lonja import listados as L
    v_ph = lonja.alta_vendedor("Pharma SA", divisa="EUR", tipo_comercio=["PHARMACY"])
    v_all = lonja.alta_vendedor("Todos SA", divisa="EUR")            # tipo_comercio None → todas
    v_bad = lonja.alta_vendedor("Bad SA", tipo_comercio=["FOO"])     # inválido → None
    vids = [v_ph["id"], v_all["id"], v_bad["id"]]

    def _cl():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            for vid in vids:
                cur.execute("DELETE FROM lonja_listados WHERE id_vendedor=%s", (vid,))
                cur.execute("DELETE FROM lonja_vendedores WHERE id=%s", (vid,))
            conn.commit()
    fab.al_limpiar(_cl)

    assert v_bad["tipo_comercio"] is None                            # normalización descarta inválidos
    lonja.publicar(v_ph["id"], "TC-1", 5.0, permite_puja=False, cantidad=3)
    lonja.publicar(v_all["id"], "TC-1", 6.0, permite_puja=False, cantidad=3)

    # Edición PHARMACY → el de farmacia + el que suministra a todos.
    ph = {r["id_vendedor"] for r in L.listar("TC-1", vertical="PHARMACY")}
    assert ph == {v_ph["id"], v_all["id"]}
    # Edición TEXTIL → solo el que suministra a todos (el de farmacia queda fuera).
    tx = {r["id_vendedor"] for r in L.listar("TC-1", vertical="TEXTIL")}
    assert tx == {v_all["id"]}
    # Sin gating (vertical=None) → ambos.
    assert len(L.listar("TC-1")) == 2

    # set_tipo_comercio actualiza la lista CSV.
    lonja.set_tipo_comercio(v_ph["id"], ["PHARMACY", "BAKERY"])
    assert lonja.obtener_vendedor(v_ph["id"])["tipo_comercio"] == "PHARMACY,BAKERY"


def test_conversion_divisa():
    # 1 USD = 0.90 EUR; convertir 100 USD → 90 EUR y viceversa.
    lonja.set_tasa("USD", 0.90)
    assert lonja.tasa("EUR") == 1.0
    assert lonja.convertir(100, "USD", "EUR") == 90.0
    assert lonja.convertir(90, "EUR", "USD") == 100.0


def test_antisniping_extiende_cierre(db, fab):
    import datetime as dt
    emp = fab.empresa("EMP snipe")
    ven = lonja.alta_vendedor("Snipe SA", divisa="EUR")
    fab.al_limpiar(lambda: _limpia(db, emp, emp, [ven["id"]]))
    limite = dt.datetime.now() + dt.timedelta(minutes=3)
    lid = lonja.publicar(ven["id"], "SNI-1", 10.0, puja_minima=10.0, cantidad=5, fecha_limite=limite)
    r = lonja.pujar(lid, emp, 11.0)
    assert r["ok"] and r["extendido"] is True
    # El cierre se ha extendido más allá del límite original (nadie gana pujando en el último segundo).
    assert lonja.obtener_listado(lid)["fecha_limite"] > limite


def test_puja_en_subasta_vencida_rechazada(db, fab):
    import datetime as dt
    emp = fab.empresa("EMP venc")
    ven = lonja.alta_vendedor("Venc SA", divisa="EUR")
    fab.al_limpiar(lambda: _limpia(db, emp, emp, [ven["id"]]))
    lid = lonja.publicar(ven["id"], "VE-1", 4.0, puja_minima=4.0, cantidad=1,
                         fecha_limite=dt.datetime.now() - dt.timedelta(minutes=1))
    assert lonja.pujar(lid, emp, 5.0)["error"] == "subasta_cerrada"


def test_job_cierre_adjudica_y_cierra(db, fab):
    import datetime as dt
    emp_a = fab.empresa("EMP cj A")
    emp_b = fab.empresa("EMP cj B")
    ven = lonja.alta_vendedor("Cierre SA", divisa="EUR")
    fab.al_limpiar(lambda: _limpia(db, emp_a, emp_b, [ven["id"]]))
    # Subasta con pujas; luego se fuerza el vencimiento.
    lid = lonja.publicar(ven["id"], "CJ-1", 5.0, puja_minima=5.0, cantidad=3,
                         fecha_limite=dt.datetime.now() + dt.timedelta(minutes=10))
    lonja.pujar(lid, emp_a, 5.5)
    lonja.pujar(lid, emp_b, 6.0)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("UPDATE lonja_listados SET fecha_limite=DATE_SUB(NOW(), INTERVAL 1 MINUTE) WHERE id=%s",
                    (lid,))
        conn.commit()
    # Subasta vencida SIN pujas.
    lid2 = lonja.publicar(ven["id"], "CJ-2", 7.0, puja_minima=7.0, cantidad=2,
                          fecha_limite=dt.datetime.now() - dt.timedelta(minutes=1))

    res = lonja.cerrar_subastas_vencidas()
    assert res["adjudicadas"] >= 1 and res["cerradas"] >= 1
    assert lonja.obtener_listado(lid)["estado"] == "adjudicado"     # adjudicada a la mejor puja (emp_b)
    assert lonja.obtener_listado(lid2)["estado"] == "cerrado"       # sin pujas → cerrada
    # La ganadora (emp_b) tiene su pedido real generado.
    assert any(t["id_empresa"] == emp_b for t in lonja.transacciones_de(id_listado=lid))
