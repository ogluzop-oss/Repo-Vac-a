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
    # IOC v3 (Bloque V): seam de identidad delegado en la fachada de datos (db -> db).
    try:
        from src.db.identidad_contexto import empresa_id
        return empresa_id(id_empresa)
    except Exception:
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


def conceder_permiso_individual(id_usuario, codigo_permiso, id_empresa=None) -> bool:
    """Concesión ADITIVA de un permiso a UN usuario concreto (pestaña Roles → tabla de usuarios),
    independiente de su perfil base y sin afectar a otros usuarios del mismo perfil."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            pid = permiso_id(codigo_permiso, cur)
            if not pid:
                return False
            cur.execute("INSERT IGNORE INTO usuarios_permisos (id_empresa, id_usuario, id_permiso) "
                        "VALUES (%s,%s,%s)", (id_empresa, id_usuario, pid))
            conn.commit()
        _invalida(id_usuario)
        _audit("CAMBIO_PERMISO", usuario=id_usuario, detalles=f"+{codigo_permiso} (individual)")
        return True
    except Exception as e:
        logger.error("conceder_permiso_individual: %s", e)
        return False


def quitar_permiso_individual(id_usuario, codigo_permiso, id_empresa=None) -> bool:
    """Revoca una concesión individual previa. Solo afecta a permisos concedidos por esta misma vía —
    NO puede quitar un permiso que el perfil base del usuario ya incluya por defecto."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            pid = permiso_id(codigo_permiso, cur)
            cur.execute("DELETE FROM usuarios_permisos WHERE id_usuario=%s AND id_permiso=%s",
                        (id_usuario, pid))
            afectadas = cur.rowcount
            conn.commit()
        if afectadas == 0:
            return False
        _invalida(id_usuario)
        _audit("CAMBIO_PERMISO", usuario=id_usuario, detalles=f"-{codigo_permiso} (individual)")
        return True
    except Exception as e:
        logger.error("quitar_permiso_individual: %s", e)
        return False


def permisos_individuales_de_usuario(id_usuario, id_empresa=None) -> list:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT p.codigo FROM usuarios_permisos up JOIN permisos p ON p.id=up.id_permiso "
                "WHERE up.id_usuario=%s AND up.id_empresa=%s ORDER BY p.codigo",
                (id_usuario, id_empresa))
            return [(r[0] if not isinstance(r, dict) else list(r.values())[0]) for r in cur.fetchall()]
    except Exception as e:
        logger.error("permisos_individuales_de_usuario: %s", e)
        return []


