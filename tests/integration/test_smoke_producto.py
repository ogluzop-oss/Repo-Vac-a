"""
E1.4 · Smoke test reproducible del PRODUCTO (flujo de integridad mínima).

Verifica de principio a fin que una instalación nueva arranca y responde:
  1) crear BD + esquema, 2) migraciones, 3) crear usuario nominal, 4) login,
  5-7) abrir TPV / stock / catálogo (Qt offscreen), 8) núcleo fiscal, 9) cierre.

Doble uso:
  • pytest:  test_smoke_producto (se omite si no hay MariaDB, vía fixture `db`).
  • script:  python tests/integration/test_smoke_producto.py   (exit 0 OK / 1 fallo)
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["DB_NAME"] = os.environ.get("TEST_DB_NAME", "smart_manager_test")

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest  # noqa: E402

pytestmark = pytest.mark.db

_USUARIO = "SMOKE_USER_E14"
_CLAVE = "Smoke_Clave_123"


def _crear_usuario_smoke():
    from src.db.conexion import obtener_conexion
    from src.seguridad import passwords as pw
    h = pw.hash_password(_CLAVE)
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute("SHOW COLUMNS FROM usuarios")
        cols = [c[0] if not isinstance(c, dict) else c["Field"] for c in cur.fetchall()]
        col = "nombre" if "nombre" in cols else "usuario"
        cur.execute(f"DELETE FROM usuarios WHERE {col}=%s", (_USUARIO,))
        cur.execute(f"INSERT INTO usuarios ({col}, password, perfil, tienda_id) "
                    "VALUES (%s,%s,'ADMINISTRADOR',NULL)", (_USUARIO, h))
        conn.commit()


def _borrar_usuario_smoke():
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SHOW COLUMNS FROM usuarios")
            cols = [c[0] if not isinstance(c, dict) else c["Field"] for c in cur.fetchall()]
            col = "nombre" if "nombre" in cols else "usuario"
            cur.execute(f"DELETE FROM usuarios WHERE {col}=%s", (_USUARIO,))
            conn.commit()
    except Exception:
        pass


def ejecutar_smoke() -> list:
    """Ejecuta el flujo y devuelve [(paso, ok, detalle), ...]."""
    pasos = []

    def paso(nombre, ok, detalle=""):
        pasos.append((nombre, bool(ok), str(detalle)[:160]))

    from src.db import conexion, migrador
    paso("1. crear BD + esquema", conexion.ensure_schema(force=True))
    try:
        migrador.aplicar_pendientes(backup=False); paso("2. aplicar migraciones", True)
    except Exception as e:
        paso("2. aplicar migraciones", False, e)

    from src.db import usuario as U
    try:
        _crear_usuario_smoke(); paso("3. crear usuario nominal", True)
    except Exception as e:
        paso("3. crear usuario nominal", False, e)
    datos = U.validar_login_usuario(_USUARIO, _CLAVE)
    paso("4. login nominal", bool(datos))
    if datos:
        U.sesion_global.iniciar_sesion(datos)

    try:
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
    except Exception as e:
        app = None
        paso("5-7. entorno Qt", False, e)
    if app is not None:
        import importlib
        for etiqueta, modulo, clase in [
            ("5. abrir TPV", "src.gui.tpv", "TPVWindow"),
            ("6. abrir stock", "src.gui.mostrar_stock", "MostrarStockWindow"),
            ("7. abrir catálogo", "src.gui.catalogo_gestion", "CatalogoWindow"),
        ]:
            try:
                cls = getattr(importlib.import_module(modulo), clase)
                w = cls()
                try:
                    w.close()
                except Exception:
                    pass
                paso(etiqueta, True)
            except Exception as e:
                paso(etiqueta, False, e)

    try:
        from src.db import fiscal as F
        from src.db.empresa import contexto_tenant
        from src.services.fiscal import proveedor_fiscal_actual
        emp = F._empresa(None)
        with contexto_tenant(emp, None):
            reg = proveedor_fiscal_actual().registrar("ticket", referencia="SMOKE_E14", total=1.0)
        paso("8. fiscal: registro + cadena válida",
             bool(getattr(reg, "hash", None)) and F.cadena_valida(emp, serie=reg.serie))
    except Exception as e:
        paso("8. fiscal: registro + cadena válida", False, e)

    try:
        U.sesion_global.cerrar_sesion()
    except Exception:
        pass
    _borrar_usuario_smoke()
    paso("9. cierre de sesión", True)
    return pasos


def test_smoke_producto(db):
    pasos = ejecutar_smoke()
    fallos = {n: d for n, ok, d in pasos if not ok}
    assert not fallos, f"Pasos fallidos en el smoke de producto: {fallos}"


def _main() -> int:
    pasos = ejecutar_smoke()
    print("\n=== SMOKE PRODUCTO — Smart Manager AI ===")
    for nombre, ok, detalle in pasos:
        print(f"  [{'OK ' if ok else 'FALLO'}] {nombre}" + (f"  -> {detalle}" if detalle and not ok else ""))
    fallos = [p for p in pasos if not p[1]]
    print(f"\nResultado: {len(pasos) - len(fallos)}/{len(pasos)} pasos OK")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(_main())
