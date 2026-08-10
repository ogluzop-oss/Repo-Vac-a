"""
Endurecimiento del módulo de videovigilancia (Fase 1): retención/purga de grabaciones antiguas, reconexión
de fuentes reales caídas (sin colgarse ni fabricar imagen) y arranque/parada del grabador continuo (solo
cámaras con fuente REAL; las simuladas de demo no se graban 24/7).
"""

import datetime as dt
import os
import shutil
import time

import pytest

from src.services.camaras import grabacion as G
from src.services.camaras import registro as R


@pytest.fixture
def emp(fab):
    return fab.EMP_DEFECTO


def _limpiar_dir(fab, emp):
    fab.al_limpiar(lambda: shutil.rmtree(os.path.join(G._base_grabaciones(), str(emp)), ignore_errors=True))


def test_purga_por_retencion(fab, emp, db):
    _limpiar_dir(fab, emp)
    carpeta = os.path.join(G._base_grabaciones(), str(emp), "CT", "77")
    os.makedirs(carpeta, exist_ok=True)
    vieja = os.path.join(carpeta, "2020-01-01.mp4")
    reciente = os.path.join(carpeta, dt.date.today().isoformat() + ".mp4")
    open(vieja, "wb").write(b"x")
    open(reciente, "wb").write(b"x")
    with db.obtener_conexion() as c, c.cursor() as cur:
        for fecha, ruta in (("2020-01-01", vieja), (dt.date.today().isoformat(), reciente)):
            cur.execute("INSERT INTO camaras_grabaciones (id_empresa,id_centro,id_camara,fecha,ruta,"
                        "duracion_seg,estado) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (emp, "CT", 77, fecha, ruta, 10, "cerrada"))
    fab._borrar("camaras_grabaciones", "id_camara", 77)

    n = G.purgar_grabaciones_antiguas(dias=30, id_empresa=emp)
    assert n >= 1
    assert not os.path.exists(vieja)      # borrada (fichero)
    assert os.path.exists(reciente)       # conservada
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM camaras_grabaciones WHERE ruta=%s", (vieja,))
        assert cur.fetchone()[0] == 0     # borrada (registro)


def test_reconexion_fuente_real_caida_no_cuelga(fab, emp):
    _limpiar_dir(fab, emp)
    cam = {"id": 77, "id_empresa": emp, "id_centro": "CT", "tipo_centro": "centro",
           "nombre": "CAMX", "fuente": "badsource://inexistente"}
    fab._borrar("camaras_grabaciones", "id_camara", 77)
    t0 = time.time()
    ruta = G.grabar_dia(cam, fecha="2099-12-31", duracion_seg=1, fps=2, reintento_seg=0)
    tardado = time.time() - t0
    # produce un fichero (con fotogramas "SIN SEÑAL"), sin colgarse ni fabricar vigilancia
    assert ruta and os.path.exists(ruta)
    assert tardado < 15


def test_arranca_solo_camaras_reales(fab, emp):
    _limpiar_dir(fab, emp)
    real = R.crear_camara("CamReal", id_empresa=emp, id_centro="CT", tipo_centro="centro",
                          fuente="badsource://x")
    sim = R.crear_camara("CamSim", id_empresa=emp, id_centro="CT", tipo_centro="centro", fuente="simulado")
    fab._borrar("camaras", "id", real)
    fab._borrar("camaras", "id", sim)
    fab._borrar("camaras_grabaciones", "id_camara", real)

    svc = G.RecorderService()                     # instancia propia (no el singleton) para no filtrar hilos
    try:
        n = svc.arrancar_departamento(emp, "CT")
        assert n == 1                              # solo la de fuente real; la simulada se ignora
        assert svc.activas() >= 1
    finally:
        svc.detener()
    time.sleep(0.3)
    assert svc.activas() == 0                      # detener para todos los hilos


# ── Fase 2: rendimiento (stream-copy FFmpeg + fps real) ───────────────────────
def test_ffmpeg_stream_copy_degradable(fab, emp):
    if G._ffmpeg_disponible():
        pytest.skip("ffmpeg instalado; la ruta stream-copy real no se evalúa sin cámara")
    _limpiar_dir(fab, emp)
    cam = {"id": 88, "id_empresa": emp, "id_centro": "CT", "tipo_centro": "centro",
           "nombre": "C", "fuente": "rtsp://x"}
    # sin ffmpeg → degrada limpio (None), sin lanzar ni registrar
    assert G.grabar_dia_ffmpeg(cam, duracion_seg=1) is None


def test_opencv_usa_fps_real_del_stream(fab, emp, tmp_path):
    import cv2
    import numpy as np
    _limpiar_dir(fab, emp)
    src = str(tmp_path / "src.mp4")
    vw = cv2.VideoWriter(src, cv2.VideoWriter_fourcc(*"mp4v"), 15, (64, 48))
    for _ in range(30):
        vw.write(np.zeros((48, 64, 3), dtype=np.uint8))
    vw.release()
    cam = {"id": 88, "id_empresa": emp, "id_centro": "CT", "tipo_centro": "centro",
           "nombre": "CF", "fuente": src}
    fab._borrar("camaras_grabaciones", "id_camara", 88)
    ruta = G.grabar_dia(cam, fecha="2099-12-30", duracion_seg=1, motor="opencv")
    assert ruta and os.path.exists(ruta)
    cap = cv2.VideoCapture(ruta)
    fps_out = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    assert abs(fps_out - 15) < 1.5      # usa el fps REAL del stream (15), no el fijo por defecto (4)


# ── Seguridad: credenciales RTSP cifradas (jamás en claro) ────────────────────
def test_credenciales_rtsp_no_en_claro(fab, emp, db):
    url = "rtsp://admin:S3cr3t@10.0.0.9:554/Streaming/Channels/101"
    cid = R.crear_camara("CamCred", id_empresa=emp, id_centro="CT", tipo_centro="centro", fuente=url)
    fab._borrar("camaras", "id", cid)
    # en la BD, `fuente` está ENMASCARADA (sin usuario:contraseña) y existe `fuente_cifrada`
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT fuente, fuente_cifrada FROM camaras WHERE id=%s", (cid,))
        fuente_bd, cifrada = cur.fetchone()
    assert "S3cr3t" not in fuente_bd and "admin" not in fuente_bd
    assert fuente_bd == "rtsp://10.0.0.9:554/Streaming/Channels/101"
    assert cifrada and "S3cr3t" not in cifrada          # cifrado, no en claro
    # la URL REAL (con credenciales) se recupera solo al conectar
    cam = R.obtener_camara(cid, id_empresa=emp)
    assert R.fuente_efectiva(cam) == url


def test_fuente_sin_credenciales_no_se_cifra(fab, emp, db):
    for url in ("rtsp://10.0.0.9:554/stream", "simulado"):
        cid = R.crear_camara("Cam", id_empresa=emp, id_centro="CT", tipo_centro="centro", fuente=url)
        fab._borrar("camaras", "id", cid)
        with db.obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT fuente, fuente_cifrada FROM camaras WHERE id=%s", (cid,))
            fuente_bd, cifrada = cur.fetchone()
        assert fuente_bd == url and cifrada is None      # sin secreto → no se cifra


def test_actualizar_fuente_protege_credenciales(fab, emp, db):
    cid = R.crear_camara("Cam", id_empresa=emp, id_centro="CT", tipo_centro="centro", fuente="simulado")
    fab._borrar("camaras", "id", cid)
    assert R.actualizar_fuente(cid, "rtsp://user:pass@1.2.3.4/s", id_empresa=emp)
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT fuente, fuente_cifrada FROM camaras WHERE id=%s", (cid,))
        fuente_bd, cifrada = cur.fetchone()
    assert "pass" not in fuente_bd and cifrada
    assert R.fuente_efectiva(R.obtener_camara(cid, id_empresa=emp)) == "rtsp://user:pass@1.2.3.4/s"
