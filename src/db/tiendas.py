"""
Capa de datos de TIENDAS + cambio de contexto multitienda (F1).

Permite que un ADMINISTRADOR gestione las tiendas de SU empresa y que un
SUPERADMIN acceda a cualquier empresa/tienda, cambiando el TenantContext en
caliente (sin cerrar sesión) y dejando traza en `auditoria_logs`
(acción CAMBIO_CONTEXTO_TIENDA). Ver [[project_multitenant]] y
[[project_centro_documental]].
"""

import json
import logging

from src.db.conexion import (
    EMPRESA_DEFAULT_ID,
    _filas_a_dicts,
    ensure_schema,
    log_auditoria,
    obtener_conexion,
)

logger = logging.getLogger("tiendas_db")


def _cols(cur, tabla) -> set:
    cur.execute(f"SHOW COLUMNS FROM {tabla}")
    return {r["Field"] if isinstance(r, dict) else r[0] for r in cur.fetchall()}


def listar_tiendas(id_empresa: str | None = None) -> list[dict]:
    """Tiendas activas. Si se indica `id_empresa`, solo las de esa empresa
    (None = todas, para SUPERADMIN). Devuelve [{id, codigo_tienda, nombre,
    id_empresa}] ordenadas por código."""
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cols = _cols(cur, "tiendas")
            campos = ["id", "codigo_tienda", "nombre"]
            if "id_empresa" in cols:
                campos.append("id_empresa")
            filtros, params = [], []
            if "activo" in cols:
                filtros.append("COALESCE(activo,1)=1")
            if id_empresa and "id_empresa" in cols:
                filtros.append("id_empresa=%s"); params.append(id_empresa)
            where = (" WHERE " + " AND ".join(filtros)) if filtros else ""
            cur.execute(
                f"SELECT {', '.join(campos)} FROM tiendas{where} ORDER BY codigo_tienda, id",
                params)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("Error listar_tiendas: %s", e)
        return []


def obtener_tienda(id_tienda) -> dict | None:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM tiendas WHERE id=%s", (id_tienda,))
            filas = _filas_a_dicts(cur, cur.fetchall())
            return filas[0] if filas else None
    except Exception as e:
        logger.error("Error obtener_tienda(%s): %s", id_tienda, e)
        return None


def tienda_de_codigo(codigo, id_empresa=None) -> int | None:
    """Resuelve un `codigo_tienda` (p.ej. 'TND-001') al `id` INT de esa tienda. Es el mismo
    texto que el JWT/sesión de un empleado lleva como `centro_codigo` (`usuarios.centro_codigo`,
    ver `api/security.py`/`api/routers/logistics.py`) cuando el empleado está asignado a una
    tienda — permite a los consumidores de la API/portales resolver el `id_tienda` INT que
    necesitan servicios como `stock_almacen.almacen_de_tienda` o `online_orders_service
    .listar_pedidos_online`, algo que el propio JWT no lleva. None si no hay tienda con ese
    código (p.ej. el centro es un almacén, no una tienda)."""
    if not codigo:
        return None
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            filtros, params = ["codigo_tienda=%s"], [codigo]
            if id_empresa:
                filtros.append("id_empresa=%s"); params.append(id_empresa)
            cur.execute(f"SELECT id FROM tiendas WHERE {' AND '.join(filtros)} LIMIT 1", params)
            r = cur.fetchone()
            return (r["id"] if isinstance(r, dict) else r[0]) if r else None
    except Exception as e:
        logger.error("tienda_de_codigo(%s): %s", codigo, e)
        return None


