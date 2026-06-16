"""Integración · EmisorVerifactu + flujo de cola con transporte simulado (C3.3.1.1)."""

import pytest

pytestmark = pytest.mark.db

_NS = ('xmlns:env="http://schemas.xmlsoap.org/soap/envelope/" '
       'xmlns:tikR="https://www2.agenciatributaria.gob.es/static_files/common/internet/'
       'dep/aplicaciones/es/aeat/tike/cont/ws/RespuestaSuministro.xsd"')


def _soap(estado_envio, estado_linea=None, csv=None, espera=None, desc=None, duplicado=False):
    linea = ""
    if estado_linea or duplicado:
        linea = (f"<tikR:RespuestaLinea>"
                 f"<tikR:EstadoRegistro>{estado_linea or ''}</tikR:EstadoRegistro>"
                 + (f"<tikR:DescripcionErrorRegistro>{desc}</tikR:DescripcionErrorRegistro>" if desc else "")
                 + ("<tikR:RegistroDuplicado/>" if duplicado else "")
                 + f"</tikR:RespuestaLinea>")
    cuerpo = (f"<tikR:RespuestaRegFactuSistemaFacturacion {_NS}>"
              + (f"<tikR:CSV>{csv}</tikR:CSV>" if csv else "")
              + (f"<tikR:TiempoEsperaEnvio>{espera}</tikR:TiempoEsperaEnvio>" if espera else "")
              + f"<tikR:EstadoEnvio>{estado_envio}</tikR:EstadoEnvio>{linea}"
              + "</tikR:RespuestaRegFactuSistemaFacturacion>")
    return f'<env:Envelope {_NS}><env:Body>{cuerpo}</env:Body></env:Envelope>'


