"""
Deteccion de anomalias (SUBFASE 4). Umbrales CONFIGURABLES, sin alarmas agresivas ni falsos
positivos. Solo lectura (analiza el historico existente).
"""

import logging
import statistics

from src.services.ia import adaptadores as A
from src.services.ia import configuracion as C
from src.services.ia.modelos import Anomalia

logger = logging.getLogger("ia.anomalias")


def detectar(id_empresa=None) -> list:
    if not C.activo("anomalias", id_empresa):
        return []
    an = []
    # ── Desviacion de ventas vs media historica ──
    try:
        v = A.ventas_por_dia(id_empresa, dias=30)
        totales = [float(x.get("total") or 0) for x in v]
        if len(totales) >= 7:
            hoy = totales[-1]
            media = statistics.mean(totales[:-1])
            umb = float(C.umbral("desviacion_ventas_pct", id_empresa) or 40)
            if media > 0 and abs(hoy - media) / media * 100 >= umb:
                alto = hoy > media
                an.append(Anomalia("ventas",
                                   f"Ventas del ultimo dia {'muy altas' if alto else 'muy bajas'} "
                                   f"respecto a la media ({hoy:.0f} vs {media:.0f})",
                                   "media" if alto else "alta", round(hoy, 2), round(media, 2)))
    except Exception as e:
        logger.debug("anomalia ventas: %s", e)
    # ── Roturas de stock ──
    bajo = A.articulos_bajo_umbral(id_empresa)
    if bajo:
        an.append(Anomalia("rotura_stock", f"{len(bajo)} articulos por debajo del umbral con stock en almacen",
                           "alta" if len(bajo) > 10 else "media", len(bajo)))
    # ── Errores de sincronizacion ──
    ses = A.sync_sesiones(id_empresa, 100)
    err = [s for s in ses if str(s.get("estado")).upper() == "ERROR"]
    if len(err) >= int(C.umbral("sync_errores", id_empresa) or 1):
        an.append(Anomalia("sincronizacion", f"{len(err)} sincronizaciones con error", "media", len(err)))
    # ── Terminales desconectadas ──
    sync = A.sincronizacion(id_empresa)
    off = [t for t in sync.get("terminales", []) if str(t.get("estado")).upper() == "OFFLINE"]
    if off:
        an.append(Anomalia("terminal_offline", f"{len(off)} terminales desconectadas", "media", len(off)))
    # ── Merma elevada ──
    try:
        m = A.mermas_recientes(id_empresa, dias=30)
        if m:
            tot = sum(int(x.get("cant") or 0) for x in m)
            if tot > 0 and len(m) >= 5:
                an.append(Anomalia("merma", f"Merma acumulada de {tot} uds en el ultimo mes", "baja", tot))
    except Exception:
        pass
    return an
