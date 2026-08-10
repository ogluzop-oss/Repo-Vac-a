"""
Sistema fiscal de Smart Manager AI: IVA por PAÍS (independiente de la divisa).

El país fiscal de la empresa (CONFIGURACIÓN → DATOS DE EMPRESA) determina
AUTOMÁTICAMENTE el tipo de IVA usado en toda la documentación (tickets,
facturas, devoluciones, informes). NO modifica precios (los PVP ya incluyen IVA)
ni la gestión de divisas (que se configura aparte, en GESTIÓN CAJA).

Fuente única y editable: ``assets/fiscalidad/iva_paises.json`` (país → divisa,
IVA principal, fecha de actualización). Para actualizar un tipo por un cambio
legal, basta editar el JSON; no hay valores fiscales repartidos por el código.

Arquitectura preparada para futuras ampliaciones (varios tipos por país,
asignación por artículo/categoría) sin rediseñar el sistema. Multiempresa:
el país fiscal depende de ``id_empresa`` (nunca global).
"""

import json
import logging
import os

logger = logging.getLogger("fiscalidad")

_THIS = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_THIS))
_DEFECTO_PAIS = "ES"
_IVA_DEFECTO = 21.0

_registro_cache = None


def _ruta_registro():
    try:
        from src.utils import recursos
        return recursos.ruta_recurso("assets", "fiscalidad", "iva_paises.json")
    except Exception:
        return os.path.join(_ROOT, "assets", "fiscalidad", "iva_paises.json")


def _registro() -> dict:
    global _registro_cache
    if _registro_cache is not None:
        return _registro_cache
    data = {}
    try:
        with open(_ruta_registro(), encoding="utf-8") as f:
            data = (json.load(f) or {}).get("paises", {})
    except Exception as e:
        logger.error("No se pudo leer el registro fiscal de IVA: %s", e)
    _registro_cache = data
    return data


def recargar():
    """Olvida la caché del registro (releer la próxima vez)."""
    global _registro_cache
    _registro_cache = None


def info_pais(code=None) -> dict:
    """Metadatos fiscales del país: {code, nombre, divisa, iva, actualizado}."""
    code = (code or _DEFECTO_PAIS).upper()
    reg = _registro()
    d = reg.get(code) or reg.get(_DEFECTO_PAIS) or {}
    return {
        "code": code if code in reg else _DEFECTO_PAIS,
        "nombre": d.get("nombre", code),
        "divisa": d.get("divisa", "EUR"),
        "iva": float(d.get("iva", _IVA_DEFECTO)),
        "actualizado": d.get("actualizado", ""),
    }


def iva_de_pais(code=None) -> float:
    """Tipo de IVA principal (%) del país indicado."""
    return info_pais(code)["iva"]


def nombre_pais(code=None) -> str:
    return info_pais(code)["nombre"]


def paises_disponibles() -> list[dict]:
    """Países compatibles con las divisas que soporta la app, ordenados por
    nombre. Cada item: {code, nombre, divisa, iva}. Si no se puede consultar la
    lista de divisas, se devuelven todos los países del registro."""
    try:
        from src.utils import divisas
        soportadas = set(divisas.monedas_soportadas())
    except Exception:
        soportadas = None
    out = []
    for code, d in _registro().items():
        if soportadas is None or d.get("divisa") in soportadas:
            out.append({"code": code, "nombre": d.get("nombre", code),
                        "divisa": d.get("divisa", ""), "iva": float(d.get("iva", _IVA_DEFECTO))})
    out.sort(key=lambda x: x["nombre"])
    return out


def pais_fiscal_empresa(id_empresa=None) -> str:
    """Código del país fiscal de la empresa (por defecto ES)."""
    try:
        from src.db.empresa import obtener_empresa
        emp = obtener_empresa(id_empresa) or {}
        return (emp.get("pais_fiscal") or _DEFECTO_PAIS).upper()
    except Exception:
        return _DEFECTO_PAIS


def iva_empresa(id_empresa=None) -> float:
    """Tipo de IVA (%) que corresponde a la empresa según su país fiscal."""
    return iva_de_pais(pais_fiscal_empresa(id_empresa))


# ── Desglose fiscal: FUENTE ÚNICA para TODOS los documentos ───────────────────
# Los precios son PVP (IVA incluido); estas funciones solo descomponen, nunca
# alteran el importe final. Cualquier generador (ticket, factura, presupuesto,
# devolución, albarán valorado, informe…) debe usar ESTAS funciones y no
# reimplementar la aritmética del IVA.

def desglose_iva(total_pvp, id_empresa=None, tipo=None) -> dict:
    """Descompone un importe IVA-incluido en {tipo, base, cuota, total}.
    `tipo` (porcentaje) opcional; si no, usa el IVA de la empresa."""
    r = float(tipo) if tipo is not None else iva_empresa(id_empresa)
    total = round(float(total_pvp or 0), 2)
    base = round(total / (1 + r / 100), 2) if r else total
    return {"tipo": r, "base": base, "cuota": round(total - base, 2), "total": total}


# ── Motor fiscal AVANZADO (FASE 3.2): recargo equiv. · ISP · intracom · IRPF ──
# Recargo de equivalencia (España) por tipo de IVA. Fuente única; ampliable.
_RECARGO_POR_IVA = {21.0: 5.2, 10.0: 1.4, 4.0: 0.5, 0.0: 0.0, 5.0: 0.62, 2.0: 0.26}

# Leyendas legales por régimen (se incrustan en la factura).
LEYENDA_ISP = ("Operación con inversión del sujeto pasivo (art. 84.Uno.2º LIVA). "
               "El IVA será liquidado por el destinatario.")
