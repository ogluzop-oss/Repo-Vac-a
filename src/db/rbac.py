"""
Persistencia y administración RBAC / ACL (FASE 1 soporte + FASE 11 backend).

CRUD de roles, permisos de rol, grupos, asignaciones usuario↔rol/grupo y ACL por recurso.
Cada mutación invalida la caché del motor de autorización y deja traza de seguridad.
Multiempresa: todo acotado por id_empresa. Reutiliza el catálogo de permisos.
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, ensure_schema, obtener_conexion

logger = logging.getLogger("rbac.db")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def _uno(cur):
    r = cur.fetchone()
    return (r[0] if not isinstance(r, dict) else list(r.values())[0]) if r else None


def _invalida(id_usuario=None):
    try:
        from src.services.autorizacion import limpiar_cache
        limpiar_cache(id_usuario)
    except Exception:
        pass


def _audit(accion, usuario=None, detalles=None):
    try:
        from src.services.seguridad import auditoria as _aud
        _aud.registrar(accion, usuario=usuario, detalles=detalles)
    except Exception:
        pass


def permiso_id(codigo, cur):
    cur.execute("SELECT id FROM permisos WHERE codigo=%s", (codigo,))
    return _uno(cur)


# ── Roles ─────────────────────────────────────────────────────────────────────
def crear_rol(codigo, nombre, *, descripcion=None, id_empresa=None) -> int | None:
    id_empresa = _emp(id_empresa)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO roles (id_empresa, codigo, nombre, descripcion) VALUES (%s,%s,%s,%s) "
                        "ON DUPLICATE KEY UPDATE nombre=VALUES(nombre), descripcion=VALUES(descripcion)",
                        (id_empresa, codigo, nombre, descripcion))
            conn.commit()
            cur.execute("SELECT id FROM roles WHERE id_empresa=%s AND codigo=%s", (id_empresa, codigo))
            rid = _uno(cur)
        _audit("CAMBIO_ROL", detalles=f"alta/upd rol {codigo}")
        return rid
    except Exception as e:
        logger.error("crear_rol: %s", e)
        return None


def listar_roles(id_empresa=None) -> list:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM roles WHERE id_empresa=%s ORDER BY codigo", (id_empresa,))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_roles: %s", e)
        return []


def asignar_permiso_rol(id_rol, codigo_permiso, id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            pid = permiso_id(codigo_permiso, cur)
            if not pid:
                return False
            cur.execute("INSERT IGNORE INTO roles_permisos (id_empresa, id_rol, id_permiso) VALUES (%s,%s,%s)",
                        (id_empresa, id_rol, pid))
            conn.commit()
        _invalida()
        _audit("CAMBIO_PERMISO", detalles=f"rol={id_rol} +{codigo_permiso}")
        return True
    except Exception as e:
        logger.error("asignar_permiso_rol: %s", e)
        return False


def quitar_permiso_rol(id_rol, codigo_permiso, id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            pid = permiso_id(codigo_permiso, cur)
            cur.execute("DELETE FROM roles_permisos WHERE id_rol=%s AND id_permiso=%s", (id_rol, pid))
            conn.commit()
        _invalida()
        _audit("CAMBIO_PERMISO", detalles=f"rol={id_rol} -{codigo_permiso}")
        return True
    except Exception as e:
        logger.error("quitar_permiso_rol: %s", e)
        return False


def permisos_de_rol(id_rol) -> list:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT p.codigo FROM roles_permisos rp JOIN permisos p ON p.id=rp.id_permiso "
                        "WHERE rp.id_rol=%s ORDER BY p.codigo", (id_rol,))
            return [(r[0] if not isinstance(r, dict) else list(r.values())[0]) for r in cur.fetchall()]
    except Exception as e:
        logger.error("permisos_de_rol: %s", e)
        return []


def asignar_rol_usuario(id_usuario, id_rol, *, ambito_tipo="empresa", ambito_id=None,
                        id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT IGNORE INTO usuarios_roles (id_empresa, id_usuario, id_rol, "
                        "ambito_tipo, ambito_id) VALUES (%s,%s,%s,%s,%s)",
                        (id_empresa, id_usuario, id_rol, ambito_tipo, ambito_id))
            conn.commit()
        _invalida(id_usuario)
        _audit("CAMBIO_ROL", usuario=id_usuario, detalles=f"+rol={id_rol} ambito={ambito_tipo}:{ambito_id}")
        return True
    except Exception as e:
        logger.error("asignar_rol_usuario: %s", e)
        return False


def quitar_rol_usuario(id_usuario, id_rol, id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM usuarios_roles WHERE id_usuario=%s AND id_rol=%s AND id_empresa=%s",
                        (id_usuario, id_rol, id_empresa))
            conn.commit()
        _invalida(id_usuario)
        _audit("CAMBIO_ROL", usuario=id_usuario, detalles=f"-rol={id_rol}")
        return True
    except Exception as e:
        logger.error("quitar_rol_usuario: %s", e)
        return False


def roles_de_usuario(id_usuario, id_empresa=None) -> list:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT r.id, r.codigo, r.nombre FROM usuarios_roles ur "
                        "JOIN roles r ON r.id=ur.id_rol WHERE ur.id_usuario=%s AND ur.id_empresa=%s",
                        (id_usuario, id_empresa))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("roles_de_usuario: %s", e)
        return []


# ── Grupos ────────────────────────────────────────────────────────────────────
def crear_grupo(codigo, nombre, id_empresa=None) -> int | None:
    id_empresa = _emp(id_empresa)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO grupos (id_empresa, codigo, nombre) VALUES (%s,%s,%s) "
                        "ON DUPLICATE KEY UPDATE nombre=VALUES(nombre)", (id_empresa, codigo, nombre))
            conn.commit()
            cur.execute("SELECT id FROM grupos WHERE id_empresa=%s AND codigo=%s", (id_empresa, codigo))
            return _uno(cur)
    except Exception as e:
        logger.error("crear_grupo: %s", e)
        return None


def asignar_permiso_grupo(id_grupo, codigo_permiso, id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            pid = permiso_id(codigo_permiso, cur)
            if not pid:
                return False
            cur.execute("INSERT IGNORE INTO grupos_permisos (id_empresa, id_grupo, id_permiso) "
                        "VALUES (%s,%s,%s)", (id_empresa, id_grupo, pid))
            conn.commit()
        _invalida()
        _audit("CAMBIO_GRUPO", detalles=f"grupo={id_grupo} +{codigo_permiso}")
        return True
    except Exception as e:
        logger.error("asignar_permiso_grupo: %s", e)
        return False


def asignar_grupo_usuario(id_usuario, id_grupo, id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT IGNORE INTO usuarios_grupos (id_empresa, id_usuario, id_grupo) "
                        "VALUES (%s,%s,%s)", (id_empresa, id_usuario, id_grupo))
            conn.commit()
        _invalida(id_usuario)
        _audit("CAMBIO_GRUPO", usuario=id_usuario, detalles=f"+grupo={id_grupo}")
        return True
    except Exception as e:
        logger.error("asignar_grupo_usuario: %s", e)
        return False


# ── ACL por recurso ─────────────────────────────────────────────────────────
def set_acl(recurso_tipo, recurso_id, sujeto_tipo, sujeto_id, accion, permitido=True,
            *, ambito_tipo="empresa", ambito_id=None, id_empresa=None) -> bool:
    """Crea/actualiza una entrada ACL (allow/deny) sobre un recurso para un sujeto."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO acl_recursos (id_empresa, recurso_tipo, recurso_id, sujeto_tipo, "
                "sujeto_id, accion, permitido, ambito_tipo, ambito_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE permitido=VALUES(permitido)",
                (id_empresa, recurso_tipo, (str(recurso_id) if recurso_id is not None else None),
                 sujeto_tipo, str(sujeto_id), accion, 1 if permitido else 0, ambito_tipo, ambito_id))
            conn.commit()
        _invalida()
        _audit("ACL_CAMBIO", detalles=f"{recurso_tipo}:{recurso_id} {sujeto_tipo}:{sujeto_id} {accion}={permitido}")
        return True
    except Exception as e:
        logger.error("set_acl: %s", e)
        return False


def listar_acl(recurso_tipo=None, recurso_id=None, id_empresa=None) -> list:
    id_empresa = _emp(id_empresa)
    q = "SELECT * FROM acl_recursos WHERE id_empresa=%s"
    p = [id_empresa]
    if recurso_tipo:
        q += " AND recurso_tipo=%s"; p.append(recurso_tipo)
    if recurso_id is not None:
        q += " AND recurso_id=%s"; p.append(str(recurso_id))
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_acl: %s", e)
        return []
