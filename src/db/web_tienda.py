"""
Configuración de la WEB PROPIA (Escenario B) por empresa.

La tienda online generada (servida por el backend) lee esta config para su marca
(nombre, color, logo, moneda, dominio) y si está activa. Una fila por empresa.
La web consume el catálogo en vivo (siempre sincronizada). Ver [[project_venta_online]].
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, ensure_schema, obtener_conexion

logger = logging.getLogger("web_tienda_db")


def _empresa(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def obtener_config(id_empresa=None) -> dict:
    id_empresa = _empresa(id_empresa)
    base = {"id_empresa": id_empresa, "activa": 0, "nombre": "", "descripcion": "",
            "color": "#00FFC6", "logo_url": "", "moneda": "EUR", "dominio": ""}
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM web_config WHERE id_empresa=%s", (id_empresa,))
            r = cur.fetchone()
            if r:
                if not isinstance(r, dict):
                    r = dict(zip([d[0] for d in cur.description], r))
                base.update({k: (r.get(k) if r.get(k) is not None else base[k]) for k in base})
    except Exception as e:
        logger.error("obtener_config: %s", e)
    return base


def guardar_config(activa=None, nombre=None, descripcion=None, color=None,
                   logo_url=None, moneda=None, dominio=None, id_empresa=None) -> bool:
    id_empresa = _empresa(id_empresa)
    a = obtener_config(id_empresa)
    n = {
        "activa": int(activa if activa is not None else a["activa"]),
        "nombre": nombre if nombre is not None else a["nombre"],
        "descripcion": descripcion if descripcion is not None else a["descripcion"],
        "color": color or a["color"],
        "logo_url": logo_url if logo_url is not None else a["logo_url"],
        "moneda": moneda or a["moneda"],
        "dominio": dominio if dominio is not None else a["dominio"],
    }
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO web_config "
                "(id_empresa, activa, nombre, descripcion, color, logo_url, moneda, dominio) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE activa=VALUES(activa), nombre=VALUES(nombre), "
                "descripcion=VALUES(descripcion), color=VALUES(color), logo_url=VALUES(logo_url), "
                "moneda=VALUES(moneda), dominio=VALUES(dominio)",
                (id_empresa, n["activa"], n["nombre"], n["descripcion"], n["color"],
                 n["logo_url"], n["moneda"], n["dominio"]))
            conn.commit()
        return True
    except Exception as e:
        logger.error("guardar_config: %s", e)
        return False
