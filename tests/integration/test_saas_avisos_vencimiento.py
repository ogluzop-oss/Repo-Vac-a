"""Avisos de vencimiento de suscripción SaaS. `db`.

Verifica dias_para_vencer / aviso_vencimiento / suscripciones_por_vencer / job_avisos_vencimiento
(lo que orquesta el banner de "Mi plan" y el job opt-in que notifica a las empresas).
"""

import datetime as _dt

import pytest

pytestmark = pytest.mark.db


def _set_proximo(db, emp, dias):
    fecha = (_dt.date.today() + _dt.timedelta(days=dias)).isoformat()
    with db.obtener_conexion() as c, c.cursor() as cur:
        cur.execute("UPDATE suscripciones SET proximo_cobro=%s WHERE id_empresa=%s", (fecha, emp))
        c.commit()


def test_avisos_vencimiento_saas(db, fab):
    from src.services.saas import suscripciones as SU

    emp = fab.empresa("EMP saas aviso")

    def _clean():
        with db.obtener_conexion() as c, c.cursor() as cur:
            cur.execute("DELETE FROM suscripciones WHERE id_empresa=%s", (emp,))
            c.commit()
    fab.al_limpiar(_clean)

    sid = SU.crear(emp, "BASIC", prueba=True, dias_prueba=15)
    assert sid

    # Próximo cobro dentro de 15 días → aviso.
    d = SU.dias_para_vencer(emp)
    assert d is not None and 13 <= d <= 15
    av = SU.aviso_vencimiento(emp)
    assert av and av["nivel"] in ("aviso", "urgente")

    # A 2 días → urgente + aparece en el listado + el job no falla.
    _set_proximo(db, emp, 2)
    assert SU.aviso_vencimiento(emp)["nivel"] == "urgente"
    assert any(r[0] == emp for r in SU.suscripciones_por_vencer(15))
    res = SU.job_avisos_vencimiento()
    assert isinstance(res, dict) and res.get("avisadas", 0) >= 1

    # Ya vencida (ayer) → nivel 'vencida'.
    _set_proximo(db, emp, -1)
    assert SU.aviso_vencimiento(emp)["nivel"] == "vencida"

    # Lejos (60 días) → sin aviso y fuera del listado.
    _set_proximo(db, emp, 60)
    assert SU.aviso_vencimiento(emp) is None
    assert not any(r[0] == emp for r in SU.suscripciones_por_vencer(15))
