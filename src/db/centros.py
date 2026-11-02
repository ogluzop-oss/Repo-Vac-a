"""
Capa de datos: CENTROS DE EMPRESA (antes "Centros de trabajo") — multi-tenant.

Tabla `centros_trabajo`, relacionada con `empresas` por `id_empresa` (y opcionalmente con una tienda
por `id_tienda` / un almacén por `id_almacen`, sin asumir relación 1:1 en ningún caso). Es la ÚNICA
tabla de centros físicos de la empresa (tienda/almacén/fábrica/oficina/otro — ver `tipo_centro`).
Forma parte de la fuente única de datos corporativos; los documentos lo consumen vía
`empresa.datos_corporativos()` ([[project_multitenant]]).

Unificación (migración 0257): esta tabla absorbe lo que hasta hoy vivía en `centros_perfil`
(retirada) — `tipo_centro`, `id_almacen` y `creado_por_id` (base del aislamiento entre superadmins
en "Cambiar de Centro"/"Vincular a centro", ver `gui/selector_tienda.py`/`gui/gestion_usuarios.py`).
También hereda el geocode-on-save: `crear_centro`/`actualizar_centro` geocodifican `codigo_postal`
(precisión de provincia, `services/geo/cp_espana.py`) y, si el centro tiene `id_almacen`, propagan el
resultado a `almacen.latitud/longitud` para que `services/tpv/online_orders_service.py::
buscar_almacenes_con_stock` siga ordenando por proximidad sin cambios. `centros_trabajo` NO guarda
latitud/longitud propias — la única propagación real es hacia el almacén enlazado.
"""

import logging
import uuid

from src.db.conexion import _fila_a_dict, _filas_a_dicts, ensure_schema, obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("centros_db")

_PERMITIDOS = (
    "tipo_centro", "id_tienda", "id_almacen", "nombre_centro", "direccion", "codigo_postal",
    "municipio", "provincia", "comunidad_autonoma", "pais", "telefono", "email",
    "codigo_cuenta_cotizacion", "codigo_centro_trabajo", "actividad_economica",
    "cod_pais", "cod_municipio", "cod_actividad",
    "es_principal", "estado", "creado_por_id",
)


def _geocodificar_y_propagar(id_empresa, codigo_postal, id_almacen) -> None:
    """Geocodifica `codigo_postal` (precisión de PROVINCIA, ver `services/geo/cp_espana.py`) y, si
    el centro tiene `id_almacen`, replica el resultado en `almacen.latitud/longitud` para que
    `buscar_almacenes_con_stock` siga ordenando por proximidad sin cambios. `centros_trabajo` no
    tiene columnas propias de latitud/longitud — no hay nada más que guardar aquí. No hace nada si
    falta `codigo_postal` o `id_almacen`, o si el CP no es válido/conocido (nunca inventa una
    coordenada, mismo criterio que `cp_espana.geocodificar_cp`)."""
    if not (codigo_postal and id_almacen):
        return
    try:
        from src.services.geo.cp_espana import geocodificar_cp
        coords = geocodificar_cp(codigo_postal)
        if not coords:
            return
        lat, lon = coords
        from src.db import stock_almacen as SA
        SA.actualizar_geolocalizacion(id_almacen, lat, lon, id_empresa=id_empresa)
    except Exception as e:
        logger.warning("No se pudo geocodificar/propagar centro (CP=%s, almacen=%s): %s",
                        codigo_postal, id_almacen, e)


def _siguiente_codigo(cur, id_empresa) -> str:
    cur.execute(
        "SELECT codigo_centro FROM centros_trabajo WHERE id_empresa=%s AND codigo_centro LIKE 'CDT-%%' "
        "ORDER BY codigo_centro DESC LIMIT 1",
        (id_empresa,),
    )
    row = cur.fetchone()
    ultimo = 0
    if row:
        val = row[0] if not isinstance(row, dict) else row["codigo_centro"]
        try:
            ultimo = int(str(val).split("-")[-1])
        except (ValueError, IndexError):
            ultimo = 0
    return f"CDT-{ultimo + 1:03d}"


def listar_centros(id_empresa=None, solo_activos=True, creado_por_id=None) -> list[dict]:
    """Centros de la empresa. Si `creado_por_id` se indica, SOLO los creados por ese usuario
    (aislamiento entre superadmins — mismo criterio que la antigua `centros_perfil.
    listar_centros_perfil`, ver "Cambiar de Centro"/"Vincular a centro", que por defecto siempre
    pasan el superadmin actual salvo desbloqueo explícito por PIN)."""
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            sql = "SELECT * FROM centros_trabajo WHERE id_empresa=%s"
            params = [id_empresa]
            if solo_activos:
                sql += " AND estado='activo'"
            if creado_por_id is not None:
                sql += " AND creado_por_id=%s"
                params.append(creado_por_id)
            sql += " ORDER BY es_principal DESC, fecha_alta ASC"
            cur.execute(sql, params)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("Error listar_centros: %s", e)
        return []


def obtener_centro(id_centro) -> dict | None:
    if not id_centro:
        return None
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM centros_trabajo WHERE id_centro=%s", (id_centro,))
            return _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        logger.error("Error obtener_centro(%s): %s", id_centro, e)
        return None


