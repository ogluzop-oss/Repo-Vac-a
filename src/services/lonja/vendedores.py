"""Vendedores de la Lonja (identidad global del proveedor en el mercado).

Un vendedor define su DIVISA de referencia (con la que publica precios/pujas). Puede originarse desde el
Portal de proveedor de una empresa (`id_empresa_origen`/`id_proveedor_origen`) pero es visible por todas
las compradoras del mercado. El token identifica al vendedor en el lado remoto (auth del portal de la Lonja).
"""

from ._common import _audit, _conn, _filas, _token, _uno, logger

ESTADOS = ("activo", "suspendido")


def alta_vendedor(nombre, *, divisa="EUR", id_empresa_origen=None, id_proveedor_origen=None) -> dict | None:
    try:
        tok = _token()
        with _conn() as c, c.cursor() as cur:
            cur.execute("INSERT INTO lonja_vendedores (nombre, divisa, token, id_empresa_origen, "
                        "id_proveedor_origen) VALUES (%s,%s,%s,%s,%s)",
                        (str(nombre)[:160], str(divisa or "EUR").upper()[:8], tok,
                         id_empresa_origen, id_proveedor_origen))
            vid = cur.lastrowid
            c.commit()
        _audit("LONJA_VENDEDOR_ALTA", f"{vid}:{nombre}", "lonja_vendedores")
        return {"id": vid, "token": tok, "divisa": str(divisa or "EUR").upper()}
    except Exception as e:
        logger.error("alta_vendedor: %s", e)
        return None


def set_divisa(id_vendedor, divisa) -> bool:
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("UPDATE lonja_vendedores SET divisa=%s WHERE id=%s",
                        (str(divisa or "EUR").upper()[:8], id_vendedor))
            ok = cur.rowcount >= 0
            c.commit()
        _audit("LONJA_VENDEDOR_DIVISA", f"{id_vendedor}:{divisa}", "lonja_vendedores")
        return ok
    except Exception as e:
        logger.error("set_divisa: %s", e)
        return False


def obtener(id_vendedor) -> dict | None:
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT id, nombre, divisa, estado, id_empresa_origen, id_proveedor_origen "
                        "FROM lonja_vendedores WHERE id=%s", (id_vendedor,))
            return _uno(cur)
    except Exception as e:
        logger.error("obtener vendedor: %s", e)
        return None


def resolver_token(token) -> dict | None:
    if not token:
        return None
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT id, nombre, divisa, estado FROM lonja_vendedores WHERE token=%s", (token,))
            r = _uno(cur)
        if not r or r.get("estado") != "activo":
            return None
        return r
    except Exception as e:
        logger.error("resolver_token vendedor: %s", e)
        return None


def listar(id_empresa_origen=None) -> list:
    cond, params = [], []
    if id_empresa_origen:
        cond.append("id_empresa_origen=%s"); params.append(id_empresa_origen)
    q = "SELECT id, nombre, divisa, estado FROM lonja_vendedores"
    if cond:
        q += " WHERE " + " AND ".join(cond)
    q += " ORDER BY nombre"
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute(q, tuple(params))
            return _filas(cur)
    except Exception as e:
        logger.error("listar vendedores: %s", e)
        return []
