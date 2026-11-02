"""
Perfil fiscal de la empresa (Fase A de "Smart Accounting") — epígrafe(s) IAE asignados y los campos
derivados (régimen de IRPF, obligación de Modelos 130/303/111) que el Paso 1 del wizard de Calculadora
Fiscal auto-rellena. Sobre las tablas `fiscal_iae_epigrafes`/`fiscal_empresa_epigrafe` (migr. 0273).

**Cardinalidad empresa↔epígrafe: MÚLTIPLE, no "uno activo a la vez".** Una empresa/autónomo puede
estar dado de alta simultáneamente en varios epígrafes IAE (p. ej. comercio al por menor + hostelería
en el mismo negocio) — es una situación legal habitual en España, no una excepción a modelar aparte.
Por eso `asignar_epigrafe()` AÑADE una fila nueva (no sustituye ninguna anterior) y
`perfil_fiscal_empresa()` combina TODOS los epígrafes activos de la empresa: el régimen de IRPF
derivado es el MÁS EXIGENTE de los asignados (si cualquiera de ellos no admite módulos, la empresa ya
no puede tributar en módulos para el conjunto de su actividad — Directa Simplificada por defecto,
salvo que TODOS los epígrafes asignados admitan módulos) y cada obligación de modelo
(130/303/111) es la UNIÓN (basta que UN epígrafe la exija para que la empresa deba presentarlo).
"""

import datetime as _dt
import logging

from src.db.conexion import _filas_a_dicts, obtener_conexion

logger = logging.getLogger("contab.fiscal_perfil")


def _empresa(id_empresa=None):
    if id_empresa is not None:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID


def buscar_epigrafes(texto, seccion=None) -> list:
    """Búsqueda por subcadena (código o descripción), case-insensitive, sobre el catálogo
    `fiscal_iae_epigrafes` activo. `texto` vacío devuelve el catálogo completo (para poblar un
    desplegable buscable de golpe, patrón `_combo_buscable` ya usado en otras pantallas de la app)."""
    texto = (texto or "").strip()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            q = "SELECT * FROM fiscal_iae_epigrafes WHERE activo=1"
            params = []
            if seccion:
                q += " AND seccion=%s"; params.append(seccion)
            if texto:
                q += " AND (codigo LIKE %s OR descripcion LIKE %s)"
                comodin = f"%{texto}%"
                params += [comodin, comodin]
            q += " ORDER BY seccion, codigo"
            cur.execute(q, tuple(params))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("buscar_epigrafes: %s", e)
        return []


def obtener_epigrafe(id_epigrafe):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM fiscal_iae_epigrafes WHERE id=%s", (id_epigrafe,))
            filas = _filas_a_dicts(cur, cur.fetchall())
            return filas[0] if filas else None
    except Exception as e:
        logger.error("obtener_epigrafe: %s", e)
        return None


def asignar_epigrafe(id_empresa, id_epigrafe) -> dict:
    """Da de alta una asignación NUEVA (no sustituye ninguna anterior — ver nota de cardinalidad del
    módulo). Idempotente: si la empresa ya tiene ese epígrafe activo, no duplica la fila."""
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM fiscal_empresa_epigrafe WHERE id_empresa=%s AND id_epigrafe=%s "
                "AND activo=1", (id_empresa, id_epigrafe))
            existente = cur.fetchone()
            if existente:
                id_asignacion = existente[0] if not isinstance(existente, dict) else existente["id"]
                return {"ok": True, "id": id_asignacion, "ya_existia": True}
            cur.execute(
                "INSERT INTO fiscal_empresa_epigrafe (id_empresa, id_epigrafe, fecha_alta, activo) "
                "VALUES (%s,%s,%s,1)", (id_empresa, id_epigrafe, _dt.datetime.now()))
            return {"ok": True, "id": cur.lastrowid, "ya_existia": False}
    except Exception as e:
        logger.error("asignar_epigrafe: %s", e)
        return {"ok": False, "error": str(e)}


def desasignar_epigrafe(id_empresa, id_epigrafe) -> bool:
    """Baja lógica (soft delete) de una asignación — conserva el historial (`fecha_baja`)."""
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE fiscal_empresa_epigrafe SET activo=0, fecha_baja=%s "
                "WHERE id_empresa=%s AND id_epigrafe=%s AND activo=1",
                (_dt.datetime.now(), id_empresa, id_epigrafe))
            return True
    except Exception as e:
        logger.error("desasignar_epigrafe: %s", e)
        return False


def epigrafes_asignados(id_empresa=None) -> list:
    """Epígrafes activos asignados a la empresa (join con el catálogo)."""
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT e.*, ae.fecha_alta AS fecha_alta_empresa "
                "FROM fiscal_empresa_epigrafe ae "
                "JOIN fiscal_iae_epigrafes e ON e.id = ae.id_epigrafe "
                "WHERE ae.id_empresa=%s AND ae.activo=1 AND e.activo=1 "
                "ORDER BY ae.fecha_alta", (id_empresa,))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("epigrafes_asignados: %s", e)
        return []


# Orden de "exigencia" del régimen de IRPF: si la empresa tiene varios epígrafes y no todos admiten el
# mismo régimen, se queda con el régimen más restrictivo (Directa gana a Módulos: en cuanto una sola
# actividad no es de módulos, el conjunto de la actividad económica ya tributa en Estimación Directa).
_RANGO_REGIMEN = {"modulos": 0, "estimacion_directa_simplificada": 1, "estimacion_directa_normal": 2}


def perfil_fiscal_empresa(id_empresa=None) -> dict:
    """Perfil fiscal derivado de TODOS los epígrafes activos de la empresa: régimen de IRPF resultante
    y qué modelos (130/303/111) son obligatorios. Sin epígrafes asignados, devuelve un perfil vacío
    (`sin_epigrafe=True`) — nunca inventa un régimen por defecto sin que el usuario haya elegido nada."""
    id_empresa = _empresa(id_empresa)
    epigrafes = epigrafes_asignados(id_empresa)
    if not epigrafes:
        return {
            "id_empresa": id_empresa, "epigrafes": [], "sin_epigrafe": True,
            "regimen_irpf": None, "modelo_130": False, "modelo_303": False, "modelo_111": False,
        }

    # El régimen resultante no se puede resolver con un `max()` alfabético de texto — se resuelve por
    # el rango de exigencia numérico definido arriba (Directa > Módulos).
    regimen = max(epigrafes, key=lambda e: _RANGO_REGIMEN.get(
        e.get("regimen_irpf_defecto") or "estimacion_directa_simplificada", 1)
    ).get("regimen_irpf_defecto")

    modelo_130 = any(bool(e.get("requiere_modelo_130")) for e in epigrafes)
    modelo_303 = any(bool(e.get("requiere_modelo_303")) for e in epigrafes)
    modelo_111 = any(bool(e.get("requiere_modelo_111_si_personal")) for e in epigrafes)

    return {
        "id_empresa": id_empresa,
        "epigrafes": [{"id": e["id"], "seccion": e["seccion"], "codigo": e["codigo"],
                      "descripcion": e["descripcion"]} for e in epigrafes],
        "sin_epigrafe": False,
        "regimen_irpf": regimen,
        "modelo_130": modelo_130,
        "modelo_303": modelo_303,
        "modelo_111": modelo_111,
    }
