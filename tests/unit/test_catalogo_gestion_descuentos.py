"""
GUI (offscreen, BD real) del panel "Descuentos" en `gui.catalogo_gestion.CatalogoWindow` — Fase 2
e-commerce: gestión de cupones (código, tipo incl. envío gratis, fechas, límite de usos, importe
mínimo) con resumen en lenguaje natural en vivo, primera pantalla que administra el motor de
cupones ya existente (`db.fidelizacion`)."""

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _sin_popups_bloqueantes(monkeypatch):
    """`_aviso()` abre un diálogo propio con `.exec()` (MODAL, bloqueante) — en un test headless,
    sin nadie que lo cierre, cuelga el proceso (visto antes exactamente con el mismo patrón en
    `contabilidad_gestion._aviso`). Se sustituye por un registro en memoria: no cambia la lógica
    bajo prueba, solo evita la ventana real."""
    import src.gui.catalogo_gestion as mod
    llamadas = []
    monkeypatch.setattr(mod, "_aviso", lambda *a, **k: llamadas.append((a, k)))
    return llamadas


@pytest.fixture
def limpio(db):
    from src.db.empresa import EMPRESA_DEFAULT_ID
    def _clean(cur):
        cur.execute("DELETE FROM cupones WHERE id_empresa=%s AND codigo LIKE 'GUITEST%%'",
                    (EMPRESA_DEFAULT_ID,))
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        _clean(cur)
        conn.commit()
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        _clean(cur)
        conn.commit()


def test_resumen_en_lenguaje_natural_se_actualiza_en_vivo(app, limpio):
    from src.gui.catalogo_gestion import CatalogoWindow
    win = CatalogoWindow()
    try:
        win.inp_cup_valor.setText("15")
        win.inp_cup_min.setText("50")
        win._actualizar_resumen_cupon()
        texto = win.lbl_resumen_cupon.text()
        assert "15" in texto and "50" in texto
        assert "descuento" in texto.lower()
    finally:
        win.close()


def test_resumen_envio_gratis(app, limpio):
    from src.gui.catalogo_gestion import CatalogoWindow
    win = CatalogoWindow()
    try:
        idx_envio = next(i for i, (_l, v) in enumerate(win._TIPOS_CUPON_UI) if v == "envio_gratis")
        win.cmb_cup_tipo.setCurrentIndex(idx_envio)
        win._actualizar_resumen_cupon()
        assert "envío gratis" in win.lbl_resumen_cupon.text().lower()
    finally:
        win.close()


def test_crear_cupon_desde_el_formulario_lo_persiste_y_lo_lista(app, limpio):
    from src.db import fidelizacion as fid
    from src.gui.catalogo_gestion import CatalogoWindow
    win = CatalogoWindow()
    try:
        win.inp_cup_cod.setText("guitest15")   # minúsculas a propósito: debe normalizarse
        win.inp_cup_valor.setText("15")
        win.inp_cup_uso_max.setText("3")
        win.inp_cup_min.setText("20")
        win._crear_cupon()

        c = fid.validar_cupon("GUITEST15")
        assert c is not None
        assert int(c["uso_maximo"]) == 3
        assert float(c["importe_minimo"]) == 20.0

        codigos_en_tabla = [win.tbl_cup.item(r, 0).text() for r in range(win.tbl_cup.rowCount())]
        assert "GUITEST15" in codigos_en_tabla
        assert win.inp_cup_cod.text() == ""   # el formulario se limpia tras crear
    finally:
        win.close()


def test_crear_cupon_sin_codigo_no_hace_nada(app, limpio):
    from src.gui.catalogo_gestion import CatalogoWindow
    win = CatalogoWindow()
    try:
        filas_antes = win.tbl_cup.rowCount()
        win.inp_cup_cod.setText("   ")
        win._crear_cupon()
        assert win.tbl_cup.rowCount() == filas_antes
    finally:
        win.close()


def test_desactivar_cupon_desde_la_tabla(app, limpio):
    from src.db import fidelizacion as fid
    from src.gui.catalogo_gestion import CatalogoWindow
    fid.emitir_cupon("GUITESTDESACT", tipo="descuento_pct", valor=10)
    win = CatalogoWindow()
    try:
        # La carga inicial de la tabla ocurre en `QTimer.singleShot(0, self._recargar_todo)`
        # (diferida, para no bloquear el arranque de la ventana) — hay que dejar correr el ciclo
        # de eventos para que dispare antes de inspeccionar `tbl_cup`.
        app.processEvents()
        fila = next(r for r in range(win.tbl_cup.rowCount())
                   if win.tbl_cup.item(r, 0).text() == "GUITESTDESACT")
        btn = win.tbl_cup.cellWidget(fila, 6)
        assert btn is not None
        btn.click()
        assert fid.validar_cupon("GUITESTDESACT") is None
    finally:
        win.close()
