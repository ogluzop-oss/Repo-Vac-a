"""
Deteccion de riesgos (Paquete Enterprise 3, SUBFASE 3.8). Indice de riesgo 0..1 y nivel
bajo/medio/alto para empresa/tienda/producto/factura, basado en MULTIPLES variables (nunca en un
unico evento). Solo lectura.
"""

from src.services.prediccion import adaptadores as A
from src.services.prediccion import configuracion as C


def _nivel(score) -> str:
    return "alto" if score >= 0.66 else ("medio" if score >= 0.33 else "bajo")


def _norm(x, tope) -> float:
    try:
        return min(float(x) / float(tope), 1.0) if tope else 0.0
    except Exception:
        return 0.0


def indice(id_empresa=None) -> list:
    if not C.activo("riesgos", id_empresa):
        return []
    bajo = A.articulos_bajo_umbral(id_empresa)
    exc = A.articulos_exceso(id_empresa)
    fp = A.facturas_pendientes(id_empresa)
    sync = A.sincronizacion(id_empresa)
    err = int(sync.get("global", {}).get("errores") or 0)
    off = len([t for t in sync.get("terminales", []) if str(t.get("estado")).upper() == "OFFLINE"])

    riesgos = []
    # ── Empresa: combinacion ponderada de variables ──
    variables = {"roturas": len(bajo), "sobrestock": len(exc), "impagos": len(fp),
                 "sync_errores": err, "terminales_offline": off}
    score = round(0.30 * _norm(len(bajo), 20) + 0.15 * _norm(len(exc), 20) +
                  0.30 * _norm(len(fp), 15) + 0.15 * _norm(err, 5) + 0.10 * _norm(off, 3), 2)
    riesgos.append({"entidad": "empresa", "entidad_id": str(id_empresa or ""),
                    "nivel": _nivel(score), "score": score, "variables": variables,
                    "descripcion": "Indice global de riesgo empresarial"})
    # ── Productos con mayor riesgo de rotura ──
    for a in sorted(bajo, key=lambda x: x.get("faltan", 0), reverse=True)[:5]:
        s = round(_norm(a.get("faltan", 0), max(a.get("objetivo", 1), 1)), 2)
        riesgos.append({"entidad": "producto", "entidad_id": a["codigo"], "nivel": _nivel(s),
                        "score": s, "variables": {"faltan": a.get("faltan"),
                                                  "stock_tienda": a.get("stock_tienda")},
                        "descripcion": "Riesgo de rotura de stock"})
    # ── Facturas con mayor riesgo de impago ──
    for f in sorted(fp, key=lambda x: float(x.get("total") or 0), reverse=True)[:5]:
        riesgos.append({"entidad": "factura",
                        "entidad_id": str(f.get("id") or f.get("numero") or ""), "nivel": "medio",
                        "score": 0.6, "variables": {"total": f.get("total"), "estado": f.get("estado")},
                        "descripcion": "Riesgo de impago"})
    return riesgos
