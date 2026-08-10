"""
Tests Etapa F · Fase F4: backup operacional.

Verifica la RESTAURACIÓN PARCIAL por subconjunto de tablas (hueco real cerrado, aditivo y
retrocompatible) y la fachada `dr.backup_operacional` que compone planificación/verificación/
restauración/simulacros/estado existentes. Sin sistema nuevo; degradable; multiempresa.
"""

import json
import os
import tempfile

import pytest

pytestmark = pytest.mark.db

EMP = "T-F4"


def _export_doc(tmp, tablas_datos):
    ruta = os.path.join(tmp, "exp_f4.json")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump({"id_empresa": "SRC", "datos": tablas_datos}, f, default=str)
    return ruta


@pytest.fixture()
def limpia(db):
    def _b():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM documentos_registro WHERE id_empresa=%s", (EMP,))
            conn.commit()
    _b()
    yield
    _b()


def test_restauracion_parcial_solo_subconjunto(limpia):
    from src.services.saas import backup_tenant
    with tempfile.TemporaryDirectory() as tmp:
        doc = {"documentos_registro": [{"tipo_documento": "factura", "nombre": "F4 doc",
                                        "ruta": "/tmp/f4.pdf"}]}
        ruta = _export_doc(tmp, doc)
        # Restaurar SOLO documentos_registro → procesa esa tabla.
        r = backup_tenant.restaurar_parcial(ruta, ["documentos_registro"], id_empresa=EMP)
        assert r["ok"] and r["tablas"] == 1
        # Filtrar a una tabla que no está en el export → no procesa nada.
        r2 = backup_tenant.restaurar_parcial(ruta, ["tabla_inexistente"], id_empresa=EMP)
        assert r2["tablas"] == 0


def test_restaurar_parcial_sin_tablas_error(db):
    from src.services.saas import backup_tenant
    assert backup_tenant.restaurar_parcial("/x.json", [], id_empresa=EMP)["ok"] is False


def test_importar_completo_retrocompatible(limpia):
    # Sin `tablas` → comportamiento previo (restaura todas las tablas del export).
    from src.services.saas import backup_tenant
    with tempfile.TemporaryDirectory() as tmp:
        ruta = _export_doc(tmp, {"documentos_registro": [{"tipo_documento": "pedido",
                                                          "nombre": "F4 full", "ruta": "/tmp/x.pdf"}]})
        r = backup_tenant.importar_empresa(ruta, id_empresa=EMP, reemplazar=True)
        assert r["ok"] and r["tablas"] >= 1


def test_facade_delegacion(db):
    from src.services.dr import backup_operacional as bop
    # Verificación reutiliza db.backup (devuelve dict aunque no haya backup).
    assert isinstance(bop.verificar(), dict)
    est = bop.estado()
    assert isinstance(est, dict) and ("backups" in est or "edad_ultimo_backup_h" in est)
    # Simulacro de verificación (reutiliza dr_drills, no crea backups pesados).
    assert isinstance(bop.simulacro("verify"), dict)


def test_facade_exportar_tenant(db):
    from src.services.dr import backup_operacional as bop
    r = bop.exportar_tenant(EMP)
    assert "ruta" in r and "tablas" in r


def test_descriptor(db):
    from src.services.dr import backup_operacional as bop
    d = bop.descriptor()
    assert d["motor_nuevo"] is False
    assert "saas.backup_tenant" in d["reutiliza"] and "dr_drills" in d["reutiliza"]
    assert {"planificar", "verificar", "restaurar_tenant", "restaurar_parcial", "simulacro",
            "estado"} <= set(d["operaciones"])
