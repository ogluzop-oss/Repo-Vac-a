"""
GUI (offscreen, BD real) de la Fase 1 e-commerce en `gui.catalogo_gestion._ProductoEditor`:
precio de comparación (promo_activa/precio_promo ya existentes), slug editable, asistente IA junto
a los campos de texto, y el generador de combinaciones de variantes (`_MatrizVariantesDialog`).
"""

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def producto(fab):
    cod = fab.articulo(nombre="Camiseta Test", precio=25.0)
    pid = fab.producto_catalogo(cod, titulo_web="Camiseta Test")
    return cod, pid


def test_precio_de_oferta_preview_tachado(app, producto):
    from src.gui.catalogo_gestion import _ProductoEditor
    cod, pid = producto
    dlg = _ProductoEditor(cod, "Camiseta Test")
    try:
        assert dlg.ck_oferta.isChecked() is False
        assert dlg.lbl_preview_precio.text() == ""
        dlg.ck_oferta.setChecked(True)
        dlg.inp_precio_oferta.setText("19.90")
        texto = dlg.lbl_preview_precio.text()
        assert "25.00" in texto and "19.90" in texto
        assert "line-through" in texto
    finally:
        dlg.deleteLater()


def test_guardar_persiste_oferta_y_slug(app, producto):
    from src.db import articulos as art_db
    from src.db import catalogo as cat
    from src.gui.catalogo_gestion import _ProductoEditor
    cod, pid = producto
    dlg = _ProductoEditor(cod, "Camiseta Test")
    try:
        dlg.ck_oferta.setChecked(True)
        dlg.inp_precio_oferta.setText("19.90")
        dlg.inp_slug.setText("camiseta especial")
        dlg._guardar()

        prod = cat.obtener_producto(id_producto=pid)
        assert prod["promo_activa"] in (1, True)
        assert float(prod["precio_promo"]) == 19.90
        assert prod["slug"] == "camiseta-especial"
    finally:
        dlg.deleteLater()


def test_boton_ia_presente_junto_a_descripcion_y_seo(app, producto):
    from src.gui.catalogo_gestion import _ProductoEditor
    cod, _pid = producto
    dlg = _ProductoEditor(cod, "Camiseta Test")
    try:
        # 3 campos con asistente IA en la Ficha: descripción, SEO título, SEO descripción.
        from PyQt6.QtWidgets import QPushButton
        botones_ia = [b for b in dlg.findChildren(QPushButton) if b.text() == "✨"]
        assert len(botones_ia) == 3
    finally:
        dlg.deleteLater()


def test_variantes_tab_muestra_atributos_precio_y_stock(app, producto, fab):
    from src.db import catalogo as cat
    from src.gui.catalogo_gestion import _ProductoEditor
    cod, pid = producto
    cod_variante = fab.articulo(nombre="Camiseta Talla M", stock_total=10, stock_tienda=2)
    vid = cat.crear_variante(pid, sku="CAM-M", nombre="Talla M", precio_dif=3.5,
                             atributos={"Talla": "M"}, codigo_articulo=cod_variante)
    fab.al_limpiar(lambda: cat.eliminar_variante(vid))
    dlg = _ProductoEditor(cod, "Camiseta Test")
    try:
        assert dlg.tbl_var.rowCount() == 1
        assert dlg.tbl_var.item(0, 1).text() == "Talla: M"
        assert dlg.tbl_var.item(0, 2).text() == "CAM-M"
        assert dlg.tbl_var.cellWidget(0, 3).text() == "3.50"
        assert dlg.tbl_var.item(0, 4).text() != "—"   # tiene stock real (artículo propio)
    finally:
        dlg.deleteLater()


def test_matriz_variantes_genera_sin_abrir_dialogos_bloqueantes(app, producto):
    from src.gui.catalogo_gestion import _MatrizVariantesDialog
    _cod, pid = producto
    dlg = _MatrizVariantesDialog(pid, "CAM")
    try:
        # Los 2 ejes de ejemplo ya vienen precargados (Talla S/M/L, Color Rojo/Azul) — 3x2=6.
        dlg._generar()
        assert dlg.tbl_preview.rowCount() == 6
        assert dlg.btn_crear.isEnabled() is True
        skus = {dlg.tbl_preview.item(r, 1).text() for r in range(6)}
        assert len(skus) == 6   # todos distintos
    finally:
        dlg.deleteLater()


def test_matriz_variantes_crear_persiste_en_bd(app, producto):
    from src.db import catalogo as cat
    from src.gui.catalogo_gestion import _MatrizVariantesDialog
    _cod, pid = producto
    dlg = _MatrizVariantesDialog(pid, "CAM")
    try:
        dlg._generar()
        dlg._crear()
        variantes = cat.listar_variantes(pid)
        assert len(variantes) == 6
        for v in variantes:
            cat.eliminar_variante(v["id"])
    finally:
        dlg.deleteLater()


def test_matriz_variantes_sin_ejes_no_habilita_crear(app, producto):
    from src.gui.catalogo_gestion import _MatrizVariantesDialog
    _cod, pid = producto
    dlg = _MatrizVariantesDialog(pid, "CAM")
    try:
        for inp_n, inp_v in dlg._filas_ejes:
            inp_n.clear(); inp_v.clear()
        dlg._generar()
        assert dlg.tbl_preview.rowCount() == 0
        assert dlg.btn_crear.isEnabled() is False
    finally:
        dlg.deleteLater()
