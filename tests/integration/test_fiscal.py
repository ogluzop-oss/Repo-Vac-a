"""Integración · núcleo fiscal C3.1: config, encadenado hash, proveedor simulado, cola."""

import pytest

pytestmark = pytest.mark.db


def _borra_fiscal(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        for t in ("fiscal_cola", "fiscal_registros", "fiscal_config"):
            cur.execute(f"DELETE FROM {t} WHERE id_empresa=%s", (emp,))
        conn.commit()


def test_config_roundtrip(db, fab):
    from src.db import fiscal as F
    emp = fab.empresa("FISCAL CFG")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    assert F.guardar_config(modo="no_verifactu", territorio="comun", serie="B",
                            activo=1, id_empresa=emp)
    c = F.obtener_config(emp)
    assert c["modo"] == "no_verifactu" and c["serie"] == "B" and c["activo"] == 1


def test_encadenado_hash_y_qr(db, fab):
    from src.db import fiscal as F
    from src.db.empresa import contexto_tenant
    from src.services.fiscal import proveedor_fiscal_actual
    emp = fab.empresa("FISCAL ENC")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    with contexto_tenant(emp, None):
        prov = proveedor_fiscal_actual()
        assert prov.nombre == "simulado"
        r1 = prov.registrar("ticket", referencia="V1", total=10.0)
        r2 = prov.registrar("ticket", referencia="V2", total=20.0)
        assert r1.hash and r1.qr and r1.numero == 1
        assert r2.numero == 2 and r2.hash_anterior == r1.hash      # encadenado
        assert F.cadena_valida(id_empresa=emp, serie=r1.serie) is True


def test_cadena_detecta_manipulacion(db, fab):
    from src.db import fiscal as F
    from src.db.empresa import contexto_tenant
    from src.services.fiscal import proveedor_fiscal_actual
    emp = fab.empresa("FISCAL TAMPER")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    with contexto_tenant(emp, None):
        r1 = proveedor_fiscal_actual().registrar("ticket", referencia="V1", total=10.0)
    # Manipulación del importe → la cadena deja de validar.
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("UPDATE fiscal_registros SET total=999 WHERE id=%s", (r1.id,))
        conn.commit()
    assert F.cadena_valida(id_empresa=emp, serie=r1.serie) is False


def test_cola_envio(db, fab):
    from src.db import fiscal as F
    from src.db.empresa import contexto_tenant
    from src.services.fiscal import proveedor_fiscal_actual
    emp = fab.empresa("FISCAL COLA")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    with contexto_tenant(emp, None):
        r = proveedor_fiscal_actual().registrar("factura", referencia="F1", total=50.0)
    cid = F.encolar(r.id, id_empresa=emp)
    assert cid and F.listar_cola(id_empresa=emp)[0]["id_registro"] == r.id
    F.actualizar_cola(cid, "enviado")
    assert F.listar_cola(id_empresa=emp) == []        # ya no hay pendientes


def test_serie_por_caja_cadenas_independientes(db, fab):
    """Estrategia 'caja': cada caja numera y encadena por separado."""
    from src.db import fiscal as F
    from src.db.empresa import contexto_tenant
    emp = fab.empresa("FISCAL CAJA")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    assert F.guardar_config(serie="A", serie_por="caja", id_empresa=emp)
    with contexto_tenant(emp, None):
        c1a = F.insertar_registro("ticket", referencia="C1V1", total=10, id_caja="CAJA-01")
        c2a = F.insertar_registro("ticket", referencia="C2V1", total=20, id_caja="CAJA-02")
        c1b = F.insertar_registro("ticket", referencia="C1V2", total=30, id_caja="CAJA-01")
    assert c1a["serie"] == "A-CCAJA01" and c2a["serie"] == "A-CCAJA02"
    # Numeración independiente por caja.
    assert c1a["numero"] == 1 and c1b["numero"] == 2 and c2a["numero"] == 1
    # Encadenado independiente por caja.
    assert c1b["hash_anterior"] == c1a["hash"]
    assert c2a["hash_anterior"] is None
    assert F.cadena_valida(emp, serie="A-CCAJA01") and F.cadena_valida(emp, serie="A-CCAJA02")


def test_serie_por_empresa_unica(db, fab):
    """Estrategia 'empresa': una sola serie aunque cambien tienda/caja."""
    from src.db import fiscal as F
    from src.db.empresa import contexto_tenant
    emp = fab.empresa("FISCAL UNICA")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    assert F.guardar_config(serie="A", serie_por="empresa", id_empresa=emp)
    with contexto_tenant(emp, None):
        r1 = F.insertar_registro("ticket", referencia="U1", total=1, id_caja="CAJA-01")
        r2 = F.insertar_registro("ticket", referencia="U2", total=2, id_caja="CAJA-09")
    assert r1["serie"] == "A" and r2["serie"] == "A"
    assert r1["numero"] == 1 and r2["numero"] == 2 and r2["hash_anterior"] == r1["hash"]


def test_config_serie_por_roundtrip(db, fab):
    from src.db import fiscal as F
    emp = fab.empresa("FISCAL SP")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp))
    assert F.guardar_config(serie_por="caja", id_empresa=emp)
    assert F.obtener_config(emp)["serie_por"] == "caja"
    # Valor inválido → cae a 'tienda'.
    assert F.guardar_config(serie_por="loquesea", id_empresa=emp)
    assert F.obtener_config(emp)["serie_por"] == "tienda"


def test_aislamiento_registros_por_empresa(db, fab):
    from src.db import fiscal as F
    from src.db.empresa import contexto_tenant
    from src.services.fiscal import proveedor_fiscal_actual
    emp_b = fab.empresa("FISCAL B")
    fab.al_limpiar(lambda: _borra_fiscal(db, emp_b))
    with contexto_tenant(emp_b, None):
        proveedor_fiscal_actual().registrar("ticket", referencia="VB", total=5.0)
    # Desde la empresa por defecto no se ven los registros de B.
    refs_a = {r["referencia"] for r in F.listar_registros()}
    refs_b = {r["referencia"] for r in F.listar_registros(id_empresa=emp_b)}
    assert "VB" in refs_b and "VB" not in refs_a