def crear_tienda(nombre, id_empresa=None, codigo_tienda=None) -> int | None:
    """Alta de una tienda REAL (tabla `tiendas`). Hasta ahora `tiendas` no tenía alta dinámica en
    ningún punto de la app — sus filas solo se sembraban vía `database/bootstrap_mariadb.sql`
    (TND-001/002/003). Esta función existe para el AUTO-PROVISIONING de "Centros de empresa"
    (`gui/gestion_usuarios.py::_de_add_centro`): cuando se crea un centro `tipo_centro='tienda'`,
    se crea inmediatamente su tienda real vinculada, en la MISMA operación — decisión explícita del
    usuario tras rechazar el diseño anterior de "crear el centro y luego vincularlo a mano a una
    tienda YA existente" (poco intuitivo: cada centro debe nacer con su PROPIA identidad, nunca
    adoptar la de otra tienda distinta).

    `codigo_tienda`: si no se indica, reutiliza el propio código/nombre del centro de origen (p. ej.
    'CDT-002') en vez de generar una secuencia 'TND-NNN' desconectada — coherente con "identidad
    propia desde la creación" (la convención TND- solo queda como fallback de compatibilidad para
    el caso, hoy inexistente en la práctica, de llamar a esta función sin un centro de origen).

    `tiendas.nombre` es UNIQUE GLOBAL (todas las empresas comparten el mismo espacio de nombres,
    limitación heredada del esquema original en `bootstrap_mariadb.sql` — no se toca aquí). Si el
    nombre ya existe, se sufija con el propio código para garantizar el alta sin inventar un nombre
    irreconocible (mismo criterio defensivo que `stock_almacen.ensure_almacenes_empresa` frente a
    `almacen.nombre`, también UNIQUE global). Devuelve el `id` INT de la tienda creada, o None."""
    from src.db.empresa import empresa_actual_id
    id_empresa = id_empresa or empresa_actual_id()
    nombre = (nombre or "").strip() or "TIENDA"
    codigo = (codigo_tienda or "").strip()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            if not codigo:
                # Fallback de compatibilidad (sin centro de origen): secuencia TND-NNN, mismo
                # patrón de "siguiente código" que `db/centros.py::_siguiente_codigo`.
                cur.execute(
                    "SELECT codigo_tienda FROM tiendas WHERE codigo_tienda LIKE 'TND-%%' "
                    "ORDER BY codigo_tienda DESC LIMIT 1")
                row = cur.fetchone()
                ultimo = 0
                if row:
                    val = row[0] if not isinstance(row, dict) else row["codigo_tienda"]
                    try:
                        ultimo = int(str(val).split("-")[-1])
                    except (ValueError, IndexError):
                        ultimo = 0
                codigo = f"TND-{ultimo + 1:03d}"
            nombre_final = nombre
            cur.execute("SELECT COUNT(*) FROM tiendas WHERE nombre=%s", (nombre_final,))
            row = cur.fetchone()
            existe = (row[0] if not isinstance(row, dict) else list(row.values())[0]) or 0
            if existe:
                nombre_final = f"{nombre} ({codigo})"
            cur.execute(
                "INSERT INTO tiendas (nombre, activo, id_empresa, codigo_tienda) VALUES (%s,1,%s,%s)",
                (nombre_final, id_empresa, codigo))
            nuevo_id = cur.lastrowid
            conn.commit()
        logger.info("Tienda creada (auto-provisioning): id=%s codigo=%s nombre=%s (empresa=%s)",
                    nuevo_id, codigo, nombre_final, id_empresa)
        return nuevo_id
    except Exception as e:
        logger.error("Error crear_tienda(%s): %s", nombre, e)
        return None


def puede_acceder(id_tienda) -> bool:
    """True si el usuario en sesión puede CAMBIAR de contexto a la tienda dada.
    SOLO SUPERADMIN puede conectarse a distintas tiendas de su empresa; ADMINISTRADOR y
    OPERARIO están atados a su propia tienda (no pueden cambiar de tienda en absoluto, ni
    siquiera dentro de la misma empresa). Esto nunca permite cruzar de empresa: la lista de
    tiendas ofrecida a SUPERADMIN ya está acotada a la empresa elegida en el selector."""
    try:
        from src.db.usuario import sesion_global
        return bool(sesion_global.es_superadmin())
    except Exception:
        return False


