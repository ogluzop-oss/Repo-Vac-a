"""
Fase Productividad · GUI (offscreen, BD real): pestaña nueva en Ventas con sus 4 secciones
exactas (Facturación Centro/Empleados/Campaña Centro/Campaña Empleados) + gate RBAC (ADMINISTRADOR
y OPERARIO son solo-lectura; SUPERADMIN edita).
"""

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_pestana_productividad_existe_con_las_4_secciones(app, db):
    import src.gui.ventas as mod
    w = mod.VentasAnaliticaWindow()
    try:
        w._cambiar_tab(2)
        panel = w.stack.widget(2)
        tabs = panel.findChild(mod.QTabWidget)
        assert tabs is not None
        assert tabs.count() == 4
        titulos = [tabs.tabText(i) for i in range(4)]
        assert titulos == ["Facturación centro", "Facturación empleados",
                           "Facturación campaña centro", "Facturación campaña empleados"]
    finally:
        w.deleteLater()


def test_sidebar_productividad_es_la_tercera_pestana(app, db):
    import src.gui.ventas as mod
    w = mod.VentasAnaliticaWindow()
    try:
        assert len(w._sidebar_btns) == 3
        assert w._sidebar_btns[2].text() == "PRODUCTIVIDAD"
    finally:
        w.deleteLater()


def test_rbac_operario_es_solo_lectura(app, db):
    from src.gui.ventas import _ProdCentroTab
    from src.db.empresa import EMPRESA_DEFAULT_ID
    usuario = {"id": 1, "perfil": "OPERARIO"}
    tab = _ProdCentroTab(usuario, EMPRESA_DEFAULT_ID)
    try:
        # isVisible() depende de que la ventana TOP-LEVEL esté mostrada (no es el caso aquí, el
        # widget nunca se muestra) — isHidden() sí refleja el estado explícito que fija `setVisible`.
        assert tab.ed_objetivo.isHidden() is True
        assert tab.btn_guardar.isHidden() is True
    finally:
        tab.deleteLater()


def test_rbac_superadmin_puede_editar(app, db):
    from src.gui.ventas import _ProdCentroTab
    from src.db.empresa import EMPRESA_DEFAULT_ID
    usuario = {"id": 1, "perfil": "SUPERADMIN"}
    tab = _ProdCentroTab(usuario, EMPRESA_DEFAULT_ID)
    try:
        assert tab.ed_objetivo.isHidden() is False
        assert tab.btn_guardar.isHidden() is False
    finally:
        tab.deleteLater()


def test_combo_periodos_tiene_los_8_tipos_con_mensual_por_defecto():
    from src.gui.ventas import _combo_periodos
    cb = _combo_periodos()
    try:
        assert cb.count() == 8
        assert cb.currentData() == "mensual"
    finally:
        cb.deleteLater()


def test_tabs_sin_borde_y_mismo_estilo_que_migrar_datos(app, db):
    """El pane sin borde fino gris + el mismo QTabBar que "Migrar datos" (ambos usan literalmente
    `foundation.tokens.qss_tabs()`, no una hoja de estilo recreada a mano) — pedido explícito."""
    import src.gui.ventas as mod
    from src.gui.foundation import tokens as T
    w = mod.VentasAnaliticaWindow()
    try:
        w._cambiar_tab(2)
        tabs = w.stack.widget(2).findChild(mod.QTabWidget)
        ss = tabs.styleSheet()
        assert ss == T.qss_tabs()
        assert "QTabWidget::pane{border:none" in ss
        # La pestaña seleccionada NUNCA pierde el font-weight:700 de la regla base (solo cambia de
        # color) — pedido explícito ("que no pierda el efecto bold"): la regla base ya lo fija y
        # `:selected` nunca lo sobreescribe.
        assert "QTabBar::tab{" in ss and "font-weight:700" in ss
        bloque_selected = ss.split("QTabBar::tab:selected{", 1)[1].split("}", 1)[0]
        assert "font-weight" not in bloque_selected
    finally:
        w.deleteLater()


