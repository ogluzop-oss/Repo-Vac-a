"""
Fase 3 videovigilancia: detección de movimiento REAL (OpenCV), eventos aislados por empresa+centro, y
control PTZ/ONVIF DEGRADABLE (honesto: sin librería/soporte → no finge movimiento).
"""

import os
import shutil

import pytest

from src.services.camaras import deteccion as D
from src.services.camaras import grabacion as G
from src.services.camaras import ptz as P
from src.services.camaras import registro as R


@pytest.fixture
def emp(fab):
    return fab.EMP_DEFECTO


def _limpiar_dir(fab, emp):
    fab.al_limpiar(lambda: shutil.rmtree(os.path.join(G._base_grabaciones(), str(emp)), ignore_errors=True))


def _video(ruta, *, mover, n=20, fps=10, w=160, h=120):
    """Crea un vídeo de prueba: un bloque blanco que se DESPLAZA (mover=True) o estático (mover=False)."""
    import cv2
    import numpy as np
    vw = cv2.VideoWriter(ruta, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    for i in range(n):
        fr = np.zeros((h, w, 3), dtype=np.uint8)
        x = (10 + i * 24) % (w - 24) if mover else 10
        fr[40:64, x:x + 24] = 255
        vw.write(fr)
    vw.release()


def test_detecta_movimiento_en_grabacion(tmp_path):
    src = str(tmp_path / "mov.mp4")
    _video(src, mover=True)
    eventos = D.analizar_grabacion(src, cooldown_seg=0)      # sin antirrebote: cuenta todos
    assert len(eventos) >= 1
    assert all("instante_seg" in e and e["score"] > 0 for e in eventos)


def test_video_estatico_no_genera_eventos(tmp_path):
    src = str(tmp_path / "quieto.mp4")
    _video(src, mover=False)
    assert D.analizar_grabacion(src, cooldown_seg=0) == []    # nada se mueve → NO inventa eventos


def test_grabacion_opencv_registra_eventos(fab, emp, tmp_path):
    _limpiar_dir(fab, emp)
    src = str(tmp_path / "cam.mp4")
    _video(src, mover=True)
    cid = R.crear_camara("CamMov", id_empresa=emp, id_centro="CT", tipo_centro="centro", fuente=src)
    fab._borrar("camaras", "id", cid)
    fab._borrar("camaras_grabaciones", "id_camara", cid)
    fab._borrar("camaras_eventos", "id_camara", cid)
    cam = R.obtener_camara(cid, id_empresa=emp)
    ruta = G.grabar_dia(cam, fecha="2099-11-01", duracion_seg=1, motor="opencv")
    assert ruta and os.path.exists(ruta)
    evs = D.listar_eventos(id_empresa=emp, id_centro="CT", id_camara=cid)
    assert len(evs) >= 1 and evs[0]["tipo"] == "movimiento"


def test_eventos_aislados_por_empresa_y_centro(fab, emp):
    cam = {"id": 777, "id_empresa": emp, "id_centro": "CT"}
    eid = D.registrar_evento(cam, "movimiento", score=0.42, id_empresa=emp)
    fab._borrar("camaras_eventos", "id", eid)
    assert eid
    assert len(D.listar_eventos(id_empresa=emp, id_centro="CT", id_camara=777)) >= 1
    # otro departamento de la MISMA empresa NO lo ve
    assert D.listar_eventos(id_empresa=emp, id_centro="OTRO", id_camara=777) == []
    # otra empresa NO lo ve
    otra = "00000000-0000-0000-0000-000000000000"
    assert D.listar_eventos(id_empresa=otra, id_centro="CT", id_camara=777) == []


def test_ptz_degradable_honesto(emp):
    cam = {"id": 1, "id_empresa": emp, "id_centro": "CT", "fuente": "rtsp://u:p@1.2.3.4/s"}
    caps = P.capacidades(cam)
    assert isinstance(caps, dict) and "onvif" in caps and "ptz" in caps
    assert P.mover(cam, "direccion_invalida")["ok"] is False        # dirección no válida
    r = P.mover(cam, "izquierda")
    assert isinstance(r, dict) and "ok" in r and "motivo" in r
    if not P._onvif_disponible():                                   # sin librería → honesto, no finge
        assert r["ok"] is False and "ONVIF" in r["motivo"]
        assert caps["onvif"] is False
