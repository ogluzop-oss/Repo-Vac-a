"""
Ejecutor de delegación — Compras: generar un borrador de pedido a proveedor a partir de una breve
descripción de lo que hace falta. Mismo criterio de grounding que `ejecutores.crm`: SOMA SOLO
puede elegir artículos reales de la empresa (nunca un código inventado). Reutiliza
`db.compras.crear_pedido` (el ÚNICO CRUD de pedidos ya existente): el pedido se crea SIEMPRE en
estado 'BORRADOR', pendiente del flujo de aprobación/envío habitual — nunca se compromete nada
con el proveedor sin revisión.
"""

import logging

from src.services.soma_delegacion.ejecutores.crm import _candidatos_articulos

logger = logging.getLogger("soma_delegacion.ejecutores.compras")


def ejecutar_generar_pedido(regla: dict, contexto: dict, *, id_empresa, usuario=None) -> dict:
    """`contexto` esperado: {"id_proveedor": int, "brief": str}."""
    from src.services.soma_delegacion.motor import MOTIVOS_LEGIBLES, preguntar_soma

    id_proveedor = contexto.get("id_proveedor")
    brief = (contexto.get("brief") or "").strip()
    if not id_proveedor or not brief:
        return {"ok": False, "estado": "error", "decision": None,
               "detalle": "Falta el proveedor o describir qué hace falta pedir."}

    from src.db import proveedores as prov_db
    proveedor = prov_db.obtener_proveedor(id_proveedor, id_empresa=id_empresa)
    if not proveedor:
        return {"ok": False, "estado": "error", "decision": None,
               "detalle": "El proveedor no existe o no pertenece a esta empresa."}
    if proveedor.get("bloqueado"):
        return {"ok": True, "estado": "descartado", "decision": None,
               "detalle": "El proveedor está bloqueado; no se puede generar un pedido."}

    candidatos = _candidatos_articulos(brief, id_empresa)
    if not candidatos:
        return {"ok": True, "estado": "descartado", "decision": None,
               "detalle": "No se encontró ningún artículo de la empresa que coincida — SOMA no "
                         "puede proponer líneas sin artículos reales."}

    catalogo_txt = "\n".join(f"- {c['codigo']}: {c['nombre']} ({c['precio']:.2f} €)"
                             for c in candidatos)
    prompt = (
        "Eres SOMA, el asistente de IA de un ERP, generando un BORRADOR de pedido de compra a un "
        "proveedor. SOLO puedes usar los artículos de la lista de abajo (nunca inventes un código "
        "que no esté en ella) y debes seguir las instrucciones del administrador sobre cómo "
        "construir pedidos (múltiplos de caja, exclusiones, observaciones a añadir…).\n\n"
        f"Instrucciones del administrador:\n\"\"\"\n{regla.get('instrucciones', '')}\n\"\"\"\n\n"
        f"Qué hace falta pedir:\n\"\"\"\n{brief}\n\"\"\"\n\n"
        f"Artículos disponibles (código: nombre (precio de referencia)):\n{catalogo_txt}\n\n"
        "Responde ÚNICAMENTE con un objeto JSON, sin texto adicional: "
        '{"lineas": [{"codigo": "...", "cantidad": numero, "precio_unitario": numero}], '
        '"observaciones": "texto breve para el pedido"}. '
        "Si ningún artículo de la lista encaja con lo que hace falta, "
        'devuelve {"lineas": [], "observaciones": "motivo por el que no se pudo generar"}.'
    )
    r = preguntar_soma(prompt, id_empresa=id_empresa, usuario=usuario, tarea="soma_delegacion_compras")
    if not r.get("ok"):
        return {"ok": False, "estado": "error", "decision": None,
               "detalle": MOTIVOS_LEGIBLES.get(r.get("motivo"), "No se pudo generar el pedido.")}

    datos = r["datos"]
    codigos_validos = {c["codigo"] for c in candidatos}
    precios = {c["codigo"]: c["precio"] for c in candidatos}
    lineas = []
    for ln in (datos.get("lineas") or []):
        codigo = ln.get("codigo")
        if codigo not in codigos_validos:
            continue
        try:
            cantidad = max(1, int(ln.get("cantidad") or 1))
        except (TypeError, ValueError):
            cantidad = 1
        try:
            precio = float(ln.get("precio_unitario"))
        except (TypeError, ValueError):
            precio = precios.get(codigo, 0.0)
        lineas.append({"codigo": codigo, "descripcion": codigo, "cantidad": cantidad,
                       "precio_unitario": precio})

    if not lineas:
        return {"ok": True, "estado": "descartado", "decision": datos,
               "detalle": datos.get("observaciones") or
                         "SOMA no encontró artículos adecuados para este pedido."}

    from src.db import compras as compras_db
    id_usuario = (usuario or {}).get("nombre") or (usuario or {}).get("id")
    pid = compras_db.crear_pedido(
        id_proveedor=id_proveedor, lineas=lineas,
        observaciones=(datos.get("observaciones") or "")[:500],
        usuario=f"SOMA (delegado por {id_usuario})" if id_usuario else "SOMA",
        id_empresa=id_empresa, origen_flujo="soma_delegacion")
    if not pid:
        return {"ok": False, "estado": "error", "decision": datos,
               "detalle": "No se pudo guardar el pedido."}
    return {"ok": True, "estado": "aplicado", "decision": datos,
           "detalle": f"Pedido #{pid} creado en borrador, pendiente de tu revisión."}