def asignar_rol_usuario(id_usuario, id_rol, *, ambito_tipo="empresa", ambito_id=None,
                        id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            # NO `INSERT IGNORE` a secas: la UNIQUE KEY (id_usuario, id_rol, ambito_tipo, ambito_id)
            # no evita duplicados cuando `ambito_id` es NULL (el caso normal, "toda la empresa") —
            # en SQL NULL nunca es igual a NULL, así que MySQL no lo considera un choque y cada
            # asignación repetida insertaba una fila NUEVA (se veía el mismo rol dos veces en la
            # tabla de Seguridad). `<=>` es la comparación NULL-segura de MySQL (NULL<=>NULL = true).
            cur.execute(
                "INSERT INTO usuarios_roles (id_empresa, id_usuario, id_rol, ambito_tipo, ambito_id) "
                "SELECT %s,%s,%s,%s,%s FROM DUAL WHERE NOT EXISTS ("
                "  SELECT 1 FROM usuarios_roles WHERE id_usuario=%s AND id_rol=%s "
                "  AND ambito_tipo=%s AND ambito_id <=> %s)",
                (id_empresa, id_usuario, id_rol, ambito_tipo, ambito_id,
                 id_usuario, id_rol, ambito_tipo, ambito_id))
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
            afectadas = cur.rowcount
            conn.commit()
        # Si no había ninguna fila que borrar (el rol no estaba asignado a este usuario), NO es un
        # éxito real — devolver True aquí hacía que la UI mostrara "rol quitado" sin haber quitado nada.
        if afectadas == 0:
            return False
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


def listar_grupos(id_empresa=None) -> list:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM grupos WHERE id_empresa=%s ORDER BY nombre", (id_empresa,))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("listar_grupos: %s", e)
        return []


def eliminar_grupo(id_grupo, id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM usuarios_grupos WHERE id_empresa=%s AND id_grupo=%s", (id_empresa, id_grupo))
            cur.execute("DELETE FROM grupos_permisos WHERE id_empresa=%s AND id_grupo=%s", (id_empresa, id_grupo))
            cur.execute("DELETE FROM grupos WHERE id_empresa=%s AND id=%s", (id_empresa, id_grupo))
            afectadas = cur.rowcount
            conn.commit()
        if afectadas == 0:
            return False
        _invalida()
        _audit("CAMBIO_GRUPO", detalles=f"-grupo={id_grupo}")
        return True
    except Exception as e:
        logger.error("eliminar_grupo: %s", e)
        return False


def permisos_de_grupo(id_grupo, id_empresa=None) -> list:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT p.id, p.codigo, p.descripcion FROM grupos_permisos gp "
                "JOIN permisos p ON p.id=gp.id_permiso "
                "WHERE gp.id_empresa=%s AND gp.id_grupo=%s ORDER BY p.codigo",
                (id_empresa, id_grupo))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("permisos_de_grupo: %s", e)
        return []


def quitar_permiso_grupo(id_grupo, codigo_permiso, id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            pid = permiso_id(codigo_permiso, cur)
            if not pid:
                return False
            cur.execute("DELETE FROM grupos_permisos WHERE id_empresa=%s AND id_grupo=%s AND id_permiso=%s",
                        (id_empresa, id_grupo, pid))
            afectadas = cur.rowcount
            conn.commit()
        if afectadas == 0:
            return False
        _invalida()
        _audit("CAMBIO_GRUPO", detalles=f"grupo={id_grupo} -{codigo_permiso}")
        return True
    except Exception as e:
        logger.error("quitar_permiso_grupo: %s", e)
        return False


def miembros_de_grupo(id_grupo, id_empresa=None) -> list:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT u.id, u.nombre FROM usuarios_grupos ug "
                "JOIN usuarios u ON u.id=ug.id_usuario "
                "WHERE ug.id_empresa=%s AND ug.id_grupo=%s ORDER BY u.nombre",
                (id_empresa, id_grupo))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("miembros_de_grupo: %s", e)
        return []


def desasignar_grupo_usuario(id_usuario, id_grupo, id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM usuarios_grupos WHERE id_empresa=%s AND id_usuario=%s AND id_grupo=%s",
                        (id_empresa, id_usuario, id_grupo))
            afectadas = cur.rowcount
            conn.commit()
        if afectadas == 0:
            return False
        _invalida(id_usuario)
        _audit("CAMBIO_GRUPO", usuario=id_usuario, detalles=f"-grupo={id_grupo}")
        return True
    except Exception as e:
        logger.error("desasignar_grupo_usuario: %s", e)
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


def eliminar_acl(recurso_tipo, recurso_id, sujeto_tipo, sujeto_id, accion, id_empresa=None) -> bool:
    """Quita una entrada ACL (misma clave compuesta que `set_acl`)."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM acl_recursos WHERE id_empresa=%s AND recurso_tipo=%s AND recurso_id=%s "
                "AND sujeto_tipo=%s AND sujeto_id=%s AND accion=%s",
                (id_empresa, recurso_tipo, (str(recurso_id) if recurso_id is not None else None),
                 sujeto_tipo, str(sujeto_id), accion))
            afectadas = cur.rowcount
            conn.commit()
        if afectadas == 0:
            return False
        _invalida()
        _audit("ACL_CAMBIO", detalles=f"-{recurso_tipo}:{recurso_id} {sujeto_tipo}:{sujeto_id} {accion}")
        return True
    except Exception as e:
        logger.error("eliminar_acl: %s", e)
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
