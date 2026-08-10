"""
Tests · Fase 12 — cierre H1 (storage documental CREATE/READ/DOWNLOAD/DELETE + legacy) y H3 (idempotencia DB
multi-worker atómica). Backends locales; sin AWS. Aislamiento multi-tenant estricto en cada camino.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytestmark = pytest.mark.db


@pytest.fixture()
def storage_local(tmp_path):
    os.environ["STORAGE_BACKEND"] = "local"
    os.environ["STORAGE_LOCAL_ROOT"] = str(tmp_path / "storage")
    from src.services import storage as S
    S._reset_para_tests()
    yield S.obtener_storage()
    S._reset_para_tests()
    os.environ.pop("STORAGE_LOCAL_ROOT", None)


def _crear_doc(tmp_path, id_empresa, tipo="factura", contenido=b"data-A", nombre="F1.pdf"):
    from src.db import documentos as D
    ruta = tmp_path / nombre
    ruta.write_bytes(contenido)
    doc_id = D.registrar_documento(str(ruta), tipo=tipo, nombre=nombre, id_empresa=id_empresa)
    return doc_id


# ── H1 · CREATE guarda storage_key ────────────────────────────────────────────
def test_h1_create_guarda_storage_key(storage_local, tmp_path, db):
    from src.db import documentos as D
    doc_id = _crear_doc(tmp_path, "F12-A", contenido=b"factura-A")
    assert doc_id
    doc = D.obtener_documento(doc_id)
    assert doc["storage_key"] == "tenant/F12-A/factura/F1.pdf"
    assert doc["storage_backend"] == "local" and doc["migracion_estado"] == "MIGRATED"
    # El binario es recuperable por el tenant correcto.
    assert storage_local.leer("F12-A", doc["storage_key"]) == b"factura-A"


# ── H1 · READ con aislamiento y RBAC ──────────────────────────────────────────
def test_h1_read_tenant_aislado(storage_local, tmp_path):
    from src.services.storage import documentos as SD
    doc_id = _crear_doc(tmp_path, "F12-A", contenido=b"secreto-A")
    r = SD.abrir_documento(doc_id, id_empresa="F12-A")
    assert r["ok"] and r["datos"] == b"secreto-A"
    # Otro tenant NO puede abrir el documento (aunque conozca el id).
    r2 = SD.abrir_documento(doc_id, id_empresa="F12-B")
    assert r2["ok"] is False and "otro tenant" in r2["error"]


def test_h1_url_descarga_tenant(storage_local, tmp_path):
    from src.services.storage import documentos as SD
    doc_id = _crear_doc(tmp_path, "F12-A")
    assert SD.url_descarga(doc_id, id_empresa="F12-A")["ok"] is True
    assert SD.url_descarga(doc_id, id_empresa="F12-B")["ok"] is False   # cross-tenant bloqueado


# ── H1 · DELETE por StorageProvider, sin pérdida silenciosa ───────────────────
def test_h1_delete_seguro(storage_local, tmp_path):
    from src.db import documentos as D
    from src.services.storage import documentos as SD
    doc_id = _crear_doc(tmp_path, "F12-A", contenido=b"borrar-A")
    key = D.obtener_documento(doc_id)["storage_key"]
    # Cross-tenant no puede borrar.
    assert SD.eliminar_documento(doc_id, id_empresa="F12-B")["ok"] is False
    assert storage_local.existe("F12-A", key) is True
    # El tenant dueño borra: objeto y registro fuera.
    assert SD.eliminar_documento(doc_id, id_empresa="F12-A")["ok"] is True
    assert storage_local.existe("F12-A", key) is False
    assert D.obtener_documento(doc_id) is None


# ── H1 · Migración legacy idempotente ─────────────────────────────────────────
def test_h1_migracion_legacy_idempotente(storage_local, tmp_path, db):
    from src.db import documentos as D
    from src.services.storage import documentos as SD
    doc_id = _crear_doc(tmp_path, "F12-A", contenido=b"legacy-A", nombre="LEG.pdf")
    # Simula documento LEGACY: limpia la storage_key persistida.
    with db.obtener_conexion() as c:
        cur = c.cursor()
        cur.execute("UPDATE documentos_registro SET storage_key=NULL, migracion_estado='LEGACY' "
                    "WHERE id_documento=%s", (doc_id,))
        c.commit()
    r1 = SD.migrar_registro_legacy(doc_id, id_empresa="F12-A")
    assert r1["ok"] and r1["estado"] == "MIGRATED" and r1["storage_key"]
    # Repetir NO duplica ni falla (idempotente/reanudable).
    r2 = SD.migrar_registro_legacy(doc_id, id_empresa="F12-A")
    assert r2["ok"] and r2["estado"] == "MIGRATED" and r2["storage_key"] == r1["storage_key"]


# ── H1 · Seguridad: no se acepta storage_key/tenant del cliente ───────────────
def test_h1_no_acepta_clave_del_cliente(storage_local, tmp_path):
    from src.services.storage import documentos as SD
    _crear_doc(tmp_path, "F12-A")
    # La API resuelve SIEMPRE por id_documento en BD; un id inexistente no da acceso a nada.
    assert SD.abrir_documento("id-inventado", id_empresa="F12-A")["ok"] is False
    assert SD.abrir_documento("id-inventado", id_empresa="")["ok"] is False


# ── H3 · Idempotencia DB multi-worker (reclamo atómico) ───────────────────────
def test_h3_reclamo_atomico_db(db, monkeypatch):
    from src.services.jobs import idempotencia as I
    monkeypatch.setenv("JOB_IDEMPOTENCY_BACKEND", "db")
    I._reset_para_tests()
    jid = "job_f12_" + os.urandom(4).hex()
    with db.obtener_conexion() as c:
        cur = c.cursor(); cur.execute("DELETE FROM jobs_idempotencia WHERE job_id=%s", (jid,)); c.commit()
    # Primer worker reclama; un segundo worker simultáneo ve 'en_curso' (sólo uno ejecuta).
    assert I.reclamar(jid, id_empresa="A") == "claimed"
    assert I.reclamar(jid, id_empresa="A") == "en_curso"
    # Al completar, una reentrega posterior → duplicado.
    I.marcar(jid, I.COMPLETADO)
    assert I.reclamar(jid, id_empresa="A") == "duplicate"


def test_h3_reclamo_memoria():
    from src.services.jobs import idempotencia as I
    os.environ["JOB_IDEMPOTENCY_BACKEND"] = "memory"
    I._reset_para_tests()
    jid = "job_mem_1"
    assert I.reclamar(jid) == "claimed"
    assert I.reclamar(jid) == "en_curso"
    I.marcar(jid, I.COMPLETADO)
    assert I.reclamar(jid) == "duplicate"
    I._reset_para_tests()
