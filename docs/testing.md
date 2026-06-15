# Pruebas automatizadas — Smart Manager AI

Suite de pruebas con **pytest** + **cobertura**. Estrategia validada: **base de
datos de pruebas dedicada** (`*_test`, aislada) con *factories* de limpieza.

## Cómo ejecutar

```bash
pip install -r requirements-dev.txt        # pytest, cobertura, etc.

python -m pytest                  # todo (unit + integración + smoke) con cobertura
python -m pytest -m "not db"      # solo pruebas que NO necesitan base de datos
python -m pytest tests/unit       # solo unitarias
python tests/smoke_test.py        # smoke independiente (sin pytest)
```

Si MariaDB no está disponible, las pruebas marcadas `@pytest.mark.db` se **omiten**
(no fallan), de modo que la parte pura corre en cualquier entorno.

## Base de datos de pruebas

- Se usa una base **independiente**: `smart_manager_test` (configurable con la
  variable `TEST_DB_NAME`). Mismo host/usuario/contraseña que `.env`.
- `tests/conftest.py` fija `DB_NAME` con el nombre de test **antes** de importar
  `src` (porque `conexion.py` lee la config en tiempo de import; `load_dotenv` no
  la sobreescribe).
- **Guard de seguridad:** los tests se abortan si la BD efectiva no termina en
  `_test`. Es imposible tocar los datos reales.
- El esquema se construye una vez por sesión con `ensure_schema()` (el bootstrap
  respeta `DB_NAME`, ver nota de compatibilidad abajo).

## Fixtures principales (`tests/conftest.py`)

- `db` → pide la base de datos (la crea/verifica la primera vez); omite el test si
  no hay MariaDB. Úsalo como argumento: `def test_x(db): ...`.
- `fab` → **fábrica con limpieza automática** (`tests/factories.py`): cada entidad
  creada se borra al terminar el test, en orden inverso. Métodos: `empresa`,
  `articulo`, `categoria`, `marca`, `producto_catalogo`, `pedido_online`,
  `pasarela`, `web`, `buzon_correo`. Mantiene intacta la semilla.

## Estructura

```
tests/
  conftest.py        # BD de pruebas + guard + fixtures
  factories.py       # datos de prueba con limpieza
  smoke_test.py      # imports + i18n + fuentes (sin BD)
  unit/              # lógica pura, sin BD (@pytest.mark.unit)
  integration/       # BD/servicios (@pytest.mark.db)
```

## Marcadores

`unit`, `db`, `integration`, `slow` (declarados en `pyproject.toml`).

## Cobertura

Configurada en `pyproject.toml` (`[tool.coverage.*]`): mide `src/`, **omite la UI
Qt** (`src/gui/*`), `__init__`, `main.py` y `tests/`. De momento solo informa; el
umbral (`--cov-fail-under`) se subirá progresivamente conforme crezca la cobertura
de `src/db` y `src/services`.

## Integración continua (CI)

`.github/workflows/tests.yml` ejecuta la suite en cada push/PR a main/master:
- Levanta un servicio **MariaDB 11** y define `TEST_DB_NAME=smart_manager_test`.
- Instala dependencias de sistema (Qt headless, zbar, unixODBC) + `requirements-dev.txt`.
- Ejecuta `pytest` con cobertura y un umbral mínimo (`--cov-fail-under=20`, se subirá
  conforme crezca la cobertura) y publica `coverage.xml` como artefacto.

El umbral solo se aplica en CI (no en `addopts`), para que `pytest -m "not db"` en
local no falle por cobertura parcial.

## Nota de compatibilidad (cambio de testabilidad)

El bootstrap (`src/database/bootstrap_mariadb.sql`) fijaba el nombre de la base
(`smart_manager_db`). Ahora `asegurar_base_de_datos()` sustituye ese nombre por el
de `DB_CONFIG["database"]`, de modo que:
- En producción (`DB_NAME=smart_manager_db`) el comportamiento es **idéntico**.
- En pruebas, el esquema se construye en `smart_manager_test` (aislamiento real).
Esto además corrige un bug latente: `DB_NAME` no se respetaba en el bootstrap.
