"""
Evaluacion de riesgos empresariales (SUBFASE 6). Puntuacion 0..1 y nivel bajo/medio/alto a
partir de la informacion existente. Solo lectura.
"""

from src.services.ia import adaptadores as A
from src.services.ia.modelos import Riesgo


def _nivel(n, medio, alto) -> str:
    if n >= alto:
        return "alto"
    if n >= medio:
        return "medio"
    return "bajo"


def evaluar(id_empresa=None) -> list:
    r = []
    bajo = A.articulos_bajo_umbral(id_empresa)
    if bajo:
        r.append(Riesgo("rotura_stock", _nivel(len(bajo), 5, 15), min(len(bajo) / 20.0, 1.0),
                        f"{len(bajo)} articulos por debajo del umbral", "inventario"))
    exc = A.articulos_exceso(id_empresa)
    if exc:
        r.append(Riesgo("exceso_stock", _nivel(len(exc), 5, 15), min(len(exc) / 20.0, 1.0),
                        f"{len(exc)} articulos con sobre-stock", "inventario"))
    fp = A.facturas_pendientes(id_empresa)
    if fp:
        r.append(Riesgo("impago", _nivel(len(fp), 3, 10), min(len(fp) / 15.0, 1.0),
                        f"{len(fp)} facturas pendientes de cobro", "tesoreria"))
    sync = A.sincronizacion(id_empresa)
    err = int(sync.get("global", {}).get("errores") or 0)
    if err:
        r.append(Riesgo("sincronizacion", _nivel(err, 1, 5), min(err / 10.0, 1.0),
                        f"{err} sincronizaciones con error", "infraestructura"))
    return r
