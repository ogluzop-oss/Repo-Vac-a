"""
GUI de variantes (edición Textil) — smoke offscreen: generar variantes talla×color desde el diálogo y ver la
rejilla de stock. Reutiliza services.variantes.
"""

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _limpiar(db):
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("DELETE FROM articulos WHERE codigo LIKE 'VARGUI%'")
        cur.execute("DELETE FROM producto_variantes WHERE codigo_padre='VARGUI'")
        c.commit()


def test_dialogo_genera_variantes_y_rejilla(app, fab, db, monkeypatch):
    emp = fab.EMP_DEFECTO
    import src.gui.variantes_gui as VG
    monkeypatch.setattr(VG, "mostrar_mensaje", lambda *a, **k: None)
    monkeypatch.setattr("src.db.empresa.empresa_actual_id", lambda: emp)
    _limpiar(db)
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("INSERT INTO articulos (codigo,id_empresa,nombre,precio) VALUES ('VARGUI',%s,'Modelo',9) "
                    "ON DUPLICATE KEY UPDATE nombre=VALUES(nombre)", (emp,))
        c.commit()
    dlg = VG.VariantesDialog(codigo_padre="VARGUI")
    try:
        dlg.in_tallas.setText("S,M")
        dlg.in_colores.setText("Rojo,Azul")
        dlg._generar()
        assert dlg.tabla.rowCount() == 2 and dlg.tabla.columnCount() == 2   # 2 tallas × 2 colores
        from src.services import variantes as V
        assert len(V.listar_variantes("VARGUI", emp)) == 4                   # 4 SKUs creados
    finally:
        dlg.deleteLater()
        _limpiar(db)
