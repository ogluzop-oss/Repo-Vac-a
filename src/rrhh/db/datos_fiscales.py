"""
Capa de datos: DATOS FISCALES DEL EMPLEADO (Modelo 145 AEAT) — Fase B2. Multi-tenant.

`rrhh_datos_fiscales` (uno por empleado, `UNIQUE(id_empresa, id_empleado)`) + sus dos tablas hijas
`rrhh_datos_fiscales_hijos`/`rrhh_datos_fiscales_ascendientes`. Patrón CRUD idéntico al resto de
`src/rrhh/db/*` (conexión de `src.db.conexion`, consultas parametrizadas, sin ORM).

Este es el ÚNICO sitio del IRPF de un empleado (`irpf_pct_calculado`) — no vive en `rrhh_contratos`.

Las tablas hijas usan el patrón "borrar e insertar" en cada guardado (no hay UPDATE fila a fila):
`guardar_datos_fiscales()` sustituye TODAS las filas de hijos/ascendientes del empleado por las que
llegan en cada llamada, dentro de la misma conexión/transacción que el upsert del padre.
"""

import logging

from src.db.conexion import (_fila_a_dict, _filas_a_dicts, ensure_schema,
                             obtener_conexion)
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("rrhh.datos_fiscales")

_PERMITIDOS = (
    "situacion_familiar", "nif_conyuge", "discapacidad_trabajador",
    "ayuda_terceros_movilidad", "movilidad_geografica", "rentas_irregulares",
    "pension_compensatoria_anual", "anualidades_alimentos_anual",
    "vivienda_habitual_pre2013", "irpf_pct_calculado", "fecha_calculo",
)
_PERMITIDOS_HIJO = ("anio_nacimiento", "anio_adopcion", "grado_discapacidad", "computo_entero")
_PERMITIDOS_ASCENDIENTE = ("anio_nacimiento", "grado_discapacidad", "convivencia_otros_descendientes")


def _normalizar_bool(campos: dict, claves) -> dict:
    """TINYINT(1): normaliza checkboxes/bool de Python a 0/1 explícito (evita 'True'/'False' string
    si algún llamador pasa un bool directamente; pymysql ya lo admite, pero se deja explícito)."""
    d = dict(campos)
    for k in claves:
        if k in d and d[k] is not None:
            d[k] = 1 if d[k] else 0
    return d


_BOOL_PADRE = ("ayuda_terceros_movilidad", "movilidad_geografica", "rentas_irregulares",
              "vivienda_habitual_pre2013")
_BOOL_HIJO = ("computo_entero",)
_BOOL_ASCENDIENTE = ("convivencia_otros_descendientes",)


# ── Padre (rrhh_datos_fiscales) ────────────────────────────────────────────────
def obtener_datos_fiscales(id_empleado, id_empresa=None) -> dict | None:
    """Fila de `rrhh_datos_fiscales` del empleado, con sus `hijos`/`ascendientes` embebidos.
    None si el empleado aún no tiene datos fiscales guardados."""
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM rrhh_datos_fiscales WHERE id_empleado=%s AND id_empresa=%s",
                (id_empleado, id_empresa))
            fila = _fila_a_dict(cur, cur.fetchone())
            if not fila:
                return None
            cur.execute(
                "SELECT * FROM rrhh_datos_fiscales_hijos WHERE id_datos_fiscales=%s ORDER BY id",
                (fila["id"],))
            fila["hijos"] = _filas_a_dicts(cur, cur.fetchall())
            cur.execute(
                "SELECT * FROM rrhh_datos_fiscales_ascendientes WHERE id_datos_fiscales=%s ORDER BY id",
                (fila["id"],))
            fila["ascendientes"] = _filas_a_dicts(cur, cur.fetchall())
            return fila
    except Exception as e:
        logger.error("obtener_datos_fiscales(emp=%s): %s", id_empleado, e)
        return None


