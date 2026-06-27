"""
Exportación de declaraciones AEAT (FASE AEAT-1).

Serializa una declaración (cabecera + casillas) a JSON y CSV. Arquitectura preparada para
añadir en el futuro la exportación al fichero/presentación telemática AEAT (no incluida aquí).
"""

import csv
import io
import json


def a_json(declaracion: dict) -> str:
    """JSON con cabecera y casillas (importes como float)."""
    cab = {k: declaracion.get(k) for k in
           ("id", "modelo", "ejercicio", "periodo", "estado", "resultado", "hash",
            "fecha_generacion", "fecha_presentacion")}
    cab["casillas"] = [{"casilla": c["casilla"], "descripcion": c.get("descripcion"),
                        "importe": round(float(c["importe"]), 2)}
                       for c in declaracion.get("casillas", [])]
    return json.dumps(cab, ensure_ascii=False, default=str, indent=2)


def a_csv(declaracion: dict) -> str:
    """CSV de casillas: casilla;descripcion;importe."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["casilla", "descripcion", "importe"])
    for c in declaracion.get("casillas", []):
        w.writerow([c["casilla"], c.get("descripcion") or "", f"{float(c['importe']):.2f}"])
    return buf.getvalue()
