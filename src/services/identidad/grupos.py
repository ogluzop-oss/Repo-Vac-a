"""
IOC v2 · Grupos empresariales — nivel superior de la jerarquía corporativa (holding / grupo /
franquicia). Una empresa puede pertenecer a un grupo (`empresas.id_grupo`). Identidad por UUID
permanente. Aditivo: las empresas sin grupo siguen funcionando igual. Auditado, con Event Bus.
"""

import logging
import uuid

from src.services.identidad import _base as B
from src.services.identidad.tipos import valida_tipo_grupo

logger = logging.getLogger("identidad.grupos")


def crear_grupo(nombre, *, tipo="GRUPO", nombre_corto=None, id_propietario=None,
                observaciones=None) -> str | None:
    gid = str(uuid.uuid4())
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO ioc_grupos_empresariales (id, nombre, nombre_corto, tipo, id_propietario, "
                "usuario_creador, observaciones) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (gid, nombre[:200], nombre_corto, valida_tipo_grupo(tipo), id_propietario,
                 B.usuario_actual(), observaciones))
            conn.commit()
        B.audit("GRUPO_ALTA", "ioc_grupos_empresariales", f"{gid}:{tipo}:{nombre}")
        B.evento("identidad.grupo_creado", ref_entidad="ioc_grupos_empresariales", ref_id=gid,
                 payload={"tipo": tipo, "nombre": nombre})
        return gid
    except Exception as e:
        logger.error("crear_grupo: %s", e)
        return None


def vincular_empresa(id_grupo, id_empresa) -> bool:
    """Vincula una empresa a un grupo (nivel superior). `empresas.id_grupo` es aditivo y NULL-able."""
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE empresas SET id_grupo=%s WHERE id_empresa=%s", (id_grupo, id_empresa))
            conn.commit()
        B.audit("GRUPO_VINCULA_EMPRESA", "empresas", f"{id_grupo}<-{id_empresa}")
        B.evento("identidad.empresa_vinculada_grupo", ref_entidad="empresas", ref_id=id_empresa,
                 id_empresa=id_empresa, payload={"id_grupo": id_grupo})
        return True
    except Exception as e:
        logger.error("vincular_empresa: %s", e)
        return False


def empresas_de_grupo(id_grupo) -> list:
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_empresa, codigo_empresa, nombre_empresa FROM empresas "
                        "WHERE id_grupo=%s", (id_grupo,))
            return B.filas(cur)
    except Exception as e:
        logger.error("empresas_de_grupo: %s", e)
        return []


def obtener_grupo(id_grupo):
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM ioc_grupos_empresariales WHERE id=%s", (id_grupo,))
            return B.fila(cur)
    except Exception as e:
        logger.error("obtener_grupo: %s", e)
        return None


def listar_grupos(*, incluir_historicos=False) -> list:
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            q = "SELECT * FROM ioc_grupos_empresariales"
            if not incluir_historicos:
                q += " WHERE estado_gobierno NOT IN ('HISTORICO','ELIMINACION_PENDIENTE')"
            q += " ORDER BY nombre"
            cur.execute(q)
            return B.filas(cur)
    except Exception as e:
        logger.error("listar_grupos: %s", e)
        return []