def centro_principal(id_empresa=None, id_tienda=None) -> dict | None:
    """Centro principal de la empresa; si se pasa id_tienda, prioriza el de esa
    tienda. Si no hay marcado principal, devuelve el primero activo."""
    id_empresa = id_empresa or empresa_actual_id()
    centros = listar_centros(id_empresa, solo_activos=True)
    if not centros:
        return None
    if id_tienda is not None:
        de_tienda = [c for c in centros if c.get("id_tienda") == id_tienda]
        if de_tienda:
            for c in de_tienda:
                if c.get("es_principal"):
                    return c
            return de_tienda[0]
    for c in centros:
        if c.get("es_principal"):
            return c
    return centros[0]


def crear_centro(id_empresa=None, **campos) -> str | None:
    id_empresa = id_empresa or empresa_actual_id()
    nuevo_id = str(uuid.uuid4())
    datos = {k: v for k, v in campos.items() if k in _PERMITIDOS}
    es_principal = 1 if datos.get("es_principal") else 0
    datos.pop("es_principal", None)
    # Geocodifica codigo_postal (si viene) y, si hay id_almacen, propaga a almacen.latitud/longitud
    # — se hace ANTES del INSERT (no altera `datos`: centros_trabajo no guarda lat/lon propias).
    _geocodificar_y_propagar(id_empresa, datos.get("codigo_postal"), datos.get("id_almacen"))
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM centros_trabajo WHERE id_empresa=%s AND estado='activo'",
                (id_empresa,),
            )
            row = cur.fetchone()
            total = (row[0] if not isinstance(row, dict) else list(row.values())[0]) or 0
            if total == 0:
                es_principal = 1
            if es_principal:
                cur.execute(
                    "UPDATE centros_trabajo SET es_principal=0 WHERE id_empresa=%s",
                    (id_empresa,),
                )
            codigo = _siguiente_codigo(cur, id_empresa)
            cols = ["id_centro", "id_empresa", "codigo_centro", "es_principal", *datos.keys()]
            vals = [nuevo_id, id_empresa, codigo, es_principal, *datos.values()]
            ph = ", ".join(["%s"] * len(cols))
            cur.execute(
                f"INSERT INTO centros_trabajo ({', '.join(cols)}) VALUES ({ph})", vals
            )
            conn.commit()
        # Delegación de tareas repetitivas a SOMA (observacional, bulletproof): si el SUPERADMIN
        # tiene activa la automatización "autorrelleno de centro", esto la dispara.
        try:
            from src.services import eventos as _EV
            _EV.publicar("CENTRO_CREADO", id_empresa=id_empresa, origen="centros",
                         ref_entidad="centro", ref_id=nuevo_id,
                         payload={"codigo_centro": codigo})
        except Exception:
            pass
        return nuevo_id
    except Exception as e:
        logger.error("Error crear_centro: %s", e)
        return None


def actualizar_centro(id_centro, **campos) -> bool:
    datos = {k: v for k, v in campos.items() if k in _PERMITIDOS and k != "es_principal"}
    if not datos:
        return False
    # Regeocodifica y propaga a almacen.latitud/longitud si cambia el codigo_postal o si se enlaza/
    # cambia el id_almacen (mismo criterio que la antigua centros_perfil.actualizar_centro_perfil,
    # ampliado: también dispara al enlazar un almacén nuevo a un centro cuyo CP no cambia).
    if "codigo_postal" in datos or "id_almacen" in datos:
        try:
            actual = obtener_centro(id_centro) or {}
            id_empresa = actual.get("id_empresa") or empresa_actual_id()
            id_almacen = datos.get("id_almacen", actual.get("id_almacen"))
            codigo_postal = datos.get("codigo_postal", actual.get("codigo_postal"))
            _geocodificar_y_propagar(id_empresa, codigo_postal, id_almacen)
        except Exception as e:
            logger.warning("No se pudo regeocodificar centro %s: %s", id_centro, e)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            asign = ", ".join(f"{k}=%s" for k in datos)
            cur.execute(
                f"UPDATE centros_trabajo SET {asign} WHERE id_centro=%s",
                [*datos.values(), id_centro],
            )
            conn.commit()
        return True
    except Exception as e:
        logger.error("Error actualizar_centro(%s): %s", id_centro, e)
        return False


def marcar_principal(id_centro, id_empresa=None) -> bool:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE centros_trabajo SET es_principal=0 WHERE id_empresa=%s",
                (id_empresa,),
            )
            cur.execute(
                "UPDATE centros_trabajo SET es_principal=1 WHERE id_centro=%s",
                (id_centro,),
            )
            conn.commit()
        return True
    except Exception as e:
        logger.error("Error marcar_principal(%s): %s", id_centro, e)
        return False


def baja_centro(id_centro) -> bool:
    """Baja lógica (mantiene histórico)."""
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE centros_trabajo SET estado='baja', es_principal=0 WHERE id_centro=%s",
                (id_centro,),
            )
            conn.commit()
        return True
    except Exception as e:
        logger.error("Error baja_centro(%s): %s", id_centro, e)
        return False
