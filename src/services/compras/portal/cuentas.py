"""Cuentas/enlace del proveedor en el portal: invitación, token de acceso, estado y resolución.

La cuenta vive en `portal_proveedor_cuentas` (migr 0198). El TOKEN identifica al proveedor y a su empresa
en el lado remoto (auth del portal); nunca se expone la clave de otro tenant. Degradable: crear la
invitación no requiere que el enlace remoto esté desplegado.
"""

from ._common import _audit, _conn, _emp, _filas, _token, _uno, logger


def invitar_proveedor(id_proveedor, *, email=None, id_empresa=None) -> dict | None:
    """Crea (o reactiva) la cuenta de portal de un proveedor y devuelve su enlace/token.
    Idempotente: si ya existía, conserva el token y la deja 'invitado'."""
    emp = _emp(id_empresa)
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT id, token FROM portal_proveedor_cuentas "
                        "WHERE id_empresa=%s AND id_proveedor=%s", (emp, id_proveedor))
            row = _uno(cur)
            if row:
                cur.execute("UPDATE portal_proveedor_cuentas SET email=COALESCE(%s,email), "
                            "estado='invitado' WHERE id=%s", (email, row["id"]))
                c.commit()
                tok, cid = row["token"], row["id"]
            else:
                tok = _token()
                cur.execute("INSERT INTO portal_proveedor_cuentas (id_empresa, id_proveedor, email, "
                            "token, estado) VALUES (%s,%s,%s,%s,'invitado')", (emp, id_proveedor, email, tok))
                cid = cur.lastrowid
                c.commit()
        _audit("PORTAL_INVITAR", f"{id_proveedor}")
        return {"id": cid, "id_proveedor": id_proveedor, "token": tok, "estado": "invitado"}
    except Exception as e:
        logger.error("invitar_proveedor: %s", e)
        return None


def estado_cuenta(id_proveedor, id_empresa=None) -> dict | None:
    emp = _emp(id_empresa)
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT id, id_proveedor, email, estado, creado_en, ultima_conexion "
                        "FROM portal_proveedor_cuentas WHERE id_empresa=%s AND id_proveedor=%s",
                        (emp, id_proveedor))
            return _uno(cur)
    except Exception as e:
        logger.error("estado_cuenta: %s", e)
        return None


def listar_cuentas(id_empresa=None, estado=None) -> list:
    """Cuentas de portal de la empresa, con la razón social del proveedor (para la GUI)."""
    emp = _emp(id_empresa)
    cond, params = ["pc.id_empresa=%s"], [emp]
    if estado:
        cond.append("pc.estado=%s"); params.append(estado)
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT pc.id, pc.id_proveedor, "
                        "COALESCE(p.razon_social, CONCAT('Proveedor ', pc.id_proveedor)) AS proveedor, "
                        "pc.email, pc.estado, pc.ultima_conexion FROM portal_proveedor_cuentas pc "
                        "LEFT JOIN proveedores p ON p.id_proveedor = pc.id_proveedor "
                        "WHERE " + " AND ".join(cond) + " ORDER BY proveedor", tuple(params))
            return _filas(cur)
    except Exception as e:
        logger.error("listar_cuentas: %s", e)
        return []


def _set_estado(id_proveedor, estado, id_empresa=None) -> bool:
    emp = _emp(id_empresa)
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("UPDATE portal_proveedor_cuentas SET estado=%s "
                        "WHERE id_empresa=%s AND id_proveedor=%s", (estado, emp, id_proveedor))
            ok = cur.rowcount > 0
            c.commit()
        _audit("PORTAL_ESTADO", f"{id_proveedor}:{estado}")
        return ok
    except Exception as e:
        logger.error("_set_estado: %s", e)
        return False


def revocar(id_proveedor, id_empresa=None) -> bool:
    """Corta el acceso del proveedor (estado 'revocado'); el token deja de resolver."""
    return _set_estado(id_proveedor, "revocado", id_empresa)


def activar(id_proveedor, id_empresa=None) -> bool:
    return _set_estado(id_proveedor, "activo", id_empresa)


def regenerar_token(id_proveedor, id_empresa=None) -> str | None:
    emp = _emp(id_empresa)
    tok = _token()
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("UPDATE portal_proveedor_cuentas SET token=%s, estado='invitado' "
                        "WHERE id_empresa=%s AND id_proveedor=%s", (tok, emp, id_proveedor))
            ok = cur.rowcount > 0
            c.commit()
        if ok:
            _audit("PORTAL_TOKEN_REGEN", f"{id_proveedor}")
            return tok
        return None
    except Exception as e:
        logger.error("regenerar_token: %s", e)
        return None


def resolver_token(token) -> dict | None:
    """Auth del portal (lado proveedor): resuelve un token a {id_empresa, id_proveedor, estado}.
    NO devuelve nada si la cuenta está 'revocado'. Sin id_empresa: el token identifica al tenant."""
    if not token:
        return None
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT id_empresa, id_proveedor, estado FROM portal_proveedor_cuentas "
                        "WHERE token=%s", (token,))
            row = _uno(cur)
        if not row or row.get("estado") == "revocado":
            return None
        return row
    except Exception as e:
        logger.error("resolver_token: %s", e)
        return None


def marcar_conexion(token) -> bool:
    """El proveedor entra al portal: sella `ultima_conexion` y activa la cuenta (si estaba invitada)."""
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("UPDATE portal_proveedor_cuentas SET ultima_conexion=NOW(), "
                        "estado=CASE WHEN estado='invitado' THEN 'activo' ELSE estado END "
                        "WHERE token=%s AND estado<>'revocado'", (token,))
            ok = cur.rowcount > 0
            c.commit()
        return ok
    except Exception as e:
        logger.error("marcar_conexion: %s", e)
        return False
