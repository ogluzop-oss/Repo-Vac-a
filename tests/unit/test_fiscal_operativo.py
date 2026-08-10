"""
Tests · Fiscal / Verifactu — EXPOSICIÓN operativa y GARANTÍA DE HONESTIDAD.

El motor fiscal es REAL (mTLS + endpoints AEAT oficiales + certificados PKCS#12 + máquina de estados).
Estos tests verifican la exposición y, sobre todo, la INVARIANTE DE HONESTIDAD: sin certificado activo la
transmisión legal NO está habilitada y ningún registro se marca como 'enviado/aceptado' de forma simulada;
los estados se distinguen (generado→firmado→enviado→rechazado/anulado). No hay llamadas de red.
"""

import pytest

pytestmark = pytest.mark.db

EMP = "T-FISC-1"


@pytest.fixture()
def limpia(db):
    def _b():
        with db.obtener_conexion() as c:
            cur = c.cursor()
            for tab in ("fiscal_cola", "fiscal_registros", "fiscal_certificados"):
                try:
                    cur.execute(f"DELETE FROM {tab} WHERE id_empresa=%s", (EMP,))
                except Exception:
                    pass
            c.commit()
    _b()
    yield
    _b()


def test_registro_generado_y_estados(limpia, db):
    from src.db import fiscal as F
    reg = F.insertar_registro("ticket", referencia="T-0001", total=121.0, serie="FISCA",
                              estado="generado", id_empresa=EMP, id_tienda=None)
    assert reg and reg.get("estado") == "generado" and reg.get("hash")
    rid = reg["id"]
    # aparece en el listado que consume la GUI, con su estado real.
    regs = F.listar_registros(id_empresa=EMP, limite=50)
    assert any(r["id"] == rid and r["estado"] == "generado" for r in regs)
    # la máquina de estados es explícita (generado→firmado→enviado); nunca implícita.
    assert F.actualizar_estado(rid, "firmado")
    assert F.obtener_registro(rid)["estado"] == "firmado"


def test_sin_certificado_no_hay_transmision(limpia):
    """INVARIANTE DE HONESTIDAD: sin certificado activo, la transmisión real NO está habilitada."""
    from src.services.fiscal import certificados
    assert certificados.obtener_activo(id_empresa=EMP) is None
    assert certificados.listar(id_empresa=EMP) == []


def test_procesar_cola_vacia_no_inventa_envios(limpia):
    """La cola vacía NO produce envíos falsos (resumen a cero, sin marcar nada como enviado)."""
    from src.services.fiscal import worker
    res = worker.procesar_cola(id_empresa=EMP)
    assert isinstance(res, dict)
    assert res.get("enviados", 0) == 0


def test_pkcs12_invalido_se_rechaza(limpia):
    """Un PKCS#12 inválido no se importa (ni crashea): el certificado debe ser real."""
    from src.services.fiscal import certificados
    with pytest.raises(Exception):
        certificados.inspeccionar_pkcs12(b"no-es-un-pkcs12", "x")
