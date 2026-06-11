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
        # FASE 2 — datos corporativos para documentos
        "nombre_comercial", "municipio", "provincia", "comunidad_autonoma",
        "cp", "pais", "regimen_ss", "ccc", "cnae", "actividad_economica",
        "convenio_colectivo",
        # Códigos oficiales (SEPE)
        "cod_pais", "cod_provincia", "cod_municipio", "cod_actividad",
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


# ============================================================
# FUENTE ÚNICA DE DATOS CORPORATIVOS (para TODOS los documentos)
# ============================================================
import json as _json
import os as _os

_JSON_EMP = _os.path.normpath(
    _os.path.join(_os.path.dirname(__file__), "..", "..", "documentos", "datos_empresa.json")
)
_json_migrado = False


def _migrar_json_a_empresa():
    """Importa UNA vez el antiguo documentos/datos_empresa.json a la fila de la
    empresa por defecto, solo en los campos que aún estén vacíos. No se pierde
    nada y la BD pasa a ser la fuente de verdad."""
    global _json_migrado
    if _json_migrado:
        return
    _json_migrado = True
    if not _os.path.exists(_JSON_EMP):
        return
    try:
        with open(_JSON_EMP, encoding="utf-8") as f:
            j = _json.load(f) or {}
    except Exception:
        return
    emp = obtener_empresa(EMPRESA_DEFAULT_ID) or {}
    mapa = {
        "razon_social": "razon_social", "cif": "cif_nif",
        "direccion": "direccion_fiscal", "telefono": "telefono",
        "email": "email_principal", "municipio": "municipio", "cp": "cp",
        "ccc": "ccc", "actividad": "actividad_economica", "convenio": "convenio_colectivo",
    }
    sets = {}
    for jk, col in mapa.items():
        val = (j.get(jk) or "").strip() if isinstance(j.get(jk), str) else j.get(jk)
        if val and not (emp.get(col) or "").strip():
            sets[col] = val
    if sets:
        actualizar_empresa(EMPRESA_DEFAULT_ID, **sets)
        logger.info("datos_empresa.json migrado a empresas: %s", list(sets))


def _refrescar_cache_json(emp: dict, centro: dict | None, rep: dict | None):
    """Reescribe documentos/datos_empresa.json como caché de lectura (compatibilidad
    con lectores legacy durante la transición)."""
    try:
        data = {
            "razon_social": emp.get("razon_social") or emp.get("nombre_empresa") or "",
            "cif": emp.get("cif_nif") or "",
            "direccion": emp.get("direccion_fiscal") or "",
            "municipio": emp.get("municipio") or "",
            "cp": emp.get("cp") or "",
            "telefono": emp.get("telefono") or "",
            "email": emp.get("email_principal") or "",
            "ccc": emp.get("ccc") or "",
            "actividad": emp.get("actividad_economica") or "",
            "convenio": emp.get("convenio_colectivo") or "",
            "iban": "",
        }
        _os.makedirs(_os.path.dirname(_JSON_EMP), exist_ok=True)
        with open(_JSON_EMP, "w", encoding="utf-8") as f:
            _json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.debug("No se pudo refrescar cache datos_empresa.json: %s", e)


def datos_corporativos(id_empresa=None, id_tienda=None, id_centro=None,
                       id_representante=None) -> dict:
    """FUENTE ÚNICA DE VERDAD para los documentos del sistema.

    Devuelve {'empresa': {...}, 'representante': {...|None}, 'centro': {...|None}}
    resolviendo por el TenantContext si no se pasan IDs. El centro/representante
    devueltos son los seleccionados, o el principal de la empresa, o el primero."""
    from src.db import centros as _centros
    from src.db import representantes as _reps

    _migrar_json_a_empresa()
    id_empresa = id_empresa or empresa_actual_id()
    id_tienda = id_tienda if id_tienda is not None else tienda_actual_id()

    empresa = obtener_empresa(id_empresa) or {}
    representante = (_reps.obtener_representante(id_representante) if id_representante
                    else _reps.representante_principal(id_empresa))
    centro = None
    if id_centro:
        centro = _centros.obtener_centro(id_centro)
    else:
        centro = _centros.centro_principal(id_empresa, id_tienda)

    _refrescar_cache_json(empresa, centro, representante)
    return {"empresa": empresa, "representante": representante, "centro": centro}


def info_documento(id_empresa=None, id_centro=None, id_representante=None) -> dict:
    """Vista PLANA de los datos corporativos para los generadores de documentos
    (facturas, albaranes, pedidos, traspasos, certificados, tickets, informes…).
    Una sola fuente de verdad; claves estables y retrocompatibles."""
    dc = datos_corporativos(id_empresa=id_empresa, id_centro=id_centro,
                            id_representante=id_representante)
    e = dc.get("empresa") or {}
    rep = dc.get("representante") or {}
    c = dc.get("centro") or {}
    nombre = e.get("razon_social") or e.get("nombre_comercial") or e.get("nombre_empresa") or "SMART MANAGER"
    partes_dir = [e.get("direccion_fiscal"), e.get("cp"), e.get("municipio")]
    direccion_completa = ", ".join(x for x in partes_dir if x)
    if e.get("provincia"):
        direccion_completa = (direccion_completa + f" ({e.get('provincia')})").strip()
    return {
        "nombre": nombre,
        "razon_social": e.get("razon_social") or "",
        "nombre_comercial": e.get("nombre_comercial") or "",
        "cif": e.get("cif_nif") or "",
        "direccion": e.get("direccion_fiscal") or "",
        "direccion_completa": direccion_completa or (e.get("direccion_fiscal") or ""),
        "municipio": e.get("municipio") or "",
        "provincia": e.get("provincia") or "",
        "cp": e.get("cp") or "",
        "pais": e.get("pais") or "ESPAÑA",
        "telefono": e.get("telefono") or "",
        "email": e.get("email_principal") or "",
        "ccc": e.get("ccc") or "",
        "cnae": e.get("cnae") or "",
        "actividad": e.get("actividad_economica") or "",
        "convenio": e.get("convenio_colectivo") or "",
        "regimen": e.get("regimen_ss") or "0111",
        # Códigos oficiales de empresa
        "cod_pais": e.get("cod_pais") or "",
        "cod_provincia": e.get("cod_provincia") or "",
        "cod_municipio": e.get("cod_municipio") or "",
        "cod_actividad": e.get("cod_actividad") or "",
        "rep_nombre": " ".join(x for x in [rep.get("nombre"), rep.get("apellidos")] if x).strip(),
        "rep_nif": rep.get("dni_nie") or "",
        "rep_cargo": rep.get("cargo") or "",
        "centro_nombre": c.get("nombre_centro") or "",
        "centro_codigo": c.get("codigo_centro") or "",
        "centro_direccion": c.get("direccion") or "",
        "centro_municipio": c.get("municipio") or "",
        "centro_provincia": c.get("provincia") or "",
        "centro_cp": c.get("codigo_postal") or "",
        "centro_ccc": c.get("codigo_cuenta_cotizacion") or "",
        "centro_actividad": c.get("actividad_economica") or "",
        "centro_cod_pais": c.get("cod_pais") or "",
        "centro_cod_municipio": c.get("cod_municipio") or "",
        "centro_cod_actividad": c.get("cod_actividad") or "",
    }
