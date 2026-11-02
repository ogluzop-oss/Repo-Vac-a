"""
Deducciones sectoriales (Calculadora Fiscal / perfil fiscal) — CRUD + resolutor sobre la tabla
`fiscal_deducciones_sectoriales` (migr. 0273), mismo idioma que `fiscal_is_reglas.py`: un catálogo
editable en tabla, nunca un fichero a mano.

`resolver_deducciones()` es el matcher de especificidad: para un mismo `concepto`, una regla ligada a
un epígrafe concreto (`id_epigrafe` no NULL) es MÁS ESPECÍFICA que la regla general (`id_epigrafe`
NULL) y la sustituye en el resultado — mismo criterio de "lo más específico gana" que
`fiscal_is_reglas.resolver()`, aplicado aquí por concepto en vez de devolver una única regla (una
empresa puede tener varias deducciones sectoriales aplicables a la vez: suministros del hogar +
dietas + vehículo, por ejemplo).
"""

import logging

from src.db.conexion import _filas_a_dicts, obtener_conexion

logger = logging.getLogger("contab.fiscal_deducciones")


def crear_deduccion(concepto, *, id_epigrafe=None, porcentaje=None, importe_fijo=None,
                    condiciones=None, prioridad=0, activo=1):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO fiscal_deducciones_sectoriales "
                "(id_epigrafe, concepto, porcentaje, importe_fijo, condiciones, prioridad, activo) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (id_epigrafe or None, concepto,
                 float(porcentaje) if porcentaje is not None else None,
                 float(importe_fijo) if importe_fijo is not None else None,
                 condiciones or None, int(prioridad), int(bool(activo))))
            return cur.lastrowid
    except Exception as e:
        logger.error("crear_deduccion: %s", e)
        return None


