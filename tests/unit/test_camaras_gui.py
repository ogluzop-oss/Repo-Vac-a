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


def test_gestion_deshabilitada_sin_permiso(app, monkeypatch):
    """RBAC granular (Parte F): sin 'camaras.gestionar', los botones de alta/baja quedan
    deshabilitados en la propia construcción del sidebar — mismo patrón que el resto del proyecto
    (monkeypatch de `autorizacion.puede`, ver test_mfa_reset.py)."""
    monkeypatch.setattr("src.services.autorizacion.puede",
                        lambda usuario, permiso, **k: permiso == "camaras.ver")
    from src.gui.camaras_gui import CamarasWindow
    win = CamarasWindow(usuario={"perfil": "OPERARIO"})
    try:
        assert win.stack is not None                 # 'camaras.ver' sí concedido: ventana normal
        assert not win.btn_anadir.isEnabled()
        assert not win.btn_eliminar.isEnabled()
    finally:
        win.deleteLater()


def test_sin_permiso_ver_no_construye_ventana(app, monkeypatch):
    monkeypatch.setattr("src.services.autorizacion.puede", lambda usuario, permiso, **k: False)
    from src.gui.camaras_gui import CamarasWindow
    win = CamarasWindow(usuario={"perfil": "OPERARIO"})
    try:
        assert win.stack is None                      # sin 'camaras.ver': no se construye la rejilla
    finally:
        win.deleteLater()


def test_camara_live_worker_honesto_sin_senal(app):
    """CamaraLiveWorker (vídeo en vivo, Parte D): sobre una fuente inexistente, emite 'sin_senal' en
    vez de colgarse o fabricar imagen — smoke test acotado en el tiempo, sin necesitar cámara real."""
    import time

    from PyQt6.QtCore import QThread

    from src.gui.camaras_gui import CamaraLiveWorker

    worker = CamaraLiveWorker("badsource://inexistente", fps=10, reintento_seg=1)
    recibidos = []
    worker.sin_senal.connect(lambda motivo: recibidos.append(motivo))
    hilo = QThread()
    worker.moveToThread(hilo)
    hilo.started.connect(worker.run)
    hilo.start()
    t0 = time.time()
    while not recibidos and time.time() - t0 < 5:
        QApplication.processEvents()
        time.sleep(0.05)
    worker.detener()
    hilo.quit()
    hilo.wait(2000)
    assert recibidos, "debe informar 'sin señal' en vez de colgarse"
