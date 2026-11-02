"""
Ejecutor de delegación — Configuración: autorrellenar los campos vacíos de un centro recién
creado con los datos corporativos de la empresa (`db.empresa.info_documento`). Reutiliza
`db.centros.actualizar_centro`, el CRUD real — nunca escribe a la tabla directamente. Siempre
seguro de automatizar en modo "automático" sin revisión: SOLO rellena campos que estén VACÍOS,
jamás sobrescribe un dato que la persona que creó el centro ya hubiera introducido a mano.
"""

import logging

logger = logging.getLogger("soma_delegacion.ejecutores.centros")


def contexto_desde_evento(ev: dict) -> dict | None:
    """Traduce el evento `CENTRO_CREADO` (`ref_id` = id del centro) al contexto que espera
    `ejecutar_autorrelleno_centro`."""
    id_centro = ev.get("ref_id")
    return {"id_centro": id_centro} if id_centro else None

# centros_trabajo <- info_documento(): mapeo de los campos que tiene sentido heredar de la
# empresa. Deliberadamente NO incluye "nombre_centro" (debe decidirlo siempre la persona).
_MAPEO = {
    "pais": "pais", "telefono": "telefono", "email": "email", "provincia": "provincia",
    "municipio": "municipio", "cod_pais": "cod_pais", "cod_municipio": "cod_municipio",
    "cod_actividad": "cod_actividad", "actividad_economica": "actividad",
}


def ejecutar_autorrelleno_centro(regla: dict, contexto: dict, *, id_empresa, usuario=None) -> dict:
    """`contexto` esperado: {"id_centro": str}. No llama a la IA (no hay ninguna decisión
    ambigua que tomar: es un autorrelleno determinista de huecos) — las `instrucciones` de la
    regla documentan el criterio para el SUPERADMIN, pero la acción en sí es mecánica y segura."""
    id_centro = contexto.get("id_centro")
    if not id_centro:
        return {"ok": False, "estado": "error", "decision": None, "detalle": "Falta el centro."}

    from src.db import centros as centros_db
    from src.db import empresa as empresa_db

    centro = centros_db.obtener_centro(id_centro)
    if not centro or centro.get("id_empresa") != id_empresa:
        return {"ok": False, "estado": "error", "decision": None,
               "detalle": "El centro no existe o no pertenece a esta empresa."}

    info = empresa_db.info_documento(id_empresa=id_empresa)
    cambios = {}
    for campo_centro, campo_info in _MAPEO.items():
        actual = (centro.get(campo_centro) or "").strip() if isinstance(centro.get(campo_centro), str) \
            else centro.get(campo_centro)
        if actual:
            continue   # ya tiene valor -> nunca se sobrescribe
        valor = (info.get(campo_info) or "").strip()
        if valor:
            cambios[campo_centro] = valor

    if not cambios:
        return {"ok": True, "estado": "descartado", "decision": None,
               "detalle": "El centro ya tenía todos sus datos completos (nada que autorrellenar)."}

    ok = centros_db.actualizar_centro(id_centro, **cambios)
    return {"ok": ok, "estado": "aplicado" if ok else "error", "decision": {"cambios": cambios},
           "detalle": (f"Autorrellenados: {', '.join(cambios)}." if ok
                      else "No se pudo guardar el autorrelleno.")}