def guardar_datos_fiscales(id_empleado, id_empresa=None, hijos=None, ascendientes=None,
                           **campos) -> int | None:
    """Upsert de `rrhh_datos_fiscales` (crea si no existe, actualiza si ya existe — respeta el
    UNIQUE(id_empresa, id_empleado)) + reemplazo completo ("borrar e insertar") de `hijos` y
    `ascendientes`. Devuelve el `id` de `rrhh_datos_fiscales` o None si falla."""
    id_empresa = id_empresa or empresa_actual_id()
    datos = _normalizar_bool({k: campos.get(k) for k in _PERMITIDOS if k in campos}, _BOOL_PADRE)
    hijos = hijos or []
    ascendientes = ascendientes or []
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM rrhh_datos_fiscales WHERE id_empleado=%s AND id_empresa=%s",
                (id_empleado, id_empresa))
            existente = cur.fetchone()
            if existente:
                id_df = existente[0] if not isinstance(existente, dict) else existente["id"]
                if datos:
                    cols = ", ".join(f"{k}=%s" for k in datos)
                    cur.execute(f"UPDATE rrhh_datos_fiscales SET {cols} WHERE id=%s",
                               (*datos.values(), id_df))
            else:
                cols = ["id_empresa", "id_empleado"] + list(datos.keys())
                vals = [id_empresa, id_empleado] + list(datos.values())
                ph = ", ".join(["%s"] * len(cols))
                cur.execute(f"INSERT INTO rrhh_datos_fiscales ({', '.join(cols)}) VALUES ({ph})", vals)
                id_df = cur.lastrowid

            # Hijos/ascendientes: reemplazo completo (patrón "borrar e insertar").
            cur.execute("DELETE FROM rrhh_datos_fiscales_hijos WHERE id_datos_fiscales=%s", (id_df,))
            for h in hijos:
                hd = _normalizar_bool({k: h.get(k) for k in _PERMITIDOS_HIJO if k in h}, _BOOL_HIJO)
                if not hd:
                    continue
                cols = ["id_datos_fiscales"] + list(hd.keys())
                vals = [id_df] + list(hd.values())
                ph = ", ".join(["%s"] * len(cols))
                cur.execute(
                    f"INSERT INTO rrhh_datos_fiscales_hijos ({', '.join(cols)}) VALUES ({ph})", vals)

            cur.execute(
                "DELETE FROM rrhh_datos_fiscales_ascendientes WHERE id_datos_fiscales=%s", (id_df,))
            for a in ascendientes:
                ad = _normalizar_bool(
                    {k: a.get(k) for k in _PERMITIDOS_ASCENDIENTE if k in a}, _BOOL_ASCENDIENTE)
                if not ad:
                    continue
                cols = ["id_datos_fiscales"] + list(ad.keys())
                vals = [id_df] + list(ad.values())
                ph = ", ".join(["%s"] * len(cols))
                cur.execute(
                    f"INSERT INTO rrhh_datos_fiscales_ascendientes ({', '.join(cols)}) VALUES ({ph})",
                    vals)

            conn.commit()
            return id_df
    except Exception as e:
        logger.error("guardar_datos_fiscales(emp=%s): %s", id_empleado, e)
        return None


def actualizar_irpf_calculado(id_empleado, id_empresa=None, pct=None, fecha_calculo=None) -> bool:
    """Persiste SOLO `irpf_pct_calculado` + `fecha_calculo` (usado por `IRPFCalculatorService` tras
    cada recálculo, sin tocar el resto del formulario). Requiere que ya exista la fila (se guarda el
    formulario antes de calcular)."""
    id_empresa = id_empresa or empresa_actual_id()
    from datetime import datetime
    fecha_calculo = fecha_calculo or datetime.now()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE rrhh_datos_fiscales SET irpf_pct_calculado=%s, fecha_calculo=%s "
                "WHERE id_empleado=%s AND id_empresa=%s",
                (pct, fecha_calculo, id_empleado, id_empresa))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception as e:
        logger.error("actualizar_irpf_calculado(emp=%s): %s", id_empleado, e)
        return False


def eliminar_datos_fiscales(id_empleado, id_empresa=None) -> bool:
    """Elimina la fila de `rrhh_datos_fiscales` del empleado (hijos/ascendientes se eliminan en
    cascada vía FK ON DELETE CASCADE)."""
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM rrhh_datos_fiscales WHERE id_empleado=%s AND id_empresa=%s",
                (id_empleado, id_empresa))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception as e:
        logger.error("eliminar_datos_fiscales(emp=%s): %s", id_empleado, e)
        return False
