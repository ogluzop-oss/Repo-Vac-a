"""Integración · EmisorVerifactu + flujo de cola completo con transporte simulado (C3.3.3)."""

import pytest

pytestmark = pytest.mark.db


def _borra_fiscal(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("fiscal_cola", "fiscal_registros", "fiscal_config"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM documentos_registro WHERE id_empresa=%s", (emp,))
        conn.commit()


def _registro_encolado(db, emp):
    from src.db import fiscal as F
    from src.db.empresa import contexto_tenant
    from src.services.fiscal.factory import proveedor_para
    F.guardar_config(proveedor="verifactu", activo=1, serie_por="empresa", id_empresa=emp)
    with contexto_tenant(emp, None):
        r = proveedor_para(F.obtener_config(emp)).registrar("ticket", referencia="V1", total=12.10)
    F.encolar(r.id, id_empresa=emp)
    return r


def test_emisor_sin_transporte_no_disponible(db, fab):
    """Sin certificado/transporte (hasta C3.5), el emisor no envía y el worker espera."""
    from src.db import fiscal as F
    from src.services.fiscal.factory import emisor_para
    from src.services.fiscal.worker import procesar_cola
    emp = fab.empresa("VF EMI OFF")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    _registro_encolado(db, emp)
    assert emisor_para(F.obtener_config(emp)).disponible() is False
    res = procesar_cola(id_empresa=emp)            # usa emisor_para → no disponible
    assert res["en_espera"] == 1 and res["enviados"] == 0


def test_emisor_envio_correcto_persiste_estado_csv_y_acuse(db, fab):
    from src.db import fiscal as F
    from src.services.fiscal.emisores.verifactu_aeat import EmisorVerifactu
    from src.services.fiscal.worker import procesar_cola
    emp = fab.empresa("VF EMI OK")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    r = _registro_encolado(db, emp)

    enviado = {}
    def transporte(url, cuerpo, cfg):
        enviado["url"], enviado["cuerpo"] = url, cuerpo
        return 200, "<EstadoEnvio>Correcto</EstadoEnvio><CSV>CSV-XYZ-1</CSV>"

    res = procesar_cola(id_empresa=emp, emisor=EmisorVerifactu(transporte=transporte))
    assert res["enviados"] == 1
    assert "prewww1.aeat.es" in enviado["url"]                 # entorno preproducción
    assert b"RegFactuSistemaFacturacion" in enviado["cuerpo"]  # XML del lote
    reg = F.obtener_registro(r.id)
    assert reg["estado"] == "enviado" and reg["estado_aeat"] == "Correcto"
    assert reg["csv_aeat"] == "CSV-XYZ-1"
    assert F.listar_cola(id_empresa=emp) == []
    # Acuse + XML quedan como evidencias documentales.
    from src.db import documentos as D
    docs = D.listar_documentos(id_empresa=emp)
    assert any(d["tipo_documento"] in ("factura", "auditoria") for d in docs)


def test_emisor_rechazo_reintenta(db, fab):
    from src.services.fiscal.emisores.verifactu_aeat import EmisorVerifactu
    from src.services.fiscal.worker import procesar_cola
    from src.db import fiscal as F
    emp = fab.empresa("VF EMI KO")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    _registro_encolado(db, emp)

    def transporte(url, cuerpo, cfg):
        return 500, "<EstadoEnvio>Incorrecto</EstadoEnvio>"

    res = procesar_cola(id_empresa=emp, emisor=EmisorVerifactu(transporte=transporte))
    assert res["enviados"] == 0 and res["en_espera"] == 1
    assert len(F.listar_cola(id_empresa=emp)) == 1            # sigue pendiente (backoff)


def test_parse_acuse():
    from src.services.fiscal.emisores.verifactu_aeat import EmisorVerifactu
    ok = EmisorVerifactu._parse(200, "<EstadoEnvio>Correcto</EstadoEnvio><CSV>A1</CSV>")
    ko = EmisorVerifactu._parse(200, "<EstadoEnvio>Incorrecto</EstadoEnvio>")
    assert ok["ok"] is True and ok["csv"] == "A1"
    assert ko["ok"] is False and ko["estado_aeat"] == "Incorrecto"
