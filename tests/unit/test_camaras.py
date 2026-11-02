"""
Tests de Videovigilancia (cámaras de seguridad).

Cubre: AISLAMIENTO ESTRICTO (cámaras/grabaciones nunca cruzan departamento ni empresa), CRUD +
renombrar, grabación real (modo simulado/degradable) del fichero del día, fechas disponibles, extracción
de clip y registro en Documentos.
"""

import os
import shutil

import pytest

EMP = "T-CAM-A"
EMP_B = "T-CAM-B"


@pytest.fixture
def limpio(db):
    def _borrar():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            for t in ("camaras", "camaras_grabaciones"):
                cur.execute(f"DELETE FROM {t} WHERE id_empresa IN (%s,%s)", (EMP, EMP_B))
            conn.commit()
    _borrar()
    yield
    _borrar()
    from src.services.camaras.grabacion import _base_grabaciones
    for e in (EMP, EMP_B):
        shutil.rmtree(os.path.join(_base_grabaciones(), e), ignore_errors=True)


def test_aislamiento_y_crud(limpio):
    from src.services import camaras
    c1 = camaras.crear_camara("Entrada", id_empresa=EMP, id_centro="1", tipo_centro="tienda")
    c2 = camaras.crear_camara("Almacén", id_empresa=EMP, id_centro="2", tipo_centro="almacen")
    cb = camaras.crear_camara("Secreta B", id_empresa=EMP_B, id_centro="1")
    assert c1 and c2 and cb
    # Aislamiento por departamento: centro 1 de EMP no ve la cámara del centro 2.
    cams1 = [c["id"] for c in camaras.listar_camaras(EMP, "1")]
    assert c1 in cams1 and c2 not in cams1
    # Aislamiento por empresa: EMP_B no ve las de EMP y viceversa.
    assert camaras.listar_camaras(EMP, "1") and cb not in cams1
    assert camaras.obtener_camara(c1, id_empresa=EMP_B) is None
    assert camaras.obtener_camara(cb, id_empresa=EMP) is None
    # Renombrar (nombre editable).
    assert camaras.renombrar_camara(c1, "Puerta principal", id_empresa=EMP)
    assert camaras.obtener_camara(c1, id_empresa=EMP)["nombre"] == "Puerta principal"
    # No se puede renombrar una cámara de otra empresa.
    assert not camaras.renombrar_camara(cb, "hack", id_empresa=EMP)
    # Eliminar.
    assert camaras.eliminar_camara(c2, id_empresa=EMP)
    assert camaras.obtener_camara(c2, id_empresa=EMP) is None


def test_grabacion_y_clip(limpio):
    from src.services import camaras
    cid = camaras.crear_camara("CAM Test", id_empresa=EMP, id_centro="1", tipo_centro="tienda")
    cam = camaras.obtener_camara(cid, id_empresa=EMP)
    import datetime
    hoy = datetime.date.today().isoformat()
    ruta = camaras.grabar_dia(cam, fecha=hoy, duracion_seg=1)
    assert ruta and os.path.exists(ruta) and os.path.getsize(ruta) > 0
    # Registrada en camaras_grabaciones + Documentos.
    grab = camaras.grabacion_de(cid, hoy, id_empresa=EMP)
    assert grab and grab["estado"] == "cerrada"
    assert hoy in camaras.fechas_disponibles(cid, id_empresa=EMP)
    # Aislamiento de grabaciones: EMP_B no ve la grabación de EMP.
    assert camaras.grabacion_de(cid, hoy, id_empresa=EMP_B) is None
    # Clip (rango → mp4).
    clip = camaras.extraer_clip(cid, hoy, inicio_seg=0, fin_seg=1, id_empresa=EMP)
    assert clip and os.path.exists(clip)
    # En Documentos aparece como tipo 'grabacion'.
    from src.db.documentos import listar_documentos
    docs = listar_documentos(tipo="grabacion", id_empresa=EMP)
    rutas = {os.path.basename(d.get("ruta", "")) for d in docs}
    assert f"{hoy}.mp4" in rutas


