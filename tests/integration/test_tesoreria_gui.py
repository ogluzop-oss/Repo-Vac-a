"""
Tesorería · FASE 12 — GUI (instanciación headless de la ventana y sus 8 pestañas).
"""

import pytest

pytestmark = pytest.mark.db

from src.db import tesoreria as T
from src.db.empresa import EMPRESA_DEFAULT_ID, contexto_tenant

E = EMPRESA_DEFAULT_ID
IBAN = "ES9121000418450200051332"


def test_ventana_tesoreria(db):
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 no disponible")
    QApplication.instance() or QApplication([])
    cid = T.crear_cuenta("GUI", IBAN, saldo_inicial=100, id_empresa=E)
    T.registrar_movimiento("COBRO", 50, id_cuenta=cid, id_empresa=E)
    try:
        with contexto_tenant(E, None):
            from src.gui.tesoreria_gui import TesoreriaWindow
            w = TesoreriaWindow()
            # 8 pestañas
            assert w.tabs.count() == 8
            titulos = [w.tabs.tabText(i) for i in range(8)]
            assert "Cuentas" in titulos and "Remesas SEPA" in titulos and "Cash Flow" in titulos
            # la tabla de cuentas se ha poblado con la cuenta creada
            assert w.tbl_cuentas.rowCount() >= 1
            assert w.tbl_mov.rowCount() >= 1
            w.refrescar()
            w.close()
    finally:
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM movimientos_tesoreria WHERE id_cuenta=%s", (cid,))
            cur.execute("DELETE FROM cuentas_bancarias WHERE id=%s", (cid,))
            conn.commit()
