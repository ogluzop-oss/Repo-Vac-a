"""
Responsabilidades por nodo (Paquete Enterprise 7, SUBFASE 7.2). Cada area conoce a su
responsable principal/suplente/supervisor/director/administrador/auditor. La IA sabra siempre
quien responde de cada area (cadena de mando via la ruta materializada).
"""

import logging

from src.services.gobierno import organigrama as _O

logger = logging.getLogger("gobierno.responsables")

ROLES_ORG = ("principal", "suplente", "supervisor", "director", "administrador", "auditor")


def _emp(id_empresa=None):
    return _O._emp(id_empresa)


def asignar(id_nodo, rol_org, usuario, id_empresa=None) -> bool:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO org_responsables (id_empresa, id_nodo, rol_org, usuario) "
                        "VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE usuario=VALUES(usuario)",
                        (emp, id_nodo, rol_org, str(usuario)[:80]))
            c.commit()
        return True
    except Exception as e:
        logger.error("asignar responsable: %s", e)
        return False


def responsable(id_nodo, rol_org="principal", id_empresa=None) -> str | None:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT usuario FROM org_responsables WHERE id_empresa=%s AND id_nodo=%s "
                        "AND rol_org=%s", (emp, id_nodo, rol_org))
            r = cur.fetchone()
            return (r[0] if not isinstance(r, dict) else r["usuario"]) if r else None
    except Exception:
        return None


def responsables_de(id_nodo, id_empresa=None) -> dict:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT rol_org, usuario FROM org_responsables WHERE id_empresa=%s AND id_nodo=%s",
                        (emp, id_nodo))
            out = {}
            for r in cur.fetchall():
                g = (lambda i, k: r[i] if not isinstance(r, dict) else r[k])
                out[g(0, "rol_org")] = g(1, "usuario")
            return out
    except Exception:
        return {}


def cadena_mando(id_nodo, id_empresa=None) -> list:
    """Del nodo hacia arriba (SUBFASE 7.9): responsable de cada nivel hasta la raiz."""
    emp = _emp(id_empresa)
    nodos = [_O.obtener(id_nodo, emp)] + list(reversed(_O.ancestros(id_nodo, emp)))
    out = []
    for n in nodos:
        if not n:
            continue
        resp = responsable(n["id"], "director", emp) or responsable(n["id"], "principal", emp) \
            or responsable(n["id"], "administrador", emp)
        if resp:
            out.append({"nodo": n["nombre"], "tipo": n["tipo"], "nivel": n["nivel"], "responsable": resp})
    return out


def nodos_de_usuario(usuario, id_empresa=None) -> list:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT id_nodo, rol_org FROM org_responsables WHERE id_empresa=%s AND usuario=%s",
                        (emp, str(usuario)))
            return [{"id_nodo": (r[0] if not isinstance(r, dict) else r["id_nodo"]),
                     "rol_org": (r[1] if not isinstance(r, dict) else r["rol_org"])}
                    for r in cur.fetchall()]
    except Exception:
        return []
