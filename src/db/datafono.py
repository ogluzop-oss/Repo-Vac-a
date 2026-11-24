"""
Configuración del DATÁFONO FÍSICO por TIENDA (cobro real con tarjeta en TPV/autocobro).

A diferencia de `db.pagos` (pasarela ONLINE, una fila por EMPRESA), el datáfono es un dispositivo
físico de CADA tienda: una fila por (id_empresa, id_tienda). Guarda el proveedor emparejado
(viva/stripe_terminal/sumup/simulado), las credenciales (cifradas en reposo) y el terminal
elegido. El servicio de cobro (`services.tpv.card_terminal_service`) usa esta config para resolver
el driver de la tienda activa. Multiempresa + multitienda estricto.
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, ensure_schema, obtener_conexion

logger = logging.getLogger("datafono_db")

# Campos sensibles cifrados en reposo (Fernet, ver src/utils/cripto.py) — mismo criterio que
# `db.pagos`/`db.correo` para cualquier credencial de un proveedor externo.
_SECRETOS = ("api_key", "api_secret")

# Centinela para "no tocar este campo" en `guardar_config` — necesario para `importe_minimo_tarjeta`
# porque `None`/`0` son valores válidos y distintos de "sin especificar" (mismo criterio que
# `db.config_ticket._SIN_CAMBIO`).
_SIN_CAMBIO = object()


def _empresa(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def _tienda(id_tienda=None):
    if id_tienda is not None:
        try:
            return int(id_tienda)
        except (TypeError, ValueError):
            return 0
    try:
        from src.db.empresa import tienda_actual_id_int
        return tienda_actual_id_int()
    except Exception:
        return 0


def obtener_config(id_tienda=None, id_empresa=None) -> dict:
    """Config del datáfono de la tienda (dict con defaults — 'simulado' — si no existe fila: una
    tienda sin emparejar sigue pudiendo cobrar en efectivo con normalidad)."""
    id_empresa = _empresa(id_empresa)
    id_tienda = _tienda(id_tienda)
    base = {"id_empresa": id_empresa, "id_tienda": id_tienda, "proveedor": "simulado",
            "api_key": "", "api_secret": "", "comercio": "", "terminal_id": "",
            "terminal_nombre": "", "modo": "test", "moneda": "EUR", "estado": "activo",
            "adaptador_json": "", "importe_minimo_tarjeta": None}
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM tpv_datafono_config WHERE id_empresa=%s AND id_tienda=%s",
                (id_empresa, id_tienda))
            r = cur.fetchone()
            if r:
                if not isinstance(r, dict):
                    r = dict(zip([d[0] for d in cur.description], r))
                base.update({k: (r.get(k) if r.get(k) is not None else base[k]) for k in base})
    except Exception as e:
        logger.error("obtener_config(tienda=%s): %s", id_tienda, e)
    from src.utils import cripto
    for k in _SECRETOS:
        base[k] = cripto.descifrar_seguro(base.get(k)) or ""
    return base


def guardar_config(*, proveedor=None, api_key=None, api_secret=None, comercio=None,
                   terminal_id=None, terminal_nombre=None, modo=None, moneda=None, estado=None,
                   adaptador_json=None, importe_minimo_tarjeta=_SIN_CAMBIO, id_tienda=None,
                   id_empresa=None) -> bool:
    """Crea/actualiza (upsert) la config del datáfono de la tienda. Solo cambia lo indicado.

    `adaptador_json` (solo proveedor "generico"): la FORMA de la API del banco (base_url, auth,
    rutas/plantillas — ver `services.tpv.datafono.generico`). No es un secreto — ahí solo van
    referencias como "{api_key}"/"{api_secret}" a los campos YA cifrados aparte — así que se
    guarda en claro, igual que `modo`/`moneda`.

    `importe_minimo_tarjeta` (petición explícita, 2026-11-23 — mínimo para aceptar pago con
    tarjeta en esta tienda, ver `gui.tpv._cobrar_con_datafono`): usa un centinela propio
    (`_SIN_CAMBIO`, mismo criterio que `db.config_ticket.guardar_config_ticket`) en vez del `or
    actual[...]` que usan los demás campos — a diferencia de un texto, aquí `None`/`0` son valores
    VÁLIDOS y distintos ("sin mínimo" y "mínimo de 0€" son lo mismo en la práctica, pero `0` debe
    poder guardarse explícitamente sin que se confunda con "no tocar este campo")."""
    id_empresa = _empresa(id_empresa)
    id_tienda = _tienda(id_tienda)
    actual = obtener_config(id_tienda, id_empresa)
    from src.utils import cripto
    nueva = {
        "proveedor": (proveedor or actual["proveedor"]),
        "api_key": cripto.cifrar(api_key) if api_key is not None else (
            cripto.cifrar(actual["api_key"]) if actual["api_key"] else None),
        "api_secret": cripto.cifrar(api_secret) if api_secret is not None else (
            cripto.cifrar(actual["api_secret"]) if actual["api_secret"] else None),
        "comercio": (comercio if comercio is not None else actual["comercio"]),
        "terminal_id": (terminal_id if terminal_id is not None else actual["terminal_id"]),
        "terminal_nombre": (terminal_nombre if terminal_nombre is not None else actual["terminal_nombre"]),
        "modo": (modo or actual["modo"]),
        "moneda": (moneda or actual["moneda"]),
        "estado": (estado or actual["estado"]),
        "adaptador_json": (adaptador_json if adaptador_json is not None else actual["adaptador_json"]),
        "importe_minimo_tarjeta": (actual["importe_minimo_tarjeta"]
                                   if importe_minimo_tarjeta is _SIN_CAMBIO
                                   else importe_minimo_tarjeta),
    }
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO tpv_datafono_config (id_empresa, id_tienda, proveedor, api_key, "
                "api_secret, comercio, terminal_id, terminal_nombre, modo, moneda, estado, "
                "adaptador_json, importe_minimo_tarjeta) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
                "proveedor=VALUES(proveedor), api_key=VALUES(api_key), api_secret=VALUES(api_secret), "
                "comercio=VALUES(comercio), terminal_id=VALUES(terminal_id), "
                "terminal_nombre=VALUES(terminal_nombre), modo=VALUES(modo), moneda=VALUES(moneda), "
                "estado=VALUES(estado), adaptador_json=VALUES(adaptador_json), "
                "importe_minimo_tarjeta=VALUES(importe_minimo_tarjeta)",
                (id_empresa, id_tienda, nueva["proveedor"], nueva["api_key"], nueva["api_secret"],
                 nueva["comercio"], nueva["terminal_id"], nueva["terminal_nombre"], nueva["modo"],
                 nueva["moneda"], nueva["estado"], nueva["adaptador_json"] or None,
                 nueva["importe_minimo_tarjeta"]))
            conn.commit()
        return True
    except Exception as e:
        logger.error("guardar_config(tienda=%s): %s", id_tienda, e)
        return False
