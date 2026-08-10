"""
Cableado GUI (Fase 3): la ventana de videovigilancia muestra los EVENTOS de movimiento del backend y expone
los controles PTZ de forma HONESTA (deshabilitados si ONVIF no está disponible). Smoke offscreen.
"""

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication

from src.db.empresa import empresa_actual_id
from src.services.camaras import deteccion as D
from src.services.camaras import registro as R


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_reproductor_muestra_eventos_y_ptz_honesto(app, fab):
    emp = empresa_actual_id() or fab.EMP_DEFECTO
    cid = R.crear_camara("CamGUI", id_empresa=emp, id_centro="CT", tipo_centro="centro",
                         fuente="rtsp://u:p@1.2.3.4/s")
    fab._borrar("camaras", "id", cid)
    fab._borrar("camaras_eventos", "id_camara", cid)
    cam = R.obtener_camara(cid, id_empresa=emp)
    D.registrar_evento(cam, "movimiento", score=0.33, id_empresa=emp)

    from src.gui.camaras_gui import CamarasWindow
    win = CamarasWindow(usuario={"perfil": "ADMINISTRADOR"})
    try:
        win._abrir_reproductor(cid)                       # abre la cámara → carga eventos + PTZ
        assert win.stack.currentIndex() == 1
        # el evento de movimiento aparece en el panel
        assert win.lst_ev.count() >= 1
        assert "%" in win.lst_ev.item(0).text()
        # PTZ honesto: sin librería ONVIF instalada → botones deshabilitados y aviso claro
        from src.services.camaras import ptz
        if not ptz.disponible():
            assert all(not b.isEnabled() for b in win._ptz_btns)
            assert "no disponible" in win.lbl_ptz.text().lower()
    finally:
        win.deleteLater()
