"""
Tests del Marketplace Corporativo (Fase IV · Bloque 2).

Cubre: firmas digitales (firmado/no_firmado/corrupto/caducado/revocado), validación de
compatibilidad, resolución de dependencias (orden topológico + ciclos + versiones), instalación
según política, historial + ROLLBACK, licencias y AISLAMIENTO multiempresa (0 cruces).
"""

from datetime import datetime, timedelta

import pytest

EMP = "T-MK-A"
EMP_B = "T-MK-B"


@pytest.fixture
def limpio(db):
    def _borrar():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            for t in ("plugins_instalados", "plugins_historial", "marketplace_licencias",
                      "marketplace_politica", "marketplace_repositorios"):
                cur.execute(f"DELETE FROM {t} WHERE id_empresa IN (%s,%s)", (EMP, EMP_B))
            cur.execute("DELETE FROM plugins_instalados WHERE clave LIKE 't_mk%'")
            cur.execute("DELETE FROM plugins_historial WHERE clave LIKE 't_mk%'")
            conn.commit()
    _borrar(); yield; _borrar()


def _firmado(clave, version, **extra):
    from src.services.marketplace import firmas
    m = {"clave": clave, "nombre": clave.upper(), "version": version, **extra}
    m["firma"] = firmas.firmar(m)
    return m


def test_firmas():
    from src.services.marketplace import firmas
    m = {"clave": "p", "nombre": "P", "version": "1.0.0"}
    assert firmas.verificar(m) == firmas.NO_FIRMADO
    m["firma"] = firmas.firmar(m)
    assert firmas.verificar(m) == firmas.FIRMADO
    alterado = dict(m); alterado["version"] = "9.9.9"
    assert firmas.verificar(alterado) == firmas.CORRUPTO
    assert firmas.verificar(m, revocadas={"p"}) == firmas.REVOCADO
    caduco = _firmado("q", "1.0.0", firma_caducidad=(datetime.now() - timedelta(days=1)).isoformat())
    assert firmas.verificar(caduco) == firmas.CADUCADO


def test_validacion_compatibilidad():
    from src.services.marketplace import validacion
    ok = validacion.validar({"clave": "p", "nombre": "P", "version": "1.0.0",
                             "version_minima": "4.0.0"})
    assert ok["compatible"] is True
    no = validacion.validar({"clave": "p", "nombre": "P", "version": "1.0.0",
                            "version_maxima": "3.0.0"})
    assert no["compatible"] is False and no["ok"] is False


def test_dependencias_orden_y_ciclo():
    from src.services.marketplace import dependencias
    cat = {"a": {"clave": "a", "version": "1.0.0",
                 "dependencias": [{"clave": "b", "version_minima": "1.0.0"}]},
           "b": {"clave": "b", "version": "1.2.0"}}
    orden, problemas = dependencias.orden_instalacion("a", cat)
    assert orden == ["b", "a"] and not problemas
    # Conflicto de versión.
    cat2 = {"a": {"clave": "a", "version": "1.0.0",
                  "dependencias": [{"clave": "b", "version_minima": "2.0.0"}]},
            "b": {"clave": "b", "version": "1.0.0"}}
    assert not dependencias.resoluble("a", cat2)
    # Ciclo.
    cat3 = {"a": {"clave": "a", "version": "1.0.0", "dependencias": ["b"]},
            "b": {"clave": "b", "version": "1.0.0", "dependencias": ["a"]}}
    o3, p3 = dependencias.orden_instalacion("a", cat3)
    assert o3 == [] and any(p["tipo"] == "ciclo" for p in p3)


def test_instalar_politica_e_historial(limpio):
    from src.services.marketplace import instalacion
    v1 = _firmado("t_mk_app", "1.0.0")
    cat = {"t_mk_app": v1}
    # Política 'firmados' con plugin firmado → instala.
    r = instalacion.instalar("t_mk_app", id_empresa=EMP, usuario="admin", politica="firmados",
                             _cat=cat)
    assert r["ok"] and "t_mk_app" in r["instalados"]
    hist = instalacion.historial("t_mk_app", EMP)
    assert hist and hist[0]["accion"] == "instalar"
    # Un plugin NO firmado con política 'firmados' → rechazado.
    r2 = instalacion.instalar("t_mk_nofirm", id_empresa=EMP, politica="firmados",
                              _cat={"t_mk_nofirm": {"clave": "t_mk_nofirm", "nombre": "N",
                                                    "version": "1.0.0"}})
    assert r2["ok"] is False


def test_rollback(limpio):
    from src.services.marketplace import instalacion
    from src import sdk
    v1 = _firmado("t_mk_roll", "1.0.0")
    v2 = _firmado("t_mk_roll", "2.0.0")
    instalacion.instalar("t_mk_roll", id_empresa=EMP, politica="todos", _cat={"t_mk_roll": v1})
    instalacion.instalar("t_mk_roll", id_empresa=EMP, politica="todos", _cat={"t_mk_roll": v2})
    actual = next(p for p in sdk.listar_instalados(EMP) if p["clave"] == "t_mk_roll")
    assert actual["version"] == "2.0.0"
    res = instalacion.rollback("t_mk_roll", id_empresa=EMP, usuario="admin")
    assert res["ok"] and res["version"] == "1.0.0"
    tras = next(p for p in sdk.listar_instalados(EMP) if p["clave"] == "t_mk_roll")
    assert tras["version"] == "1.0.0"


def test_aislamiento_empresa(limpio):
    from src.services.marketplace import instalacion
    from src import sdk
    v1 = _firmado("t_mk_iso", "1.0.0")
    instalacion.instalar("t_mk_iso", id_empresa=EMP, politica="todos", _cat={"t_mk_iso": v1})
    claves_a = {p["clave"] for p in sdk.listar_instalados(EMP)}
    claves_b = {p["clave"] for p in sdk.listar_instalados(EMP_B)}
    assert "t_mk_iso" in claves_a
    assert "t_mk_iso" not in claves_b     # otra empresa NO ve el plugin instalado


def test_licencias(limpio):
    from src.services.marketplace import licencias
    # Sin licencia registrada y sin exigirla → permitido (modelo abierto, sin cobro).
    assert licencias.tiene_licencia("t_mk_lic", id_empresa=EMP, requerir=False) is True
    assert licencias.tiene_licencia("t_mk_lic", id_empresa=EMP, requerir=True) is False
    assert licencias.conceder("t_mk_lic", id_empresa=EMP, tipo=licencias.EMPRESA)
    assert licencias.tiene_licencia("t_mk_lic", id_empresa=EMP, requerir=True) is True
    # Aislamiento: la licencia de EMP no vale para EMP_B.
    assert licencias.tiene_licencia("t_mk_lic", id_empresa=EMP_B, requerir=True) is False
    licencias.revocar("t_mk_lic", id_empresa=EMP)
    assert licencias.tiene_licencia("t_mk_lic", id_empresa=EMP, requerir=True) is False
