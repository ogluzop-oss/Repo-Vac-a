"""
PCD · Catálogo Comercial Global (Etapa B · Fase B3).

Evolución de la Product Publication Layer a un catálogo comercial COMPLETO: variantes + idiomas +
países + monedas + impuestos + reglas comerciales. NO duplica motores: COMPONE en runtime sobre:
  · PPL (`publicaciones.preparar_para_canal`) → contenido/SEO/media + overlay i18n (idioma/región).
  · multidivisa (`capabilities.divisas`) → formato/símbolo/decimales de la moneda.
  · fiscalidad (`capabilities.fiscalidad`) → IVA por país.
  · reglas comerciales (`capabilities.rules`, degradable) → visibilidad/condiciones.

Es una capa de COMPOSICIÓN/LECTURA (no muta el producto ni el dominio). Multiempresa. Los adaptadores
recibirán la ficha comercial ya compuesta (Dominio → Adaptador → Canal).
"""

from __future__ import annotations

import json
import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion

logger = logging.getLogger("cd.catalogo")

FASE = "B3"


def _emp(id_empresa=None):
    from src.services.comercio_digital._base import emp as _emp_base
    return _emp_base(id_empresa)
# ── Variantes ─────────────────────────────────────────────────────────────────
def agregar_variante(id_publicacion, sku, *, atributos=None, precio_delta=0, codigo_articulo=None,
                     activo=True, orden=0, id_empresa=None):
    emp = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO cd_catalogo_variantes (id_publicacion, id_empresa, sku, atributos, "
                "precio_delta, codigo_articulo, activo, orden) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE atributos=VALUES(atributos), precio_delta=VALUES(precio_delta), "
                "codigo_articulo=VALUES(codigo_articulo), activo=VALUES(activo), orden=VALUES(orden)",
                (id_publicacion, emp, sku, json.dumps(atributos or {}), float(precio_delta or 0),
                 codigo_articulo, 1 if activo else 0, int(orden)))
            conn.commit()
            return True
    except Exception as e:
        logger.error("agregar_variante(%s/%s): %s", id_publicacion, sku, e)
        return False


def variantes(id_publicacion, *, id_empresa=None, solo_activas=True):
    emp = _emp(id_empresa)
    out = []
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            sql = ("SELECT sku, atributos, precio_delta, codigo_articulo, activo, orden FROM "
                   "cd_catalogo_variantes WHERE id_publicacion=%s AND id_empresa=%s")
            if solo_activas:
                sql += " AND activo=1"
            sql += " ORDER BY orden, sku"
            cur.execute(sql, (id_publicacion, emp))
            cols = ("sku", "atributos", "precio_delta", "codigo_articulo", "activo", "orden")
            for f in cur.fetchall():
                d = f if isinstance(f, dict) else dict(zip(cols, f))
                if isinstance(d.get("atributos"), str):
                    try:
                        d["atributos"] = json.loads(d["atributos"])
                    except Exception:
                        pass
                d["precio_delta"] = float(d.get("precio_delta") or 0)
                out.append(d)
    except Exception as e:
        logger.error("variantes(%s): %s", id_publicacion, e)
    return out


def variantes_batch(id_publicaciones, *, id_empresa=None, solo_activas=True):
    """Variantes de VARIAS publicaciones en UNA sola consulta (optimización N+1 de `catalogo`).
    Devuelve {id_publicacion: [variantes]} con el mismo formato que `variantes()`."""
    emp = _emp(id_empresa)
    ids = list(dict.fromkeys(id_publicaciones or []))
    out = {pid: [] for pid in ids}
    if not ids:
        return out
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            ph = ",".join(["%s"] * len(ids))
            sql = ("SELECT id_publicacion, sku, atributos, precio_delta, codigo_articulo, activo, "
                   f"orden FROM cd_catalogo_variantes WHERE id_empresa=%s AND id_publicacion IN ({ph})")
            if solo_activas:
                sql += " AND activo=1"
            sql += " ORDER BY orden, sku"
            cur.execute(sql, (emp, *ids))
            cols = ("id_publicacion", "sku", "atributos", "precio_delta", "codigo_articulo", "activo",
                    "orden")
            for f in cur.fetchall():
                d = f if isinstance(f, dict) else dict(zip(cols, f))
                if isinstance(d.get("atributos"), str):
                    try:
                        d["atributos"] = json.loads(d["atributos"])
                    except Exception:
                        pass
                d["precio_delta"] = float(d.get("precio_delta") or 0)
                pid = d.pop("id_publicacion")
                out.setdefault(pid, []).append(d)
    except Exception as e:
        logger.error("variantes_batch: %s", e)
    return out


def eliminar_variante(id_publicacion, sku, *, id_empresa=None):
    emp = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM cd_catalogo_variantes WHERE id_publicacion=%s AND id_empresa=%s "
                        "AND sku=%s", (id_publicacion, emp, sku))
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error("eliminar_variante(%s/%s): %s", id_publicacion, sku, e)
        return False


# ── Composición fiscal / monetaria (reutiliza capacidades) ────────────────────
def _iva_pct(pais, id_empresa):
    try:
        from src.platform import capabilities as cap
        fis = cap.fiscalidad()
        if fis is not None:
            if pais and hasattr(fis, "iva_de_pais"):
                return float(fis.iva_de_pais(pais))
            if hasattr(fis, "iva_empresa"):
                return float(fis.iva_empresa(id_empresa))
    except Exception as e:
        logger.debug("iva_pct(%s): %s", pais, e)
    return 0.0


