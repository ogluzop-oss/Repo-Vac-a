"""
Marketplace · Resolución de dependencias (Fase IV · Bloque 2). Calcula el orden de instalación,
detecta ciclos, conflictos de versión y plugins incompatibles. Reutiliza el versionado SemVer de
la plataforma. Sin BD: opera sobre el catálogo (dict clave→manifest).
"""

from __future__ import annotations

from src.platform.versioning import Version


def _deps(manifest) -> list:
    """Normaliza dependencias: admite ["clave"] o [{"clave","version_minima","version_maxima"}]."""
    out = []
    for d in (manifest or {}).get("dependencias", []) or []:
        if isinstance(d, str):
            out.append({"clave": d, "version_minima": None, "version_maxima": None})
        elif isinstance(d, dict) and d.get("clave"):
            out.append({"clave": d["clave"], "version_minima": d.get("version_minima"),
                        "version_maxima": d.get("version_maxima")})
    return out


def conflictos(clave, catalogo: dict) -> list:
    """Lista de conflictos de dependencia para `clave` según el `catalogo` (clave→manifest)."""
    problemas = []
    raiz = catalogo.get(clave)
    if not raiz:
        return [{"tipo": "ausente", "clave": clave}]
    for dep in _deps(raiz):
        m = catalogo.get(dep["clave"])
        if not m:
            problemas.append({"tipo": "dependencia_ausente", "clave": dep["clave"]})
            continue
        v = Version.parse(m.get("version"))
        if not v.en_rango(dep.get("version_minima"), dep.get("version_maxima")):
            problemas.append({"tipo": "version_incompatible", "clave": dep["clave"],
                              "disponible": str(v), "requiere_min": dep.get("version_minima"),
                              "requiere_max": dep.get("version_maxima")})
    # Incompatibilidades declaradas explícitamente.
    for inc in raiz.get("incompatibles", []) or []:
        if inc in catalogo:
            problemas.append({"tipo": "incompatible", "clave": inc})
    return problemas


def orden_instalacion(clave, catalogo: dict) -> tuple:
    """Orden topológico (dependencias primero) para instalar `clave`. (orden[], problemas[]).
    Detecta ciclos. Devuelve orden vacío si hay problemas bloqueantes."""
    problemas = []
    orden = []
    visitando = set()
    visitado = set()

    def visita(k, cadena):
        if k in visitado:
            return
        if k in visitando:
            problemas.append({"tipo": "ciclo", "clave": k, "cadena": cadena + [k]})
            return
        m = catalogo.get(k)
        if not m:
            problemas.append({"tipo": "dependencia_ausente", "clave": k})
            return
        visitando.add(k)
        for dep in _deps(m):
            dm = catalogo.get(dep["clave"])
            if dm and not Version.parse(dm.get("version")).en_rango(
                    dep.get("version_minima"), dep.get("version_maxima")):
                problemas.append({"tipo": "version_incompatible", "clave": dep["clave"]})
            visita(dep["clave"], cadena + [k])
        visitando.discard(k)
        visitado.add(k)
        orden.append(k)

    visita(clave, [])
    bloqueante = any(p["tipo"] in ("ciclo", "dependencia_ausente", "version_incompatible")
                     for p in problemas)
    return ([] if bloqueante else orden), problemas


def resoluble(clave, catalogo: dict) -> bool:
    orden, problemas = orden_instalacion(clave, catalogo)
    return bool(orden) and not problemas


__all__ = ["conflictos", "orden_instalacion", "resoluble"]