def _borra_fiscal(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("fiscal_cola", "fiscal_registros", "fiscal_config"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM documentos_registro WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


def _empresa_con_nif(db, fab, nombre):
    emp = fab.empresa(nombre)
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("UPDATE empresas SET razon_social=%s, cif_nif=%s WHERE id_empresa=%s",
                    (nombre, "B12345678", emp))
        conn.commit()
    return emp


def _registro_encolado(db, emp):
    from src.db import fiscal as F
    from src.db.empresa import contexto_tenant
    from src.services.fiscal.factory import proveedor_para
    F.guardar_config(proveedor="verifactu", activo=1, serie_por="empresa", id_empresa=emp)
    with contexto_tenant(emp, None):
        r = proveedor_para(F.obtener_config(emp)).registrar("ticket", referencia="V1", total=12.10)
    F.encolar(r.id, id_empresa=emp)
    return r


@pytest.fixture(autouse=True)
def _reset_pacing():
    from src.services.fiscal.emisores import verifactu_aeat as M
    M._proximo_envio.clear()
    yield
    M._proximo_envio.clear()


def test_emisor_sin_transporte_no_disponible(db, fab):
    from src.db import fiscal as F
    from src.services.fiscal.factory import emisor_para
    from src.services.fiscal.worker import procesar_cola
    emp = _empresa_con_nif(db, fab, "VF EMI OFF")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    _registro_encolado(db, emp)
    assert emisor_para(F.obtener_config(emp)).disponible() is False
    res = procesar_cola(id_empresa=emp)
    assert res["en_espera"] == 1 and res["enviados"] == 0


def test_emisor_envio_correcto_persiste_estado_csv_y_acuse(db, fab):
    from src.db import documentos as D, fiscal as F
    from src.services.fiscal.emisores.verifactu_aeat import EmisorVerifactu
    from src.services.fiscal.worker import procesar_cola
    emp = _empresa_con_nif(db, fab, "VF EMI OK")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    r = _registro_encolado(db, emp)

    enviado = {}
    def transporte(url, cuerpo, cfg):
        enviado["url"], enviado["cuerpo"] = url, cuerpo
        return 200, _soap("Correcto", estado_linea="Correcto", csv="CSV-XYZ-1")

    res = procesar_cola(id_empresa=emp, emisor=EmisorVerifactu(transporte=transporte))
    assert res["enviados"] == 1
    assert "prewww1.aeat.es" in enviado["url"]
    assert b"RegFactuSistemaFacturacion" in enviado["cuerpo"] and b"soapenv:Body" in enviado["cuerpo"]
    reg = F.obtener_registro(r.id)
    assert reg["estado"] == "enviado" and reg["estado_aeat"] == "Correcto" and reg["csv_aeat"] == "CSV-XYZ-1"
    assert F.listar_cola(id_empresa=emp) == []
    assert any(d["tipo_documento"] in ("factura", "auditoria") for d in D.listar_documentos(id_empresa=emp))


def test_emisor_incorrecto_reintenta(db, fab):
    from src.db import fiscal as F
    from src.services.fiscal.emisores.verifactu_aeat import EmisorVerifactu
    from src.services.fiscal.worker import procesar_cola
    emp = _empresa_con_nif(db, fab, "VF EMI KO")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    r = _registro_encolado(db, emp)

    def transporte(url, cuerpo, cfg):
        return 200, _soap("Incorrecto", estado_linea="Incorrecto", desc="NIF no identificado")

    res = procesar_cola(id_empresa=emp, emisor=EmisorVerifactu(transporte=transporte))
    assert res["enviados"] == 0 and res["en_espera"] == 1
    assert F.obtener_registro(r.id)["estado_aeat"] == "Incorrecto"
    assert len(F.listar_cola(id_empresa=emp)) == 1


def test_emisor_duplicado_es_aceptado(db, fab):
    from src.services.fiscal.emisores.verifactu_aeat import EmisorVerifactu
    from src.services.fiscal.worker import procesar_cola
    emp = _empresa_con_nif(db, fab, "VF EMI DUP")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    _registro_encolado(db, emp)

    def transporte(url, cuerpo, cfg):
        return 200, _soap("ParcialmenteCorrecto", estado_linea="Correcto", duplicado=True, csv="C2")

    res = procesar_cola(id_empresa=emp, emisor=EmisorVerifactu(transporte=transporte))
    assert res["enviados"] == 1


def test_tiempo_espera_envio_pacing(db, fab):
    """TiempoEsperaEnvio fija una ventana de pacing en memoria sin tocar el worker."""
    from src.services.fiscal.emisores import verifactu_aeat as M
    from src.services.fiscal.emisores.verifactu_aeat import EmisorVerifactu
    emp = _empresa_con_nif(db, fab, "VF EMI ESPERA")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    r = _registro_encolado(db, emp)

    def transporte(url, cuerpo, cfg):
        return 200, _soap("Correcto", estado_linea="Correcto", csv="C1", espera=60)

    from src.services.fiscal.base import RegistroFiscal
    fila = __import__("src.db.fiscal", fromlist=["obtener_registro"]).obtener_registro(r.id)
    emi = EmisorVerifactu(transporte=transporte)
    res1 = emi.enviar(RegistroFiscal.desde_fila(fila), {"entorno": "preproduccion"})
    assert res1["ok"] and res1["espera"] == 60
    assert emp in M._proximo_envio                      # ventana de pacing activa
    # Un segundo envío inmediato queda bloqueado por el throttling.
    res2 = emi.enviar(RegistroFiscal.desde_fila(fila), {"entorno": "preproduccion"})
    assert res2["ok"] is False and "espera" in res2["mensaje"].lower()


def test_parse_directo():
    from src.services.fiscal.emisores.verifactu_aeat import EmisorVerifactu
    ok = EmisorVerifactu._parse(200, _soap("Correcto", estado_linea="Correcto", csv="A1"))
    ko = EmisorVerifactu._parse(200, _soap("Incorrecto", estado_linea="Incorrecto", desc="err"))
    assert ok["ok"] and ok["csv"] == "A1" and ok["estado_aeat"] == "Correcto"
    assert ko["ok"] is False and ko["estado_aeat"] == "Incorrecto" and ko["mensaje"] == "err"
