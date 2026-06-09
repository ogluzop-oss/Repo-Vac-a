"""
Capa de datos de EMPRESA — entidad raíz del modelo multiempresa (multi-tenant).

Jerarquía objetivo del sistema:

    empresa  →  tienda  →  usuario  →  (correos, documentos, stock, ...)

La identidad raíz es `id_empresa` (UUID interno) con un código visible (EMP-001).
En esta fase la app sigue siendo de escritorio mono-empresa: hay UNA empresa por
defecto ([[project_multidivisa]] no relacionado) y todo cuelga de ella, de forma
que las consultas actuales (sin filtro de tenant) siguen funcionando igual.

`TenantContext` mantiene la empresa/tienda ACTIVA del proceso. Hoy apunta siempre
a la empresa por defecto; en el futuro se fijará al iniciar sesión, y los módulos
filtrarán por `empresa_actual_id()` para aislar datos entre empresas.
"""

import logging
import uuid

from src.db.conexion import (
    EMPRESA_DEFAULT_CODIGO,
    EMPRESA_DEFAULT_ID,
    _fila_a_dict,
    _filas_a_dicts,
    ensure_schema,
    obtener_conexion,
)

logger = logging.getLogger("empresa_db")

# Re-export para comodidad de los consumidores.
DEFAULT_ID = EMPRESA_DEFAULT_ID
DEFAULT_CODIGO = EMPRESA_DEFAULT_CODIGO


# ============================================================
# CONTEXTO DE TENANT (empresa / tienda activa del proceso)
# ============================================================
class TenantContext:
    """Singleton con la empresa y tienda activas. Defecto: empresa por defecto.

    Uso futuro: al iniciar sesión se fijará la empresa/tienda del usuario, y los
    módulos llamarán a `empresa_actual_id()` para filtrar por tenant."""

    _instancia = None

    def __new__(cls):
        if cls._instancia is None:
            cls._instancia = super().__new__(cls)
            cls._instancia.empresa_id = EMPRESA_DEFAULT_ID
            cls._instancia.tienda_id = None
        return cls._instancia


_ctx = TenantContext()


def empresa_actual_id() -> str:
    """ID (UUID) de la empresa activa. Hoy, la empresa por defecto."""
    return _ctx.empresa_id or EMPRESA_DEFAULT_ID


def tienda_actual_id():
    """ID de la tienda activa (o None si no hay una fijada)."""
    return _ctx.tienda_id


def set_empresa_actual(id_empresa: str):
    _ctx.empresa_id = id_empresa or EMPRESA_DEFAULT_ID


def set_tienda_actual(id_tienda):
    _ctx.tienda_id = id_tienda


# ============================================================
# CRUD DE EMPRESAS
# ============================================================
def obtener_empresa(id_empresa: str | None = None) -> dict | None:
    """Devuelve la empresa indicada (o la activa) como dict, o None."""
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM empresas WHERE id_empresa = %s", (id_empresa,))
                return _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        logger.error("Error obtener_empresa(%s): %s", id_empresa, e)
        return None


def listar_empresas() -> list[dict]:
    """Lista todas las empresas (para el futuro panel SUPERADMIN)."""
    try:
        ensure_schema()
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM empresas ORDER BY codigo_empresa ASC"
                )
                return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("Error listar_empresas: %s", e)
        return []


def _siguiente_codigo_empresa(cur) -> str:
    """Calcula el próximo código visible EMP-00N."""
    cur.execute(
        "SELECT codigo_empresa FROM empresas WHERE codigo_empresa LIKE 'EMP-%' "
        "ORDER BY codigo_empresa DESC LIMIT 1"
    )
    row = cur.fetchone()
    ultimo = 0
    if row:
        val = row[0] if not isinstance(row, dict) else row["codigo_empresa"]
        try:
            ultimo = int(str(val).split("-")[-1])
        except (ValueError, IndexError):
            ultimo = 0
    return f"EMP-{ultimo + 1:03d}"


def crear_empresa(nombre_empresa: str, **campos) -> str | None:
    """Crea una empresa nueva (UUID interno + código EMP-00N visible).
    Acepta campos opcionales: razon_social, cif_nif, direccion_fiscal, telefono,
    email_principal, plan_licencia. Devuelve el id_empresa creado o None."""
    nuevo_id = str(uuid.uuid4())
    permitidos = (
        "razon_social", "cif_nif", "direccion_fiscal",
        "telefono", "email_principal", "plan_licencia",
    )
    extra = {k: v for k, v in campos.items() if k in permitidos and v is not None}
    try:
        ensure_schema()
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                codigo = _siguiente_codigo_empresa(cur)
                cols = ["id_empresa", "codigo_empresa", "nombre_empresa", *extra.keys()]
                vals = [nuevo_id, codigo, nombre_empresa, *extra.values()]
                ph = ", ".join(["%s"] * len(cols))
                cur.execute(
                    f"INSERT INTO empresas ({', '.join(cols)}) VALUES ({ph})", vals
                )
            conn.commit()
        logger.info("Empresa creada: %s (%s)", codigo, nuevo_id)
        return nuevo_id
    except Exception as e:
        logger.error("Error crear_empresa: %s", e)
        return None


def actualizar_empresa(id_empresa: str, **campos) -> bool:
    """Actualiza campos de una empresa."""
    permitidos = (
        "nombre_empresa", "razon_social", "cif_nif", "direccion_fiscal",
        "telefono", "email_principal", "estado", "plan_licencia",
    )
    sets = {k: v for k, v in campos.items() if k in permitidos}
    if not sets:
        return False
    try:
        ensure_schema()
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                asign = ", ".join(f"{k}=%s" for k in sets)
                cur.execute(
                    f"UPDATE empresas SET {asign} WHERE id_empresa=%s",
                    [*sets.values(), id_empresa],
                )
            conn.commit()
        return True
    except Exception as e:
        logger.error("Error actualizar_empresa(%s): %s", id_empresa, e)
        return False
