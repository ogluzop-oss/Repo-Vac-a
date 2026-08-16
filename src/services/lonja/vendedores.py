"""Vendedores de la Lonja (identidad global del proveedor en el mercado).

Un vendedor define su DIVISA de referencia (con la que publica precios/pujas). Puede originarse desde el
Portal de proveedor de una empresa (`id_empresa_origen`/`id_proveedor_origen`) pero es visible por todas
las compradoras del mercado. El token identifica al vendedor en el lado remoto (auth del portal de la Lonja).
"""

from ._common import _audit, _conn, _filas, _token, _uno, logger

ESTADOS = ("activo", "suspendido")


def _norm_tipos(tipo_comercio) -> str | None:
    """Normaliza el tipo de comercio a una lista CSV de verticales válidos (o None = todos)."""
    try:
        from src.services import verticales
        validos = set(verticales.VERTICALES)
    except Exception:
        validos = {"SUPERMARKET", "RETAIL", "PHARMACY", "TEXTIL", "BAKERY"}
    if not tipo_comercio:
        return None
    items = tipo_comercio if isinstance(tipo_comercio, (list, tuple, set)) else str(tipo_comercio).split(",")
    out = [str(x).strip().upper() for x in items if str(x).strip().upper() in validos]
    return ",".join(dict.fromkeys(out)) or None


def alta_vendedor(nombre, *, divisa="EUR", id_empresa_origen=None, id_proveedor_origen=None,
                  tipo_comercio=None) -> dict | None:
    try:
        tok = _token()
        tc = _norm_tipos(tipo_comercio)
        with _conn() as c, c.cursor() as cur:
            cur.execute("INSERT INTO lonja_vendedores (nombre, divisa, token, id_empresa_origen, "
                        "id_proveedor_origen, tipo_comercio) VALUES (%s,%s,%s,%s,%s,%s)",
                        (str(nombre)[:160], str(divisa or "EUR").upper()[:8], tok,
                         id_empresa_origen, id_proveedor_origen, tc))
            vid = cur.lastrowid
            c.commit()
        _audit("LONJA_VENDEDOR_ALTA", f"{vid}:{nombre}", "lonja_vendedores")
        return {"id": vid, "token": tok, "divisa": str(divisa or "EUR").upper(), "tipo_comercio": tc}
    except Exception as e:
        logger.error("alta_vendedor: %s", e)
        return None


def set_tipo_comercio(id_vendedor, tipo_comercio) -> bool:
    """Fija los tipos de comercio (verticales) a los que suministra el vendedor. Se define en el
    onboarding ANTES que la divisa, para gatear sus listados por edición."""
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("UPDATE lonja_vendedores SET tipo_comercio=%s WHERE id=%s",
                        (_norm_tipos(tipo_comercio), id_vendedor))
            ok = cur.rowcount >= 0
            c.commit()
        _audit("LONJA_VENDEDOR_TIPO", f"{id_vendedor}:{tipo_comercio}", "lonja_vendedores")
        return ok
    except Exception as e:
        logger.error("set_tipo_comercio: %s", e)
        return False


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
            cur.execute("SELECT id, nombre, divisa, estado, tipo_comercio, id_empresa_origen, "
                        "id_proveedor_origen FROM lonja_vendedores WHERE id=%s", (id_vendedor,))
            return _uno(cur)
    except Exception as e:
        logger.error("obtener vendedor: %s", e)
        return None


def resolver_token(token) -> dict | None:
    if not token:
        return None
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT id, nombre, divisa, estado, tipo_comercio, iban_mascara "
                        "FROM lonja_vendedores WHERE token=%s", (token,))
            r = _uno(cur)
        if not r or r.get("estado") != "activo":
            return None
        return r
    except Exception as e:
        logger.error("resolver_token vendedor: %s", e)
        return None


def vendedor_de_proveedor(id_empresa, id_proveedor, *, nombre=None, divisa="EUR",
                          tipo_comercio=None) -> int | None:
    """Devuelve el id del vendedor de la Lonja vinculado a un proveedor de una empresa; lo crea si no
    existe (puente empresa↔mercado: proveedor y vendedor son el MISMO suministrador). Idempotente por
    (id_empresa_origen, id_proveedor_origen); si se pasa `tipo_comercio`, lo actualiza."""
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT id FROM lonja_vendedores WHERE id_empresa_origen=%s "
                        "AND id_proveedor_origen=%s", (id_empresa, id_proveedor))
            r = _uno(cur)
        if r:
            if tipo_comercio is not None:
                set_tipo_comercio(r["id"], tipo_comercio)
            return r["id"]
        inv = alta_vendedor(nombre or f"Proveedor {id_proveedor}", divisa=divisa,
                            id_empresa_origen=id_empresa, id_proveedor_origen=id_proveedor,
                            tipo_comercio=tipo_comercio)
        return inv["id"] if inv else None
    except Exception as e:
        logger.error("vendedor_de_proveedor: %s", e)
        return None


def token_de_proveedor(id_empresa, id_proveedor, *, nombre=None) -> str | None:
    """Puente proveedor→vendedor: asegura el vendedor de la Lonja del proveedor y devuelve su token, para
    que el MISMO panel del proveedor pueda operar también en el mercado (unificación proveedor↔vendedor)."""
    vid = vendedor_de_proveedor(id_empresa, id_proveedor, nombre=nombre)
    if not vid:
        return None
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT token FROM lonja_vendedores WHERE id=%s", (vid,))
            r = _uno(cur)
        return r["token"] if r else None
    except Exception as e:
        logger.error("token_de_proveedor: %s", e)
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
