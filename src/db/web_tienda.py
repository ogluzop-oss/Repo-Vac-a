"""
Configuración de la WEB PROPIA (Escenario B) por empresa.

La tienda online generada (servida por el backend) lee esta config para su marca
(nombre, color, logo, moneda, dominio) y si está activa. Una fila por empresa.
La web consume el catálogo en vivo (siempre sincronizada). Ver [[project_venta_online]].

@deprecated-ownership (Rearquitectura Comercio Digital · Fase 1 → Fase 2):
    Esta configuración (marca/logo/color/moneda/dominio de la presencia digital propia) NO pertenece
    al CATÁLOGO (que es un PIM: solo producto). Su propietario definitivo es CANAL WEB. En Fase 2,
    Canal Web pasará a ser el ÚNICO editor de `web_config` (o se unificará con `cd_canal_web`), y el
    storefront leerá la fuente unificada. Se CONSERVA íntegra como capa de compatibilidad: el backend
    (`backend/storefront.py`) sigue leyéndola sin cambios; NO se elimina hasta que no queden lectores.
    Único escritor actual: la pestaña «Web» de CatalogoWindow (a retirar en Fase 2).
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, ensure_schema, obtener_conexion

logger = logging.getLogger("web_tienda_db")


def _empresa(id_empresa=None):
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


def obtener_config(id_empresa=None) -> dict:
    id_empresa = _empresa(id_empresa)
    base = {"id_empresa": id_empresa, "activa": 0, "nombre": "", "descripcion": "",
            "color": "#00FFC6", "logo_url": "", "moneda": "EUR", "dominio": "",
            # Acento secundario (Generador de Apps Móviles PWA, Fase 1, migr. 0300) — rol propio
            # en el manifest.json (`background_color`) distinto del acento principal
            # (`theme_color`); "" = sin fijar, la PWA/tienda cae al color principal para ambos.
            "color_secundario": "",
            # Políticas legales (Fase 3 e-commerce, migr. 0290) — texto plano, editable, servido
            # por el storefront real (`backend/storefront.py`).
            "texto_terminos": "", "texto_privacidad": "", "texto_devoluciones": "",
            "texto_politica_envios": "",
            # Tema visual (Fase 4 e-commerce, migr. 0291) — JSON (string) con las secciones/bloques
            # de la home, editadas desde el editor visual (`gui/tema_editor_dialog.py`). Vacío ("")
            # = sin tema guardado todavía: `storefront.pagina_home` sigue generando el layout fijo
            # de siempre (cero regresión para tiendas ya creadas).
            "tema_json": "",
            # Borrador con contraseña (Fase 5 e-commerce, migr. 0292) — `borrador=0` (de serie) deja
            # la tienda exactamente como siempre; `borrador=1` + `password_hash` exige credencial
            # HTTP Basic en el storefront (`backend/storefront.py`). El hash lo calcula SIEMPRE el
            # llamante (`canal_web.configurar_borrador`, vía `seguridad.passwords.hash_password`) —
            # esta capa nunca ve la contraseña en claro.
            "borrador": 0, "password_hash": ""}
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
                   logo_url=None, moneda=None, dominio=None, id_empresa=None,
                   texto_terminos=None, texto_privacidad=None, texto_devoluciones=None,
                   texto_politica_envios=None, tema_json=None, borrador=None,
                   password_hash=None, color_secundario=None) -> bool:
    id_empresa = _empresa(id_empresa)
    a = obtener_config(id_empresa)
    n = {
        "activa": int(activa if activa is not None else a["activa"]),
        "nombre": nombre if nombre is not None else a["nombre"],
        "descripcion": descripcion if descripcion is not None else a["descripcion"],
        "color": color or a["color"],
        "color_secundario": color_secundario if color_secundario is not None else a["color_secundario"],
        "logo_url": logo_url if logo_url is not None else a["logo_url"],
        "moneda": moneda or a["moneda"],
        "dominio": dominio if dominio is not None else a["dominio"],
        "texto_terminos": texto_terminos if texto_terminos is not None else a["texto_terminos"],
        "texto_privacidad": texto_privacidad if texto_privacidad is not None else a["texto_privacidad"],
        "texto_devoluciones": texto_devoluciones if texto_devoluciones is not None else a["texto_devoluciones"],
        "texto_politica_envios": texto_politica_envios if texto_politica_envios is not None
                                 else a["texto_politica_envios"],
        "tema_json": tema_json if tema_json is not None else a["tema_json"],
        "borrador": int(borrador if borrador is not None else a["borrador"]),
        "password_hash": password_hash if password_hash is not None else a["password_hash"],
    }
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO web_config "
                "(id_empresa, activa, nombre, descripcion, color, color_secundario, logo_url, "
                "moneda, dominio, texto_terminos, texto_privacidad, texto_devoluciones, "
                "texto_politica_envios, tema_json, borrador, password_hash) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE activa=VALUES(activa), nombre=VALUES(nombre), "
                "descripcion=VALUES(descripcion), color=VALUES(color), "
                "color_secundario=VALUES(color_secundario), logo_url=VALUES(logo_url), "
                "moneda=VALUES(moneda), dominio=VALUES(dominio), "
                "texto_terminos=VALUES(texto_terminos), texto_privacidad=VALUES(texto_privacidad), "
                "texto_devoluciones=VALUES(texto_devoluciones), "
                "texto_politica_envios=VALUES(texto_politica_envios), tema_json=VALUES(tema_json), "
                "borrador=VALUES(borrador), password_hash=VALUES(password_hash)",
                (id_empresa, n["activa"], n["nombre"], n["descripcion"], n["color"],
                 n["color_secundario"] or None, n["logo_url"], n["moneda"], n["dominio"],
                 n["texto_terminos"], n["texto_privacidad"], n["texto_devoluciones"],
                 n["texto_politica_envios"], n["tema_json"], n["borrador"],
                 n["password_hash"] or None))
            conn.commit()
        return True
    except Exception as e:
        logger.error("guardar_config: %s", e)
        return False