LEYENDA_INTRACOM = ("Entrega intracomunitaria exenta (art. 25 LIVA). "
                    "Operación exenta de IVA.")
LEYENDA_EXENTO = "Operación exenta de IVA."


def recargo_de(tipo_iva) -> float:
    """% de recargo de equivalencia que corresponde a un tipo de IVA."""
    try:
        return float(_RECARGO_POR_IVA.get(round(float(tipo_iva), 2), 0.0))
    except Exception:
        return 0.0


def calcular_fiscalidad(lineas, perfil=None, id_empresa=None, tipo_general=None) -> dict:
    """MOTOR ÚNICO de fiscalidad de una factura a partir de sus líneas y del PERFIL
    fiscal del cliente (clientes.perfil_fiscal). Determina automáticamente:

    - IVA por tipo (PVP IVA-incluido), como el desglose actual.
    - Recargo de equivalencia (si el perfil lo aplica): cuota adicional por tipo.
    - ISP / intracomunitaria / exento: IVA repercutido = 0 (el subtotal es la base) + leyenda.
    - Retención de IRPF (si aplica): importe = base × % (resta del total).

    Devuelve un dict completo. Con perfil GENERAL (o None) el resultado de base/cuota/total es
    IDÉNTICO al de `desglose_iva_lineas` (cero impacto en facturas sin régimen especial)."""
    p = perfil or {}
    exento = bool(p.get("exento") or p.get("isp") or p.get("intracomunitario"))
    aplica_recargo = bool(p.get("recargo_equivalencia"))
    base_emp = float(tipo_general) if tipo_general is not None else iva_empresa(id_empresa)

    por_tipo: dict = {}
    for ln in lineas or []:
        sub = round(float(ln.get("subtotal", 0) or 0), 2)
        r = float(ln.get("iva", base_emp) if ln.get("iva") is not None else base_emp)
        if exento:
            # Sin IVA repercutido: el subtotal ES la base imponible (precio neto).
            acc = por_tipo.setdefault(0.0, {"base": 0.0, "cuota": 0.0, "total": 0.0,
                                            "tipo_recargo": 0.0, "cuota_recargo": 0.0})
            acc["base"] += sub; acc["total"] += sub
        else:
            d = desglose_iva(sub, tipo=r)
            acc = por_tipo.setdefault(r, {"base": 0.0, "cuota": 0.0, "total": 0.0,
                                          "tipo_recargo": 0.0, "cuota_recargo": 0.0})
            acc["base"] += d["base"]; acc["cuota"] += d["cuota"]; acc["total"] += d["total"]
            if aplica_recargo:
                tr = recargo_de(r)
                acc["tipo_recargo"] = tr
                acc["cuota_recargo"] += round(d["base"] * tr / 100, 2)
    for r, acc in por_tipo.items():
        for k in ("base", "cuota", "total", "cuota_recargo"):
            acc[k] = round(acc[k], 2)

    base = round(sum(a["base"] for a in por_tipo.values()), 2)
    cuota_iva = round(sum(a["cuota"] for a in por_tipo.values()), 2)
    cuota_recargo = round(sum(a["cuota_recargo"] for a in por_tipo.values()), 2)
    # Retención de IRPF sobre la base imponible (resta del total).
    pct_ret = float(p.get("porcentaje_retencion") or 0) if p.get("retencion_irpf") else 0.0
    retencion = round(base * pct_ret / 100, 2)
    total = round(base + cuota_iva + cuota_recargo - retencion, 2)

    leyendas = []
    if p.get("isp"):
        leyendas.append(LEYENDA_ISP)
    elif p.get("intracomunitario"):
        leyendas.append(LEYENDA_INTRACOM)
    elif p.get("exento"):
        leyendas.append(LEYENDA_EXENTO)

    return {
        "por_tipo": por_tipo, "base": base, "cuota": cuota_iva, "cuota_iva": cuota_iva,
        "cuota_recargo": cuota_recargo, "retencion_pct": pct_ret, "retencion": retencion,
        "total": total, "regimen": p.get("regimen") or "general",
        "exento": exento, "isp": bool(p.get("isp")),
        "intracomunitario": bool(p.get("intracomunitario")),
        "recargo_equivalencia": aplica_recargo,
        "leyenda": "  ".join(leyendas) if leyendas else None,
    }


def desglose_iva_lineas(lineas, id_empresa=None, tipo_general=None) -> dict:
    """Desglose por tipo de IVA de una lista de líneas (cada una con 'subtotal'
    PVP y, opcionalmente, 'iva'; si no, se usa `tipo_general` o el IVA de la
    empresa). Devuelve {'por_tipo': {r: {base,cuota,total}}, 'base','cuota','total'}."""
    base_emp = float(tipo_general) if tipo_general is not None else iva_empresa(id_empresa)
    por_tipo: dict = {}
    for ln in lineas or []:
        sub = round(float(ln.get("subtotal", 0) or 0), 2)
        r = float(ln.get("iva", base_emp) if ln.get("iva") is not None else base_emp)
        d = desglose_iva(sub, tipo=r)
        acc = por_tipo.setdefault(r, {"base": 0.0, "cuota": 0.0, "total": 0.0})
        acc["base"] += d["base"]; acc["cuota"] += d["cuota"]; acc["total"] += d["total"]
    for r, acc in por_tipo.items():
        acc["base"] = round(acc["base"], 2)
        acc["cuota"] = round(acc["cuota"], 2)
        acc["total"] = round(acc["total"], 2)
    return {
        "por_tipo": por_tipo,
        "base": round(sum(a["base"] for a in por_tipo.values()), 2),
        "cuota": round(sum(a["cuota"] for a in por_tipo.values()), 2),
        "total": round(sum(a["total"] for a in por_tipo.values()), 2),
    }
