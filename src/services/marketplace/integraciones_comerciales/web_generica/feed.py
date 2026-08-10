"""
Conector Web tradicional · FEED de catálogo (Modo A). Genera LOCALMENTE (sin red, SIN COSTE) un feed del
catálogo de la empresa (JSON/CSV/XML) que una web tradicional SIN API puede consumir (importar por URL/FTP).

REUTILIZA el PIM existente (`db.catalogo.articulos_para_catalogo`: código/nombre/precio/stock). Multiempresa
(aislado por `id_empresa`). Escribe en ``documentos/integraciones/web_feed/<id_empresa>/``. NO crea tablas ni
motores nuevos.
"""

import csv
import json
import logging
import os
import time
from xml.sax.saxutils import escape

logger = logging.getLogger("marketplace.integraciones_comerciales.web_generica.feed")

FORMATOS = ("json", "csv", "xml")


def _dir_salida(id_empresa):
    base = os.path.join("documentos", "integraciones", "web_feed",
                        str(id_empresa if id_empresa is not None else "default"))
    os.makedirs(base, exist_ok=True)
    return base


def productos(id_empresa=None, solo_visibles=False) -> list:
    """Productos del catálogo de la empresa para el feed (no bloqueados). Reutiliza el PIM."""
    from src.db import catalogo as C
    filas = C.articulos_para_catalogo(id_empresa=id_empresa) or []
    out = []
    for a in filas:
        if a.get("bloqueado"):
            continue
        if solo_visibles and not a.get("visible_web"):
            continue
        out.append({"codigo": a.get("codigo"), "nombre": a.get("nombre"),
                    "precio": float(a.get("precio") or 0), "stock": int(a.get("stock") or 0),
                    "visible_web": bool(a.get("visible_web"))})
    return out


def generar_feed(id_empresa=None, formato="json", solo_visibles=False, usuario=None) -> dict:
    """Genera el fichero de feed y devuelve {ok, ruta, formato, productos}. Operación LOCAL (sin red)."""
    formato = (formato or "json").lower()
    if formato not in FORMATOS:
        return {"ok": False, "error": f"formato no soportado: {formato}"}
    prods = productos(id_empresa, solo_visibles=solo_visibles)
    ts = time.strftime("%Y%m%d_%H%M%S")
    ruta = os.path.join(_dir_salida(id_empresa), f"catalogo_{ts}.{formato}")
    try:
        if formato == "json":
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump({"empresa": id_empresa, "generado": ts, "productos": prods}, f,
                          ensure_ascii=False, indent=2)
        elif formato == "csv":
            with open(ruta, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(["codigo", "nombre", "precio", "stock"])
                for p in prods:
                    w.writerow([p["codigo"], p["nombre"], p["precio"], p["stock"]])
        else:  # xml
            lineas = ['<?xml version="1.0" encoding="UTF-8"?>', "<catalogo>"]
            for p in prods:
                lineas.append(
                    f'  <producto codigo="{escape(str(p["codigo"] or ""))}">'
                    f'<nombre>{escape(str(p["nombre"] or ""))}</nombre>'
                    f'<precio>{p["precio"]}</precio><stock>{p["stock"]}</stock></producto>')
            lineas.append("</catalogo>")
            with open(ruta, "w", encoding="utf-8") as f:
                f.write("\n".join(lineas))
    except Exception as e:
        logger.error("generar feed: %s", e)
        return {"ok": False, "error": str(e)}
    logger.info("feed generado (%s productos) → %s", len(prods), ruta)
    return {"ok": True, "ruta": ruta, "formato": formato, "productos": len(prods)}
