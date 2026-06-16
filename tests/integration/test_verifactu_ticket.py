"""Integración · QR + leyenda Verifactu en el ticket, condicionados (C3.3.4)."""

import datetime as dt

import pytest

pytestmark = pytest.mark.db


def _borra_fiscal(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("fiscal_cola", "fiscal_registros", "fiscal_config"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (emp,))
        conn.commit()


def _ticket(emp, venta_id):
    from src.db.empresa import contexto_tenant
    from src.utils.ticket_data import construir_datos_ticket
    with contexto_tenant(emp, None):
        return construir_datos_ticket(
            venta_id=venta_id, fecha=dt.datetime(2026, 6, 16, 10, 0, 0),
            id_caja="CAJA-01", empleado="OP",
            lineas=[{"nombre": "X", "cantidad": 1, "precio": 12.10, "subtotal": 12.10}],
            pago={"forma_pago": "efectivo", "total": 12.10})


def test_ticket_sin_fiscal_es_generico(db, fab):
    emp = fab.empresa("TCK OFF")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    datos = _ticket(emp, 1)
    assert datos["fiscal"] is None
    assert datos["qr"].startswith("SMART|")          # QR genérico, como siempre


def test_ticket_verifactu_lleva_qr_legal_y_leyenda(db, fab):
    from src.db import conexion as cx, fiscal as F
    from src.db.empresa import contexto_tenant
    emp = fab.empresa("TCK VF")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    F.guardar_config(proveedor="verifactu", activo=1, serie_por="empresa", id_empresa=emp)
    cod = fab.articulo(id_empresa=emp, precio=12.10, stock_tienda=10)
    with contexto_tenant(emp, None):
        vid = cx.registrar_venta_con_items([{"codigo": cod, "cantidad": 1, "precio_unitario": 12.10}])
    datos = _ticket(emp, vid)
    assert datos["fiscal"] and datos["fiscal"]["leyenda"] == "VERI*FACTU"
    assert datos["qr"].startswith("https://prewww2.aeat.es")   # QR de cotejo AEAT
    assert datos["fiscal"]["numserie"].startswith("A/")