def _formatear(monto, moneda):
    try:
        from src.platform import capabilities as cap
        div = cap.divisas()
        if div is not None and hasattr(div, "formatear"):
            return div.formatear(monto, moneda)
    except Exception:
        pass
    return f"{float(monto or 0):.2f}"


def _precio(base, delta, moneda, iva_pct):
    neto = round(float(base or 0) + float(delta or 0), 2)
    impuesto = round(neto * iva_pct / 100.0, 2)
    total = round(neto + impuesto, 2)
    return {"neto": neto, "iva_pct": iva_pct, "impuesto": impuesto, "total": total,
            "moneda": moneda, "neto_fmt": _formatear(neto, moneda), "total_fmt": _formatear(total, moneda)}


def _reglas_comerciales(id_publicacion, pais, id_empresa):
    """Visibilidad/condiciones comerciales (degradable vía Rules). Por defecto: visible."""
    try:
        from src.platform import capabilities as cap
        rules = cap.rules()
        if rules is not None and hasattr(rules, "reglas_catalogo"):
            return rules.reglas_catalogo(id_publicacion=id_publicacion, pais=pais,
                                         id_empresa=id_empresa) or {"visible": True}
    except Exception:
        pass
    return {"visible": True}


def ficha_comercial(id_publicacion, *, pais=None, idioma=None, moneda=None, id_empresa=None,
                    iva_pct=None, variantes_pre=None):
    """Compone la ficha comercial global de una publicación para (país, idioma, moneda): contenido/SEO
    localizado (PPL) + variantes + precio con impuestos del país en la moneda dada + reglas. LECTURA.

    `iva_pct`/`variantes_pre` son valores PRECOMPUTADOS opcionales (optimización N+1 de `catalogo`);
    si no se aportan se calculan como siempre → el resultado es idéntico para llamadas externas."""
    emp = _emp(id_empresa)
    prep = None
    try:
        from src.services.comercio_digital import publicaciones as ppl
        prep = ppl.preparar_para_canal(id_publicacion, idioma=idioma, region=pais or "", id_empresa=emp)
    except Exception as e:
        logger.debug("preparar_para_canal(%s): %s", id_publicacion, e)
    if not prep:
        return None
    if not moneda:
        try:
            from src.platform import capabilities as cap
            div = cap.divisas()
            moneda = div.divisa_actual() if (div and hasattr(div, "divisa_actual")) else "EUR"
        except Exception:
            moneda = "EUR"
    base_precio = float((prep.get("contenido") or {}).get("precio_escaparate") or 0)
    iva_pct = _iva_pct(pais, emp) if iva_pct is None else iva_pct
    vars_ = variantes(id_publicacion, id_empresa=emp) if variantes_pre is None else variantes_pre
    return {
        "id_publicacion": id_publicacion, "tipo": prep.get("tipo"), "estado": prep.get("estado"),
        "pais": pais, "idioma": idioma, "moneda": moneda,
        "contenido": prep.get("contenido"), "seo": prep.get("seo"), "media": prep.get("media"),
        "precio": _precio(base_precio, 0, moneda, iva_pct),
        "variantes": [{"sku": v["sku"], "atributos": v["atributos"],
                       "precio": _precio(base_precio, v["precio_delta"], moneda, iva_pct)}
                      for v in vars_],
        "reglas": _reglas_comerciales(id_publicacion, pais, emp),
    }


def catalogo(id_empresa=None, *, pais=None, idioma=None, moneda=None, estado="PUBLICADA"):
    """Catálogo comercial global (fichas compuestas) de las publicaciones en `estado`.

    Optimización N+1 (C0.P2): el IVA del país se calcula UNA vez y las variantes se cargan en UNA
    sola consulta (batch), en lugar de por publicación. El resultado es idéntico al no optimizado."""
    emp = _emp(id_empresa)
    fichas = []
    try:
        from src.services.comercio_digital import publicaciones as ppl
        pubs = ppl.listar(emp, estado=estado)
        ids = [p["id_publicacion"] for p in pubs]
        iva = _iva_pct(pais, emp)                              # una sola vez por país
        vmap = variantes_batch(ids, id_empresa=emp)            # una sola consulta de variantes
        for p in pubs:
            f = ficha_comercial(p["id_publicacion"], pais=pais, idioma=idioma, moneda=moneda,
                                id_empresa=emp, iva_pct=iva,
                                variantes_pre=vmap.get(p["id_publicacion"], []))
            if f and f.get("reglas", {}).get("visible", True):
                fichas.append(f)
    except Exception as e:
        logger.error("catalogo: %s", e)
    return fichas


def descriptor() -> dict:
    return {"servicio": "cd_catalogo", "etapa": "B", "fase": FASE, "estado": "implementado",
            "dimensiones": ["variantes", "idiomas", "paises", "monedas", "impuestos", "reglas"],
            "compone_sobre": ["product_publication_layer", "divisas", "fiscalidad", "rules"],
            "es_motor": False, "muta_dominio": False}


__all__ = ["FASE", "agregar_variante", "variantes", "variantes_batch", "eliminar_variante",
           "ficha_comercial", "catalogo", "descriptor"]
