"""
CRUD de reglas del Impuesto de Sociedades (Calculadora Fiscal) — clon del patrón de
`services.precio_dinamico.reglas` (mismo idioma, misma forma de las funciones) sobre la tabla
`fiscal_is_reglas` (migr. 0237). SUSTITUYE el JSON plano de la primera versión: el tipo general y las
deducciones se editan aquí, desde la propia pantalla de la Calculadora Fiscal — nunca a mano en un
fichero.

`resolver()` es el matcher de especificidad: de las reglas activas de un concepto compatibles con el
contexto (CCAA/tipo de entidad/tramo de base imponible/vigencia), elige la más específica. Sin ninguna
regla aplicable, devuelve `None` — el motor de cálculo (`calculadora_fiscal.py`) NUNCA convierte un
`None` en un cero silencioso, lo reporta como `reglas_faltantes`.
"""

import datetime as _dt
import logging

from src.db.conexion import _filas_a_dicts, obtener_conexion

logger = logging.getLogger("contab.fiscal_is_reglas")

CONCEPTOS = ("tipo_general", "empleo_indefinido", "empleo_bonificado", "id", "digitalizacion")
UNIDADES = ("pct", "eur")

# Semilla de reglas nacionales por defecto (mismos valores que tenía el JSON de la v1) — se insertan
# UNA vez, la primera vez que `listar_reglas()` no encuentra ninguna fila para la empresa. A partir de
# ahí son datos normales de la tabla: 100% editables/borrables desde la pantalla, nunca se vuelve a
# escribir un fichero.
_SEMILLA = (
    ("tipo_general", "pct", 25.0),
    ("empleo_indefinido", "eur", 3000.0),
    ("empleo_bonificado", "eur", 9000.0),
    ("id", "pct", 25.0),
    ("digitalizacion", "pct", 15.0),
)


def _empresa(id_empresa=None):
    if id_empresa is not None:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID


def crear_regla(concepto, *, ccaa=None, tipo_entidad=None, base_desde=None, base_hasta=None,
                unidad="pct", valor=0, vigente_desde=None, vigente_hasta=None, prioridad=0,
                activo=1, id_empresa=None):
    if concepto not in CONCEPTOS or unidad not in UNIDADES:
        return None
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO fiscal_is_reglas (id_empresa, concepto, ccaa, tipo_entidad, base_desde, "
                "base_hasta, unidad, valor, vigente_desde, vigente_hasta, prioridad, activo) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (_empresa(id_empresa), concepto, ccaa or None, tipo_entidad or None, base_desde,
                 base_hasta, unidad, float(valor), vigente_desde or None, vigente_hasta or None,
                 int(prioridad), int(bool(activo))))
            return cur.lastrowid
    except Exception as e:
        logger.error("crear_regla: %s", e)
        return None


def _sembrar_defecto(id_empresa):
    for concepto, unidad, valor in _SEMILLA:
        crear_regla(concepto, unidad=unidad, valor=valor, id_empresa=id_empresa)


def listar_reglas(id_empresa=None, concepto=None, solo_activas=False):
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM fiscal_is_reglas WHERE id_empresa=%s", (id_empresa,))
            row = cur.fetchone()
            n = row[0] if not isinstance(row, dict) else list(row.values())[0]
        if not n:
            _sembrar_defecto(id_empresa)
        with obtener_conexion() as conn, conn.cursor() as cur:
            q = "SELECT * FROM fiscal_is_reglas WHERE id_empresa=%s"
            params = [id_empresa]
            if concepto:
                q += " AND concepto=%s"; params.append(concepto)
            if solo_activas:
                q += " AND activo=1"
            q += " ORDER BY concepto, prioridad DESC, id"
            cur.execute(q, tuple(params))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_reglas: %s", e)
        return []


def obtener_regla(id_regla, id_empresa=None):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM fiscal_is_reglas WHERE id=%s AND id_empresa=%s",
                        (id_regla, _empresa(id_empresa)))
            filas = _filas_a_dicts(cur, cur.fetchall())
            return filas[0] if filas else None
    except Exception as e:
        logger.error("obtener_regla: %s", e)
        return None


def actualizar_regla(id_regla, id_empresa=None, **campos):
    permitidos = ("concepto", "ccaa", "tipo_entidad", "base_desde", "base_hasta", "unidad", "valor",
                 "vigente_desde", "vigente_hasta", "prioridad", "activo")
    datos = {k: v for k, v in campos.items() if k in permitidos}
    if not datos:
        return False
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            sets = ", ".join(f"{k}=%s" for k in datos)
            cur.execute(f"UPDATE fiscal_is_reglas SET {sets} WHERE id=%s AND id_empresa=%s",
                        (*datos.values(), id_regla, _empresa(id_empresa)))
            return True
    except Exception as e:
        logger.error("actualizar_regla: %s", e)
        return False


def eliminar_regla(id_regla, id_empresa=None):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM fiscal_is_reglas WHERE id=%s AND id_empresa=%s",
                        (id_regla, _empresa(id_empresa)))
            return True
    except Exception as e:
        logger.error("eliminar_regla: %s", e)
        return False


def _fecha(v):
    if v is None:
        return None
    if isinstance(v, _dt.date):
        return v
    try:
        return _dt.date.fromisoformat(str(v)[:10])
    except Exception:
        return None


def _aplica(regla, *, ccaa, tipo_entidad, base_imponible, fecha):
    if not regla.get("activo"):
        return False
    r_ccaa = regla.get("ccaa")
    if r_ccaa and (ccaa or "").strip().lower() != r_ccaa.strip().lower():
        return False
    r_tipo = regla.get("tipo_entidad")
    if r_tipo and (tipo_entidad or "").strip().upper() != r_tipo.strip().upper():
        return False
    bd, bh = regla.get("base_desde"), regla.get("base_hasta")
    if base_imponible is not None:
        if bd is not None and float(base_imponible) < float(bd):
            return False
        if bh is not None and float(base_imponible) > float(bh):
            return False
    vd, vh = _fecha(regla.get("vigente_desde")), _fecha(regla.get("vigente_hasta"))
    if vd and fecha < vd:
        return False
    if vh and fecha > vh:
        return False
    return True


def _especificidad(regla):
    """Cuanto más alto, más específica: CCAA propio > tipo_entidad propio > tramo de base propio."""
    return (
        1 if regla.get("ccaa") else 0,
        1 if regla.get("tipo_entidad") else 0,
        1 if (regla.get("base_desde") is not None or regla.get("base_hasta") is not None) else 0,
        int(regla.get("prioridad") or 0),
        int(regla.get("id") or 0),
    )


def resolver(concepto, *, ccaa=None, tipo_entidad=None, base_imponible=None, fecha=None,
            id_empresa=None) -> dict | None:
    """Devuelve la regla activa MÁS ESPECÍFICA compatible con el contexto, o `None` si ninguna
    aplica (nunca inventa un valor por defecto silenciosamente)."""
    fecha = fecha or _dt.date.today()
    candidatas = [r for r in listar_reglas(id_empresa, concepto=concepto, solo_activas=True)
                 if _aplica(r, ccaa=ccaa, tipo_entidad=tipo_entidad, base_imponible=base_imponible,
                           fecha=fecha)]
    if not candidatas:
        return None
    return max(candidatas, key=_especificidad)
