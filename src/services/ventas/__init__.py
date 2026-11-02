"""
Resumen de facturación (Fase 8 móvil): hoy / esta semana / este mes, con filtro opcional por sección.
Reutiliza `db.ventas_analitica.serie_por_dia` (mismo motor que el dashboard de escritorio `gui/ventas`)
— no reimplementa ningún criterio de agregación ni el aislamiento de tenant.

"Vaciar datos cada inicio de mes" (requisito original) se consigue SIN caché ni job: los límites de
semana (lunes actual) y mes (día 1 actual) se calculan en vivo desde `date.today()` en cada llamada,
mismo patrón que `services/bi/kpis.py::_rango`.
"""

from datetime import date, timedelta


def _total(desde, hasta, id_empresa, id_tienda, seccion) -> float:
    from src.db import ventas_analitica as va
    filas = va.serie_por_dia(desde, hasta, secc=seccion or None,
                             id_empresa=id_empresa, id_tienda=id_tienda)
    return round(sum(float(f[1] or 0) for f in filas), 2)


def resumen(id_empresa, id_tienda=None, *, seccion=None) -> dict:
    from src.db import ventas_analitica as va
    hoy = date.today()
    inicio_semana = hoy - timedelta(days=hoy.weekday())
    inicio_mes = hoy.replace(day=1)
    return {
        "hoy": _total(hoy, hoy, id_empresa, id_tienda, seccion),
        "semana": _total(inicio_semana, hoy, id_empresa, id_tienda, seccion),
        "mes": _total(inicio_mes, hoy, id_empresa, id_tienda, seccion),
        "seccion": seccion,
        "secciones": va.secciones_disponibles(id_empresa=id_empresa, id_tienda=id_tienda),
        "actualizado": hoy.isoformat(),
    }
