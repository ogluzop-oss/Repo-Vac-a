"""Flujo de la pestaña Contratos (módulo Proveedores) sobre services/contratos. `db`.

Verifica el ciclo que orquesta la GUI: alta → listado → próximos vencimientos → obligaciones
(alta/cumplir) → renovación. La GUI (compras_gestion._page_contratos) solo llama a estas funciones.
"""

import datetime as _dt

import pytest

pytestmark = pytest.mark.db


def test_contratos_flujo_compras(db, fab):
    from src.services.contratos import contratos_pro as CT

    emp = fab.empresa("EMP contratos compras")

    def _clean():
        with db.obtener_conexion() as c, c.cursor() as cur:
            cur.execute("DELETE FROM contrato_obligaciones WHERE id_empresa=%s", (emp,))
            cur.execute("DELETE FROM contratos WHERE id_empresa=%s", (emp,))
            c.commit()
    fab.al_limpiar(_clean)

    fin = (_dt.date.today() + _dt.timedelta(days=30)).isoformat()
    cid = CT.crear_contrato(codigo="C-COMP-1", tipo="proveedor", contraparte="ACME S.L.",
                            fecha_inicio=_dt.date.today().isoformat(), fecha_fin=fin,
                            valor=1500, id_empresa=emp)
    assert cid

    # Listado (lo que llena la tabla de la pestaña).
    assert any(x["id"] == cid for x in CT.listar_contratos(id_empresa=emp))

    # Vigente → aparece en próximos vencimientos (aviso naranja de la pestaña).
    assert CT.cambiar_estado(cid, "VIGENTE", id_empresa=emp)["ok"]
    assert any(v.get("id") == cid for v in CT.proximos_vencimientos(emp, dias=60))

    # Obligaciones: alta + cumplir.
    oid = CT.registrar_obligacion(cid, "Entregar informe trimestral", id_empresa=emp)
    assert oid
    assert any(o["id"] == oid for o in CT.obligaciones(cid, id_empresa=emp))
    assert CT.cumplir_obligacion(oid)["ok"]
    assert not CT.obligaciones(cid, solo_pendientes=True, id_empresa=emp)

    # Renovación: marca el actual RENOVADO y crea uno nuevo VIGENTE.
    res = CT.renovar_contrato(cid, meses=12, id_empresa=emp)
    assert res["ok"] and res.get("id_nuevo")
    estados = {x["id"]: x["estado"] for x in CT.listar_contratos(id_empresa=emp)}
    assert estados.get(cid) == "RENOVADO"
    assert estados.get(res["id_nuevo"]) == "VIGENTE"