def test_flechas_usan_el_mismo_diseno_que_el_boton_volver_de_crm_presupuestos(app, db):
    from src.gui.ventas import _ProdCentroTab
    from src.gui.catalogo_gestion import _btn
    from src.db.empresa import EMPRESA_DEFAULT_ID
    usuario = {"id": 1, "perfil": "SUPERADMIN"}
    tab = _ProdCentroTab(usuario, EMPRESA_DEFAULT_ID)
    referencia = _btn("←", None, primary=True)
    try:
        # Mismo diseño base (color/borde/hover/disabled) + el glifo +3pt pedido explícito (+2pt:
        # a 16px quedaba descentrado verticalmente dentro de la caja 44x44; +1pt más después) +
        # nudge hacia arriba (padding-bottom) para compensar el desplazamiento hacia abajo que
        # introdujo ese aumento de tamaño.
        assert (tab.btn_atras.styleSheet()
               == referencia.styleSheet() + "QPushButton{font-size:19px;padding-bottom:2px;}")
        assert tab.btn_atras.size() == referencia.size()
    finally:
        tab.deleteLater()
        referencia.deleteLater()


def test_barra_progreso_tamano_texto_13px():
    from src.gui.ventas import _SS_PROD_BARRA
    assert "font-size:13px" in _SS_PROD_BARRA


def test_facturacion_empleados_muestra_rango_de_fechas_sin_empleado_elegido(app, db):
    """Bug reportado: antes, sin un empleado todavía elegido, la pestaña mostraba "—" en vez del
    rango de fechas del periodo (al contrario que "Facturación Centro", que sí lo muestra siempre).
    Ahora el rango se calcula SOLO a partir del periodo + cursor, igual en ambas pestañas."""
    from src.gui.ventas import _ProdEmpleadoTab
    from src.db.empresa import EMPRESA_DEFAULT_ID
    usuario = {"id": 1, "perfil": "SUPERADMIN"}
    tab = _ProdEmpleadoTab(usuario, EMPRESA_DEFAULT_ID)
    try:
        assert tab.cb_empleado.currentData() is None   # sin empleado elegido
        assert tab.lbl_periodo.text() != "—"
        assert "/" in tab.lbl_periodo.text() and "–" in tab.lbl_periodo.text()
    finally:
        tab.deleteLater()


def test_campos_fecha_campana_son_neondateedit_no_fechafilter(app, db):
    """El triángulo del desplegable debe ser el icono estándar `combo_arrow.png` (como el resto de
    desplegables de la app), no el triángulo cian pintado a mano de `tpv._FechaFilter`."""
    from src.gui.ventas import _ProdCampanaCentroTab, _NeonDateEdit
    from src.db.empresa import EMPRESA_DEFAULT_ID
    usuario = {"id": 1, "perfil": "SUPERADMIN"}
    tab = _ProdCampanaCentroTab(usuario, EMPRESA_DEFAULT_ID)
    try:
        assert isinstance(tab.df_desde, _NeonDateEdit)
        assert isinstance(tab.df_hasta, _NeonDateEdit)
        assert "font-weight:700" in tab.df_desde.styleSheet()
        assert "font-size:13px" in tab.df_desde.styleSheet()
    finally:
        tab.deleteLater()


def test_pestanas_productividad_tienen_transicion_instalada(app, db):
    import src.gui.ventas as mod
    w = mod.VentasAnaliticaWindow()
    try:
        w._cambiar_tab(2)
        tabs = w.stack.widget(2).findChild(mod.QTabWidget)
        assert tabs.property("_trans_ok") is True
    finally:
        w.deleteLater()


# ── Centro IMPLÍCITO (reconsiderado): nunca un desplegable, se resuelve solo ────────────────
def test_ningun_tab_de_productividad_tiene_desplegable_de_centro(app, db):
    """Pedido explícito (reconsiderado): el filtro "Centro" se retira de las 4 secciones — el
    centro es SIEMPRE el que el SUPERADMIN tiene conectado o el vinculado al ADMINISTRADOR/
    OPERARIO, nunca uno elegible a mano."""
    from src.gui.ventas import (_ProdCentroTab, _ProdEmpleadoTab, _ProdCampanaCentroTab,
                                _ProdCampanaEmpleadoTab)
    from src.db.empresa import EMPRESA_DEFAULT_ID
    usuario = {"id": 1, "perfil": "SUPERADMIN"}
    tabs = [cls(usuario, EMPRESA_DEFAULT_ID) for cls in
            (_ProdCentroTab, _ProdEmpleadoTab, _ProdCampanaCentroTab, _ProdCampanaEmpleadoTab)]
    try:
        for t in tabs:
            assert not hasattr(t, "cb_centro")
            assert hasattr(t, "lbl_centro")   # etiqueta de SOLO LECTURA en su lugar
    finally:
        for t in tabs:
            t.deleteLater()


