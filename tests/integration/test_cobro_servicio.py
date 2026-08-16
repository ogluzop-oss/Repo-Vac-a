"""Cuentas bancarias (proveedor/vendedor) + cobro del servicio Smart Manager. `db`.

Cubre: alta de cuenta con IBAN cifrado + máscara (rechaza IBAN inválido); cobro a la EMPRESA (app) y al
PROVEEDOR (portal) idempotente por periodo; marcar cobrado + total pendiente; cuenta del vendedor.
"""

import pytest

from src.db import proveedores as PROV
from src.services.compras import cobro_servicio as CS

pytestmark = pytest.mark.db

IBAN_OK = "ES9121000418450200051332"


def _limpia(db, emp, vid=None):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM servicio_cobros WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM proveedores WHERE id_empresa=%s", (emp,))
        if vid:
            cur.execute("DELETE FROM lonja_vendedores WHERE id=%s", (vid,))
        conn.commit()


def test_cuenta_proveedor(db, fab):
    emp = fab.empresa("EMP cuenta")
    fab.al_limpiar(lambda: _limpia(db, emp))
    prov = PROV.crear_proveedor("Prov Banco", id_empresa=emp)

    # IBAN inválido → rechazado.
    assert CS.set_cuenta_proveedor(prov, "ES00", id_empresa=emp)["ok"] is False
    # IBAN válido → guardado con máscara (nunca en claro en la UI).
    r = CS.set_cuenta_proveedor(prov, IBAN_OK, titular="Prov Banco SL", id_empresa=emp)
    assert r["ok"] is True and r["iban_mascara"] and IBAN_OK not in r["iban_mascara"]
    cta = CS.cuenta_proveedor(prov, emp)
    assert cta["iban_mascara"] == r["iban_mascara"] and cta["titular_cuenta"] == "Prov Banco SL"


def test_cobros_app_y_portal_idempotentes(db, fab):
    emp = fab.empresa("EMP cobros")
    fab.al_limpiar(lambda: _limpia(db, emp))
    prov = PROV.crear_proveedor("Prov Cobro", id_empresa=emp)

    c1 = CS.cobrar_app(emp, 49.0, periodo="2026-08")
    c2 = CS.cobrar_portal(prov, 19.0, id_empresa=emp, periodo="2026-08")
    assert c1 and c2 and c1 != c2
    # Idempotente: mismo periodo/concepto → misma fila.
    assert CS.cobrar_app(emp, 49.0, periodo="2026-08") == c1

    cobros = CS.listar_cobros(emp)
    assert {x["concepto"] for x in cobros} == {"app", "portal"}
    assert {x["parte"] for x in cobros} == {"empresa", "proveedor"}
    assert CS.total_pendiente(emp) == 68.0

    assert CS.marcar_cobrado(c1, emp) is True
    assert CS.total_pendiente(emp) == 19.0   # ya solo queda el del portal


def test_cuenta_vendedor(db, fab):
    from src.services import lonja
    emp = fab.empresa("EMP vend banco")
    ven = lonja.alta_vendedor("Vend Banco", divisa="EUR")
    fab.al_limpiar(lambda: _limpia(db, emp, ven["id"]))
    assert CS.set_cuenta_vendedor(ven["id"], IBAN_OK)["ok"] is True
    r = lonja.resolver_token(  # el token del vendedor expone la máscara (no el IBAN)
        [v for v in [ven] ][0]["token"])
    assert r["iban_mascara"] and IBAN_OK not in r["iban_mascara"]
