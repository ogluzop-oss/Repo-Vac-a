"""
Configuración de pytest para Smart Manager AI.

CLAVE: fija la base de datos de PRUEBAS (`DB_NAME`) ANTES de importar cualquier
módulo de `src`, porque `src/db/conexion.py` construye `DB_CONFIG` en tiempo de
import (con `load_dotenv(override=False)`, que NO sobrescribe lo ya puesto aquí).

Estrategia (validada): base de datos DEDICADA `*_test` + factories con limpieza.
Guard de seguridad: los tests de BD se niegan a ejecutarse si la BD efectiva no
termina en `_test`, para no tocar jamás los datos reales.
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Qt en modo headless para poder importar módulos que tocan widgets.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Base de datos de pruebas (se puede sobreescribir con TEST_DB_NAME).
os.environ["DB_NAME"] = os.environ.get("TEST_DB_NAME", "smart_manager_test")

import pytest  # noqa: E402

# QApplication única para todo el proceso (necesaria al importar widgets).
try:
    from PyQt6.QtWidgets import QApplication
    _APP = QApplication.instance() or QApplication([])
except Exception:
    _APP = None


@pytest.fixture(scope="session")
def esquema_test():
    """Construye el esquema en la BD de pruebas una vez por sesión.

    `ensure_schema()` crea la base de datos de test y todas sus tablas (el
    bootstrap respeta `DB_NAME`). Si MariaDB no está disponible, omite los tests
    que dependan de BD en vez de fallar."""
    from src.db import conexion
    dbname = conexion.DB_CONFIG.get("database", "")
    # Guard de seguridad: nunca operar sobre una BD que no sea de pruebas.
    if not dbname.endswith("_test"):
        pytest.exit(f"SEGURIDAD: la BD de pruebas debe terminar en '_test' (es '{dbname}').", 1)
    try:
        import pymysql
        cfg = {k: v for k, v in conexion.DB_CONFIG.items() if k != "database"}
        pymysql.connect(**cfg).close()        # comprueba que el servidor responde
    except Exception as e:
        pytest.skip(f"MariaDB no disponible para tests de BD: {e}")
        return None
    if not conexion.ensure_schema(force=True):
        pytest.skip("No se pudo construir el esquema de pruebas.")
    return dbname


@pytest.fixture
def db(esquema_test):
    """Marca el test como dependiente de BD y devuelve el módulo de conexión.

    Úsalo pidiéndolo como argumento: ``def test_x(db): ...``. Pulls del esquema
    de sesión (lo crea la primera vez) y omite el test si no hay MariaDB."""
    from src.db import conexion
    return conexion


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    """Limpia el contador de rate limiting entre tests (mismo IP/endpoint en el
    mismo proceso) para evitar 429 espurios."""
    try:
        from src.seguridad import rate_limit as RL
        RL.backend().reset()
    except Exception:
        pass
    yield


@pytest.fixture
def fab(db):
    """Fábrica de datos de prueba con LIMPIEZA automática.

    Cada `fab.*` inserta una fila y registra su borrado; al terminar el test se
    eliminan en orden inverso. Mantiene intacta la semilla (empresas/tiendas)."""
    from tests.factories import Fabrica
    f = Fabrica(db)
    try:
        yield f
    finally:
        f.limpiar()
