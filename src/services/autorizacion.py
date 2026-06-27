"""
Motor central de autorización RBAC / ACL (FASE 3-4).

`puede(usuario, permiso, ...)` resuelve permisos efectivos combinando roles + grupos + ACL,
con SUPERADMIN como comodín, ámbito multiempresa y caché por sesión. Si el usuario no tiene
asignaciones RBAC en BD (instalación LEGACY), recurre al mapeo del `perfil` — de modo que el
comportamiento histórico se preserva (compatibilidad total). Incluye decoradores aplicables a
servicios, API y acciones de GUI.
"""

import functools
import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion
from src.services.seguridad import catalogo as _cat

logger = logging.getLogger("autorizacion")


class ErrorAutorizacion(PermissionError):
    """Se lanza cuando un actor no tiene el permiso requerido."""


# ── Caché por (usuario, empresa) ─────────────────────────────────────────────
_CACHE: dict = {}


def limpiar_cache(id_usuario=None):
    """Invalida la caché (toda, o la de un usuario). Llamar al cambiar roles/permisos/grupos."""
    if id_usuario is None:
        _CACHE.clear()
    else:
        for k in [k for k in _CACHE if k[0] == id_usuario]:
            _CACHE.pop(k, None)


def _empresa(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def _norm_usuario(usuario):
    """Acepta dict, SesionUsuario o None → dict {id, perfil, id_empresa}."""
    if usuario is None:
        try:
            from src.db.usuario import sesion_global
            usuario = getattr(sesion_global, "usuario_actual", None)
        except Exception:
            usuario = None
    if usuario is None:
        return None
    if isinstance(usuario, dict):
        return {"id": usuario.get("id"), "perfil": (usuario.get("perfil") or usuario.get("rol") or ""),
                "id_empresa": usuario.get("id_empresa")}
    ua = getattr(usuario, "usuario_actual", None)
    if isinstance(ua, dict):
        return {"id": ua.get("id"), "perfil": (ua.get("perfil") or ua.get("rol") or ""),
                "id_empresa": ua.get("id_empresa")}
    return None


def _ids_roles_grupos(uid, emp):
    roles, grupos = [], []
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_rol FROM usuarios_roles WHERE id_usuario=%s AND id_empresa=%s",
                        (uid, emp))
            roles = [r[0] if not isinstance(r, dict) else list(r.values())[0] for r in cur.fetchall()]
            cur.execute("SELECT id_grupo FROM usuarios_grupos WHERE id_usuario=%s AND id_empresa=%s",
                        (uid, emp))
            grupos = [r[0] if not isinstance(r, dict) else list(r.values())[0] for r in cur.fetchall()]
    except Exception as e:
        logger.debug("_ids_roles_grupos: %s", e)
    return roles, grupos


def _permisos_efectivos(uid, emp):
    """Conjunto de permisos del usuario (roles ∪ grupos). Cacheado. None si no hay asignaciones
    RBAC (→ se aplicará el fallback legacy)."""
    clave = (uid, emp)
    if clave in _CACHE:
        return _CACHE[clave]
    roles, grupos = _ids_roles_grupos(uid, emp)
    if not roles and not grupos:
        _CACHE[clave] = None        # sin asignaciones → legacy
        return None
    perms = set()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            if roles:
                marcas = ",".join(["%s"] * len(roles))
                cur.execute(f"SELECT p.codigo FROM roles_permisos rp JOIN permisos p ON p.id=rp.id_permiso "
                            f"WHERE rp.id_rol IN ({marcas})", roles)
                perms.update(r[0] if not isinstance(r, dict) else list(r.values())[0] for r in cur.fetchall())
            if grupos:
                marcas = ",".join(["%s"] * len(grupos))
                cur.execute(f"SELECT p.codigo FROM grupos_permisos gp JOIN permisos p ON p.id=gp.id_permiso "
                            f"WHERE gp.id_grupo IN ({marcas})", grupos)
                perms.update(r[0] if not isinstance(r, dict) else list(r.values())[0] for r in cur.fetchall())
    except Exception as e:
        logger.error("_permisos_efectivos: %s", e)
    _CACHE[clave] = perms
    return perms


def _coincide(permiso, conjunto):
    """True si `permiso` está concedido (exacto o por comodín 'modulo.*' / '*')."""
    if "*" in conjunto:
        return True
    if permiso in conjunto:
        return True
    modulo = permiso.split(".", 1)[0]
    return f"{modulo}.*" in conjunto


