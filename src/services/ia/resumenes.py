"""
Resumenes empresariales e inteligentes (SUBFASE 2/3). Se generan EXCLUSIVAMENTE desde los
eventos existentes (Centro de Actividad) + estado de sincronizacion. No crea tablas.
"""

from src.services.ia import adaptadores as A
from src.services.ia import configuracion as C

_DIAS = {"dia": 1, "semana": 7, "mes": 30, "anio": 365}


def resumen(id_empresa=None, *, periodo="dia", usuario=None, perfil=None) -> dict:
    dias = _DIAS.get(periodo, 1)
    por_tipo = A.resumen_eventos(id_empresa, dias=dias, usuario=usuario, perfil=perfil)
    total = sum(int(x.get("total") or 0) for x in por_tipo)
    pend = sum(int(x.get("pendientes") or 0) for x in por_tipo)
    destacados = sorted(por_tipo, key=lambda x: x.get("total", 0), reverse=True)[:5]
    sync = A.sincronizacion(id_empresa).get("global", {})
    return {
        "periodo": periodo, "total_eventos": total, "pendientes": pend,
        "por_tipo": por_tipo, "destacados": destacados, "sincronizacion": sync,
        "puntos_atencion": [p.to_dict() for p in puntos_atencion(id_empresa, usuario=usuario, perfil=perfil)],
        "texto": _narrativa(periodo, total, pend, destacados, sync),
    }


def _narrativa(periodo, total, pend, destacados, sync) -> str:
    et = {"dia": "hoy", "semana": "esta semana", "mes": "este mes", "anio": "este año"}.get(periodo, periodo)
    if total == 0:
        return f"Sin actividad relevante {et}."
    top = ", ".join(f"{d.get('tipo_legible')} ({d.get('total')})" for d in destacados[:3])
    frase = f"{et.capitalize()} se han registrado {total} eventos. Lo mas destacado: {top}."
    if pend:
        frase += f" Quedan {pend} cambios pendientes de aplicar."
    err = int(sync.get("errores") or 0)
    if err:
        frase += f" Atencion: {err} sincronizaciones con error."
    return frase


def puntos_atencion(id_empresa=None, *, usuario=None, perfil=None) -> list:
    """Resumen INTELIGENTE (3): que requiere atencion / esta pendiente / fallo."""
    from src.services.ia.modelos import Insight
    ins = []
    bajo = A.articulos_bajo_umbral(id_empresa)
    if bajo:
        ins.append(Insight("stock", f"{len(bajo)} articulos por debajo del umbral de reposicion",
                           "Requieren reposicion desde almacen.", "aviso", {"n": len(bajo)}))
    fp = A.facturas_pendientes(id_empresa)
    if fp:
        ins.append(Insight("facturacion", f"{len(fp)} facturas pendientes de cobro", "", "aviso",
                           {"n": len(fp)}))
    cv = A.contratos_por_vencer(id_empresa)
    if cv:
        ins.append(Insight("rrhh", f"{len(cv)} contratos proximos a vencer", "", "aviso", {"n": len(cv)}))
    ses = A.sync_sesiones(id_empresa, 100)
    err = [s for s in ses if str(s.get("estado")).upper() == "ERROR"]
    if err:
        ins.append(Insight("sincronizacion", f"{len(err)} sincronizaciones fallidas",
                           "Revisar terminales / reintentar.", "critico", {"n": len(err)}))
    lic = A.licencia(id_empresa)
    if lic and str(lic.get("estado")) not in ("activa", "prueba", None, ""):
        ins.append(Insight("suscripcion", f"Licencia en estado '{lic.get('estado')}'",
                           "Revisar la suscripcion.", "critico", lic))
    return ins