def test_fuente_para_fallback_sin_perfiles(limpio):
    """Cámara sin perfiles ONVIF (alta manual, o dada de alta antes de esta capacidad): main y sub
    caen los dos a la URL legacy — cero regresión para el resto del sistema (grabación 24/7, PTZ)."""
    from src.services import camaras
    cid = camaras.crear_camara("Legacy", id_empresa=EMP, id_centro="1", tipo_centro="tienda",
                               fuente="rtsp://u:p@1.2.3.4:554/stream")
    cam = camaras.obtener_camara(cid, id_empresa=EMP)
    assert camaras.fuente_para(cam, "main") == "rtsp://u:p@1.2.3.4:554/stream"
    assert camaras.fuente_para(cam, "sub") == "rtsp://u:p@1.2.3.4:554/stream"


def test_actualizar_perfiles_protege_credenciales(limpio):
    """Mismo criterio que `test_credenciales_rtsp_no_en_claro` (hardening), aplicado a los perfiles
    dual-stream: fuente_main/fuente_sub nunca quedan en claro en las columnas visibles."""
    from src.services import camaras
    cid = camaras.crear_camara("DualStream", id_empresa=EMP, id_centro="1", tipo_centro="tienda")
    ok = camaras.actualizar_perfiles(
        cid, fuente_main="rtsp://usuario:secreto@1.2.3.4:554/main",
        fuente_sub="rtsp://usuario:secreto@1.2.3.4:554/sub", id_empresa=EMP)
    assert ok
    cam = camaras.obtener_camara(cid, id_empresa=EMP)
    assert "secreto" not in (cam["fuente_main"] or "")
    assert "secreto" not in (cam["fuente_sub"] or "")
    assert cam["fuente_main_cifrada"] and cam["fuente_sub_cifrada"]
    assert camaras.fuente_para(cam, "main") == "rtsp://usuario:secreto@1.2.3.4:554/main"
    assert camaras.fuente_para(cam, "sub") == "rtsp://usuario:secreto@1.2.3.4:554/sub"
    # Solo actualizar 'sub': 'main' conserva lo que ya tenía (actualización parcial).
    assert camaras.actualizar_perfiles(cid, fuente_sub="rtsp://usuario:secreto@1.2.3.4:554/sub2",
                                       id_empresa=EMP)
    cam2 = camaras.obtener_camara(cid, id_empresa=EMP)
    assert camaras.fuente_para(cam2, "main") == "rtsp://usuario:secreto@1.2.3.4:554/main"
    assert camaras.fuente_para(cam2, "sub") == "rtsp://usuario:secreto@1.2.3.4:554/sub2"


def test_crear_camara_onvif_degradable_sin_onvif(limpio):
    """Sin ONVIF disponible/cámara alcanzable, `crear_camara_onvif` da de alta la cámara igual que el
    flujo manual de siempre (URL de respaldo), sin perfiles inventados."""
    from src.services import camaras
    cid = camaras.crear_camara_onvif("SinONVIF", "10.255.255.1", "u", "p", id_empresa=EMP,
                                     id_centro="1", tipo_centro="tienda")
    assert cid
    cam = camaras.obtener_camara(cid, id_empresa=EMP)
    assert cam["fuente"] and cam["fuente_main"] is None and cam["fuente_sub"] is None


def test_apifirst_camaras_sin_pyqt():
    import importlib
    import pkgutil
    import src.services.camaras as pkg
    ofensores = []
    for mod in pkgutil.walk_packages(pkg.__path__, prefix="src.services.camaras."):
        try:
            m = importlib.import_module(mod.name)
        except Exception:
            continue
        f = getattr(m, "__file__", None)
        if f and "PyQt6" in open(f, encoding="utf-8").read():
            ofensores.append(mod.name)
    assert ofensores == []