def _acl_override(uid, emp, roles, grupos, recurso_tipo, recurso_id, accion):
    """Consulta acl_recursos. Devuelve True/False (permitido/denegado) o None si no aplica.
    La denegación explícita gana sobre el permiso."""
    sujetos = [("usuario", str(uid))]
    sujetos += [("rol", str(r)) for r in roles] + [("grupo", str(g)) for g in grupos]
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cond_suj = " OR ".join(["(sujeto_tipo=%s AND sujeto_id=%s)"] * len(sujetos))
            params = [emp, recurso_tipo, accion]
            for st, sid in sujetos:
                params += [st, sid]
            cur.execute(
                "SELECT permitido FROM acl_recursos WHERE id_empresa=%s AND recurso_tipo=%s "
                "AND accion=%s AND (recurso_id=%s OR recurso_id IS NULL) AND (" + cond_suj + ") "
                "ORDER BY permitido ASC LIMIT 1",
                [params[0], params[1], params[2], (str(recurso_id) if recurso_id is not None else None)]
                + sum([[st, sid] for st, sid in sujetos], []))
            r = cur.fetchone()
            if r is None:
                return None
            return bool(r[0] if not isinstance(r, dict) else list(r.values())[0])
    except Exception as e:
        logger.debug("_acl_override: %s", e)
        return None


def puede(usuario, permiso, *, id_empresa=None, recurso_tipo=None, recurso_id=None) -> bool:
    """¿`usuario` tiene `permiso`? Resuelve roles+grupos (+ACL si se indica recurso). SUPERADMIN
    siempre. Sin asignaciones RBAC → fallback al mapeo del perfil (legacy)."""
    u = _norm_usuario(usuario)
    if not u or not u.get("id"):
        # Sin contexto de usuario (flujos internos/tests): no se bloquea (comportamiento legacy).
        return True
    perfil = (u.get("perfil") or "").upper()
    if perfil == "SUPERADMIN":
        return True
    emp = _empresa(id_empresa or u.get("id_empresa"))
    perms = _permisos_efectivos(u["id"], emp)
    concedido = _coincide(permiso, perms) if perms is not None else _coincide(permiso, _cat.permisos_de_perfil(perfil))
    # ACL fina sobre un recurso concreto (la denegación explícita prevalece).
    if recurso_tipo is not None:
        roles, grupos = _ids_roles_grupos(u["id"], emp)
        ov = _acl_override(u["id"], emp, roles, grupos, recurso_tipo, recurso_id, permiso.split(".")[-1])
        if ov is not None:
            concedido = ov
    return bool(concedido)


def exigir(usuario, permiso, *, id_empresa=None, recurso_tipo=None, recurso_id=None):
    """Como `puede` pero LANZA ErrorAutorizacion (y audita la denegación) si no está permitido."""
    if not puede(usuario, permiso, id_empresa=id_empresa, recurso_tipo=recurso_tipo, recurso_id=recurso_id):
        u = _norm_usuario(usuario) or {}
        try:
            from src.services.seguridad import auditoria as _aud
            _aud.registrar("PERMISO_DENEGADO", usuario=u.get("id"),
                           detalles=f"permiso={permiso} recurso={recurso_tipo}:{recurso_id}")
        except Exception:
            pass
        raise ErrorAutorizacion(f"Permiso denegado: {permiso}")
    return True


# ── Decoradores ──────────────────────────────────────────────────────────────
def _actor_de_contexto(args, kwargs):
    if "actor" in kwargs:
        return kwargs["actor"]
    if "usuario" in kwargs:
        return kwargs["usuario"]
    try:
        from flask import g
        if getattr(g, "usuario", None):
            return g.usuario
    except Exception:
        pass
    return None        # _norm_usuario recurrirá a sesion_global


def requiere_permiso(permiso):
    """Exige `permiso` al actor (kwarg actor/usuario, flask.g.usuario o sesión activa)."""
    def deco(f):
        @functools.wraps(f)
        def envoltorio(*args, **kwargs):
            exigir(_actor_de_contexto(args, kwargs), permiso)
            return f(*args, **kwargs)
        return envoltorio
    return deco


def requiere_rol(*roles):
    roles_norm = {r.upper() for r in roles}
    def deco(f):
        @functools.wraps(f)
        def envoltorio(*args, **kwargs):
            u = _norm_usuario(_actor_de_contexto(args, kwargs)) or {}
            perfil = (u.get("perfil") or "").upper()
            if perfil != "SUPERADMIN" and perfil not in roles_norm:
                raise ErrorAutorizacion(f"Rol requerido: {roles_norm}")
            return f(*args, **kwargs)
        return envoltorio
    return deco


def requiere_superadmin(f):
    @functools.wraps(f)
    def envoltorio(*args, **kwargs):
        u = _norm_usuario(_actor_de_contexto(args, kwargs)) or {}
        if (u.get("perfil") or "").upper() != "SUPERADMIN":
            raise ErrorAutorizacion("Requiere SUPERADMIN")
        return f(*args, **kwargs)
    return envoltorio
