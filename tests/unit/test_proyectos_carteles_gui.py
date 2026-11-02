"""
Carteles/Folletos publicitarios — editor interactivo (`gui.proyectos_carteles_gui.CartelesTab`).
Offscreen (QT_QPA_PLATFORM=offscreen, fijado en conftest) + BD real: construye el widget, añade
elementos al lienzo (sin pasar por los QDialog modales de "Nuevo diseño"/Asistente IA, que no son
automatizables sin interacción) y verifica que el guardado persiste el modelo de contenido y que
el panel de propiedades reacciona a la selección.

Rama funcional INDEPENDIENTE del tablero Kanban (feedback directo del usuario): la pestaña debe
funcionar sin crear ni seleccionar ningún proyecto — `cargar()` (llamado por `ProyectosWindow` al
ENTRAR en la pestaña) repone siempre la vista de galería, sin depender de ningún `id_proyecto`.
"""

import os

import pytest

from src.gui.proyectos_carteles_gui import CartelesTab
from src.services.proyectos import carteles as C

pytestmark = pytest.mark.db


@pytest.fixture
def emp(fab):
    return fab.EMP_DEFECTO


@pytest.fixture(autouse=True)
def _limpia(db, emp):
    yield
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT thumbnail_path FROM proyecto_carteles WHERE id_empresa=%s", (emp,))
        rutas = [r[0] if not isinstance(r, dict) else r["thumbnail_path"] for r in cur.fetchall()]
        cur.execute("DELETE FROM proyecto_carteles WHERE id_empresa=%s", (emp,))
        conn.commit()
    for r in rutas:
        if r and os.path.exists(r):
            try:
                os.remove(r)
            except OSError:
                pass


def _tab():
    return CartelesTab(usuario={"id": 1}, puede_fn=lambda _p: True)


def test_tab_funciona_sin_ningun_proyecto(emp):
    tab = _tab()
    tab.cargar()
    assert not tab._lbl_vacio.isHidden()   # sin diseños todavía -> placeholder visible
    assert tab._btn_nuevo.isEnabled()      # nunca deshabilitado por falta de proyecto


def test_cargar_repone_siempre_la_vista_de_galeria(emp):
    cid = C.crear_cartel("Diseño de prueba", formato="cartel_a3", id_empresa=emp)
    tab = _tab()
    tab._abrir_editor(cid)
    assert tab.stack.currentIndex() == 1       # se quedó dentro del editor
    tab.cargar()
    assert tab.stack.currentIndex() == 0       # "entrar" en la pestaña repone la galería


def test_abrir_editor_anadir_elementos_guardar_y_releer(emp):
    cid = C.crear_cartel("Diseño de prueba", formato="cartel_a3", id_empresa=emp)
    tab = _tab()
    tab._abrir_editor(cid)
    assert tab.stack.currentIndex() == 1

    tab._anadir_texto()
    tab._anadir_forma("rectangulo")
    # El QR se añade vía QInputDialog (modal) en producción; aquí se construye el item
    # directamente para probar la lógica de creación/guardado sin depender de interacción.
    el_qr = {"tipo": "qr", "x": 5, "y": 5, "w": 20, "h": 20, "payload": "https://x.test",
            "z": tab._siguiente_z()}
    item_qr = tab._crear_item(el_qr)
    tab.scene.addItem(item_qr)

    assert len(tab._items_de_contenido()) == 3
    tab._guardar()

    c = C.obtener_cartel(cid, id_empresa=emp)
    assert len(c["contenido"]["elementos"]) == 3
    assert {e["tipo"] for e in c["contenido"]["elementos"]} == {"texto", "forma", "qr"}
    assert c["thumbnail_path"] and os.path.exists(c["thumbnail_path"])


def test_seleccionar_texto_muestra_editor_de_texto_en_el_panel(emp):
    cid = C.crear_cartel("Panel", formato="cartel_a3", id_empresa=emp)
    tab = _tab()
    tab._abrir_editor(cid)
    tab._anadir_texto()

    seleccion = tab.scene.selectedItems()
    assert len(seleccion) == 1 and seleccion[0].data(0)["tipo"] == "texto"
    from PyQt6.QtWidgets import QPlainTextEdit
    hay_editor_texto = any(
        isinstance(tab._panel_cuerpo.itemAt(i).widget(), QPlainTextEdit)
        for i in range(tab._panel_cuerpo.count()) if tab._panel_cuerpo.itemAt(i).widget())
    assert hay_editor_texto


def test_editar_texto_en_el_panel_actualiza_el_item(emp):
    cid = C.crear_cartel("Edicion", formato="cartel_a3", id_empresa=emp)
    tab = _tab()
    tab._abrir_editor(cid)
    tab._anadir_texto()
    item = tab.scene.selectedItems()[0]
    tab._aplicar_texto(item, "Nuevo texto editado")
    assert item.toPlainText() == "Nuevo texto editado"
    assert item.data(0)["texto"] == "Nuevo texto editado"


def test_traer_al_frente_y_enviar_al_fondo_cambian_z(emp):
    cid = C.crear_cartel("Capas", formato="cartel_a3", id_empresa=emp)
    tab = _tab()
    tab._abrir_editor(cid)
    tab._anadir_forma("rectangulo")
    item = tab.scene.selectedItems()[0]
    z_antes = item.zValue()
    tab._enviar_al_fondo()
    assert item.zValue() < z_antes
    tab._traer_al_frente()
    assert item.zValue() > z_antes


def test_borrar_seleccion_quita_el_elemento_del_lienzo(emp):
    cid = C.crear_cartel("Borrado", formato="cartel_a3", id_empresa=emp)
    tab = _tab()
    tab._abrir_editor(cid)
    tab._anadir_texto()
    assert len(tab._items_de_contenido()) == 1
    tab._borrar_seleccion()
    assert len(tab._items_de_contenido()) == 0


def test_redimensionar_forma_actualiza_el_tamano_guardado(emp):
    cid = C.crear_cartel("Redimension", formato="cartel_a3", id_empresa=emp)
    tab = _tab()
    tab._abrir_editor(cid)
    tab._anadir_forma("rectangulo")
    item = tab.scene.selectedItems()[0]
    tab._aplicar_tamano(item, 80, 50)
    tab._guardar()
    c = C.obtener_cartel(cid, id_empresa=emp)
    forma = next(e for e in c["contenido"]["elementos"] if e["tipo"] == "forma")
    assert abs(forma["w"] - 80) < 0.5 and abs(forma["h"] - 50) < 0.5


def test_guias_de_sangrado_y_plegado_se_pintan_para_diptico(emp):
    cid = C.crear_cartel("Díptico guías", formato="folleto_a4_diptico", id_empresa=emp)
    tab = _tab()
    tab._abrir_editor(cid)
    guias = [it for it in tab.scene.items() if it.data(1) == "guia"]
    # Sangrado (1 rectángulo) + 1 línea de plegado (díptico) = al menos 2 guías.
    assert len(guias) >= 2
    tab.chk_sangrado.setChecked(False)
    tab.chk_plegado.setChecked(False)
    guias_tras_ocultar = [it for it in tab.scene.items() if it.data(1) == "guia"]
    assert guias_tras_ocultar == []
