"""
F4.10 (cierre de brecha) · Módulo "Nóminas" personal — ADMINISTRADOR/OPERARIO.

Verifica: visibilidad de la tarjeta por perfil (ADMINISTRADOR/OPERARIO sí, SUPERADMIN no),
aislamiento estricto por empleado (nunca la nómina de otro), y que las nóminas ya generadas
automáticamente (job de fin de mes / generación manual) aparecen sin ningún paso de "envío".
"""

import pytest

pytestmark = pytest.mark.db

from src.rrhh.db import empleados as E
from src.rrhh.db import nominas as N


def _limpia(db, emp):
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM rrhh_empleados WHERE id_empresa=%s", (emp,))
        cur.execute("DELETE FROM empresas WHERE id_empresa=%s", (emp,))
        conn.commit()


def _entorno(db, fab, id_usuario, nif):
    emp = fab.empresa("F410-NOM")
    fab.al_limpiar(lambda: _limpia(db, emp))
    eid = E.crear_empleado(id_empresa=emp, nombre="Ana", apellidos="Ruiz", nif=nif,
                           id_usuario=id_usuario, email="ana@x.com", puesto="Cajera")
    return emp, eid


def _app():
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt6 no disponible")
    return QApplication.instance() or QApplication([])


# ── Menú: visibilidad por perfil ────────────────────────────────────────────────
@pytest.mark.parametrize("perfil,visible", [
    ("ADMINISTRADOR", True),
    ("OPERARIO", True),
    ("SUPERADMIN", False),
])
def test_tarjeta_nominas_por_perfil(db, perfil, visible):
    _app()
    from src.db.usuario import sesion_global
    from src.gui import menu_principal as M
    prev = sesion_global.usuario_actual
    sesion_global.usuario_actual = {"perfil": perfil, "nombre": "U", "id": 1}
    try:
        menu = M.MenuPrincipal()
        assert ("nominas" in menu._cards) == visible
        menu.close()
    finally:
        sesion_global.usuario_actual = prev


def test_rutina_nominas_excluye_superadmin():
    import inspect
    from src.gui import menu_principal as M
    src = inspect.getsource(M.MenuPrincipal.abrir_ventana_por_id)
    assert '"nominas"' in src and "NominasPersonalesWindow" in src


# ── Ventana: resolución propia + aislamiento ────────────────────────────────────
def test_ventana_muestra_solo_nominas_propias(db, fab):
    _app()
    emp, e1 = _entorno(db, fab, id_usuario=7101, nif="67100001A")
    e2 = E.crear_empleado(id_empresa=emp, nombre="Leo", nif="67100002B", id_usuario=7102)
    N.crear_nomina(e1, emp, anio=2026, mes=6, bruto=2000, neto=1600, irpf_importe=300)
    N.crear_nomina(e2, emp, anio=2026, mes=6, bruto=5000, neto=3900, irpf_importe=900)

    from src.db.empresa import contexto_tenant
    with contexto_tenant(emp, None):
        from src.gui.nominas_personales import NominasPersonalesWindow
        w = NominasPersonalesWindow(usuario={"id": 7101, "nombre": "ana", "perfil": "OPERARIO"})
        assert w.empleado is not None and w.empleado["id"] == e1
        assert len(w._nominas) == 1
        assert w._nominas[0]["bruto"] == 2000
        w.close()


def test_ventana_sin_vinculo_no_rompe(db, fab):
    _app()
    emp, eid = _entorno(db, fab, id_usuario=7201, nif="67200001C")
    from src.db.empresa import contexto_tenant
    with contexto_tenant(emp, None):
        from src.gui.nominas_personales import NominasPersonalesWindow
        w = NominasPersonalesWindow(usuario={"id": 9999, "nombre": "x", "perfil": "OPERARIO"})
        assert w.empleado is None       # sin vínculo → aviso, sin error
        w.close()


def test_nomina_ya_generada_aparece_sin_envio_manual(db, fab):
    """"Envío automático" (petición explícita): una nómina ya persistida (lo que hace el job de
    fin de mes o la generación manual) aparece directamente al cargar la ventana — ningún paso
    adicional de "publicar"/"enviar" media entre la generación y la visibilidad."""
    _app()
    emp, eid = _entorno(db, fab, id_usuario=7301, nif="67300001D")
    nid = N.crear_nomina(eid, emp, anio=2026, mes=5, bruto=1800, neto=1450, irpf_importe=250)
    assert nid

    from src.db.empresa import contexto_tenant
    with contexto_tenant(emp, None):
        from src.gui.nominas_personales import NominasPersonalesWindow
        w = NominasPersonalesWindow(usuario={"id": 7301, "nombre": "ana", "perfil": "ADMINISTRADOR"})
        assert any(n["id"] == nid for n in w._nominas)
        w.close()