def listar_deducciones(id_epigrafe=None, concepto=None, solo_activas=False):
    """Lista cruda de la tabla (sin resolver especificidad). `id_epigrafe`: filtra exactamente esa
    columna (usa `None` explícito para ver solo las generales; omite el argumento para verlas todas)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            q = "SELECT * FROM fiscal_deducciones_sectoriales WHERE 1=1"
            params = []
            if id_epigrafe is not None:
                q += " AND id_epigrafe=%s"; params.append(id_epigrafe)
            if concepto:
                q += " AND concepto=%s"; params.append(concepto)
            if solo_activas:
                q += " AND activo=1"
            q += " ORDER BY concepto, prioridad DESC, id"
            cur.execute(q, tuple(params))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_deducciones: %s", e)
        return []


def obtener_deduccion(id_deduccion):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM fiscal_deducciones_sectoriales WHERE id=%s", (id_deduccion,))
            filas = _filas_a_dicts(cur, cur.fetchall())
            return filas[0] if filas else None
    except Exception as e:
        logger.error("obtener_deduccion: %s", e)
        return None


def actualizar_deduccion(id_deduccion, **campos):
    permitidos = ("id_epigrafe", "concepto", "porcentaje", "importe_fijo", "condiciones",
                 "prioridad", "activo")
    datos = {k: v for k, v in campos.items() if k in permitidos}
    if not datos:
        return False
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            sets = ", ".join(f"{k}=%s" for k in datos)
            cur.execute(f"UPDATE fiscal_deducciones_sectoriales SET {sets} WHERE id=%s",
                        (*datos.values(), id_deduccion))
            return True
    except Exception as e:
        logger.error("actualizar_deduccion: %s", e)
        return False


def desactivar_deduccion(id_deduccion):
    return actualizar_deduccion(id_deduccion, activo=0)


def _especificidad(regla):
    """Cuanto más alto, más específica: ligada a un epígrafe concreto > general."""
    return (
        1 if regla.get("id_epigrafe") is not None else 0,
        int(regla.get("prioridad") or 0),
        int(regla.get("id") or 0),
    )


# Conceptos cuyo efecto fiscal es una BONIFICACIÓN DIRECTA EN CUOTA (crédito fiscal que resta del
# resultado final), en vez de un gasto deducible adicional (que resta de la base antes de aplicar el
# tipo). Ninguno de los conceptos sembrados hasta ahora en `fiscal_deducciones_sectoriales` (migr.
# 0273: suministros del hogar, dietas de manutención, vehículo) es de este tipo — los tres son SIEMPRE
# gasto deducible adicional bajo IRPF de autónomos (art. 9/11 RIRPF), nunca un crédito de cuota. Se
# deja preparado (frozenset vacío) para cuando se siembre alguno realmente de tipo crédito, sin tocar
# el esquema de la tabla (no tiene columna `tipo` y no hace falta una: la clasificación es de
# aplicación/negocio, no un dato editable por fila).
CONCEPTOS_CUOTA = frozenset()


def tipo_deduccion(concepto: str) -> str:
    """'cuota' si el concepto reduce directamente el resultado final (crédito fiscal); 'gasto' en
    cualquier otro caso (deducción que se aplica como gasto deducible adicional, aumentando la bolsa
    de gastos antes de calcular rendimiento neto/base imponible) — el valor por defecto honesto para
    todo lo sembrado hoy."""
    return "cuota" if concepto in CONCEPTOS_CUOTA else "gasto"


def separar_por_tipo(deducciones_aceptadas) -> tuple:
    """Suma total 'gasto' vs 'cuota' de una lista de deducciones ACEPTADAS por el usuario (shape del
    Paso 3 de la Calculadora Fiscal: `{'concepto', 'tipo', 'importe', ...}`, `importe` ya en euros,
    calculado en el propio Paso 3 a partir de `porcentaje`/`importe_fijo` + la base/cantidad que
    facilitó el usuario). Utilidad COMPARTIDA por `aeat.modelo_130` y `contabilidad.calculadora_fiscal`
    para no duplicar el mismo bucle de clasificación en los dos motores. Nunca se inventa un valor: un
    elemento sin 'importe' numérico o con `tipo` ausente cuenta como gasto de 0€."""
    gasto = 0.0
    cuota = 0.0
    for d in (deducciones_aceptadas or []):
        try:
            importe = float(d.get("importe") or 0)
        except Exception:
            importe = 0.0
        if d.get("tipo") == "cuota":
            cuota += importe
        else:
            gasto += importe
    return round(gasto, 2), round(cuota, 2)


def resolver_deducciones(id_epigrafe=None, id_empresa=None) -> list:
    """Devuelve la lista de deducciones sectoriales APLICABLES: todas las reglas activas generales
    (`id_epigrafe IS NULL`) más las activas del `id_epigrafe` dado, con UNA fila por `concepto` — si
    existen ambas (general + específica del epígrafe) para el mismo concepto, gana la más específica
    (nunca se devuelven las dos para no duplicar/sumar la misma deducción).

    `id_empresa` se acepta por simetría con `fiscal_is_reglas.resolver()` (mismo idioma de firma) pero
    hoy la tabla no es multiempresa (catálogo compartido, igual que `fiscal_iae_epigrafes`) — reservado
    para cuando alguna empresa necesite su propia deducción sectorial particular."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            q = "SELECT * FROM fiscal_deducciones_sectoriales WHERE activo=1 AND (id_epigrafe IS NULL"
            params = []
            if id_epigrafe is not None:
                q += " OR id_epigrafe=%s"
                params.append(id_epigrafe)
            q += ")"
            cur.execute(q, tuple(params))
            candidatas = _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("resolver_deducciones: %s", e)
        return []

    por_concepto = {}
    for regla in candidatas:
        actual = por_concepto.get(regla["concepto"])
        if actual is None or _especificidad(regla) > _especificidad(actual):
            por_concepto[regla["concepto"]] = regla
    return sorted(por_concepto.values(), key=lambda r: (r["concepto"], r.get("id") or 0))
