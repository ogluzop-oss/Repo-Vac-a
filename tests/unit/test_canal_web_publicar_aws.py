"""
Fase 5 e-commerce (Catálogo Web / Canal Web) — publicación en un clic a AWS
(`canal_web.publicar_aws`/`estado_publicacion_aws`): reutiliza el backend de almacenamiento YA
existente (`services.storage`, Fase 10/12 AWS-readiness) y el renderizador REAL del storefront
(`backend.storefront.pagina_home`) — nunca finge haber publicado en AWS si en realidad se guardó
en el backend local degradado."""

import os

import pytest

pytestmark = pytest.mark.db

EMP = "T-CW-F5-AWS"
GER = {"perfil": "ADMINISTRADOR", "id": "g5aws"}


@pytest.fixture()
def limpia(db):
    def _b():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM web_config WHERE id_empresa=%s", (EMP,))
            cur.execute("DELETE FROM cd_canal_web WHERE id_empresa=%s", (EMP,))
            conn.commit()
    _b()
    yield
    _b()


@pytest.fixture()
def storage_local(monkeypatch):
    """Fuerza el backend LOCAL (degradable, sin credenciales) y resetea el singleton de
    `services.storage` — igual patrón que `test_aws_readiness_fase10.py`."""
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    from src.services import storage as S
    S._reset_para_tests()
    yield
    S._reset_para_tests()


def test_publicar_aws_respeta_rbac(limpia, storage_local):
    from src.services.comercio_digital import canal_web
    r = canal_web.publicar_aws(id_empresa=EMP, usuario={"perfil": "SIN", "id": "x"})
    assert r.get("error") == "forbidden"


def test_publicar_aws_sin_credenciales_reales_degrada_a_simulado(db, fab, limpia, storage_local):
    from src.services.comercio_digital import canal_web
    fab.web(activa=1, nombre="Tienda AWS Test", id_empresa=EMP)
    r = canal_web.publicar_aws(id_empresa=EMP, usuario=GER)
    assert r["ok"] is True
    assert r["modo"] == "simulado"   # backend local, nunca se finge "aws" sin boto3/bucket real
    assert r["clave"]


def test_estado_publicacion_aws_sin_configurar_informa_no_disponible(limpia, storage_local):
    from src.services.comercio_digital import canal_web
    e = canal_web.estado_publicacion_aws(EMP)
    assert e["disponible"] is False
    assert e["ultima_publicacion"] is None


def test_estado_publicacion_aws_refleja_la_ultima_publicacion(db, fab, limpia, storage_local):
    from src.services.comercio_digital import canal_web
    fab.web(activa=1, nombre="Tienda AWS Test 2", id_empresa=EMP)
    canal_web.publicar_aws(id_empresa=EMP, usuario=GER)
    e = canal_web.estado_publicacion_aws(EMP)
    assert e["ultima_publicacion"]["modo"] == "simulado"
    assert e["ultima_publicacion"]["clave"]


def test_publicar_aws_degrada_honesto_si_el_backend_s3_no_tiene_boto3(db, fab, limpia, monkeypatch):
    from src.services.storage.s3 import boto3_disponible
    if boto3_disponible():
        pytest.skip("boto3 presente en este entorno")
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    from src.services import storage as S
    S._reset_para_tests()
    try:
        from src.services.comercio_digital import canal_web
        fab.web(activa=1, nombre="Tienda AWS Sin Boto3", id_empresa=EMP)
        r = canal_web.publicar_aws(id_empresa=EMP, usuario=GER)
        assert r["ok"] is False
        assert r["modo"] == "no_disponible"
        assert r["motivo"]
    finally:
        monkeypatch.setenv("STORAGE_BACKEND", "local")
        S._reset_para_tests()
