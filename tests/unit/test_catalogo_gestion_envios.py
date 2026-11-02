"""
GUI (offscreen, BD real) del panel "Envíos" en `gui.catalogo_gestion.CatalogoWindow` — Fase 3
e-commerce: gestión de zonas de envío (nombre, países ISO, tarifa base/kg, umbral de envío
gratis), primera pantalla que administra el motor de zonas ya existente
(`comercio_digital.envios.zonas`)."""

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _sin_popups_bloqueantes(monkeypatch):
    """Mismo patrón que `test_catalogo_gestion_descuentos.py`: `_aviso()` es un diálogo modal
    bloqueante en GUI real — se sustituye por un registro en memoria para no colgar el test."""
    import src.gui.catalogo_gestion as mod
    llamadas = []
    monkeypatch.setattr(mod, "_aviso", lambda *a, **k: llamadas.append((a, k)))
    return llamadas


@pytest.fixture
def limpio(db):
    from src.db.empresa import EMPRESA_DEFAULT_ID
    def _clean(cur):
        cur.execute("DELETE FROM cd_envios_zonas WHERE id_empresa=%s AND nombre LIKE 'GUITEST%%'",
                    (EMPRESA_DEFAULT_ID,))
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        _clean(cur)
        conn.commit()
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        _clean(cur)
        conn.commit()


def test_crear_zona_desde_el_formulario_la_persiste_y_la_lista(app, limpio):
    from src.services.comercio_digital.envios import zonas as _zonas
    from src.gui.catalogo_gestion import CatalogoWindow
    win = CatalogoWindow()
    try:
        win.inp_env_nombre.setText("GUITEST Peninsula")
        win.inp_env_paises.setText("es,pt")
        win.inp_env_base.setText("4.5")
        win.inp_env_kg.setText("0.8")
        win.inp_env_umbral.setText("50")
        win._crear_zona_envio()

        zs = _zonas.listar_zonas()
        z = next((z for z in zs if z["nombre"] == "GUITEST Peninsula"), None)
        assert z is not None
        assert z["paises"] == "ES,PT"
        assert float(z["tarifa_base"]) == 4.5
        assert float(z["tarifa_por_kg"]) == 0.8
        assert float(z["envio_gratis_desde"]) == 50.0

        nombres_en_tabla = [win.tbl_env.item(r, 0).text() for r in range(win.tbl_env.rowCount())]
        assert "GUITEST Peninsula" in nombres_en_tabla
        assert win.inp_env_nombre.text() == ""   # el formulario se limpia tras crear
    finally:
        win.close()


def test_crear_zona_sin_nombre_no_hace_nada(app, limpio):
    from src.gui.catalogo_gestion import CatalogoWindow
    win = CatalogoWindow()
    try:
        filas_antes = win.tbl_env.rowCount()
        win.inp_env_nombre.setText("   ")
        win._crear_zona_envio()
        assert win.tbl_env.rowCount() == filas_antes
    finally:
        win.close()


def test_zona_sin_paises_se_muestra_como_resto_del_mundo(app, limpio):
    from src.services.comercio_digital.envios import zonas as _zonas
    from src.gui.catalogo_gestion import CatalogoWindow
    _zonas.crear_zona("GUITEST Resto", paises=None, tarifa_base=9.9)
    win = CatalogoWindow()
    try:
        app.processEvents()
        fila = next(r for r in range(win.tbl_env.rowCount())
                   if win.tbl_env.item(r, 0).text() == "GUITEST Resto")
        assert "resto del mundo" in win.tbl_env.item(fila, 1).text().lower()
    finally:
        win.close()


def test_eliminar_zona_desde_la_tabla(app, limpio):
    from src.services.comercio_digital.envios import zonas as _zonas
    from src.gui.catalogo_gestion import CatalogoWindow
    _zonas.crear_zona("GUITEST Eliminar", tarifa_base=1)
    win = CatalogoWindow()
    try:
        # Carga inicial diferida (`QTimer.singleShot(0, self._recargar_todo)`): dejar correr el
        # ciclo de eventos antes de inspeccionar la tabla.
        app.processEvents()
        fila = next(r for r in range(win.tbl_env.rowCount())
                   if win.tbl_env.item(r, 0).text() == "GUITEST Eliminar")
        btn = win.tbl_env.cellWidget(fila, 6)
        assert btn is not None
        btn.click()
        zs = _zonas.listar_zonas()
        assert not any(z["nombre"] == "GUITEST Eliminar" for z in zs)
    finally:
        win.close()
