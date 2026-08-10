"""Visualizer (Fase III · B6) — formatea la reconstrucción para su presentación (texto/estructura)."""


def a_texto(reconstruccion) -> str:
    lineas = []
    r = reconstruccion.get("resumen", {})
    lineas.append(f"Reconstrucción: {r.get('total', 0)} sucesos "
                  f"({r.get('inicio')} → {r.get('fin')})")
    for it in reconstruccion.get("cronologia", []):
        lineas.append(f"  [{it['fecha']}] ({it['fuente']}/{it['tipo']}) {it['detalle']}"
                      + (f"  · {it['actor']}" if it.get("actor") else ""))
    return "\n".join(lineas)
