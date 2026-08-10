"""
IOC · Centros — servicio de dominio del centro operativo. Reutiliza la entidad existente
`centros_trabajo` (y `db.centros` para la secuencia de código y `es_principal`), añadiendo los
atributos de identidad (tipo, jerarquía padre, alias, archivado…) sin duplicar la tabla ni reescribir
`db/centros.py`. Multiempresa, auditado, con Event Bus. Punto único de verdad del centro.
"""

import logging

from src.services.identidad import _base as B
from src.services.identidad.tipos import valida_tipo_centro

logger = logging.getLogger("identidad.centros")


def crear_centro(nombre, *, tipo="OTRO", nombre_corto=None, alias=None, id_centro_padre=None,
                 id_tienda=None, observaciones=None, es_principal=False, nivel=None,
                 id_propietario=None, id_responsable_operativo=None, id_empresa=None,
                 **datos_fiscales) -> str | None:
    """Crea un centro operativo. Reutiliza `db.centros.crear_centro` (código CDT-NNN + es_principal)
    y completa los atributos de identidad IOC. `nivel` (GRUPO/CENTRO/SUBCENTRO/ZONA) permite modelar
    la jerarquía. `datos_fiscales` acepta los campos ya soportados por `centros_trabajo`."""
    id_empresa = B.emp(id_empresa)
    tipo = valida_tipo_centro(tipo)
    try:
        from src.db import centros as _c
        nuevo_id = _c.crear_centro(
            id_empresa=id_empresa, nombre_centro=nombre, id_tienda=id_tienda,
            es_principal=es_principal, **{k: v for k, v in datos_fiscales.items()})
        if not nuevo_id:
            return None
        # Nivel jerárquico (IOC v2): validado si se aporta; por defecto lo deja la BD ('CENTRO').
        _nivel = None
        if nivel is not None:
            try:
                from src.services.identidad.tipos import valida_nivel
                _nivel = valida_nivel(nivel)
            except Exception:
                _nivel = None
        usuario = B.usuario_actual()
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE centros_trabajo SET tipo=%s, nombre_corto=%s, alias=%s, id_centro_padre=%s, "
                "observaciones=%s, usuario_creador=%s, fecha_modificacion=NOW() WHERE id_centro=%s",
                (tipo, nombre_corto, alias, id_centro_padre, observaciones, usuario, nuevo_id))
            # Columnas de gobierno IOC v2 (aditivas; guard si la migración 0122 aún no se aplicó).
            for col, val in (("nivel", _nivel), ("id_propietario", id_propietario),
                             ("id_responsable_operativo", id_responsable_operativo)):
                if val is not None:
                    try:
                        cur.execute(f"UPDATE centros_trabajo SET {col}=%s WHERE id_centro=%s",
                                    (val, nuevo_id))
                    except Exception:
                        pass
            conn.commit()
        B.audit("CENTRO_ALTA", "centros_trabajo", f"{nuevo_id}:{tipo}:{nombre}")
        B.evento("identidad.centro_creado", ref_entidad="centros_trabajo", ref_id=nuevo_id,
                 id_empresa=id_empresa, payload={"tipo": tipo, "nombre": nombre})
        return nuevo_id
    except Exception as e:
        logger.error("crear_centro: %s", e)
        return None


def actualizar_centro(id_centro, *, id_empresa=None, **campos) -> bool:
    """Actualiza atributos de identidad y/o fiscales del centro. Los campos fiscales soportados por
    `centros_trabajo` se delegan en `db.centros.actualizar_centro` (sin reescribirlo)."""
    id_empresa = B.emp(id_empresa)
    ioc_campos = {}
    for k in ("tipo", "nombre_corto", "alias", "id_centro_padre", "observaciones", "estado"):
        if k in campos:
            ioc_campos[k] = valida_tipo_centro(campos.pop(k)) if k == "tipo" else campos.pop(k)
    ok = True
    try:
        # Campos fiscales/base → módulo existente (compatibilidad, sin duplicar).
        if campos:
            from src.db import centros as _c
            ok = _c.actualizar_centro(id_centro, **campos)
        if ioc_campos:
            sets = ", ".join(f"{k}=%s" for k in ioc_campos)
            from src.db.conexion import obtener_conexion
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute(
                    f"UPDATE centros_trabajo SET {sets}, usuario_modificacion=%s, fecha_modificacion=NOW() "
                    "WHERE id_centro=%s", [*ioc_campos.values(), B.usuario_actual(), id_centro])
                conn.commit()
        B.audit("CENTRO_MOD", "centros_trabajo", f"{id_centro}:{list(ioc_campos)+list(campos)}")
        B.evento("identidad.centro_modificado", ref_entidad="centros_trabajo", ref_id=id_centro,
                 id_empresa=id_empresa, payload=ioc_campos)
        return ok
    except Exception as e:
        logger.error("actualizar_centro(%s): %s", id_centro, e)
        return False


def archivar_centro(id_centro, *, id_empresa=None) -> bool:
    """Archivado lógico (distinto de la baja de `db.centros`, que se conserva)."""
    id_empresa = B.emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE centros_trabajo SET archivado=1, usuario_modificacion=%s, "
                        "fecha_modificacion=NOW() WHERE id_centro=%s", (B.usuario_actual(), id_centro))
            conn.commit()
        B.audit("CENTRO_ARCHIVADO", "centros_trabajo", str(id_centro))
        B.evento("identidad.centro_archivado", ref_entidad="centros_trabajo", ref_id=id_centro,
                 id_empresa=id_empresa)
        return True
    except Exception as e:
        logger.error("archivar_centro(%s): %s", id_centro, e)
        return False


def obtener_centro(id_centro):
    """Devuelve el centro (identidad completa) reutilizando `db.centros.obtener_centro`."""
    try:
        from src.db import centros as _c
        return _c.obtener_centro(id_centro)
    except Exception as e:
        logger.error("obtener_centro(%s): %s", id_centro, e)
        return None


def listar_centros(*, id_empresa=None, tipo=None, incluir_archivados=False, solo_activos=True) -> list:
    id_empresa = B.emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            q = "SELECT * FROM centros_trabajo WHERE id_empresa=%s"
            p = [id_empresa]
            if solo_activos:
                q += " AND estado='activo'"
            if not incluir_archivados:
                q += " AND COALESCE(archivado,0)=0"
            if tipo:
                q += " AND tipo=%s"; p.append(valida_tipo_centro(tipo))
            q += " ORDER BY es_principal DESC, fecha_alta ASC"
            cur.execute(q, p)
            return B.filas(cur)
    except Exception as e:
        logger.error("listar_centros: %s", e)
        return []


def hijos_de(id_centro_padre, *, id_empresa=None) -> list:
    id_empresa = B.emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM centros_trabajo WHERE id_empresa=%s AND id_centro_padre=%s "
                        "AND COALESCE(archivado,0)=0 ORDER BY fecha_alta", (id_empresa, id_centro_padre))
            return B.filas(cur)
    except Exception as e:
        logger.error("hijos_de(%s): %s", id_centro_padre, e)
        return []
