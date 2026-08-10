"""
Marketplace · Catálogo (Fase IV · Bloque 2). Agrega los plugins disponibles de todos los
repositorios de la empresa, marca cuáles están instalados y expone búsqueda + categorías + detalle.
Reutiliza `repositorios` y el estado instalado del Plugin SDK. Multiempresa.
"""

from __future__ import annotations

from src.services.marketplace import firmas, repositorios

# Marketplaces de PRIMER NIVEL del App Store (misma infraestructura de plugins, distinta categoría — N7):
# Extensiones · IA · Conectores · Plantillas. Se muestran siempre como secciones aunque estén vacías.
CATEGORIAS_ESTANDAR = ("extension", "ia", "conector", "plantilla", "general")


def _disponibles(id_empresa) -> dict:
    """clave → manifest (con _ruta y _repo) del repo de MAYOR prioridad que lo ofrezca."""
    catalogo = {}
    for repo in repositorios.listar_repositorios(id_empresa):
        for m in repositorios.plugins_de(repo):
            clave = m.get("clave")
            if clave and clave not in catalogo:   # ya ordenado por prioridad → gana el primero
                m = dict(m); m["_repo"] = repo.get("nombre"); m["_repo_tipo"] = repo.get("tipo")
                catalogo[clave] = m
    return catalogo


def catalogo_manifests(id_empresa=None) -> dict:
    """clave → manifest disponible (para dependencias/validación)."""
    return _disponibles(id_empresa)


def catalogo(id_empresa=None, *, categoria=None, texto="") -> list:
    """Lista de items del marketplace (dict resumido), filtrada por categoría/texto."""
    disponibles = _disponibles(id_empresa)
    instalados = _claves_instaladas(id_empresa)
    items = []
    t = (texto or "").strip().lower()
    for clave, m in disponibles.items():
        if categoria and (m.get("categoria") or "").lower() != categoria.lower():
            continue
        if t and t not in clave.lower() and t not in (m.get("nombre") or "").lower():
            continue
        items.append(_resumen(m, clave in instalados))
    items.sort(key=lambda x: (x.get("nombre") or x.get("clave") or "").lower())
    return items


def _resumen(m, instalado) -> dict:
    estado_firma = firmas.verificar(m)
    return {"clave": m.get("clave"), "nombre": m.get("nombre"), "version": m.get("version"),
            "categoria": m.get("categoria") or "general", "autor": m.get("autor"),
            "descripcion": m.get("descripcion"), "icono": m.get("icono"),
            "firma": estado_firma, "firmado": firmas.es_valida(estado_firma),
            "licencia": m.get("licencia"), "repo": m.get("_repo"),
            "instalado": instalado,
            "dependencias": [d.get("clave") if isinstance(d, dict) else d
                             for d in (m.get("dependencias") or [])]}


def _claves_instaladas(id_empresa) -> set:
    try:
        from src import sdk
        return {p.get("clave") for p in sdk.listar_instalados(id_empresa)}
    except Exception:
        return set()


def categorias(id_empresa=None) -> list:
    cats = {(m.get("categoria") or "general") for m in _disponibles(id_empresa).values()}
    cats |= set(CATEGORIAS_ESTANDAR)          # las 4 secciones estándar existen siempre
    return sorted(cats)


def catalogo_ia(id_empresa=None, *, texto="") -> list:
    """Marketplace de IA (extensiones/modelos de categoría 'ia')."""
    return catalogo(id_empresa, categoria="ia", texto=texto)


def catalogo_plantillas(id_empresa=None, *, texto="") -> list:
    """Marketplace de plantillas (documentos/informes de categoría 'plantilla')."""
    return catalogo(id_empresa, categoria="plantilla", texto=texto)


def catalogo_conectores(id_empresa=None, *, texto="") -> list:
    """Marketplace de conectores (integraciones de categoría 'conector')."""
    return catalogo(id_empresa, categoria="conector", texto=texto)


def detalle(clave, id_empresa=None) -> dict | None:
    m = _disponibles(id_empresa).get(clave)
    if not m:
        return None
    d = _resumen(m, clave in _claves_instaladas(id_empresa))
    d["changelog"] = m.get("changelog")
    d["version_minima"] = m.get("version_minima")
    d["version_maxima"] = m.get("version_maxima")
    d["hash"] = firmas.hash_manifest(m)
    return d


__all__ = ["catalogo", "catalogo_manifests", "categorias", "detalle", "CATEGORIAS_ESTANDAR",
           "catalogo_ia", "catalogo_plantillas", "catalogo_conectores"]
