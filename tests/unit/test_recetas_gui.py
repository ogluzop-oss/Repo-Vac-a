"""
GUI de recetas (edición Pharmacy) — smoke offscreen: crear receta desde la ventana y dispensarla (descuenta
stock por el motor oficial). Reutiliza services.recetas.
"""

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _limpiar(db):
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("DELETE FROM recetas_lineas WHERE id_receta IN (SELECT id FROM recetas WHERE paciente='RXGUI')")
        cur.execute("DELETE FROM recetas WHERE paciente='RXGUI'")
        cur.execute("DELETE FROM articulos WHERE codigo='RXGUI-MED'")
        cur.execute("DELETE FROM movimientos_stock WHERE codigo_articulo='RXGUI-MED'")
        c.commit()


def test_ventana_crea_y_dispensa(app, fab, db, monkeypatch):
    emp = fab.EMP_DEFECTO
    import src.gui.recetas_gui as RG
    monkeypatch.setattr(RG, "mostrar_mensaje", lambda *a, **k: None)
    monkeypatch.setattr("src.db.empresa.empresa_actual_id", lambda: emp)
    _limpiar(db)
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("INSERT INTO articulos (codigo,id_empresa,nombre,Stock_tienda,Stock_total) "
                    "VALUES ('RXGUI-MED',%s,'Med',10,10) ON DUPLICATE KEY UPDATE Stock_tienda=10,Stock_total=10",
                    (emp,))
        c.commit()
    win = RG.RecetasWindow(usuario={"nombre": "tester"})
    try:
        win.in_paciente.setText("RXGUI")
        win._add_linea("RXGUI-MED", 3, "1/día")
        win._crear()
        sid = win.ultima_id
        fila = next(i for i in range(win.lst.count())
                    if win.lst.item(i).data(Qt.ItemDataRole.UserRole) == sid)
        win.lst.setCurrentRow(fila)
        win._dispensar()
        from src.services import recetas as R
        assert R.obtener_receta(sid, id_empresa=emp)["estado"] == "DISPENSADA"
    finally:
        win.deleteLater()
        _limpiar(db)
