"""Smart Suppliers (Fase E) · Ventana de Compras: dashboard de entrada a la Extranet B2B."""

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication  # noqa: E402

pytestmark = pytest.mark.db

_app = QApplication.instance() or QApplication([])


def test_ventana_muestra_botones_b2b(db, fab):
    from src.db.empresa import contexto_tenant
    from src.gui.compras_gestion import ComprasWindow
    emp = fab.empresa("GUI B2B DASH")
    with contexto_tenant(emp, None):
        w = ComprasWindow(callback_vuelta=lambda: None, usuario={"id": 1, "nombre": "Tester"})
        assert hasattr(w, "_entrar_portal_b2b")
        assert hasattr(w, "_dlg_invitar_proveedor")
        w.close()


def test_sin_tienda_conectada_avisa_y_no_crea_sesion(db, fab, monkeypatch):
    from src.db.empresa import contexto_tenant
    import src.gui.compras_gestion as CG
    emp = fab.empresa("GUI B2B SIN TIENDA")
    avisos = []
    monkeypatch.setattr(CG, "_aviso", lambda *a, **k: avisos.append(a))
    with contexto_tenant(emp, None):   # sin tienda activa
        w = CG.ComprasWindow(usuario={"id": 1, "nombre": "Tester"})
        w._entrar_portal_b2b()
        assert avisos   # avisó en vez de intentar abrir el navegador
        w.close()


def test_entrar_portal_b2b_crea_sesion_real(db, fab, monkeypatch):
    """Con sector comercial + tienda activa, `_entrar_portal_b2b` crea una sesión real
    (`b2b_sesiones_empresa`) y abre la URL del portal con su token."""
    from src.db.empresa import contexto_tenant
    from src.services.compras import sectores as SEC
    import src.gui.compras_gestion as CG
    emp = fab.empresa("GUI B2B CON TIENDA")

    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM sectores_comerciales LIMIT 1")
        row = cur.fetchone()
        sector_id = (row[0] if not isinstance(row, dict) else row["id"]) if row else None
        if sector_id is None:
            sector_id = SEC.crear("test-gui-b2b", "Sector de prueba GUI")
        cur.execute("UPDATE empresas SET sector_id=%s WHERE id_empresa=%s", (sector_id, emp))
        conn.commit()

    def _cleanup():
        with db.obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM b2b_sesiones_empresa WHERE id_empresa=%s", (emp,))
            conn.commit()
    fab.al_limpiar(_cleanup)

    abiertas = []
    monkeypatch.setattr("webbrowser.open", lambda url: abiertas.append(url) or True)
    with contexto_tenant(emp, 1):   # tienda activa = 1
        w = CG.ComprasWindow(usuario={"id": 1, "nombre": "Tester"})
        w._entrar_portal_b2b()
        w.close()
    assert len(abiertas) == 1 and "/portal/empresa/" in abiertas[0] and "/dashboard" in abiertas[0]
    with db.obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM b2b_sesiones_empresa WHERE id_empresa=%s", (emp,))
        row = cur.fetchone()
        n = row[0] if not isinstance(row, dict) else row["COUNT(*)"]
        assert n == 1


def test_menu_principal_incluye_compras_solo_superadmin(db):
    """La tarjeta 'Compras'/Proveedores SOLO aparece para SUPERADMIN (restringido a
    propósito) y enruta a ComprasWindow; ADMINISTRADOR ya no la ve."""
    from src.db.usuario import sesion_global
    from src.gui import menu_principal as M
    prev = sesion_global.usuario_actual
    try:
        sesion_global.usuario_actual = {"perfil": "SUPERADMIN", "nombre": "SUPER"}
        menu = M.MenuPrincipal()
        assert "compras" in menu._cards
        menu.close()

        sesion_global.usuario_actual = {"perfil": "ADMINISTRADOR", "nombre": "ADMIN"}
        menu2 = M.MenuPrincipal()
        assert "compras" not in menu2._cards
        menu2.close()
    finally:
        sesion_global.usuario_actual = prev
    # Routing declarado en abrir_ventana_por_id.
    import inspect
    assert "ComprasWindow" in inspect.getsource(M.MenuPrincipal.abrir_ventana_por_id)