def test_prod_centro_actual_superadmin_usa_tienda_conectada(app, db, monkeypatch):
    from src.gui.ventas import _prod_centro_actual
    from src.db.empresa import EMPRESA_DEFAULT_ID
    monkeypatch.setattr("src.db.empresa.tienda_actual_id", lambda: 777)
    monkeypatch.setattr("src.db.centros.listar_centros",
                        lambda *a, **k: [{"id_centro": 1, "id_tienda": 777, "nombre_centro": "A"},
                                         {"id_centro": 2, "id_tienda": 999, "nombre_centro": "B"}])
    c = _prod_centro_actual({"id": 1, "perfil": "SUPERADMIN"}, EMPRESA_DEFAULT_ID)
    assert c is not None and c["nombre_centro"] == "A"


def test_prod_centro_actual_superadmin_sin_tienda_conectada_es_honesto_none(app, db, monkeypatch):
    from src.gui.ventas import _prod_centro_actual
    from src.db.empresa import EMPRESA_DEFAULT_ID
    monkeypatch.setattr("src.db.empresa.tienda_actual_id", lambda: None)
    c = _prod_centro_actual({"id": 1, "perfil": "SUPERADMIN"}, EMPRESA_DEFAULT_ID)
    assert c is None


def test_prod_centro_actual_operario_usa_su_propio_centro_vinculado(app, db, monkeypatch):
    from src.gui.ventas import _prod_centro_actual
    from src.db.empresa import EMPRESA_DEFAULT_ID
    monkeypatch.setattr("src.db.centros.listar_centros",
                        lambda *a, **k: [{"id_centro": 1, "codigo_centro": "CDT-001", "nombre_centro": "Mío"},
                                         {"id_centro": 2, "codigo_centro": "CDT-002", "nombre_centro": "Otro"}])
    c = _prod_centro_actual({"id": 5, "perfil": "OPERARIO", "centro_codigo": "CDT-001"},
                            EMPRESA_DEFAULT_ID)
    assert c is not None and c["nombre_centro"] == "Mío"


def test_prod_centro_actual_operario_sin_centro_vinculado_es_honesto_none(app, db):
    from src.gui.ventas import _prod_centro_actual
    from src.db.empresa import EMPRESA_DEFAULT_ID
    c = _prod_centro_actual({"id": 5, "perfil": "OPERARIO"}, EMPRESA_DEFAULT_ID)
    assert c is None


def test_labels_y_combos_centro_periodo_facturacion_centro_bold_13px(app, db):
    from src.gui.ventas import _ProdCentroTab
    from src.db.empresa import EMPRESA_DEFAULT_ID
    usuario = {"id": 1, "perfil": "SUPERADMIN"}
    tab = _ProdCentroTab(usuario, EMPRESA_DEFAULT_ID)
    try:
        assert "font-weight:700" in tab.cb_periodo.styleSheet()
        assert "font-size:13px" in tab.cb_periodo.styleSheet()
    finally:
        tab.deleteLater()


def test_combos_empleado_y_periodo_facturacion_empleados_bold_13px(app, db):
    from src.gui.ventas import _ProdEmpleadoTab
    from src.db.empresa import EMPRESA_DEFAULT_ID
    usuario = {"id": 1, "perfil": "SUPERADMIN"}
    tab = _ProdEmpleadoTab(usuario, EMPRESA_DEFAULT_ID)
    try:
        for cb in (tab.cb_empleado, tab.cb_periodo):
            assert "font-weight:700" in cb.styleSheet()
            assert "font-size:13px" in cb.styleSheet()
    finally:
        tab.deleteLater()


def test_combo_campana_bold_13px_en_ambas_campanas(app, db):
    from src.gui.ventas import _ProdCampanaCentroTab, _ProdCampanaEmpleadoTab
    from src.db.empresa import EMPRESA_DEFAULT_ID
    usuario = {"id": 1, "perfil": "SUPERADMIN"}
    for cls in (_ProdCampanaCentroTab, _ProdCampanaEmpleadoTab):
        tab = cls(usuario, EMPRESA_DEFAULT_ID)
        try:
            assert "font-weight:700" in tab.cb_campana.styleSheet()
            assert "font-size:13px" in tab.cb_campana.styleSheet()
        finally:
            tab.deleteLater()