def codigo_tienda_actual() -> str | None:
    """`codigo_tienda` (p.ej. 'TND-001') de la tienda ACTIVA del proceso (`tienda_actual_id()`, la
    que fija "Cambiar de centro") — el MISMO espacio de valores que `usuarios.centro_codigo`
    (ver `tienda_de_codigo`). None si no hay tienda activa fijada (p. ej. un superadmin que aún no
    ha elegido centro). Extraído para que cualquier feature que necesite "el centro_codigo EFECTIVO
    ahora mismo" (no solo el fijo del usuario) use el mismo resolutor — ver
    `gui.components.remote_scan._centro_codigo_activo`, que antes duplicaba esta misma lógica."""
    from src.db import empresa as emp_db
    tid = emp_db.tienda_actual_id()
    if tid is None:
        return None
    t = obtener_tienda(tid)
    return (t or {}).get("codigo_tienda") or None


def etiqueta_tienda_actual() -> str:
    """Texto de la tienda activa para la UI (chip del menú, contexto de Documentos):
    1) la tienda del TenantContext si está fijada (selector F1), 2) si no, la referencia legada
    (ASIGNAR REFERENCIA, DEPRECADA) leída a través de la fachada de Identidad Operativa. Cadena vacía si nada."""
    from src.db import empresa as emp_db
    tid = emp_db.tienda_actual_id()
    if tid is not None:
        t = obtener_tienda(tid)
        if t:
            return f"{t.get('codigo_tienda', '')} · {t.get('nombre', '')}".strip(" ·")
    try:
        # Deprecación «Asignar referencia»: el fallback pasa por la fachada IOC (Strangler), no por el
        # acceso directo a configuraciones.ref_tienda.
        from src.services.identidad import identidad as _ident
        refs = _ident.referencia_legada() or {}
        if refs.get("ref_tienda"):
            return f"T-{refs['ref_tienda']}"
    except Exception:
        pass
    return ""


def cambiar_contexto_tienda(id_tienda) -> dict | None:
    """Cambia la tienda (y empresa) ACTIVAS del proceso sin cerrar sesión, con
    control de acceso y traza de auditoría. Devuelve la tienda destino o None."""
    from src.db import empresa as emp_db
    from src.db.usuario import sesion_global

    tienda = obtener_tienda(id_tienda)
    if not tienda:
        return None
    if not puede_acceder(id_tienda):
        logger.warning("Acceso a tienda %s denegado para %s",
                       id_tienda, sesion_global.obtener_nombre())
        return None

    # Origen (para la traza) → destino.
    origen = {"empresa": emp_db.empresa_actual_id(), "tienda": emp_db.tienda_actual_id()}
    destino_empresa = tienda.get("id_empresa") or EMPRESA_DEFAULT_ID
    # Aislamiento de STOCK (3b.1-2c): persistir el stock de la tienda saliente y
    # cargar el de la entrante en el stock de trabajo (articulos.Stock_tienda).
    try:
        from src.db import stock as stock_db
        stock_db.cambiar_stock_de_tienda(origen["tienda"], tienda.get("id"), origen["empresa"])
    except Exception as _e:
        logger.debug("Sincronización de stock por tienda omitida: %s", _e)
    emp_db.set_empresa_actual(destino_empresa)
    emp_db.set_tienda_actual(tienda.get("id"))

    try:
        log_auditoria(
            usuario=sesion_global.obtener_nombre(),
            accion="CAMBIO_CONTEXTO_TIENDA",
            tabla_afectada="tiendas",
            detalles=json.dumps({
                "empresa_origen": origen["empresa"], "tienda_origen": origen["tienda"],
                "empresa_destino": destino_empresa, "tienda_destino": tienda.get("id"),
                "codigo_tienda": tienda.get("codigo_tienda"),
            }, ensure_ascii=False),
        )
    except Exception as e:
        logger.debug("No se pudo registrar CAMBIO_CONTEXTO_TIENDA: %s", e)
    logger.info("Contexto de tienda cambiado a %s (%s).",
                tienda.get("codigo_tienda"), tienda.get("nombre"))
    return tienda
