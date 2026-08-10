"""
Migración de FOTOS de artículo (importador maestro): el importador auto-mapea la columna de imagen
(imagen/foto/url…) y lleva la imagen a una RUTA LOCAL que la ficha del artículo muestra (`articulos.imagen`).
Fichero local → se copia; URL http(s) → se descargaría (no se prueba red). Idempotente (COALESCE: no borra la
imagen previa al reimportar sin ella).
"""

import os

import pytest

from src.services import importacion as I


@pytest.fixture
def emp(fab):
    return fab.EMP_DEFECTO


def _imagen(db, emp, cod):
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("SELECT imagen FROM articulos WHERE codigo=%s AND id_empresa=%s", (cod, emp))
        r = cur.fetchone()
        if not r:
            return None
        return r[0] if not isinstance(r, dict) else r.get("imagen")


def test_mapeo_detecta_columna_de_imagen():
    for col in ("imagen", "foto", "image", "url_imagen", "imageUrl"):
        m = I.sugerir_mapeo(["codigo", "nombre", col], I.PRODUCTOS)
        assert m.get("imagen") == col, f"no mapeó {col}"


def test_importa_foto_local_y_es_visible(emp, db, fab, tmp_path):
    fab._borrar("articulos", "codigo", "IMG-1")
    origen = tmp_path / "foto_prod.png"
    origen.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)     # bytes de una "imagen"
    filas = [{"codigo": "IMG-1", "nombre": "Producto con foto", "foto": str(origen)}]

    inf = I.simular_filas(filas, id_empresa=emp)
    assert inf["ok"] and inf["resumen"]["con_imagen"] == 1

    res = I.ejecutar_filas(filas, id_empresa=emp, origen="test-fotos")
    assert res["ok"] and res["imagenes"] == 1
    ruta = _imagen(db, emp, "IMG-1")
    assert ruta and os.path.isfile(ruta)                     # se copió a una ruta local existente
    assert os.path.abspath(ruta) != os.path.abspath(str(origen))   # copiada dentro de Smart Manager
    fab.al_limpiar(lambda: os.path.exists(ruta) and os.remove(ruta))


def test_reimportar_sin_foto_conserva_la_imagen(emp, db, fab, tmp_path):
    fab._borrar("articulos", "codigo", "IMG-2")
    origen = tmp_path / "f2.png"; origen.write_bytes(b"\x89PNG\r\n\x1a\n" + b"1" * 32)
    I.ejecutar_filas([{"codigo": "IMG-2", "nombre": "Con foto", "foto": str(origen)}], id_empresa=emp)
    antes = _imagen(db, emp, "IMG-2")
    assert antes and os.path.isfile(antes)
    fab.al_limpiar(lambda: os.path.exists(antes) and os.remove(antes))
    # reimportación SIN columna de foto → la imagen NO se borra (COALESCE)
    I.ejecutar_filas([{"codigo": "IMG-2", "nombre": "Sin foto ahora"}], id_empresa=emp)
    assert _imagen(db, emp, "IMG-2") == antes
