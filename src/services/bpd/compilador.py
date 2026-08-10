"""
BPD · Compilador (Fase V · Bloque 4). Traduce un DISEÑO visual (grafo de bloques) a una definición
ejecutable del WORKFLOW ENGINE existente. NO ejecuta ni crea un motor nuevo: reutiliza
`src.services.workflow`. La ejecución de un proceso publicado se delega íntegramente en el Workflow
Engine (`iniciar_proceso`). Multiempresa.
"""

from __future__ import annotations

from src.services.bpd import bloques, diseno


def compilar(definicion) -> dict:
    """Convierte {nodos, aristas} en una definición de workflow (pasos ordenados por las aristas)."""
    nodos = {n["id"]: n for n in (definicion or {}).get("nodos", []) if n.get("id")}
    aristas = (definicion or {}).get("aristas", [])
    # Orden por recorrido desde 'inicio' siguiendo aristas (grafo dirigido simple).
    siguientes = {}
    for a in aristas:
        siguientes.setdefault(a.get("desde"), []).append(a.get("hasta"))
    inicio = next((nid for nid, n in nodos.items() if n.get("tipo") == "inicio"), None)
    pasos, visto = [], set()
    pila = [inicio] if inicio else []
    while pila:
        nid = pila.pop(0)
        if not nid or nid in visto or nid not in nodos:
            continue
        visto.add(nid)
        n = nodos[nid]
        if n.get("tipo") not in ("inicio", "fin"):
            pasos.append({"id": nid, "tipo": n.get("tipo"),
                          "destino": bloques.destino(n.get("tipo")),
                          "config": n.get("config", {})})
        pila.extend(siguientes.get(nid, []))
    return {"pasos": pasos, "motor": "workflow"}


def compilar_proceso(id_proceso, version=None, *, id_empresa=None) -> dict:
    v = diseno.obtener_version(id_proceso, version)
    if not v:
        return {"ok": False, "errores": ["versión no encontrada"]}
    ok, errores = diseno.validar_definicion(diseno.definicion_de(v))
    if not ok:
        return {"ok": False, "errores": errores}
    return {"ok": True, **compilar(diseno.definicion_de(v))}


def ejecutar(id_proceso, entidad, entidad_id, *, version=None, id_empresa=None, actor=None,
             contexto=None) -> dict:
    """Ejecuta un proceso publicado DELEGANDO en el Workflow Engine existente (no motor nuevo)."""
    comp = compilar_proceso(id_proceso, version, id_empresa=id_empresa)
    if not comp.get("ok"):
        return comp
    try:
        from src.services.workflow import workflow_engine as wf
        res = wf.iniciar_proceso(entidad, entidad_id, contexto={**(contexto or {}),
                                 "_bpd_pasos": comp["pasos"]}, actor=actor, id_empresa=id_empresa)
        return {"ok": True, "workflow": res, "pasos": len(comp["pasos"])}
    except Exception as e:
        # Degradable: si el motor no admite la entidad, se devuelve la compilación (preparada).
        return {"ok": True, "compilado": comp["pasos"], "ejecutado": False, "nota": str(e)}


__all__ = ["compilar", "compilar_proceso", "ejecutar"]
