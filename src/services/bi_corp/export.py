"""
FASE I — Exportacion corporativa. Exporta cualquier dataset (lista de dicts) a JSON / CSV /
Excel (openpyxl si esta) / PDF (reportlab si esta). Formatos "Power BI / Looker friendly" = JSON/CSV
plano (filas homogeneas). API JSON via dict serializable. Degradable.
"""

import csv
import datetime as _dt
import io
import json
import logging
import os

logger = logging.getLogger("bi_corp.export")


def _dir():
    base = os.path.join("documentos", "bi")
    try:
        from src.utils.recursos import ruta_datos
        base = ruta_datos("bi")
    except Exception:
        pass
    os.makedirs(base, exist_ok=True)
    return base


def _cols(filas):
    cols = []
    for f in filas:
        for k in f:
            if k not in cols:
                cols.append(k)
    return cols


def a_json(filas) -> str:
    """JSON plano (API / Power BI / Looker friendly)."""
    return json.dumps(filas, ensure_ascii=False, default=str, indent=2)


def a_csv(filas) -> str:
    if not filas:
        return ""
    buf = io.StringIO()
    cols = _cols(filas)
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for f in filas:
        w.writerow(f)
    return buf.getvalue()


def exportar(filas, formato="json", *, nombre="bi_export") -> dict:
    """Exporta a fichero (json/csv/excel/pdf). Devuelve {ok, ruta|contenido, formato}."""
    ts = _dt.datetime.now().strftime("%Y%m%d%H%M%S")
    formato = (formato or "json").lower()
    if formato in ("json", "powerbi", "looker", "api"):
        contenido = a_json(filas)
        ruta = os.path.join(_dir(), f"{nombre}_{ts}.json")
        with open(ruta, "w", encoding="utf-8") as fh:
            fh.write(contenido)
        return {"ok": True, "ruta": ruta, "formato": "json", "contenido": contenido}
    if formato == "csv":
        contenido = a_csv(filas)
        ruta = os.path.join(_dir(), f"{nombre}_{ts}.csv")
        with open(ruta, "w", encoding="utf-8", newline="") as fh:
            fh.write(contenido)
        return {"ok": True, "ruta": ruta, "formato": "csv", "contenido": contenido}
    if formato in ("excel", "xlsx"):
        try:
            from openpyxl import Workbook
            wb = Workbook(); ws = wb.active; ws.title = "BI"
            cols = _cols(filas)
            ws.append(cols)
            for f in filas:
                ws.append([f.get(c) for c in cols])
            ruta = os.path.join(_dir(), f"{nombre}_{ts}.xlsx")
            wb.save(ruta)
            return {"ok": True, "ruta": ruta, "formato": "xlsx"}
        except Exception as e:
            logger.warning("excel no disponible (%s); degrada a csv", e)
            return exportar(filas, "csv", nombre=nombre)
    if formato == "pdf":
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
            ruta = os.path.join(_dir(), f"{nombre}_{ts}.pdf")
            c = canvas.Canvas(ruta, pagesize=A4); y = 800
            c.setFont("Helvetica-Bold", 12); c.drawString(40, y, f"BI Corporativo — {nombre}"); y -= 24
            c.setFont("Helvetica", 8)
            cols = _cols(filas)
            for f in filas[:120]:
                linea = " | ".join(f"{c2}={f.get(c2)}" for c2 in cols[:6])
                c.drawString(40, y, linea[:110]); y -= 12
                if y < 50:
                    c.showPage(); y = 800; c.setFont("Helvetica", 8)
            c.save()
            return {"ok": True, "ruta": ruta, "formato": "pdf"}
        except Exception as e:
            logger.warning("pdf no disponible (%s); degrada a json", e)
            return exportar(filas, "json", nombre=nombre)
    return {"ok": False, "error": "formato no soportado"}
