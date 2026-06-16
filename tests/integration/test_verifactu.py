"""Integración · proveedor Verifactu (C3.3.1): registro legal, QR, cadena y hook."""

import json

import pytest

pytestmark = pytest.mark.db


def _borra_fiscal(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("fiscal_cola", "fiscal_registros", "fiscal_config"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (emp,))
        conn.commit()


def test_verifactu_es_proveedor_por_config(db, fab):
    from src.db import fiscal as F
    from src.services.fiscal.factory import proveedor_para
    emp = fab.empresa("VF PROV")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    F.guardar_config(proveedor="verifactu", territorio="comun", id_empresa=emp)
    p = proveedor_para(F.obtener_config(emp))
    assert p is not None and p.nombre == "verifactu"


def test_verifactu_registro_legal_y_qr(db, fab):
    from src.db import fiscal as F
    from src.db.empresa import contexto_tenant
    from src.services.fiscal.factory import proveedor_para
    emp = fab.empresa("VF REG")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    F.guardar_config(proveedor="verifactu", entorno="preproduccion", serie_por="empresa",
                     id_empresa=emp)
    with contexto_tenant(emp, None):
        prov = proveedor_para(F.obtener_config(emp))
        r1 = prov.registrar("ticket", referencia="V1", total=12.10)
        r2 = prov.registrar("ticket", referencia="V2", total=20.0)
    assert r1.proveedor == "verifactu"
    assert len(r1.hash) == 64 and r1.hash == r1.hash.upper()      # huella legal MAYÚS
    assert r1.qr.startswith("https://prewww2.aeat.es") and "numserie=A%2F1" in r1.qr
    assert r2.hash_anterior == r1.hash                            # encadenado
    # El payload guarda los datos legales (no derivables) para XML/verificación.
    reg = F.obtener_registro(r1.id)
    meta = json.loads(reg["payload"])
    assert meta["tipo_factura"] == "F2" and "importe_total" in meta
    assert F.cadena_valida(emp, serie=r1.serie) is True


def test_verifactu_cadena_detecta_manipulacion(db, fab):
    from src.db import fiscal as F
    from src.db.empresa import contexto_tenant
    from src.services.fiscal.factory import proveedor_para
    emp = fab.empresa("VF TAMPER")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    F.guardar_config(proveedor="verifactu", serie_por="empresa", id_empresa=emp)
    with contexto_tenant(emp, None):
        r = proveedor_para(F.obtener_config(emp)).registrar("ticket", referencia="V1", total=10.0)
    # Manipular el importe legal del payload → la cadena legal deja de validar.
    meta = json.loads(F.obtener_registro(r.id)["payload"])
    meta["importe_total"] = "999.00"
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("UPDATE fiscal_registros SET payload=%s WHERE id=%s",
                    (json.dumps(meta), r.id))
        conn.commit()
    assert F.cadena_valida(emp, serie=r.serie) is False


def test_verifactu_via_hook_tpv(db, fab):
    """Venta real con Verifactu activo → registro legal + encolado, sin tocar caja."""
    from src.db import conexion as cx, fiscal as F
    from src.db.empresa import contexto_tenant
    emp = fab.empresa("VF HOOK")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    F.guardar_config(proveedor="verifactu", activo=1, serie_por="empresa", id_empresa=emp)
    cod = fab.articulo(id_empresa=emp, precio=12.10, stock_tienda=50)
    with contexto_tenant(emp, None):
        vid = cx.registrar_venta_con_items([{"codigo": cod, "cantidad": 1, "precio_unitario": 12.10}])
    regs = F.listar_registros(id_empresa=emp)
    assert vid and len(regs) == 1 and regs[0]["proveedor"] == "verifactu"
    assert regs[0]["referencia"] == str(vid)
    assert F.listar_cola(id_empresa=emp)            # encolado para envío AEAT
